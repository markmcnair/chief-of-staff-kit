"""Shared schema + deterministic helpers for MaxOS (Grok Bot rebuild)."""
import re

SCHEMA = """
CREATE TABLE weight(id INTEGER PRIMARY KEY, date TEXT NOT NULL, lbs REAL NOT NULL, note TEXT, source TEXT DEFAULT 'chat', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE cardio(id INTEGER PRIMARY KEY, date TEXT NOT NULL, time TEXT, kind TEXT, preset TEXT, activity TEXT, met REAL, minutes REAL,
  miles REAL, mph REAL, grade_pct REAL, route TEXT, net_kcal REAL, weight_lbs REAL, home_hours REAL, week TEXT, note TEXT, source TEXT DEFAULT 'chat');
CREATE TABLE workout_sessions(id INTEGER PRIMARY KEY, date TEXT NOT NULL, focus TEXT, raw TEXT, source TEXT DEFAULT 'chat');
CREATE TABLE workout_exercises(id INTEGER PRIMARY KEY, session_id INTEGER REFERENCES workout_sessions(id) ON DELETE CASCADE, ord INTEGER,
  name TEXT, lift TEXT, next_target TEXT, next_set_by TEXT);
CREATE TABLE workout_sets(id INTEGER PRIMARY KEY, exercise_id INTEGER REFERENCES workout_exercises(id) ON DELETE CASCADE, ord INTEGER,
  lb REAL, reps INTEGER, time TEXT, is_drop INTEGER DEFAULT 0, note TEXT);
CREATE TABLE workout_notes(id INTEGER PRIMARY KEY, session_id INTEGER REFERENCES workout_sessions(id) ON DELETE CASCADE,
  exercise_id INTEGER REFERENCES workout_exercises(id) ON DELETE CASCADE, note TEXT NOT NULL, affects INTEGER DEFAULT 1, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE program(id INTEGER PRIMARY KEY, dow INTEGER, focus TEXT, ord INTEGER, lift TEXT, sets INTEGER, scheme TEXT, seat TEXT);
CREATE TABLE progression_rules(key TEXT PRIMARY KEY, value TEXT, description TEXT);
CREATE TABLE seat_settings(lift TEXT PRIMARY KEY, setting TEXT);
CREATE TABLE lift_aliases(alias TEXT PRIMARY KEY, lift TEXT);
CREATE TABLE body_measurements(id INTEGER PRIMARY KEY, date TEXT, kind TEXT, value REAL, unit TEXT, note TEXT, data TEXT);
CREATE TABLE checkin_days(date TEXT PRIMARY KEY, raw TEXT);
CREATE TABLE checkins(id INTEGER PRIMARY KEY, date TEXT NOT NULL, item TEXT NOT NULL, done INTEGER DEFAULT 1, detail TEXT, source TEXT DEFAULT 'chat',
  UNIQUE(date,item));
CREATE TABLE family_members(id INTEGER PRIMARY KEY, name TEXT, role TEXT, dob TEXT, notes TEXT);
CREATE TABLE family_weeks(week_start TEXT PRIMARY KEY, raw TEXT);
CREATE TABLE family_week_items(id INTEGER PRIMARY KEY, week_start TEXT, item TEXT, kid TEXT, date TEXT, count INTEGER);
CREATE TABLE goals(id TEXT PRIMARY KEY, short TEXT, full TEXT, deadline TEXT, domain TEXT, status TEXT, achieved_on TEXT, primary_goal INTEGER, next_step TEXT, data TEXT);
CREATE TABLE nutrition_targets(id INTEGER PRIMARY KEY, effective_from TEXT, until TEXT, dow INTEGER, mode TEXT, calories REAL, protein_g REAL, fat_g REAL, weekly_calories REAL, note TEXT);
CREATE TABLE food_meals(id INTEGER PRIMARY KEY, date TEXT, time TEXT, name TEXT, source TEXT, confidence REAL, calories REAL, protein_g REAL, carbs_g REAL, fat_g REAL, note TEXT, orig_id TEXT, data TEXT);
CREATE TABLE food_items(id INTEGER PRIMARY KEY, meal_id INTEGER REFERENCES food_meals(id), name TEXT, servings REAL, calories REAL, protein_g REAL, carbs_g REAL, fat_g REAL, std TEXT);
CREATE TABLE food_days(date TEXT PRIMARY KEY, meal_count INTEGER, data TEXT);
CREATE TABLE food_corrections(id INTEGER PRIMARY KEY, data TEXT);
CREATE TABLE saved_foods(id INTEGER PRIMARY KEY, name TEXT, calories REAL, protein_g REAL, carbs_g REAL, fat_g REAL, description TEXT, per_100g TEXT, added TEXT);
CREATE TABLE recipes(id TEXT PRIMARY KEY, title TEXT, status TEXT, data TEXT);
CREATE TABLE protein_checks(date TEXT PRIMARY KEY, protein_g REAL, note TEXT);
CREATE TABLE raw_docs(path TEXT PRIMARY KEY, content TEXT);
CREATE INDEX ix_w ON weight(date); CREATE INDEX ix_c ON cardio(date); CREATE INDEX ix_ws ON workout_sessions(date);
CREATE INDEX ix_we ON workout_exercises(lift); CREATE INDEX ix_ck ON checkins(date);
"""

