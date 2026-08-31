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

def is_leap_year(year): return (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)

def compute_fixed_date(year, month, day):
    # JS Date(2026,1,29) rolls to Mar 1; DLSU custom for Feb 29 -> Feb 28 in common years (Br. Andrew Gonzalez)
    if month == 2 and day == 29 and not is_leap_year(year):
        return datetime.date(year, 2, 28)
    return datetime.date(year, month, day)

def nth_weekday(year, month, weekday, n):
    # unified: n = 1|2|3|4|"last"|-1  (weekday 0=Sun)
    import calendar
    if n == "last" or n == -1 or n == "-1":
        last_day = calendar.monthrange(year, month)[1]
        d = datetime.date(year, month, last_day)
        while d.weekday() != (weekday -1) % 7:  # convert Sun0 to Mon0
            d -= datetime.timedelta(days=1)
        return d
    # nth
    first = datetime.date(year, month, 1)
    target = (weekday -1) % 7
    offset = (target - first.weekday()) % 7
    day = 1 + offset + (int(n)-1)*7
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
                date_obj = compute_fixed_date(year, ev["month"], ev["day"])
            elif ev["logic"] == "movable_nth":
                rule = ev["raw"].get("rule")
                # generic rule support: {n, weekday, month} — unified last/-1
                if rule and "n" in rule and "weekday" in rule:
                    try:
                        n = rule["n"]
                        # allow -1 alias
                        if n == -1: n = "last"
                        date_obj = nth_weekday(year, rule.get("month", ev["month"]), int(rule["weekday"]), n)
                    except:
                        date_obj = None
                elif ev["title"] == "Grandparents Day":
                    date_obj = nth_weekday(year, 9, 0, 2)
                elif ev["title"] == "World Habitat Day":
                    date_obj = nth_weekday(year, 10, 1, 1)
                elif ev["title"] == "National Heroes' Day":
                    date_obj = nth_weekday(year, 8, 1, "last")
                elif "Mothers" in ev["title"]:
                    date_obj = nth_weekday(year, 5, 0, 2)
                elif "Fathers" in ev["title"]:
                    date_obj = nth_weekday(year, 6, 0, 3)
                else:
                    date_obj = compute_fixed_date(year, ev["month"], ev["day"] or 1)
            elif ev["logic"] == "fixed_month":
                # whole month: show as 1st for sorting, display as month only
                date_obj = datetime.date(year, ev["month"], 1)
            elif ev["logic"] in ("movable_liturgical", "movable"):
                # use easter for demo
                date_obj = compute_fixed_date(year, ev["month"], ev["day"] or 1)
            else:
                if ev["day"]:
                    date_obj = compute_fixed_date(year, ev["month"], ev["day"])
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
        id TEXT PRIMARY KEY, issue_id TEXT, event_id TEXT, status TEXT, added_by TEXT, created_at TEXT, custom_date TEXT,
        UNIQUE(issue_id, event_id))""")
    # migration for existing DB without custom_date
    try:
        con.execute("SELECT custom_date FROM monthly_picks LIMIT 1")
    except sqlite3.OperationalError:
        try: con.execute("ALTER TABLE monthly_picks ADD COLUMN custom_date TEXT")
        except: pass
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
    # map event id -> date for picked items (respects custom_date override per basket)
    ev_by_id = {e["id"]: e for e in ALL}
    date_counts = {}
    basket_by_day = {}
    # precompute effective dates for picks
    pick_effective = {}  # pick_id -> date or None
    for p in picks:
        cd = p["custom_date"] if "custom_date" in p.keys() and p["custom_date"] else None
        eff_date = None
        ev = ev_by_id.get(p["event_id"])
        if cd:
            try:
                dt = datetime.date.fromisoformat(cd)
                if dt.year == year and dt.month == month:
                    eff_date = dt
            except: pass
        else:
            # no override: use computed date if dated, else None (undated stays undated until edited)
            if ev and not ev["isUndated"]:
                for e in events:
                    if e["id"] == p["event_id"] and e["date"]:
                        eff_date = e["date"]
                        break
            else:
                eff_date = None
        pick_effective[p["id"]] = eff_date
        if eff_date:
            d = eff_date.day
            date_counts[d] = date_counts.get(d, 0) + 1
            # for basket_by_day, use event title
            display_ev = ev if ev else {"title": p["event_id"]}
            basket_by_day.setdefault(d, []).append(display_ev)
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
        "pick_effective": pick_effective,
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

@app.post("/{year}/{month}/update_date")
def update_pick_date(request: Request, year: int, month: int, event_id: str = Form(...), custom_date: str = Form("")):
    # custom_date: YYYY-MM-DD or empty to clear (revert to computed)
    issue, _ = get_issue(year, month)
    con = sqlite3.connect(DB_PATH)
    # validate date if provided
    cd = None
    if custom_date and custom_date.strip():
        try:
            # normalize to YYYY-MM-DD
            dt = datetime.date.fromisoformat(custom_date.strip())
            cd = dt.isoformat()
        except:
            con.close()
            raise HTTPException(status_code=400, detail="Invalid date format, use YYYY-MM-DD")
    con.execute("UPDATE monthly_picks SET custom_date=? WHERE issue_id=? AND event_id=?", (cd, issue["id"], event_id))
    con.execute("UPDATE monthly_issues SET version=version+1 WHERE id=?", (issue["id"],))
    con.commit()
    con.close()
    return RedirectResponse(url=f"/{year}/{month}", status_code=303)

@app.get("/{year}/{month}/export")
def export_basket(request: Request, year: int, month: int):
    # 2 columns: Event, Date (for the year) — uses custom_date if set, else computed
    from fastapi.responses import PlainTextResponse
    issue, picks = get_issue(year, month)
    # build event map
    ev_by_id = {e["id"]: e for e in ALL}
    # compute dates for this year/month for fallback
    events_by_id = {e["id"]: e for e in compute_for_month(year, month)}
    rows = []
    for p in picks:
        ev = ev_by_id.get(p["event_id"])
        title = ev["title"] if ev else p["event_id"]
        # custom_date overrides
        cd = p["custom_date"] if "custom_date" in p.keys() and p["custom_date"] else None
        if cd:
            date_str = cd
        else:
            # use computed date if available
            comp = events_by_id.get(p["event_id"])
            if comp and comp["date"]:
                date_str = comp["date"].isoformat()
            elif ev and ev.get("day") and ev.get("month"):
                # fallback to fixed
                try: date_str = compute_fixed_date(year, ev["month"], ev["day"]).isoformat()
                except: date_str = ""
            else:
                date_str = ""
        rows.append((title, date_str))
    # sort by date
    rows.sort(key=lambda x: (x[1] or "9999-12-31", x[0]))
    # CSV
    lines = ["Event,Date"]
    for title, d in rows:
        # escape commas/quotes
        t = '"' + title.replace('"', '""') + '"' if ("," in title or '"' in title) else title
        lines.append(f"{t},{d}")
    csv = "\n".join(lines)
    return PlainTextResponse(csv, media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="basket-{year}-{month:02d}.csv"'})

@app.post("/events/add")
def add_undated(
    request: Request,
    title: str = Form(...),
    category: str = Form("TLS"),
    logic: str = Form("fixed"),
    month: str = Form(""),
    day: str = Form(""),
    nth: str = Form(""),
    weekday: str = Form(""),
    nth_month: str = Form(""),
):
    global ALL
    import uuid, json as _json
    # Normalize logic
    logic = (logic or "fixed").strip()
    m, d, is_undated = None, None, False
    rule, rule_json = None, None
    # Fixed date: month+day
    if logic == "fixed":
        try:
            m = int(month) if month.strip() else None
            d = int(day) if day.strip() else None
            if m is None or d is None:
                raise ValueError
            is_undated = False
        except:
            is_undated, logic, m, d = True, "undated", None, None
    elif logic == "fixed_month":
        try:
            m = int(month) if month.strip() else None
            if m is None: raise ValueError
            d, is_undated = None, False
        except:
            is_undated, logic, m = True, "undated", None
    elif logic == "movable_nth":
        # unified: n = 1|2|3|4|last|-1
        try:
            n_raw = (nth or "").strip().lower()
            n = -1 if n_raw in ("-1", "last") else int(n_raw)
            if n not in (1,2,3,4,-1,"last"):
                if str(n) == "-1": n = -1
                else: raise ValueError
            wd = int(weekday) if weekday.strip() else 0
            m = int(nth_month) if nth_month.strip() else int(month) if month.strip() else None
            if m is None: raise ValueError
            # normalize -1 to "last" canonical
            n = "last" if n == -1 else n
            rule = {"n": n, "weekday": wd, "month": m}
            rule_json = _json.dumps(rule)
            is_undated = False
            logic = "movable_nth"
            d = None  # computed via nthWeekday
        except Exception as e:
            print("movable_nth parse failed", e)
            is_undated, logic, m, d, rule_json = True, "undated", None, None, None
    elif logic in ("undated", "tba", "tba_academic", "tba_government"):
        is_undated, m, d = True, None, None
        logic = "undated"
    else:
        is_undated, logic = True, "undated"
        m, d = None, None

    # For movable_nth, persist rule
    new_ev = {"title": title, "month": m, "day": d, "logic": logic, "isUndated": is_undated, "category": category, "foundedYear": None, "rule": rule}
    try:
        with open(SEED_PATH) as f:
            data = json.load(f)
        payload = {"id": len(data)+1 if isinstance(data, list) else 0, "title": title, "event": title, "month": m, "day": d, "logic": logic, "isUndated": is_undated, "category": category, "rule": rule}
        if rule_json:
            payload["rule"] = rule
        if isinstance(data, list):
            # map month back to string for consistency? keep int
            if isinstance(m, int):
                # keep int month for new list format
                payload["month"] = ["JANUARY","FEBRUARY","MARCH","APRIL","MAY","JUNE","JULY","AUGUST","SEPTEMBER","OCTOBER","NOVEMBER","DECEMBER"][m-1] if 1 <= m <= 12 else m
            data.append(payload)
        else:
            data["existing"].append(payload)
            data["existing_139_count"] = len(data["existing"])
            data["total"] = len(data["existing"]) + len(data.get("new_candidates", []))
        with open(SEED_PATH, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print("persist failed", e)
    ALL.append({"id": f"e{len(ALL)}", "slug": title.lower().replace(" ", "-"), "title": title, "month": m if logic!="movable_nth" else (rule["month"] if rule else m), "day": d, "logic": logic, "foundedYear": None, "category": category, "isUndated": is_undated, "raw": new_ev if not rule else {**new_ev, "rule": rule}})
    # redirect to appropriate month if dated, else next month
    if m:
        # find year for redirect: use next occurrence or current view? use current year
        import datetime as _dt
        y = _dt.datetime.now().year
        return RedirectResponse(url=f"/{y}/{m}", status_code=303)
    return RedirectResponse(url="/", status_code=303)  # goes to next month via /


