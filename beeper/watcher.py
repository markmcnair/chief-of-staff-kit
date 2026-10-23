#!/usr/bin/env python3
"""Beeper -> Grok Bot webhook watcher. Polls /v1/chats every POLL s; for chats whose
lastActivity changed, fetches latest messages and forwards unseen, non-self ones."""
import json, os, sys, time, urllib.request, urllib.parse, urllib.error, datetime
BASE = os.environ.get("BEEPER_URL", "http://localhost:23373").rstrip("/")
DIR = os.environ.get("BEEPER_STATE_DIR", os.path.dirname(os.path.abspath(__file__))); STATE = f"{DIR}/watcher_state.json"; LOG = f"{DIR}/watcher.log"
POLL = int(os.environ.get("WATCHER_POLL", "10"))
SKIP_TYPES = {"REACTION"}
AUTH_MODE_FILE = f"{DIR}/watcher_authmode"

def log(m):
    with open(LOG, "a") as f: f.write(f"{datetime.datetime.now().isoformat(timespec='seconds')} {m}\n")

def api(path, params=None):
    q = "?" + urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None}) if params else ""
    r = urllib.request.Request(BASE + path + q, headers={"Authorization": "Bearer " + os.environ["BEEPER_TOKEN"]})
    with urllib.request.urlopen(r, timeout=30) as x: return json.load(x)

def auth_headers(mode):
    s = os.environ["BEEPER_WEBHOOK_SECRET"]
    return {"bearer": {"Authorization": "Bearer " + s}, "xkey": {"X-Webhook-Key": s},
            "xsecret": {"X-Webhook-Secret": s}}[mode]

def post(payload):
    url = os.environ["BEEPER_WEBHOOK_URL"]  # your Grok Bot webhook routine URL
    modes = ["bearer", "xkey", "xsecret"]
    try: pref = open(AUTH_MODE_FILE).read().strip(); modes.remove(pref); modes.insert(0, pref)
    except Exception: pass
    last = None
    for m in modes:
        h = {"Content-Type": "application/json", **auth_headers(m)}
        r = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=h, method="POST")
        try:
            with urllib.request.urlopen(r, timeout=30) as x:
                open(AUTH_MODE_FILE, "w").write(m); return x.status, m
        except urllib.error.HTTPError as e:
            last = (e.code, m)
            if e.code not in (401, 403): return last
    return last

def load():
    try: return json.load(open(STATE))
    except Exception: return None

def save(st):
    tmp = STATE + ".tmp"; json.dump(st, open(tmp, "w")); os.replace(tmp, STATE)

def chats():
    out, cur = [], None
    for _ in range(5):
        d = api("/v1/chats", {"limit": 50, "cursor": cur})
        out += d.get("items", []); cur = d.get("oldestCursor") or d.get("cursor")
        if not d.get("hasMore") or not cur: break
    return out

def msgs(cid):
    return api(f"/v1/chats/{urllib.parse.quote(cid, safe='')}/messages").get("items", [])

def payload(c, m):
    atts = []
    for a in m.get("attachments") or []:
        atts.append({k: a.get(k) for k in ("type", "mimeType", "fileName", "srcURL", "fileSize", "duration", "isVoiceNote") if a.get(k) is not None})
    voice = [a for a in atts if a.get("type") == "audio" or a.get("isVoiceNote") or str(a.get("mimeType", "")).startswith("audio")]
    return {"source": "beeper", "network": c.get("network"), "accountID": m.get("accountID") or c.get("accountID"),
            "chatID": c.get("id"), "chatName": c.get("title"), "chatType": c.get("type"),
            "messageID": m.get("id"), "senderID": m.get("senderID"), "senderName": m.get("senderName"),
            "timestamp": m.get("timestamp"), "type": m.get("type"), "text": m.get("text"),
            "attachments": atts, "audio": voice[0] if voice else None,
            "audioPath": (voice[0].get("srcURL") if voice else None)}

def main():
    st = load(); first = st is None
    if first: st = {"activity": {}, "seen": {}}
    while True:
        try:
            for c in chats():
                cid, act = c["id"], c.get("lastActivity")
                if st["activity"].get(cid) == act: continue
                seen = set(st["seen"].get(cid, []))
                new = []
                for m in sorted(msgs(cid), key=lambda m: int(m.get("sortKey") or 0)):
                    if m["id"] in seen: continue
                    seen.add(m["id"])
                    if m.get("isSender") or m.get("type") in SKIP_TYPES or m.get("isDeleted"): continue
                    new.append(m)
                if first: new = []
                ok = True
                for m in new:
                    p = payload(c, m); res = post(p)
                    log(f"forward chat={cid} msg={m['id']} type={m.get('type')} -> {res}")
                    if not res or not (200 <= res[0] < 300): ok = False
                st["seen"][cid] = list(seen)[-500:]
                if ok: st["activity"][cid] = act
                save(st)
            if first: log("first run: baseline saved, nothing forwarded"); first = False
        except Exception as e:
            log(f"error: {type(e).__name__}: {e}")
        time.sleep(POLL)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        print(post({"source": "beeper", "network": "test", "accountID": "test", "chatID": "test", "chatName": "Watcher test",
                    "messageID": "test-1", "senderName": "Watcher test", "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "type": "TEXT", "text": "TEST from watcher, not urgent, ignore", "attachments": [], "audio": None, "audioPath": None}))
    else: main()
