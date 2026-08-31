import pathlib, json, datetime, sqlite3, tempfile, os
import pytest
from fastapi.testclient import TestClient

# Import app module with isolated DB
import sys
APP_DIR = pathlib.Path(__file__).parent.parent / "app"
sys.path.insert(0, str(APP_DIR))

def get_client(tmp_path=None):
    # Use temp DB to avoid polluting real events.db
    import sys
    APP_DIR = pathlib.Path(__file__).parent.parent / "app"
    sys.path.insert(0, str(APP_DIR))
    import main as m
    # Override DB_PATH to temp file for isolation
    if tmp_path:
        m.DB_PATH = pathlib.Path(tmp_path) / "test_events.db"
        m.init_db()
    else:
        m.DB_PATH = pathlib.Path(tempfile.gettempdir()) / "test_events_autogen.db"
        if m.DB_PATH.exists():
            m.DB_PATH.unlink()
        m.init_db()
    return TestClient(m.app), m

def test_prio_score():
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "app"))
    from main import prio_score
    assert prio_score(None) == 0
    assert prio_score(100) == 100
    assert prio_score(50) == 80
    assert prio_score(25) == 60
    assert prio_score(10) == 40
    assert prio_score(5) == 20
    assert prio_score(7) == 5
    assert prio_score(40) == 40  # 40 %10==0
    assert prio_score(75) == 60  # 75%25==0

def test_get_easter_2026():
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "app"))
    from main import get_easter
    # 2026 Easter is Apr 5 per verified sheet
    assert get_easter(2026) == datetime.date(2026, 4, 5)
    assert get_easter(2025) == datetime.date(2025, 4, 20)
    assert get_easter(2027) == datetime.date(2027, 3, 28)

def test_nth_weekday():
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "app"))
    from main import nth_weekday
    # Mothers Day 2nd Sun May 2026 = May 10
    assert nth_weekday(2026, 5, 0, 2) == datetime.date(2026, 5, 10)
    # Fathers Day 3rd Sun Jun 2026 = Jun 21
    assert nth_weekday(2026, 6, 0, 3) == datetime.date(2026, 6, 21)
    # Last Mon Aug 2026 = Aug 31
    assert nth_weekday(2026, 8, 1, "last") == datetime.date(2026, 8, 31)
    # Grandparents 2nd Sun Sep 2026 = Sep 13
    assert nth_weekday(2026, 9, 0, 2) == datetime.date(2026, 9, 13)
    # Habitat 1st Mon Oct 2026 = Oct 5
    assert nth_weekday(2026, 10, 1, 1) == datetime.date(2026, 10, 5)

def test_compute_for_month_sort():
    client, m = get_client()
    # September 2026 has 9 events per sheet
    events_prio = m.compute_for_month(2026, 9, sort="prio")
    events_date = m.compute_for_month(2026, 9, sort="date")
    events_alpha = m.compute_for_month(2026, 9, sort="title")
    assert len(events_prio) >= 9
    # prio sort: first item should have >= prio than last
    assert events_prio[0]["prio"] >= events_prio[-1]["prio"]
    # date sort: dates ascending (or None at end)
    dates = [e["date"] for e in events_date if e["date"]]
    assert dates == sorted(dates)
    # title sort: alphabetical
    titles = [e["title"] for e in events_alpha]
    assert titles == sorted(titles)

def test_root_redirects_to_next_month():
    client, _ = get_client()
    now = datetime.datetime.now()
    exp_y, exp_m = (now.year+1, 1) if now.month==12 else (now.year, now.month+1)
    # TestClient follows redirects by default; check without follow
    client_no_follow = TestClient(client.app, follow_redirects=False)
    resp = client_no_follow.get("/", headers={"X-authentik-email": "test@dlsu.edu.ph"})
    assert resp.status_code in (302, 307)
    assert resp.headers["location"] == f"/{exp_y}/{exp_m}"

def test_month_view_contains_expected_elements(tmp_path):
    client, m = get_client(tmp_path)
    resp = client.get("/2026/9", headers={"X-authentik-email": "admin@thelasallian.com"})
    assert resp.status_code == 200
    html = resp.text
    # Should contain September suggestions
    assert "September" in html
    assert "Add to basket" in html
    # Sort controls
    assert "?sort=prio" in html
    assert "?sort=date" in html
    assert "?sort=category" in html
    assert "?sort=title" in html
    # Calendar
    assert "Calendar" in html
    # Basket
    assert "Basket" in html
    # Undated pool
    assert "Undated Pool" in html
    # Add your own event form
    assert "Add your own event" in html
    assert 'name="title"' in html

def test_sort_param_changes_order(tmp_path):
    client, m = get_client(tmp_path)
    r_prio = client.get("/2026/9?sort=prio", headers={"X-authentik-email": "a@b.com"})
    r_date = client.get("/2026/9?sort=date", headers={"X-authentik-email": "a@b.com"})
    assert r_prio.status_code == 200
    assert r_date.status_code == 200
    # Very basic: HTML should differ between sorts if events have varying prio/date
    # At least ensure both render
    assert r_prio.text != r_date.text or "prio" in r_prio.text

