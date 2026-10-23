#!/usr/bin/env python3
"""MaxOS CLI (Grok Bot rebuild). Deterministic: all math is in code. Run `maxos.py -h`."""
import argparse, datetime as dt, json, os, re, sqlite3, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from maxos_lib import canon_lift, note_affects, parse_sets, epley, next_target, load_step

DB = os.environ.get("MAXOS_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "maxos.db"))
DAYN = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
ROLE_ITEMS = ["faith", "trading", "spouse", "father"]  # example roles - edit to taste
AUTO_ITEMS = ["eat", "move", "fast"]
ITEM_ALIASES = {"trade": "trading", "faith": "faith", "bible": "faith", "spouse": "spouse", "wife": "spouse", "husband": "spouse", "father": "father", "dad": "father", "kids": "father", "trading": "trading",
                "eat": "eat", "move": "move", "fast": "fast"}
KIDS = [k.strip().lower() for k in os.environ.get("MAXOS_KIDS", "kid1,kid2").split(",") if k.strip()]
GYM_DOW = {int(x) for x in os.environ.get("MAXOS_GYM_DOW", "1,3,5").split(",") if x.strip()}  # 0=Sun..6=Sat; match your program table

def db():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row; c.execute("PRAGMA foreign_keys=ON"); return c
def D(s): return dt.date.fromisoformat(s)
def dow(d): return (d.weekday() + 1) % 7          # 0=Sun..6=Sat
def week_start(d): return d - dt.timedelta(days=dow(d))
def today(a): return D(a.date) if getattr(a, "date", None) else dt.date.today()
def now_hm(): return dt.datetime.now().strftime("%H:%M")

# ---------- weight ----------
def weight_series(c, upto=None):
    q = "SELECT date, lbs FROM weight" + (" WHERE date<=?" if upto else "") + " ORDER BY date, id"
    rows = c.execute(q, (upto.isoformat(),) if upto else ()).fetchall()
    by = {}
    for r in rows: by[r["date"]] = r["lbs"]          # last reading of a day wins
    return sorted(by.items())

def avg7(series, d):
    vals = [v for k, v in series if d - dt.timedelta(days=6) <= D(k) <= d]
    return round(sum(vals) / len(vals), 2) if vals else None

def slope_per_week(series, d, days=28):
    pts = [((D(k) - d).days, v) for k, v in series if d - dt.timedelta(days=days) < D(k) <= d]
    if len(pts) < 3: return None
    n = len(pts); mx = sum(x for x, _ in pts) / n; my = sum(y for _, y in pts) / n
    den = sum((x - mx) ** 2 for x, _ in pts)
    return round(7 * sum((x - mx) * (y - my) for x, y in pts) / den, 2) if den else None

def cmd_weight(a):
    c = db(); d = today(a)
    if not 80 <= a.lbs <= 400: sys.exit("refused: %s is not a plausible weight" % a.lbs)
    c.execute("INSERT INTO weight(date,lbs,note) VALUES(?,?,?)", (d.isoformat(), a.lbs, a.note)); c.commit()
    s = weight_series(c, d); t = avg7(s, d); prev = avg7(s, d - dt.timedelta(days=7)); sl = slope_per_week(s, d)
    print("⚖️ Logged %.1f lb (%s). 7-day avg %s%s. Trend %s lb/wk (28d)." % (
        a.lbs, d, t, "" if prev is None else " (%+.2f vs last wk)" % (t - prev), "n/a" if sl is None else "%+.2f" % sl))

# ---------- cardio ----------
def met_for(kind, mph, grade):
    if mph:
        mpm = mph * 26.8224; g = (grade or 0) / 100.0
        vo2 = (0.2 * mpm + 0.9 * mpm * g + 3.5) if mph >= 4.5 else (0.1 * mpm + 1.8 * mpm * g + 3.5)
        return round(vo2 / 3.5, 2)
    return {"run": 9.8, "walk": 3.5, "bike": 7.0, "row": 7.0, "swim": 7.0, "elliptical": 5.0, "stairs": 9.0,
            "pickleball": 4.1, "hike": 6.0, "treadmill": 4.5}.get(kind, 4.0)

def cmd_cardio(a):
    c = db(); d = today(a); t = " ".join(a.text).lower()
    mins = None
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:h|hr|hrs|hours?)\b", t); mins = float(m.group(1)) * 60 if m else None
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:m|min|mins|minutes?)\b(?!i)", t); mins = (mins or 0) + float(m.group(1)) if m else mins
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:mi|miles?)\b", t); miles = float(m.group(1)) if m else None
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:%|grade|incline)", t); grade = float(m.group(1)) if m else 0.0
    m = re.search(r"(\d+(?:\.\d+)?)\s*mph", t); mph = float(m.group(1)) if m else None
    kind = next((k for k in ["run", "ran", "jog", "walk", "bike", "cycl", "row", "swim", "elliptical", "stair", "pickleball", "hike", "treadmill"] if k in t), "activity")
    kind = {"ran": "run", "jog": "run", "cycl": "bike", "stair": "stairs"}.get(kind, kind)
    if mph is None and miles and mins: mph = round(miles / (mins / 60), 2)
    if mins is None and miles and mph: mins = round(miles / mph * 60, 1)
    if mins is None and miles: mph = {"run": 6.0, "walk": 3.0}.get(kind); mins = round(miles / mph * 60, 1) if mph else None
    if mins is None: sys.exit("refused: need a duration or distance (e.g. 'ran 3mi 28min')")
    met = met_for(kind, mph, grade)
    s = weight_series(c, d); wlb = s[-1][1] if s else 180.0
    kcal = round((met - 1) * (wlb / 2.20462) * mins / 60, 1)
    c.execute("""INSERT INTO cardio(date,time,kind,activity,met,minutes,miles,mph,grade_pct,net_kcal,weight_lbs,week,note)
                 VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""", (d.isoformat(), now_hm(), "activity" if not mph else ("route" if miles else "machine"),
                 kind, met, mins, miles, mph, grade, kcal, wlb, "%d-W%02d" % d.isocalendar()[:2], " ".join(a.text)))
    c.commit()
    wk = c.execute("SELECT COALESCE(SUM(minutes),0) m, COALESCE(SUM(net_kcal),0) k FROM cardio WHERE date BETWEEN ? AND ?",
                   (week_start(d).isoformat(), d.isoformat())).fetchone()
    print("🏃 Logged %s %g min%s%s · MET %.1f · ~%d net kcal. Week (Sun-): %d min, %d kcal." % (
        kind, mins, " · %g mi" % miles if miles else "", " · %.1f mph" % mph if mph else "", met, kcal, wk["m"], wk["k"]))

