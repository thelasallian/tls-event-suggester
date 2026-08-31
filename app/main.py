"""TLS Event Suggester — copy of webdesk forward-auth pattern.
Auth via Authentik nginx auth_request: X-authentik-* headers.
Uses SQLite (events.db) for MonthlyIssue picks. Seed from seed.json.
"""
import json, pathlib, datetime, sqlite3, os
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

BASE = pathlib.Path(__file__).parent
# seed may be at app/seed.json (VPS) or ../seed.json (repo root) — try both
SEED_PATH = BASE / "seed.json"
if not SEED_PATH.exists():
    alt = BASE.parent / "seed.json"
    if alt.exists():
        SEED_PATH = alt
DB_PATH = BASE / "events.db"

app = FastAPI()
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE / "templates"))

def prio_score(anniv):
    if anniv is None: return 0
    if anniv % 100 == 0: return 100
    if anniv % 50 == 0: return 80
    if anniv % 25 == 0: return 60
    if anniv % 10 == 0: return 40
    if anniv % 5 == 0: return 20
    return 5

def get_easter(year):
    a=year%19; b=year//100; c=year%100; d=b//4; e=b%4; f=(b+8)//25; g=(b-f+1)//3
    h=(19*a+b-d-g+15)%30; i=c//4; k=c%4; l=(32+2*e+2*i-h-k)%7; m=(a+11*h+22*l)//451
    month=(h+l-7*m+114)//31; day=((h+l-7*m+114)%31)+1
    return datetime.date(year, month, day)

def nth_weekday(year, month, weekday, n):
    # weekday 0=Mon ... 6=Sun, python monday=0
    # we use 0=Sun for consistency, convert
    # input weekday: 0=Sun
    import calendar
    if n == "last":
        last_day = calendar.monthrange(year, month)[1]
        d = datetime.date(year, month, last_day)
        while d.weekday() != (weekday -1) % 7:  # convert Sun0 to Mon0
            d -= datetime.timedelta(days=1)
        return d
    # nth
    first = datetime.date(year, month, 1)
    # python weekday Mon0
    target = (weekday -1) % 7
    offset = (target - first.weekday()) % 7
    day = 1 + offset + (n-1)*7
    return datetime.date(year, month, day)

# Load seed — handles both old dict format {existing, new_candidates} and new list format [events]
with open(SEED_PATH) as f:
    raw = json.load(f)
if isinstance(raw, list):
    EXISTING = raw
    NEW = []
else:
    EXISTING = raw.get("existing", [])
    NEW = raw.get("new_candidates", [])

# Normalize: combine and add ids
ALL = []
for idx, e in enumerate(EXISTING + NEW):
    title = e.get("title") or e.get("event") or f"event-{idx}"
    slug = title.lower().replace(" ", "-").replace("'", "").replace("/", "-")[:50]
    month = e.get("month")
    # handle SEPTEMBER etc
    if isinstance(month, str):
        try:
            month = {"JANUARY":1,"FEBRUARY":2,"MARCH":3,"APRIL":4,"MAY":5,"JUNE":6,"JULY":7,"AUGUST":8,"SEPTEMBER":9,"OCTOBER":10,"NOVEMBER":11,"DECEMBER":12}[month.upper()]
        except: month = None
    ALL.append({
        "id": f"e{idx}",
        "slug": slug,
        "title": title,
        "month": month,
        "day": e.get("day"),
        "logic": e.get("logic") or "fixed",
        "foundedYear": e.get("foundedYear") or e.get("founded_year"),
        "category": e.get("category") or "GLOBAL",
        "isUndated": bool(e.get("isUndated")) or e.get("logic")=="undated" or month is None,
        "raw": e,
    })