LIFTS = [  # (regex, canonical program name) - order matters
    (r"trap\s*-?bar|^tbdl?$|deadlift", "Trap bar deadlift"),
    (r"incline", "Incline dumbbell press"),
    (r"pulldown", "Close-grip chin-up pulldown"),
    (r"dip", "Weighted dips"),
    (r"pull[\s-]?ups?|^pu$|chin[\s-]?up pulldown", "Pull-ups"),
    (r"dragon", "Dragon flags"),
    (r"leg\s*ext", "Leg extension"),
    (r"leg\s*curl", "Seated leg curl"),
    (r"rear delt|reverse pec|^rpd$", "Reverse pec deck"),
    (r"chest[\s-]*(supported)?\s*row|^csr$|^chestrow$", "Chest-supported row"),
    (r"^clr$|cable lat", "Cable lateral raise"),
    (r"^mlr$|machine lat|lat raise machine|lateral raise \(machine\)|lat raises? machine", "Machine lateral raise"),
    (r"cuffed lat", "Cuffed lateral raise"),
    (r"preacher|^pc$", "Preacher curls"),
    (r"bayesian|^bc$|bicep", "Bayesian cable curl"),
    (r"captain|chair|^ccr$|knee raise", "Captain's chair knee raise"),
    (r"dumbbell (bench|press)|^db (bench|press)|dumbbellbench", "Dumbbell press"),
    (r"^lateral raises?$", "Lateral raise (legacy)"),
]

def canon_lift(name):
    n = (name or "").strip().lower()
    for rx, c in LIFTS:
        if re.search(rx, n): return c
    return (name or "").strip()

AFFECT_RX = re.compile(r"hurt|pain|tweak|injur|strain|pull(ed)? (a|my)|sore|ache|sick|\bill\b|tired|exhaust|no sleep|"
                       r"rush|didn.?t rest|no rest|short rest|cut short|stopped|skip|pickleball|shoulder|elbow|back|knee|wrist|"
                       r"fasted|hungover|distract|time crunch", re.I)

def note_affects(note):
    """1 if a free-text context note signals the performance is not representative."""
    return 1 if note and AFFECT_RX.search(note) else 0

SET_RX = re.compile(r"(?:(bw|\d+(?:\.\d+)?)\s*(?:lb|lbs|#)?\s*[x×*]\s*(\d+))|(?:(\d+)\s*(?:reps?\s*)?(?:@|at)\s*(\d+(?:\.\d+)?)\s*(?:lb|lbs)?)", re.I)

def parse_sets(text):
    """'55x12' / '55x12, 45x10' / '11 at 10lb' / 'bwx8' -> [(lb|None, reps)]"""
    out = []
    for m in SET_RX.finditer(text):
        if m.group(2):
            lb = None if m.group(1).lower() == "bw" else float(m.group(1)); out.append((lb, int(m.group(2))))
        else:
            out.append((float(m.group(4)), int(m.group(3))))
    return out

def epley(lb, reps):
    if lb is None or reps is None: return None
    return round(lb * (1 + reps / 30.0), 1)

def load_step(lift):
    return 10 if re.search(r"dip|pull-up|chin", lift or "", re.I) else 5

def next_target(lift, sets, assisted=False):
    """Deterministic 15-rep gate on the top non-drop set. Returns (lb, reps_floor, text)."""
    work = [s for s in sets if not s.get("is_drop")]
    loaded = [s for s in work if s.get("lb") is not None and s.get("reps") is not None]
    if not loaded:
        bw = [s for s in work if s.get("reps") is not None]
        if not bw: return (None, None, "no basis yet - log a set")
        r = bw[-1]["reps"]
        if r >= 15: return (None, None, "add %d lb, max reps (15-rep gate cleared at bodyweight)" % load_step(lift))
        return (None, r + 1, "bodyweight x %d+ reps" % (r + 1))
    top = max(loaded, key=lambda s: (s["lb"], s["reps"]))
    lb, r = top["lb"], top["reps"]
    step = load_step(lift)
    if lift == "Trap bar deadlift":
        if r >= 10: return (lb + 5, 7, "%g lb x 7+ (10 reached: +5 lb, reset to 7)" % (lb + 5))
        return (lb, r + 1, "%g lb x %d+ reps (work 7-10)" % (lb, r + 1))
    if r >= 15:
        if assisted:
            nlb = max(lb - step, 0)
            return (nlb, None, "%g lb assist x max reps (gate cleared: -%d lb assistance)" % (nlb, step))
        return (lb + step, None, "%g lb x max reps (15-rep gate cleared: +%d lb)" % (lb + step, step))
    return (lb, r + 1, "%g lb x %d+ reps" % (lb, r + 1))
