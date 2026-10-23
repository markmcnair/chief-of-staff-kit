# chief-of-staff-kit

The plumbing behind a "Chief of Staff" setup on **Grok Bot**: a personal agent that reads your incoming messages
(WhatsApp/Signal/Telegram/etc. via Beeper, plus iMessage from your Mac), keeps a deterministic daily
habit/fitness log, and drafts replies that **only go out after you approve them**.

Everything here is small, stdlib-first Python plus one Supabase table and edge function. Secrets live in env vars or
a local `config.json`. None are committed.

```
 Beeper Desktop ──(local API :23373)──> beeper/watcher.py ──POST──┐
                                                                   ├──> Grok Bot webhook routine ──> your agent
 Mac Messages chat.db ──> imessage-bridge/bridge.py ──POST────────┘          │
                                ^                                             │ drafts a reply, asks you
                                │ approved rows only                          ▼
                     Supabase bridge-outbox fn <── bridge.outbox table <── (you approve) agent marks row 'approved'

 maxos/maxos.py: SQLite CLI the agent calls for check-ins, weight, cardio, lifting, morning card
```

## Pieces

| Folder | What it does |
|---|---|
| `beeper/watcher.py` | Polls the Beeper Desktop API every `WATCHER_POLL` s (default 10). For each chat whose `lastActivity` changed, it fetches recent messages and POSTs each new, non-self, non-reaction message (text, sender, chat, attachments, voice note info) to your Grok Bot webhook. The first run only records a baseline and forwards nothing. If a POST fails, the chat is retried on the next poll. |
| `beeper/start-watcher.sh` | flock'd supervisor that keeps the watcher running and restarts it if it exits. |
| `beeper/start-beeper.sh` | Optional supervisor that keeps the Beeper Desktop AppImage running on a headless Linux display (for example a Grok Bot box). |
| `beeper/beeper_cli.py` | Small CLI for the agent: `info`, `accounts`, `chats`, `search-chats`, `messages`, `search-messages`, `send`. `send` refuses to run without `--approved`. |
| `imessage-bridge/bridge.py` | Runs on your Mac every 20 s via launchd. **Inbound:** reads new rows from `~/Library/Messages/chat.db` (and decodes `attributedBody`) and POSTs them to the webhook. **Outbound:** asks the `bridge-outbox` function for *approved* rows, claims each one atomically, sends it with AppleScript through Messages.app, and reports sent or failed. It also alerts the webhook if Full Disk Access is lost for more than 10 minutes. |
| `imessage-bridge/install.sh` + plist | Installs to `~/.imessage-bridge` and registers the LaunchAgent. |
| `supabase/migrations.sql` | `bridge.outbox` table, RLS lock-down, and the atomic `claim_outbox()` function. |
| `supabase/functions/bridge-outbox` | Deno edge function: `fetch` / `claim` / `finish`, authenticated with the `x-bridge-secret` header. |
| `maxos/` | "MaxOS": a deterministic personal-ops CLI (SQLite). The agent maps chat phrases to commands and relays the receipt word for word. All math lives in code, never in the LLM. |