# ---------- workouts ----------
def session_for(c, d, focus=None, create=True):
    r = c.execute("SELECT id FROM workout_sessions WHERE date=? ORDER BY id DESC LIMIT 1", (d.isoformat(),)).fetchone()
    if r: return r["id"]
    if not create: return None
    if focus is None:
        p = c.execute("SELECT focus FROM program WHERE dow=? LIMIT 1", (dow(d),)).fetchone(); focus = p["focus"] if p else None
    return c.execute("INSERT INTO workout_sessions(date,focus) VALUES(?,?)", (d.isoformat(), focus)).lastrowid

def resolve_lift(c, name):
    r = c.execute("SELECT lift FROM lift_aliases WHERE alias=?", (re.sub(r"[^a-z]", "", name.lower()),)).fetchone()
    if r: return r["lift"]
    l = canon_lift(name)
    known = [x[0] for x in c.execute("SELECT lift FROM program UNION SELECT DISTINCT lift FROM workout_exercises e JOIN workout_sessions s ON s.id=e.session_id WHERE s.source='import'")]
    if l in known: return l
    words = [w for w in re.findall(r"[a-z]+", name.lower()) if len(w) > 2]
    prog = [x[0] for x in c.execute("SELECT lift FROM program")]
    for pool in (prog, known):
        hits = sorted({k for k in pool if words and all(w in k.lower() for w in words)})
        if len(hits) == 1: return hits[0]
    return l