def compute_for_month(year, month, sort="prio"):
    easter = get_easter(year)
    result = []
    for ev in ALL:
        if ev["isUndated"]:
            continue
        if ev["month"] != month:
            continue
        anniv = (year - ev["foundedYear"]) if ev["foundedYear"] else None
        prio = prio_score(anniv)
        # compute date for display
        date_obj = None
        try:
            if ev["logic"] == "fixed" and ev["month"] and ev["day"]:
                date_obj = datetime.date(year, ev["month"], ev["day"])
            elif ev["logic"] == "movable_nth":
                # parse rule if exists else fallback
                rule = ev["raw"].get("rule")
                # simple heuristics for known events
                if ev["title"] == "Grandparents Day":
                    date_obj = nth_weekday(year, 9, 0, 2)  # 2nd Sun Sep
                elif ev["title"] == "World Habitat Day":
                    date_obj = nth_weekday(year, 10, 1, 1)  # 1st Mon Oct
                elif ev["title"] == "National Heroes' Day":
                    date_obj = nth_weekday(year, 8, 1, "last")
                elif "Mothers" in ev["title"]:
                    date_obj = nth_weekday(year, 5, 0, 2)
                elif "Fathers" in ev["title"]:
                    date_obj = nth_weekday(year, 6, 0, 3)
                else:
                    date_obj = datetime.date(year, ev["month"], ev["day"] or 1)
            elif ev["logic"] in ("movable_liturgical", "movable"):
                # use easter for demo
                date_obj = datetime.date(year, ev["month"], ev["day"] or 1)
            else:
                if ev["day"]:
                    date_obj = datetime.date(year, ev["month"], ev["day"])
        except: date_obj = None
        result.append({**ev, "anniv": anniv, "prio": prio, "date": date_obj})
    if sort == "date":
        result.sort(key=lambda x: (x["date"] or datetime.date(year, month, 28), x["title"]))
    elif sort == "category":
        result.sort(key=lambda x: (x["category"], -x["prio"], x["title"]))
    elif sort == "title":
        result.sort(key=lambda x: x["title"])
    else:  # prio
        result.sort(key=lambda x: (-x["prio"], -(x["anniv"] or 0), x["title"]))
    return result

def get_undated():
    return [ev for ev in ALL if ev["isUndated"]]

def init_db():
    con = sqlite3.connect(DB_PATH)
    con.execute("""CREATE TABLE IF NOT EXISTS monthly_issues (
        id TEXT PRIMARY KEY, year INT, month INT, status TEXT, version INT, created_at TEXT, UNIQUE(year, month))""")
    con.execute("""CREATE TABLE IF NOT EXISTS monthly_picks (
        id TEXT PRIMARY KEY, issue_id TEXT, event_id TEXT, status TEXT, added_by TEXT, created_at TEXT,
        UNIQUE(issue_id, event_id))""")
    con.commit()
    con.close()
init_db()

def get_issue(year, month):
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    row = con.execute("SELECT * FROM monthly_issues WHERE year=? AND month=?", (year, month)).fetchone()
    if not row:
        import uuid
        iid = str(uuid.uuid4())
        con.execute("INSERT INTO monthly_issues (id, year, month, status, version, created_at) VALUES (?,?,?,?,?,?)",
                    (iid, year, month, "draft", 1, datetime.datetime.now().isoformat()))
        con.commit()
        row = con.execute("SELECT * FROM monthly_issues WHERE id=?", (iid,)).fetchone()
    picks = con.execute("SELECT * FROM monthly_picks WHERE issue_id=?", (row["id"],)).fetchall()
    con.close()
    return row, picks

@app.get("/healthz")
def healthz():
    return {"ok": True}

@app.get("/api/suggestions")
def api_suggestions(year: int, month: int, sort: str = "prio"):
    events = compute_for_month(year, month, sort=sort)
    out = []
    for e in events:
        out.append({"id": e["id"], "title": e["title"], "month": e["month"], "day": e["day"], "date": e["date"].isoformat() if e["date"] else None, "anniv": e["anniv"], "prio": e["prio"], "category": e["category"]})
    return JSONResponse(out)

@app.get("/api/pool")
def api_pool():
    und = get_undated()
    return JSONResponse([{"id": e["id"], "title": e["title"], "category": e["category"]} for e in und])

@app.get("/", response_class=RedirectResponse)
def root(request: Request):
    now = datetime.datetime.now()
    # default to next month (editor is planning ahead)
    y, m = now.year, now.month
    if m == 12:
        y, m = y + 1, 1
    else:
        m += 1
    return RedirectResponse(url=f"/{y}/{m}")