## Requirements
- Python 3.9+ (stdlib only). Supabase CLI for the outbound iMessage path.
- [Beeper Desktop](https://www.beeper.com/) with the Desktop API enabled.
- macOS with Messages signed in (for the iMessage bridge).
- A Grok Bot **webhook routine** (a routine with a webhook trigger). Copy its URL and secret.

## Setup

### 1. Env
```bash
cp .env.example .env    # fill in. Never commit .env
set -a; . ./.env; set +a
```

### 2. Beeper watcher
1. In Beeper Desktop go to **Settings → Developers**, enable the Desktop API, and create a token (`BEEPER_TOKEN`). The API listens on `http://localhost:23373`.
2. Smoke test: `python3 beeper/beeper_cli.py info`, then `python3 beeper/watcher.py test` (this posts one test payload to your webhook).
3. Run: `setsid nohup beeper/start-watcher.sh >/dev/null 2>&1 &`. Logs go to `beeper/watcher.log` and state to `beeper/watcher_state.json` (both are gitignored).
4. Webhook auth: the watcher sends `Authorization: Bearer $BEEPER_WEBHOOK_SECRET`. If that's rejected it falls back to `X-Webhook-Key` / `X-Webhook-Secret` and remembers which one worked.
5. Headless box: `start-beeper.sh` runs the AppImage with `--appimage-extract-and-run --no-sandbox` on `$BEEPER_DISPLAY` (default `:2`). Without systemd, start both supervisors from `~/.profile`.

### 3. iMessage bridge (Mac)
1. `cp imessage-bridge/config.example.json imessage-bridge/config.json` and fill it in (webhook URL and secret, outbox URL, bridge secret).
2. `bash imessage-bridge/install.sh`. It prints the **exact Python binary** it will use.
3. **Full Disk Access:** open System Settings → Privacy & Security → Full Disk Access → **+**, press ⌘⇧G, and paste that path. macOS checks FDA against the *resolved* binary, so a symlink or shim won't work.
   - **Homebrew Python note:** if you'd rather use Homebrew's python, pass the real path, e.g. `bash install.sh "$(python3 -c 'import os,sys;print(os.path.realpath(sys.executable))')"`, and grant FDA to that file (something like `/opt/homebrew/Cellar/python@3.x/.../Python.app/Contents/MacOS/Python`). After `brew upgrade python` the path changes, so you'll need to grant FDA again and re-run install. The bridge will alert you if access goes missing.
4. The first send triggers a macOS prompt asking to let Python control Messages. Click Allow.
5. Test: `~/.imessage-bridge/bridge.py --test` (posts a `bridge_test` event). Log: `~/.imessage-bridge/bridge.log`.
6. The cursor starts at the newest message, so your history is never replayed.

### 4. Supabase (outbound iMessage)
```bash
supabase link --project-ref YOUR_PROJECT_REF
psql "$DATABASE_URL" -f supabase/migrations.sql      # or paste into the SQL editor
# Dashboard: Settings > API > Exposed schemas: add "bridge"
supabase secrets set BRIDGE_SECRET=long-random-string
supabase functions deploy bridge-outbox --no-verify-jwt
```
To queue a message, your agent (with service-role access, e.g. through the Supabase connector) inserts a row
`(handle, body, service)` with `status='pending'`, shows you the draft, and sets `status='approved', approved_at=now()` **only after you say yes**.
The Mac picks it up within about 20 s.

### 5. MaxOS
```bash
python3 maxos/maxos.py init                       # creates maxos.db from schema
python3 -c "import sqlite3;c=sqlite3.connect('maxos/maxos.db');c.executescript(open('maxos/seed_example.sql').read());c.commit()"
python3 maxos/maxos.py weight 180.2
python3 maxos/maxos.py set trap bar 225x8
python3 maxos/maxos.py checkin faith father kid1
python3 maxos/maxos.py card
```
See `maxos/README.md` for the chat → command map you can paste into your agent's instructions.

## Hooking it into Grok Bot
1. Create a routine with a **webhook trigger**, and put its URL and secret into `.env` / `config.json`.
2. Routine instructions (example): *"Each payload is one inbound message (`source` = `beeper` or `type` = `imessage`). Decide whether it needs me. If it does, summarize it and draft a reply in my voice, then wait for my approval. Never send. For `bridge_alert`, tell me Full Disk Access was lost."*
3. Sending: Beeper uses `beeper_cli.py send <chat> "<text>" --approved`, and iMessage uses an approved row in `bridge.outbox`. Both happen only after you explicitly approve that exact text.

## Safety
- **Nothing sends without owner approval.** `beeper_cli.py send` refuses without `--approved`, and the bridge only ever sees rows already marked `approved`. Claims are atomic, so a message can't go out twice.
- Inbound forwarding is read-only. The first run baselines without forwarding.
- Secrets stay in `.env`, `~/.imessage-bridge/config.json` (chmod 600), or Supabase function secrets. Logs and state are gitignored, and the bridge never logs secrets or message bodies.
- `bridge.outbox` has RLS enabled and no anon access. Only the edge function (service role, shared secret) can reach it.
- Review the code before granting Full Disk Access. It can read your entire Messages history.

## License
MIT