def cmd_set(a):
    c = db(); d = today(a); text = " ".join(a.text)
    sets = parse_sets(text)
    if not sets: sys.exit("refused: no set found (use e.g. 55x12)")
    name = SET_STRIP(text) or a.lift
    if not name: sys.exit("refused: which lift?")
    lift = resolve_lift(c, name)
    sid = session_for(c, d)
    ex = c.execute("SELECT id FROM workout_exercises WHERE session_id=? AND lift=?", (sid, lift)).fetchone()
    eid = ex["id"] if ex else c.execute("INSERT INTO workout_exercises(session_id,ord,name,lift,next_set_by) VALUES(?,(SELECT COUNT(*) FROM workout_exercises WHERE session_id=?),?,?,'program')",
                                        (sid, sid, name, lift)).lastrowid
    drop = 1 if a.drop or re.search(r"\bdrop", text, re.I) else 0
    n0 = c.execute("SELECT COUNT(*) FROM workout_sets WHERE exercise_id=?", (eid,)).fetchone()[0]
    for i, (lb, reps) in enumerate(sets):
        c.execute("INSERT INTO workout_sets(exercise_id,ord,lb,reps,is_drop,note) VALUES(?,?,?,?,?,?)",
                  (eid, n0 + i, lb, reps, 1 if (drop and (i > 0 or n0 > 0)) else 0, "drop set" if drop and (i > 0 or n0 > 0) else None))
    if a.note:
        c.execute("INSERT INTO workout_notes(session_id,exercise_id,note,affects) VALUES(?,?,?,?)", (sid, eid, a.note, 0 if a.no_affect else 1))
    c.commit()
    allsets = [dict(r) for r in c.execute("SELECT * FROM workout_sets WHERE exercise_id=? ORDER BY ord", (eid,))]
    assisted = "assist" in text.lower() or "assist" in (c.execute("SELECT name FROM workout_exercises WHERE id=?", (eid,)).fetchone()[0] or "").lower()
    nt = next_target(lift, allsets, assisted)
    c.execute("UPDATE workout_exercises SET next_target=? WHERE id=? AND COALESCE(next_set_by,'program')='program'", (nt[2], eid)); c.commit()
    seat = c.execute("SELECT setting FROM seat_settings WHERE lift=?", (lift,)).fetchone()
    if not c.execute("SELECT 1 FROM program WHERE lift=? UNION SELECT 1 FROM workout_exercises WHERE lift=? AND id<>?", (lift, lift, eid)).fetchone():
        print("❓ '%s' is a new lift name. If you meant a program lift, `undo set` and re-log with the full name." % lift)
    print("🏋️ %s %s: %s%s. Next time: %s.%s" % (d, lift, ", ".join("%sx%d" % ("bw" if lb is None else "%g" % lb, r) for lb, r in sets),
          " (drop)" if drop else "", nt[2], " Seat: %s." % seat[0] if seat else ""))

def SET_STRIP(text):
    t = re.sub(r"(?:bw|\d+(?:\.\d+)?)\s*(?:lb|lbs|#)?\s*[x×*]\s*\d+|\d+\s*(?:reps?\s*)?(?:@|at)\s*\d+(?:\.\d+)?\s*(?:lb|lbs)?|\bdrops?\b|[,/>+]", " ", text, flags=re.I)
    return re.sub(r"\s+", " ", t).strip()

def cmd_note(a):
    c = db(); d = today(a); sid = session_for(c, d, create=True); eid = None
    if a.lift:
        lift = resolve_lift(c, a.lift)
        r = c.execute("SELECT id FROM workout_exercises WHERE session_id=? AND lift=?", (sid, lift)).fetchone()
        eid = r["id"] if r else c.execute("INSERT INTO workout_exercises(session_id,ord,name,lift,next_set_by) VALUES(?,99,?,?,'program')", (sid, a.lift, lift)).lastrowid
    note = " ".join(a.text); aff = 0 if a.no_affect else 1
    c.execute("INSERT INTO workout_notes(session_id,exercise_id,note,affects) VALUES(?,?,?,?)", (sid, eid, note, aff)); c.commit()
    print("📝 Note on %s %s: \"%s\". %s" % (d, ("· " + resolve_lift(c, a.lift)) if a.lift else "(whole session)", note,
          "Trends will discount this." if aff else "Kept as info only (not discounted)."))

def cmd_undo(a):
    c = db()
    if a.what == "weight": r = c.execute("SELECT id,date,lbs FROM weight ORDER BY id DESC LIMIT 1").fetchone(); c.execute("DELETE FROM weight WHERE id=?", (r["id"],)); msg = "weight %s %s" % (r["date"], r["lbs"])
    elif a.what == "cardio": r = c.execute("SELECT id,date,note FROM cardio ORDER BY id DESC LIMIT 1").fetchone(); c.execute("DELETE FROM cardio WHERE id=?", (r["id"],)); msg = "cardio %s %s" % (r["date"], r["note"])
    elif a.what == "set":
        r = c.execute("SELECT s.id,e.lift,s.lb,s.reps,e.id eid FROM workout_sets s JOIN workout_exercises e ON e.id=s.exercise_id ORDER BY s.id DESC LIMIT 1").fetchone()
        c.execute("DELETE FROM workout_sets WHERE id=?", (r["id"],)); msg = "set %s %sx%s" % (r["lift"], r["lb"], r["reps"])
        if not c.execute("SELECT 1 FROM workout_sets WHERE exercise_id=?", (r["eid"],)).fetchone(): c.execute("DELETE FROM workout_exercises WHERE id=?", (r["eid"],))
    elif a.what == "note": r = c.execute("SELECT id,note FROM workout_notes ORDER BY id DESC LIMIT 1").fetchone(); c.execute("DELETE FROM workout_notes WHERE id=?", (r["id"],)); msg = "note \"%s\"" % r["note"]
    c.commit(); print("↩️ Removed last %s." % msg)

