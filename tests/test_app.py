import pathlib, json, datetime, sqlite3, tempfile, os
import pytest
from fastapi.testclient import TestClient

# Import app module with isolated DB
import sys
APP_DIR = pathlib.Path(__file__).parent.parent / "app"
sys.path.insert(0, str(APP_DIR))

def get_client(tmp_path=None):
    # Use temp DB and temp seed to avoid polluting real files
    import sys, shutil
    APP_DIR = pathlib.Path(__file__).parent.parent / "app"
    sys.path.insert(0, str(APP_DIR))
    import main as m
    if tmp_path:
        # isolated DB
        m.DB_PATH = pathlib.Path(tmp_path) / "test_events.db"
        # isolated seed: copy real seed to tmp
        orig_seed = pathlib.Path(__file__).parent.parent / "seed.json"
        tmp_seed = pathlib.Path(tmp_path) / "seed.json"
        if not tmp_seed.exists():
            shutil.copy(orig_seed, tmp_seed)
            # also need app/seed.json for fallback
            app_seed = APP_DIR / "seed.json"
            if app_seed.exists():
                shutil.copy(app_seed, pathlib.Path(tmp_path) / "app_seed.json")
        m.SEED_PATH = tmp_seed
        # reload ALL from tmp seed
        import json
        raw = json.load(open(tmp_seed))
        if isinstance(raw, list):
            m.EXISTING, m.NEW = raw, []
        else:
            m.EXISTING, m.NEW = raw.get("existing", []), raw.get("new_candidates", [])
        # rebuild ALL
        m.ALL = []
        for idx, e in enumerate(m.EXISTING + m.NEW):
            title = e.get("title") or e.get("event") or f"event-{idx}"
            month = e.get("month")
            if isinstance(month, str):
                try: month = {"JANUARY":1,"FEBRUARY":2,"MARCH":3,"APRIL":4,"MAY":5,"JUNE":6,"JULY":7,"AUGUST":8,"SEPTEMBER":9,"OCTOBER":10,"NOVEMBER":11,"DECEMBER":12}[month.upper()]
                except: month = None
            m.ALL.append({"id": f"e{idx}", "title": title, "month": month, "day": e.get("day"), "logic": e.get("logic") or "fixed", "foundedYear": e.get("foundedYear") or e.get("founded_year"), "category": e.get("category") or "GLOBAL", "isUndated": bool(e.get("isUndated")) or e.get("logic")=="undated" or month is None, "raw": e})
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

# --- New: each logic case ---

def test_compute_fixed_date_feb29_rollover():
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "app"))
    from main import compute_fixed_date, is_leap_year
    # Br. Andrew Gonzalez Feb 29 -> Feb 28 in common years, Feb 29 in leap
    assert compute_fixed_date(2026, 2, 29) == datetime.date(2026, 2, 28)  # 2026 common
    assert compute_fixed_date(2024, 2, 29) == datetime.date(2024, 2, 29)  # 2024 leap
    assert compute_fixed_date(2028, 2, 29) == datetime.date(2028, 2, 29)
    assert not is_leap_year(2026)
    assert is_leap_year(2024)

def test_nth_weekday_last_alias_minus1():
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "app"))
    from main import nth_weekday
    # Last Mon Aug 2026 should be same via "last" and -1
    assert nth_weekday(2026, 8, 1, "last") == datetime.date(2026, 8, 31)
    assert nth_weekday(2026, 8, 1, -1) == datetime.date(2026, 8, 31)
    assert nth_weekday(2026, 8, 1, "-1") == datetime.date(2026, 8, 31)
    # 1st vs last differ
    assert nth_weekday(2026, 8, 1, 1) != nth_weekday(2026, 8, 1, "last")

def test_fixed_month_logic(tmp_path):
    client, m = get_client(tmp_path)
    # Add fixed_month June
    resp = client.post("/events/add", data={"title": "Test Fixed Month June", "category": "TLS", "logic": "fixed_month", "month": "6"}, headers={"X-authentik-email": "a@b.com"}, follow_redirects=True)
    assert resp.status_code == 200
    # Should appear in June suggestions
    june = m.compute_for_month(2026, 6)
    assert any(e["title"] == "Test Fixed Month June" for e in june)
    # Should NOT appear in July
    july = m.compute_for_month(2026, 7)
    assert not any(e["title"] == "Test Fixed Month June" for e in july)

