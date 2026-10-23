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
