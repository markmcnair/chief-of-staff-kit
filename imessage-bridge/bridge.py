#!/usr/bin/python3
"""iMessage bridge (Mac). Runs every 20s via launchd (com.example.imessage-bridge).
Inbound: new chat.db rows -> Grok Bot webhook. Outbound: owner-approved rows from the
bridge-outbox function -> Messages. Secrets are never logged."""
import fcntl, json, os, re, sqlite3, subprocess, sys, time, urllib.request, urllib.error
from datetime import datetime, timezone

D = os.path.expanduser(os.environ.get("BRIDGE_DIR", "~/.imessage-bridge"))
DB = os.path.expanduser("~/Library/Messages/chat.db")
CUR, LOG = f"{D}/cursor", f"{D}/bridge.log"
UA = "imessage-bridge/1.0"


def log(msg):
    try:
        if os.path.exists(LOG) and os.path.getsize(LOG) > 2_000_000:
            os.replace(LOG, LOG + ".1")
        with open(LOG, "a") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")
    except Exception:
        pass


def cfg():
    with open(f"{D}/config.json") as f:
        return json.load(f)


# Decodes the NSAttributedString blob newer macOS versions store instead of message.text.
def decode_attributed_body(blob):
    if not blob or len(blob) < 20:
        return None
    blob = bytes(blob)
    ns_idx = blob.find(b"NSString")
    if ns_idx < 0:
        return None
    plus_offset = blob[ns_idx:ns_idx + 30].find(b"+")
    if plus_offset < 0:
        return None
    text_start = ns_idx + plus_offset + 1
    if text_start >= len(blob):
        return None
    first_byte = blob[text_start]
    if first_byte == 0x81:
        if text_start + 2 >= len(blob):
            return None
        text_start += 3
    elif first_byte == 0x82:
        if text_start + 3 >= len(blob):
            return None
        text_start += 4
    elif first_byte < 0x80:
        text_start += 1
    else:
        return None
    end_marker = blob.find(b"NSDictionary", text_start)
    end_pos = end_marker if end_marker > 0 else len(blob)
    try:
        text = blob[text_start:end_pos].decode("utf-8", errors="ignore")
        text = re.sub(r"\x02?iI.{0,10}$", "", text, flags=re.DOTALL)
        text = text.strip("".join(chr(c) for c in range(32) if c not in (9, 10, 13)))
        return text.strip() or None
    except Exception:
        return None


def auth_headers(c):
    name = (c.get("webhook_auth_header") or "Authorization").strip()
    scheme = c.get("webhook_auth_scheme", "Bearer" if name.lower() == "authorization" else "")
    val = f"{scheme} {c['webhook_key']}".strip() if scheme else c["webhook_key"]
    return {name: val}


def post(url, payload, headers, timeout=15):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": UA, **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""


def webhook(c, payload):
    return post(c["webhook_url"], payload, auth_headers(c))[0]


FDA_STATE = f"{D}/fda_state.json"
TRANSIENT = ("database is locked", "database is busy", "disk i/o error", "database table is locked")
PERMISSION = ("authorization denied", "unable to open database", "not authorized", "operation not permitted", "not readable")


def classify(err):
    m = str(err).lower()
    if isinstance(err, PermissionError) or any(p in m for p in PERMISSION):
        return "permission"
    if any(t in m for t in TRANSIENT):
        return "transient"
    return "other"


def open_db():
    if not os.path.exists(DB):
        raise PermissionError("chat.db not readable")
    conn = sqlite3.connect(DB, timeout=10)
    try:
        conn.execute("select 1 from message limit 1")
    except Exception:
        conn.close()
        raise
    return conn


def open_db_retry(tries=3, wait=3):
    last = None
    for _ in range(tries):
        try:
            return open_db()
        except Exception as e:
            last = e
            time.sleep(wait)
    raise last


def load_state():
    try:
        with open(FDA_STATE) as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(st):
    with open(FDA_STATE, "w") as f:
        json.dump(st, f)