# ---------- check-ins ----------
def cmd_checkin(a):
    c = db(); d = today(a); done = []
    if dow(d) == 6 and not a.force: print("🕊️ Saturday is Sabbath - no check-in needed. (Use --force if you want it logged.)"); return
    words = [w.lower().strip(",.") for w in a.items if w.lower() not in ("and", "did", "done", "&")]
    kid = next((w for w in words if w in KIDS), None)
    for w in words:
        if w in KIDS: continue
        it = ITEM_ALIASES.get(w)
        if not it: sys.exit("refused: unknown item '%s' (faith, trading, spouse, father, eat, move, fast)" % w)
        detail = None
        if it == "father":
            detail = kid or (a.kid.lower() if a.kid else None)
        c.execute("INSERT INTO checkins(date,item,done,detail) VALUES(?,?,?,?) ON CONFLICT(date,item) DO UPDATE SET done=excluded.done, detail=COALESCE(excluded.detail,checkins.detail)",
                  (d.isoformat(), it, 0 if a.undo else 1, detail)); done.append(it)
    if kid and "father" not in done:
        c.execute("INSERT INTO checkins(date,item,done,detail) VALUES(?,?,?,?) ON CONFLICT(date,item) DO UPDATE SET done=1, detail=excluded.detail", (d.isoformat(), "father", 1, kid)); done.append("father")
    c.commit()
    st = {r["item"]: r["done"] for r in c.execute("SELECT item,done FROM checkins WHERE date=?", (d.isoformat(),))}
    print("✅ %s %s: %s. Today: %s" % ("Unchecked" if a.undo else "Checked", d, ", ".join(done),
          " ".join(("☑" if st.get(i) else "☐") + i for i in ROLE_ITEMS)))

def cmd_protein(a):
    c = db(); d = today(a)
    c.execute("INSERT INTO protein_checks(date,protein_g,note) VALUES(?,?,?) ON CONFLICT(date) DO UPDATE SET protein_g=excluded.protein_g, note=excluded.note", (d.isoformat(), a.grams, a.note)); c.commit()
    t = target_for(c, d)
    print("🥩 Protein %s: %gg vs %s floor%s." % (d, a.grams, "%gg" % t["protein_g"] if t and t["protein_g"] else "no",
          "" if not (t and t["protein_g"]) else (" - hit" if a.grams >= t["protein_g"] else " - %gg short" % (t["protein_g"] - a.grams))))

def target_for(c, d):
    return c.execute("SELECT * FROM nutrition_targets WHERE dow=? AND effective_from<=? AND (until IS NULL OR until>=?) ORDER BY effective_from DESC LIMIT 1",
                     (dow(d), d.isoformat(), d.isoformat())).fetchone() or \
           c.execute("SELECT * FROM nutrition_targets WHERE dow=? AND until IS NULL", (dow(d),)).fetchone()

# ---------- body / family ----------
def cmd_body(a):
    c = db(); d = today(a)
    if a.kind == "show":
        for r in c.execute("SELECT date,kind,value,unit FROM body_measurements ORDER BY date"): print("%s %-6s %g %s" % tuple(r))
        return
    c.execute("INSERT INTO body_measurements(date,kind,value,unit,note) VALUES(?,?,?,?,?)", (d.isoformat(), a.kind, a.value, {"waist": "in", "dexa": "%bf"}.get(a.kind, a.unit), a.note)); c.commit()
    prev = c.execute("SELECT date,value FROM body_measurements WHERE kind=? AND date<? ORDER BY date DESC LIMIT 1", (a.kind, d.isoformat())).fetchone()
    print("📏 %s %s: %g%s" % (a.kind, d, a.value, "" if not prev else " (%+.2f since %s)" % (a.value - prev["value"], prev["date"])))

FAM_ITEMS = ["songs", "games", "bible", "lunch", "sabbathdinner", "sabbath", "church", "solo"]
def cmd_fam(a):
    c = db(); d = today(a); wk = week_start(d).isoformat(); it = a.item.lower()
    if it not in FAM_ITEMS: sys.exit("refused: fam item must be one of " + ", ".join(FAM_ITEMS))
    if it in ("songs", "games"):
        r = c.execute("SELECT id,count FROM family_week_items WHERE week_start=? AND item=?", (wk, it)).fetchone()
        if r: c.execute("UPDATE family_week_items SET count=count+1 WHERE id=?", (r["id"],))
        else: c.execute("INSERT INTO family_week_items(week_start,item,count) VALUES(?,?,1)", (wk, it))
    else:
        c.execute("INSERT INTO family_week_items(week_start,item,kid,date) VALUES(?,?,?,?)", (wk, it, a.kid.title() if a.kid else None, d.isoformat()))
    c.commit(); print("👨‍👩‍👧 Family week of %s: %s" % (wk, fam_summary(c, wk)))

