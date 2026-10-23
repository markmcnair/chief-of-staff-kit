# MaxOS: deterministic personal-ops CLI

DB: `$MAXOS_DB` (default `maxos/maxos.db`, SQLite). Run `python3 maxos.py <cmd>`. Every log accepts `--date YYYY-MM-DD` and prints a one-line receipt. Have your agent relay that receipt word for word.
Rules for the agent: math lives in the CLI (never compute in chat). The owner's numbers are final. Questions never write. If something is ambiguous, ask once.
`undo weight|cardio|set|note` removes the most recent row of that kind.

Config: `MAXOS_KIDS=kid1,kid2` (names for 1-on-1 rotation), `MAXOS_GYM_DOW=1,3,5` (0=Sun). Role check-in items (`faith, trading, spouse, father`) and family items in `maxos.py` are examples, so edit them to match your own life.

| Chat | Command |
|---|---|
| `176.4` / `weighed 176.4` | `maxos.py weight 176.4 [--note ...]` |
| `ran 3mi 28min` / `45 min treadmill 3.0mph 12%` | `maxos.py cardio ...` |
| `trap bar 315x8` / `incline db 55x12 drop 45x10` | `maxos.py set ...` (sets after the first are drops) |
| `assisted dips 20x15` | `maxos.py set assisted dips 20x15` |
| `shoulder hurt` about lift X | `maxos.py note shoulder hurt --lift "X"` (`--no-affect` to keep in trends) |
| `did faith and father` | `maxos.py checkin faith father [kid]` · `--undo` |
| `protein 172` | `maxos.py protein 172` |
| `waist 34.4` | `maxos.py body waist 34.4` · `body show` |
| `fam bible` / `solo kid1` | `maxos.py fam bible` / `maxos.py fam solo kid1` |
| `gym?` | `maxos.py gym today` |
| morning / `how am I doing` | `maxos.py card` |
| `trends` | `maxos.py trends [weight|lifts|lift "name"]` |
| integrity | `maxos.py verify` |

Saturday is treated as a rest day: `checkin` refuses unless you pass `--force`.

Logic (in `maxos_lib.py`): progression gates on the top non-drop set. Under 15 reps, keep the weight and add a rep. At 15 reps, add 5 lb (10 lb for dips and pull-ups). Trap bar works 7–10 reps: at 10, add 5 lb and reset to 7. Notes flagged `affects` drop that session out of trend math. Weight uses a 7-day average plus 14/28-day least-squares slope. Cardio kcal uses the ACSM equations or a MET table.