@app.get("/{year}/{month}", response_class=HTMLResponse)
def month_view(request: Request, year: int, month: int):
    email = request.headers.get("x-authentik-email", "anonymous")
    name = request.headers.get("x-authentik-username", email)
    sort = request.query_params.get("sort", "prio")
    events = compute_for_month(year, month, sort=sort)
    undated = get_undated()
    issue, picks = get_issue(year, month)
    picked_ids = {p["event_id"] for p in picks}
    month_name = datetime.date(year, month, 1).strftime("%B")
    # calendar data for right side: counts per day for basket
    import calendar as cal
    days_in_month = cal.monthrange(year, month)[1]
    # map event id -> date for picked items
    ev_by_id = {e["id"]: e for e in ALL}
    date_counts = {}
    basket_by_day = {}
    for p in picks:
        ev = ev_by_id.get(p["event_id"])
        if not ev or ev["isUndated"]:
            continue
        # use computed date for this year/month
        for e in events:
            if e["id"] == p["event_id"] and e["date"]:
                d = e["date"].day
                date_counts[d] = date_counts.get(d, 0) + 1
                basket_by_day.setdefault(d, []).append(e)
                break
    # calendar weeks for rendering
    first_weekday = datetime.date(year, month, 1).weekday()  # Mon=0
    # Convert to Sun=0 grid
    first_weekday_sun = (first_weekday + 1) % 7
    cal_weeks = []
    day = 1
    for wk in range(6):
        week = []
        for wd in range(7):
            if wk == 0 and wd < first_weekday_sun:
                week.append(None)
            elif day > days_in_month:
                week.append(None)
            else:
                week.append(day)
                day += 1
        cal_weeks.append(week)
        if day > days_in_month:
            break
    return templates.TemplateResponse(request, "month.html", {
        "year": year, "month": month, "month_name": month_name,
        "events": events, "undated": undated, "issue": dict(issue), "picks": picks,
        "picked_ids": picked_ids, "email": email, "name": name,
        "all_events": ALL,
        "days_in_month": days_in_month, "date_counts": date_counts,
        "basket_by_day": basket_by_day, "cal_weeks": cal_weeks,
    })

@app.post("/{year}/{month}/pick")
def pick_event(request: Request, year: int, month: int, event_id: str = Form(...)):
    email = request.headers.get("x-authentik-email", "anonymous")
    issue, _ = get_issue(year, month)
    con = sqlite3.connect(DB_PATH)
    # check exists
    cur = con.execute("SELECT * FROM monthly_picks WHERE issue_id=? AND event_id=?", (issue["id"], event_id)).fetchone()
    if cur:
        con.close()
        return RedirectResponse(url=f"/{year}/{month}", status_code=303)
    import uuid
    pid = str(uuid.uuid4())
    con.execute("INSERT INTO monthly_picks (id, issue_id, event_id, status, added_by, created_at) VALUES (?,?,?,?,?,?)",
                (pid, issue["id"], event_id, "picked", email, datetime.datetime.now().isoformat()))
    con.execute("UPDATE monthly_issues SET version=version+1 WHERE id=?", (issue["id"],))
    con.commit()
    con.close()
    return RedirectResponse(url=f"/{year}/{month}", status_code=303)

@app.post("/{year}/{month}/unpick")
def unpick_event(request: Request, year: int, month: int, event_id: str = Form(...)):
    issue, _ = get_issue(year, month)
    con = sqlite3.connect(DB_PATH)
    con.execute("DELETE FROM monthly_picks WHERE issue_id=? AND event_id=?", (issue["id"], event_id))
    con.execute("UPDATE monthly_issues SET version=version+1 WHERE id=?", (issue["id"],))
    con.commit()
    con.close()
    return RedirectResponse(url=f"/{year}/{month}", status_code=303)

@app.post("/events/add")
def add_undated(request: Request, title: str = Form(...), category: str = Form("TLS"), month: str = Form(""), day: str = Form("")):
    global ALL
    import uuid
    # month/day optional — if provided, creates dated event, otherwise undated pool
    m = None
    d = None
    is_undated = True
    logic = "undated"
    if month and month.strip() and month != "0":
        try:
            m = int(month)
            d = int(day) if day and day.strip() else 1
            is_undated = False
            logic = "fixed"
        except:
            m, d = None, None
            is_undated = True
            logic = "undated"
    new_ev = {"title": title, "month": m, "day": d, "logic": logic, "isUndated": is_undated, "category": category, "foundedYear": None}
    try:
        with open(SEED_PATH) as f:
            data = json.load(f)
        if isinstance(data, list):
            data.append({"id": len(data)+1, "title": title, "event": title, "month": m, "day": d, "logic": logic, "isUndated": is_undated, "category": category})
        else:
            data["existing"].append({"title": title, "event": title, "month": m, "day": d, "logic": logic, "isUndated": is_undated, "category": category})
            data["existing_139_count"] = len(data["existing"])
            data["total"] = len(data["existing"]) + len(data.get("new_candidates", []))
        with open(SEED_PATH, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print("persist failed", e)
    ALL.append({"id": f"e{len(ALL)}", "slug": title.lower().replace(" ", "-"), "title": title, "month": m, "day": d, "logic": logic, "foundedYear": None, "category": category, "isUndated": is_undated, "raw": new_ev})
    # redirect to appropriate month if dated, else next month
    if m:
        # find year for redirect: use next occurrence or current view? use current year
        import datetime as _dt
        y = _dt.datetime.now().year
        return RedirectResponse(url=f"/{y}/{m}", status_code=303)
    return RedirectResponse(url="/", status_code=303)  # goes to next month via /