def fam_summary(c, wk):
    rows = c.execute("SELECT item,kid,date,count FROM family_week_items WHERE week_start=?", (wk,)).fetchall()
    out = []
    for i in FAM_ITEMS:
        rs = [r for r in rows if r["item"] == i]
        if i in ("songs", "games"): out.append("%s %d" % (i, sum(r["count"] or 0 for r in rs)))
        elif i == "solo": out.append("1-on-1s: " + (",".join(sorted({r["kid"] for r in rs if r["kid"]})) or "none"))
        else: out.append(("☑" if rs else "☐") + i)
    return " · ".join(out)

# ---------- gym today ----------
def lift_history(c, lift, before):
    rows = c.execute("""SELECT e.id eid, e.name, e.next_target, e.next_set_by, s.date, s.id sid FROM workout_exercises e
        JOIN workout_sessions s ON s.id=e.session_id WHERE e.lift=? AND s.date<? ORDER BY s.date DESC, e.id DESC""", (lift, before.isoformat())).fetchall()
    out = []
    for r in rows:
        sets = [dict(x) for x in c.execute("SELECT * FROM workout_sets WHERE exercise_id=? ORDER BY ord", (r["eid"],))]
        notes = c.execute("SELECT note FROM workout_notes WHERE affects=1 AND (exercise_id=? OR (session_id=? AND exercise_id IS NULL))", (r["eid"], r["sid"])).fetchall()
        out.append(dict(r) | {"sets": sets, "affected": [n["note"] for n in notes]})
    return out

def fmt_sets(sets):
    return ", ".join(("bw" if s["lb"] is None else "%g" % s["lb"]) + ("x%d" % s["reps"] if s["reps"] is not None else "") + ("d" if s["is_drop"] else "") for s in sets) or "(no sets)"

def gym_plan(c, d):
    prog = c.execute("SELECT * FROM program WHERE dow=? ORDER BY ord", (dow(d),)).fetchall()
    return prog

def cmd_gym(a):
    c = db(); d = today(a)
    prog = gym_plan(c, d)
    if not prog:
        nd = next(d + dt.timedelta(days=i) for i in range(1, 8) if dow(d + dt.timedelta(days=i)) in GYM_DOW)
        print("😴 %s %s is not a gym day (Sun/Tue/Thu). Next: %s %s - %s." % (DAYN[dow(d)], d, DAYN[dow(nd)], nd, gym_plan(c, nd)[0]["focus"]))
        if dow(d) != 6: return
        return
    print("🏋️ %s %s - %s (90-min cap)" % (DAYN[dow(d)], d, prog[0]["focus"]))
    for p in prog:
        h = lift_history(c, p["lift"], d + dt.timedelta(days=0 if a.include_today is False else 1)) if False else lift_history(c, p["lift"], d)
        seat = c.execute("SELECT setting FROM seat_settings WHERE lift=?", (p["lift"],)).fetchone()
        line = "• %s - %s sets%s" % (p["lift"], p["sets"], " · seat: %s" % seat[0] if seat else "")
        if not h: print(line + "\n    last: none logged → start conservative, log the top set"); continue
        last = h[0]; clean = next((x for x in h if not x["affected"]), None)
        basis = last if not last["affected"] else (clean or last)
        assisted = "assist" in (basis["name"] or "").lower()
        nt = next_target(p["lift"], basis["sets"], assisted)
        target = nt[2]; why = "rule"
        if basis is last and last["next_set_by"] == "owner" and last["next_target"]:
            target, why = last["next_target"], "your call"
        if target.startswith("no basis"):
            nts = [x["note"] for x in basis["sets"] if x.get("note")]
            target = "to form failure - beat last" + (": " + nts[-1] if nts else " session")
        print(line)
        print("    last %s: %s%s" % (last["date"], fmt_sets(last["sets"]), "  ⚠️ " + "; ".join(last["affected"]) if last["affected"] else ""))
        if basis is not last: print("    basis %s (clean): %s" % (basis["date"], fmt_sets(basis["sets"])))
        print("    target: %s (%s)" % (target, why))
        if last["affected"]:
            inj = [n for n in last["affected"] if re.search(r"hurt|pain|tweak|injur|elbow|shoulder|back|knee|wrist|strain", n, re.I)]
            if inj: print("    ⚠️ caution: %s. Test a light pain-free set first; stop on any tweak." % inj[-1][:70])
            else: print("    ℹ️ last session discounted (%s); target uses the clean session." % last["affected"][0][:60])