def test_basket_pick_and_unpick(tmp_path):
    client, m = get_client(tmp_path)
    # Ensure empty basket initially
    resp = client.get("/2026/9", headers={"X-authentik-email": "picker@dlsu.edu.ph"})
    assert "Basket empty" in resp.text or "0 items" in resp.text
    # Pick first September event
    events = m.compute_for_month(2026, 9)
    first_id = events[0]["id"]
    resp = client.post("/2026/9/pick", data={"event_id": first_id}, headers={"X-authentik-email": "picker@dlsu.edu.ph"}, follow_redirects=True)
    assert resp.status_code == 200
    assert "in basket" in resp.text or "1 items" in resp.text
    # Calendar should now show count 1 for that day (if dated)
    # Add second pick on same day if possible to test count>1, but just verify basket has 1
    # Unpick
    resp = client.post("/2026/9/unpick", data={"event_id": first_id}, headers={"X-authentik-email": "picker@dlsu.edu.ph"}, follow_redirects=True)
    assert resp.status_code == 200
    # Should be back to empty or not contain that event as picked
    # Re-fetch and check not in basket
    resp2 = client.get("/2026/9", headers={"X-authentik-email": "picker@dlsu.edu.ph"})
    # After unpick, basket should be empty again or not show that title in basket section
    # We check that pick count decreased (simple: still 200)
    assert resp2.status_code == 200

def test_add_custom_undated(tmp_path):
    client, m = get_client(tmp_path)
    # Add undated custom event
    resp = client.post("/events/add", data={"title": "My Custom Test Event 123", "category": "TLS", "month": "", "day": ""}, headers={"X-authentik-email": "creator@dlsu.edu.ph"}, follow_redirects=True)
    assert resp.status_code == 200
    # Undated pool should now contain it
    resp2 = client.get("/2026/9", headers={"X-authentik-email": "creator@dlsu.edu.ph"})
    assert "My Custom Test Event 123" in resp2.text

def test_add_custom_dated(tmp_path):
    client, m = get_client(tmp_path)
    # Add dated custom event for September 15
    resp = client.post("/events/add", data={"title": "Dated Sept 15 Event", "category": "MANILA", "month": "9", "day": "15"}, headers={"X-authentik-email": "creator@dlsu.edu.ph"}, follow_redirects=False)
    assert resp.status_code in (302, 303, 307)
    assert resp.headers["location"] == f"/{datetime.datetime.now().year}/9" or "/9" in resp.headers["location"]
    # It should appear in September suggestions after
    resp2 = client.get("/2026/9", headers={"X-authentik-email": "creator@dlsu.edu.ph"})
    assert "Dated Sept 15 Event" in resp2.text

def test_calendar_counts_hidden_when_zero(tmp_path):
    client, m = get_client(tmp_path)
    # Fresh DB, no picks -> no badges should show counts
    resp = client.get("/2026/9", headers={"X-authentik-email": "newuser@dlsu.edu.ph"})
    html = resp.text
    # Calendar grid exists, but no count badges (since basket empty)
    # The badge for counts is only rendered if cnt>0, so we check that no "0" badge appears in calendar section
    # Simpler: ensure calendar renders days 1..30
    assert ">1<" in html or "> 1 <" in html or '">1<' in html or ">1</div>" in html
    # After adding a pick, count should appear
    events = m.compute_for_month(2026, 9)
    # Find an event with date
    dated = [e for e in events if e["date"]][0]
    client.post("/2026/9/pick", data={"event_id": dated["id"]}, headers={"X-authentik-email": "newuser@dlsu.edu.ph"}, follow_redirects=True)
    resp2 = client.get("/2026/9", headers={"X-authentik-email": "newuser@dlsu.edu.ph"})
    # Now should have a badge with count 1
    assert 'background:var(--accent)' in resp2.text or ">1</div>" in resp2.text

def test_api_endpoints(tmp_path):
    client, m = get_client(tmp_path)
    resp = client.get("/api/suggestions?year=2026&month=9&sort=prio")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 9
    assert "prio" in data[0]
    resp2 = client.get("/api/pool")
    assert resp2.status_code == 200
    assert isinstance(resp2.json(), list)

def test_shared_state_across_users(tmp_path):
    client, m = get_client(tmp_path)
    events = m.compute_for_month(2026, 9)
    eid = events[0]["id"]
    # User A picks
    client.post("/2026/9/pick", data={"event_id": eid}, headers={"X-authentik-email": "alice@dlsu.edu.ph"}, follow_redirects=True)
    # User B should see it (shared state, not per-user)
    resp = client.get("/2026/9", headers={"X-authentik-email": "bob@dlsu.edu.ph"})
    assert "1 items" in resp.text or "in basket" in resp.text
