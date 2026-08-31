"""Light frontend interaction checks using TestClient HTML parsing (no browser needed).
Validates buttons, forms, sorting links, basket, calendar rendering."""
import re
from fastapi.testclient import TestClient
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "app"))
# get_client defined in test_app
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from test_app import get_client

def get_html(path="/2026/9", sort=None):
    client, _ = get_client()
    url = f"{path}?sort={sort}" if sort else path
    resp = client.get(url, headers={"X-authentik-email": "admin@thelasallian.com"})
    return resp.text

def test_buttons_exist():
    html = get_html()
    # Add to basket buttons
    assert html.count("Add to basket") >= 5
    # Forms have correct actions
    assert 'action="/2026/9/pick"' in html
    assert 'action="/events/add"' in html
    # Sort badges are links
    assert 'href="/2026/9?sort=prio"' in html
    assert 'href="/2026/9?sort=date"' in html

def test_sort_buttons_change_active_state():
    html_prio = get_html(sort="prio")
    html_date = get_html(sort="date")
    # Active sort should have accent background
    assert 'var(--accent)' in html_prio
    assert 'var(--accent)' in html_date
    # They should differ
    assert html_prio != html_date

def test_calendar_structure():
    html = get_html()
    # Calendar header
    assert "Calendar" in html
    # Weekday headers
    for day in ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"]:
        assert day in html
    # Days 1..30 for September (30 days)
    assert ">30<" in html or ">30</div>" in html or '"30"' in html

def test_basket_empty_state():
    html = get_html()
    assert "Basket" in html
    assert "Basket empty" in html or "0 items" in html

def test_add_custom_form_fields():
    html = get_html()
    assert 'name="title"' in html
    assert 'name="category"' in html
    assert 'name="month"' in html
    assert 'name="day"' in html
    assert "Add your own event" in html