# ---------- trends ----------
def lift_points(c, lift):
    pts = []
    for r in c.execute("""SELECT e.id eid, e.name, s.date, s.id sid FROM workout_exercises e JOIN workout_sessions s ON s.id=e.session_id
                          WHERE e.lift=? ORDER BY s.date""", (lift,)):
        sets = [dict(x) for x in c.execute("SELECT * FROM workout_sets WHERE exercise_id=? AND is_drop=0 AND lb IS NOT NULL AND reps IS NOT NULL", (r["eid"],))]
        aff = [n[0] for n in c.execute("SELECT note FROM workout_notes WHERE affects=1 AND (exercise_id=? OR (session_id=? AND exercise_id IS NULL))", (r["eid"], r["sid"]))]
        if not sets: continue
        top = max(sets, key=lambda s: (s["lb"], s["reps"]))
        pts.append({"date": r["date"], "lb": top["lb"], "reps": top["reps"], "e1rm": epley(top["lb"], top["reps"]), "affected": aff, "assisted": "assist" in r["name"].lower()})
    return pts

def lift_trend(pts):
    clean = [p for p in pts if not p["affected"] and not p["assisted"]]
    if len(clean) < 2: return None
    first, last = clean[0], clean[-1]; best = max(clean, key=lambda p: p["e1rm"])
    recent = clean[-3:]
    plateau = len(recent) == 3 and max(p["e1rm"] for p in recent[1:]) <= recent[0]["e1rm"]
    return {"first": first, "last": last, "best": best, "delta": round(last["e1rm"] - first["e1rm"], 1),
            "pct": round(100 * (last["e1rm"] - first["e1rm"]) / first["e1rm"], 1), "plateau": plateau, "n": len(clean), "dropped": len(pts) - len(clean)}

def cmd_trends(a):
    c = db(); d = today(a)
    if a.what in ("all", "weight"):
        s = weight_series(c, d)
        if s:
            print("⚖️ Weight: %s→%s: %.1f → %.1f lb (%+.1f). 7d avg now %s; 28d trend %s lb/wk; 14d trend %s lb/wk." % (
                s[0][0], s[-1][0], s[0][1], s[-1][1], s[-1][1] - s[0][1], avg7(s, D(s[-1][0])), slope_per_week(s, D(s[-1][0])), slope_per_week(s, D(s[-1][0]), 14)))
            wk = {}
            for k, v in s: wk.setdefault(week_start(D(k)).isoformat(), []).append(v)
            print("   weekly avg: " + "  ".join("%s %.1f" % (k[5:], sum(v) / len(v)) for k, v in sorted(wk.items())[-8:]))
    if a.what in ("all", "lifts", "lift"):
        lifts = [a.lift and resolve_lift(c, a.lift)] if a.what == "lift" else [r[0] for r in c.execute("SELECT DISTINCT lift FROM program ORDER BY dow, ord")]
        print("🏋️ Lifts (top non-drop set, e1RM Epley; * = context note, excluded):")
        for l in lifts:
            pts = lift_points(c, l)
            if not pts:
                bw = [(r[0], r[1]) for r in c.execute("""SELECT s.date, MAX(ws.reps) FROM workout_sets ws JOIN workout_exercises e ON e.id=ws.exercise_id
                      JOIN workout_sessions s ON s.id=e.session_id WHERE e.lift=? AND ws.lb IS NULL AND ws.reps IS NOT NULL GROUP BY s.date ORDER BY s.date""", (l,))]
                print("  %-28s %s" % (l, ("bodyweight reps: " + " ".join("%s:%d" % (d_[5:], r_) for d_, r_ in bw[-6:])) if bw else "no numeric sets (form-failure notes only)"))
                continue
            t = lift_trend(pts)
            hist = " ".join("%s:%gx%d%s" % (p["date"][5:], p["lb"], p["reps"], "*" if p["affected"] else ("a" if p["assisted"] else "")) for p in pts[-6:])
            if t: print("  %-28s e1RM %g→%g (%+g, %+g%%) over %d clean · best %g on %s%s%s\n      %s" % (
                l, t["first"]["e1rm"], t["last"]["e1rm"], t["delta"], t["pct"], t["n"], t["best"]["e1rm"], t["best"]["date"],
                " · PLATEAU (3 clean sessions, no gain)" if t["plateau"] else "", " · %d discounted" % t["dropped"] if t["dropped"] else "", hist))
            else: print("  %-28s not enough clean sessions\n      %s" % (l, hist))
        flagged = c.execute("""SELECT s.date, COALESCE(e.lift,'(session)') l, n.note FROM workout_notes n JOIN workout_sessions s ON s.id=n.session_id
            LEFT JOIN workout_exercises e ON e.id=n.exercise_id WHERE n.affects=1 ORDER BY s.date""").fetchall()
        if a.what != "lift": print("  Discounted context: " + "; ".join("%s %s (%s)" % (r[0], r[1], r[2][:50]) for r in flagged))