def on_db_fail(c, err):
    kind = classify(err)
    st = load_state()
    now = time.time()
    log(f"chat.db open failed class={kind} type={type(err).__name__} msg={str(err)[:80]}")
    if kind != "permission":
        st.pop("perm_since", None)  # transient (locked/busy/asleep): never alerts
        save_state(st)
        return
    st.setdefault("perm_since", now)
    save_state(st)
    down = now - st["perm_since"]
    if down < 600 or now - st.get("last_alert", 0) < 6 * 3600:
        return
    s = webhook(c, {"type": "bridge_alert", "reason": "full_disk_access_lost",
                    "detail": type(err).__name__, "down_minutes": int(down // 60),
                    "python": os.path.realpath(sys.executable),
                    "ts_utc": datetime.now(timezone.utc).isoformat()})
    log(f"fda alert sent http={s}")
    if 200 <= s < 300:
        st["last_alert"] = now
        st["alerted"] = True
        save_state(st)


def on_db_ok(c):
    st = load_state()
    if not st.get("alerted") and "perm_since" not in st:
        return
    if st.get("alerted"):
        s = webhook(c, {"type": "bridge_recovered", "ts_utc": datetime.now(timezone.utc).isoformat()})
        log(f"recovered event http={s}")
        if not 200 <= s < 300:
            return
        st.pop("alerted", None)
    if "perm_since" in st:
        log("chat.db readable again")
    st.pop("perm_since", None)
    save_state(st)


SQL = """select m.ROWID, m.guid, m.text, m.attributedBody, m.date, m.is_from_me, m.service,
  m.cache_has_attachments, h.id, c.chat_identifier, c.display_name,
  (select count(*) from chat_handle_join j where j.chat_id = c.ROWID)
 from message m left join handle h on m.handle_id = h.ROWID
 left join chat_message_join cm on cm.message_id = m.ROWID
 left join chat c on c.ROWID = cm.chat_id
 where m.ROWID > ? order by m.ROWID limit 100"""


def inbound(c, conn):
    if not os.path.exists(CUR):
        mx = conn.execute("select coalesce(max(ROWID),0) from message").fetchone()[0]
        open(CUR, "w").write(str(mx))
        log(f"cursor initialised at {mx}")
        return
    last = int(open(CUR).read().strip() or 0)
    seen = set()
    for (rid, guid, text, ab, date, from_me, svc, att, handle, cident, cname, members) in conn.execute(SQL, (last,)).fetchall():
        if rid in seen:
            continue
        seen.add(rid)
        body = text or decode_attributed_body(ab) or ""
        ts = datetime.fromtimestamp((date or 0) / 1e9 + 978307200, timezone.utc).isoformat()
        payload = {"type": "imessage", "guid": guid, "rowid": rid, "is_from_me": bool(from_me),
                   "sender": "me" if from_me else handle, "handle": handle, "text": body,
                   "has_attachments": bool(att), "service": svc, "ts_utc": ts,
                   "chat_id": cident, "chat_name": cname or None, "is_group": (members or 0) > 1}
        try:
            s = webhook(c, payload)
        except Exception as e:
            log(f"inbound rowid={rid} error={type(e).__name__}")
            return
        if not 200 <= s < 300:
            log(f"inbound rowid={rid} http={s}; will retry")
            return
        open(CUR, "w").write(str(rid))


APPLESCRIPT = '''on run {h, t, svc}
  tell application "Messages"
    if svc is "SMS" then
      set acct to 1st account whose service type = SMS
    else
      set acct to 1st account whose service type = iMessage
    end if
    send t to participant h of acct
  end tell
end run'''


def outbound(c):
    url, H = c["outbox_url"], {"x-bridge-secret": c["bridge_secret"]}
    s, b = post(url, {"action": "fetch", "limit": 5}, H)
    if s != 200:
        log(f"outbox fetch http={s}")
        return
    for r in json.loads(b).get("rows", []):
        s, b = post(url, {"action": "claim", "id": int(r["id"])}, H)
        if s != 200 or not json.loads(b).get("claimed"):
            continue
        row = json.loads(b)["row"]
        ok, err = True, None
        try:
            p = subprocess.run(["/usr/bin/osascript", "-e", APPLESCRIPT, row["handle"], row["body"], row.get("service") or "iMessage"],
                               capture_output=True, text=True, timeout=45)
            if p.returncode != 0:
                ok, err = False, (p.stderr or "osascript failed").strip()[:300]
        except Exception as e:
            ok, err = False, type(e).__name__
        post(url, {"action": "finish", "id": int(row["id"]), "ok": ok, "error": err}, H)
        log(f"outbox id={row['id']} {'sent' if ok else 'failed'}")


def main():
    os.makedirs(D, exist_ok=True)
    lock = open(f"{D}/.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return
    c = cfg()
    if "--test" in sys.argv:
        s = webhook(c, {"type": "bridge_test", "ts_utc": datetime.now(timezone.utc).isoformat()})
        print(s)
        return
    if "--check-db" in sys.argv:
        try:
            open_db().close()
            print("ok")
        except Exception as e:
            print(classify(e))
        return
    if "--init-cursor" in sys.argv:
        conn = open_db()
        mx = conn.execute("select coalesce(max(ROWID),0) from message").fetchone()[0]
        open(CUR, "w").write(str(mx))
        print(mx)
        return
    try:
        conn = open_db_retry()
    except Exception as e:
        try:
            on_db_fail(c, e)
        except Exception as e2:
            log(f"alert error {type(e2).__name__}")
        conn = None
    if conn:
        try:
            on_db_ok(c)
        except Exception as e:
            log(f"recover error {type(e).__name__}")
    if conn:
        try:
            inbound(c, conn)
        except Exception as e:
            log(f"inbound error {type(e).__name__}: {str(e)[:120]}")
        finally:
            conn.close()
    try:
        outbound(c)
    except Exception as e:
        log(f"outbound error {type(e).__name__}")


if __name__ == "__main__":
    main()