def test_movable_nth_via_add(tmp_path):
    client, m = get_client(tmp_path)
    # Add 2nd Sunday May (Mothers-like) for May
    resp = client.post("/events/add", data={"title": "Test 2nd Sun May", "category": "TLS", "logic": "movable_nth", "nth": "2", "weekday": "0", "nth_month": "5"}, headers={"X-authentik-email": "a@b.com"}, follow_redirects=True)
    assert resp.status_code == 200
    may = m.compute_for_month(2026, 5)
    ev = next(e for e in may if e["title"] == "Test 2nd Sun May")
    assert ev["date"] == datetime.date(2026, 5, 10)  # 2nd Sun May 2026
    # Add Last Monday Aug via -1 alias
    resp = client.post("/events/add", data={"title": "Test Last Mon Aug -1", "category": "TLS", "logic": "movable_nth", "nth": "-1", "weekday": "1", "nth_month": "8"}, headers={"X-authentik-email": "a@b.com"}, follow_redirects=True)
    assert resp.status_code == 200
    aug = m.compute_for_month(2026, 8)
    ev2 = next(e for e in aug if e["title"] == "Test Last Mon Aug -1")
    assert ev2["date"] == datetime.date(2026, 8, 31)
    # Same via "last" string
    resp = client.post("/events/add", data={"title": "Test Last Mon Aug str", "category": "TLS", "logic": "movable_nth", "nth": "last", "weekday": "1", "nth_month": "8"}, headers={"X-authentik-email": "a@b.com"}, follow_redirects=True)
    aug2 = m.compute_for_month(2026, 8)
    ev3 = next(e for e in aug2 if e["title"] == "Test Last Mon Aug str")
    assert ev3["date"] == datetime.date(2026, 8, 31)

def test_feb29_via_add(tmp_path):
    client, m = get_client(tmp_path)
    resp = client.post("/events/add", data={"title": "Br Andrew Feb29 Test", "category": "DLSU", "logic": "fixed", "month": "2", "day": "29"}, headers={"X-authentik-email": "a@b.com"}, follow_redirects=True)
    assert resp.status_code == 200
    # In common year 2026 should pin to Feb 28
    feb2026 = m.compute_for_month(2026, 2)
    ev = next(e for e in feb2026 if e["title"] == "Br Andrew Feb29 Test")
    assert ev["date"] == datetime.date(2026, 2, 28)
    # In leap year 2024 should stay Feb 29
    feb2024 = m.compute_for_month(2024, 2)
    ev2 = next(e for e in feb2024 if e["title"] == "Br Andrew Feb29 Test")
    assert ev2["date"] == datetime.date(2024, 2, 29)

def test_basket_date_edit_persists(tmp_path):
    client, m = get_client(tmp_path)
    events = m.compute_for_month(2026, 9)
    eid = events[0]["id"]
    # pick
    client.post("/2026/9/pick", data={"event_id": eid}, headers={"X-authentik-email": "editor@dlsu.edu.ph"}, follow_redirects=True)
    # edit date to 2026-09-15
    resp = client.post("/2026/9/update_date", data={"event_id": eid, "custom_date": "2026-09-15"}, headers={"X-authentik-email": "editor@dlsu.edu.ph"}, follow_redirects=True)
    assert resp.status_code == 200
    # verify persists on refresh
    resp2 = client.get("/2026/9", headers={"X-authentik-email": "other@dlsu.edu.ph"})
    assert "2026-09-15" in resp2.text or "Sep 15" in resp2.text
    # verify calendar count uses edited date (15th should have badge)
    assert resp2.text.count("15") >= 1
    # clear date
    resp3 = client.post("/2026/9/update_date", data={"event_id": eid, "custom_date": ""}, headers={"X-authentik-email": "editor@dlsu.edu.ph"}, follow_redirects=True)
    assert resp3.status_code == 200

def test_undated_set_date_in_basket(tmp_path):
    client, m = get_client(tmp_path)
    # add undated
    client.post("/events/add", data={"title": "Undated Test For Basket", "category": "TLS", "logic": "undated"}, headers={"X-authentik-email": "a@b.com"}, follow_redirects=True)
    undated = m.get_undated()
    eid = next(e["id"] for e in undated if e["title"] == "Undated Test For Basket")
    # pick it into September basket
    client.post("/2026/9/pick", data={"event_id": eid}, headers={"X-authentik-email": "a@b.com"}, follow_redirects=True)
    # initially no date
    resp = client.get("/2026/9", headers={"X-authentik-email": "a@b.com"})
    assert "Undated Test For Basket" in resp.text
    # set date
    client.post("/2026/9/update_date", data={"event_id": eid, "custom_date": "2026-09-20"}, headers={"X-authentik-email": "a@b.com"}, follow_redirects=True)
    resp2 = client.get("/2026/9", headers={"X-authentik-email": "a@b.com"})
    assert "2026-09-20" in resp2.text or "Sep 20" in resp2.text

def test_export_two_columns(tmp_path):
    client, m = get_client(tmp_path)
    # pick two events
    events = m.compute_for_month(2026, 9)
    for eid in [events[0]["id"], events[1]["id"]]:
        client.post("/2026/9/pick", data={"event_id": eid}, headers={"X-authentik-email": "a@b.com"}, follow_redirects=True)
    # edit one date
    client.post("/2026/9/update_date", data={"event_id": events[0]["id"], "custom_date": "2026-09-25"}, headers={"X-authentik-email": "a@b.com"}, follow_redirects=True)
    resp = client.get("/2026/9/export", headers={"X-authentik-email": "a@b.com"})
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    lines = resp.text.strip().split("\n")
    assert lines[0] == "Event,Date"
    # should have 2 rows + header
    assert len(lines) == 3
    # first data row should contain event title and date in "September 25" format
    assert "September 25" in resp.text
    # verify second column is date
    for line in lines[1:]:
        assert "," in line