# ---------- card ----------
def cmd_card(a):
    c = db(); d = today(a); ds = d.isoformat(); wd = dow(d)
    print("🃏 MaxOS Card - %s %s" % (DAYN[wd], ds))
    if wd == 6:
        print("🕊️ Sabbath. Rest. No blocks, no scoreboard today.")
        fam = fam_summary(c, week_start(d).isoformat()); print("Family week: " + fam); return
    print("🎯 Goals:")
    for g in c.execute("SELECT * FROM goals ORDER BY primary_goal DESC, deadline"):
        if g["status"] == "achieved": print("  🏆 %s - achieved %s" % (g["short"], g["achieved_on"])); continue
        days = (D(g["deadline"]) - d).days if g["deadline"] else None
        print("  %s%s - %s days left (%s)%s" % ("⭐ " if g["primary_goal"] else "", g["short"], days, g["deadline"], " · next: " + g["next_step"] if g["next_step"] else ""))
    for m in c.execute("SELECT name, dob FROM family_members WHERE dob IS NOT NULL"):
        b = D(m["dob"]); nb = b.replace(year=d.year)
        if nb < d: nb = nb.replace(year=d.year + 1)
        if (nb - d).days <= 7: print("🎂 %s turns %d %s" % (m["name"].split()[0], nb.year - b.year, "TODAY" if nb == d else "on %s %s" % (DAYN[dow(nb)], nb)))
    s = weight_series(c, d)
    if s:
        last = s[-1]; gap = (d - D(last[0])).days
        print("⚖️ Weight %.1f (%s) · 7d avg %s · trend %s lb/wk (28d)" % (last[1], "today" if gap == 0 else "%dd ago" % gap, avg7(s, d) or avg7(s, D(last[0])), slope_per_week(s, d)))
    t = target_for(c, d)
    if t: print("🍽️ Today: %s · protein floor %gg · fat floor %gg%s" % (t["mode"], t["protein_g"] or 0, t["fat_g"] or 0, " · FAST DAY" if t["mode"] == "fast" else ""))
    ck = {r["item"]: r for r in c.execute("SELECT * FROM checkins WHERE date=?", (ds,))}
    moved = c.execute("SELECT (SELECT COUNT(*) FROM cardio WHERE date=?)+(SELECT COUNT(*) FROM workout_sessions WHERE date=?)", (ds, ds)).fetchone()[0] > 0
    pc = c.execute("SELECT protein_g FROM protein_checks WHERE date=?", (ds,)).fetchone()
    print("🧱 Today's blocks:")
    kid = next_kid(c, d)
    for i, lab in [("faith", "🙏 Faith"), ("trading", "📈 Trading step"), ("spouse", "💝 Spouse"), ("father", "👧 Father (1-on-1 up next: %s)" % kid)]:
        print("  %s %s%s" % ("☑" if ck.get(i) and ck[i]["done"] else "☐", lab, " - " + ck[i]["detail"] if ck.get(i) and ck[i]["detail"] else ""))
    fast = t and t["mode"] == "fast"
    eat_ok = (ck.get("eat") and ck["eat"]["done"]) or (pc and t and t["protein_g"] and pc[0] >= t["protein_g"])
    if fast: print("  %s ⏳ Fast (Sunday fast day)" % ("☑" if ck.get("fast") and ck["fast"]["done"] else "☐"))
    else: print("  %s 🥩 Eat (protein floor)%s" % ("☑" if eat_ok else "☐", " - %gg logged" % pc[0] if pc else ""))
    print("  %s 🏃 Move%s" % ("☑" if moved or (ck.get("move") and ck["move"]["done"]) else "☐", " - gym day: " + gym_plan(c, d)[0]["focus"] if wd in GYM_DOW and gym_plan(c, d) else ""))
    sl = slipping(c, d)
    print("⚠️ Slipping:" + ("" if sl else " nothing - clean."))
    for x in sl: print("  • " + x)

def next_kid(c, d):
    last = {}
    for r in c.execute("SELECT date, detail FROM checkins WHERE item='father' AND detail IS NOT NULL AND date<=?", (d.isoformat(),)):
        for k in r["detail"].split(","): last[k] = r["date"]
    return min(KIDS, key=lambda k: last.get(k, "0000"))

def slipping(c, d):
    out = []; ws = week_start(d)
    for it in ROLE_ITEMS:
        days = [ws + dt.timedelta(days=i) for i in range(dow(d))]           # Sun..yesterday this week
        if len(days) < 2:
            days = [d - dt.timedelta(days=i) for i in range(1, 4) if dow(d - dt.timedelta(days=i)) != 6]
        hit = c.execute("SELECT COUNT(*) FROM checkins WHERE item=? AND done=1 AND date IN (%s)" % ",".join("?" * len(days)), [it] + [x.isoformat() for x in days]).fetchone()[0]
        last = c.execute("SELECT MAX(date) FROM checkins WHERE item=? AND done=1 AND date<?", (it, d.isoformat())).fetchone()[0]
        if days and hit < len(days) - 1:
            out.append("%s: %d of last %d days%s" % (it, hit, len(days), " (last %s)" % last if last else ""))
    s = weight_series(c, d)
    if s and (d - D(s[-1][0])).days >= 3: out.append("weigh-in: none for %d days" % (d - D(s[-1][0])).days)
    for i in range(dow(d)):
        gd = ws + dt.timedelta(days=i)
        if dow(gd) in GYM_DOW and not c.execute("SELECT 1 FROM workout_sessions WHERE date BETWEEN ? AND ?", (gd.isoformat(), (gd + dt.timedelta(days=1)).isoformat())).fetchone():
            out.append("gym: %s %s session not logged" % (DAYN[dow(gd)], gd))
    if dow(d) >= 4:
        rows = {r["item"] for r in c.execute("SELECT item FROM family_week_items WHERE week_start=?", (ws.isoformat(),))}
        miss = [i for i in ("bible", "lunch") if i not in rows]
        if miss: out.append("family week: not yet " + ", ".join(miss))
    return out

# ---------- verify ----------
EXPECTED = []  # optional (name, sql, expected_count) rows to sanity-check an import
def cmd_verify(a):
    c = db(); ok = True
    for name, q, exp in EXPECTED:
        n = c.execute(q).fetchone()[0]; ok &= n == exp
        print("%-14s %5d  expected %4d  %s" % (name, n, exp, "OK" if n == exp else "MISMATCH"))
    for t in ["saved_foods", "recipes", "food_days", "food_items", "food_corrections", "goals", "nutrition_targets", "program", "seat_settings", "workout_notes", "checkins", "family_week_items", "raw_docs"]:
        print("%-18s %5d" % (t, c.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0]))
    ic = c.execute("PRAGMA integrity_check").fetchone()[0]; print("integrity_check", ic); ok &= ic == "ok"
    sys.exit(0 if ok else 1)

def cmd_init(a):
    from maxos_lib import SCHEMA
    c = db(); c.executescript(SCHEMA); c.commit(); print("initialised " + DB)

def main():
    p = argparse.ArgumentParser(prog="maxos.py", description="MaxOS CLI. All logs accept --date YYYY-MM-DD (default today, CT).")
    sp = p.add_subparsers(dest="cmd", required=True)
    def sub(n, f, **kw):
        x = sp.add_parser(n, **kw); x.set_defaults(fn=f); x.add_argument("--date"); return x
    x = sub("weight", cmd_weight); x.add_argument("lbs", type=float); x.add_argument("--note")
    x = sub("cardio", cmd_cardio); x.add_argument("text", nargs="+")
    x = sub("set", cmd_set, help="set trap bar 315x8 | set dips 50x10 drop 25x8"); x.add_argument("text", nargs="+"); x.add_argument("--lift"); x.add_argument("--drop", action="store_true"); x.add_argument("--note"); x.add_argument("--no-affect", action="store_true")
    x = sub("note", cmd_note); x.add_argument("text", nargs="+"); x.add_argument("--lift"); x.add_argument("--no-affect", action="store_true")
    x = sub("checkin", cmd_checkin); x.add_argument("items", nargs="+"); x.add_argument("--kid"); x.add_argument("--undo", action="store_true"); x.add_argument("--force", action="store_true")
    x = sub("protein", cmd_protein); x.add_argument("grams", type=float); x.add_argument("--note")
    x = sub("body", cmd_body); x.add_argument("kind", choices=["waist", "dexa", "neck", "chest", "arm", "thigh", "hips", "bodyfat", "show"]); x.add_argument("value", type=float, nargs="?"); x.add_argument("--unit", default="in"); x.add_argument("--note")
    x = sub("fam", cmd_fam); x.add_argument("item"); x.add_argument("kid", nargs="?")
    x = sub("gym", cmd_gym); x.add_argument("which", nargs="?", default="today"); x.set_defaults(include_today=False)
    sub("card", cmd_card)
    x = sub("trends", cmd_trends); x.add_argument("what", nargs="?", default="all", choices=["all", "weight", "lifts", "lift"]); x.add_argument("lift", nargs="?")
    x = sub("undo", cmd_undo); x.add_argument("what", choices=["weight", "cardio", "set", "note"])
    sub("verify", cmd_verify)
    sub("init", cmd_init)
    a = p.parse_args(); a.fn(a)

if __name__ == "__main__": main()
