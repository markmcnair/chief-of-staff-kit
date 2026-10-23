#!/usr/bin/env python3
"""Minimal Beeper Desktop API CLI (stdlib only). 
Token: env BEEPER_TOKEN. Base URL: env BEEPER_URL (default http://localhost:23373).
Sending requires --approved (only pass it after the owner explicitly approves the exact text)."""
import argparse, json, os, sys, urllib.parse, urllib.request, urllib.error

BASE = os.environ.get("BEEPER_URL", "http://localhost:23373").rstrip("/")

def call(method, path, params=None, body=None):
    tok = os.environ.get("BEEPER_TOKEN")
    if not tok:
        sys.exit("BEEPER_TOKEN not set")
    url = BASE + path
    if params:
        q = [(k, v) for k, v in params.items() if v is not None]
        url += "?" + urllib.parse.urlencode(q, doseq=True)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code}: {e.read().decode(errors='replace')[:500]}")

def out(x): print(json.dumps(x, indent=2, ensure_ascii=False))

def main():
    p = argparse.ArgumentParser(description=__doc__)
    s = p.add_subparsers(dest="cmd", required=True)
    s.add_parser("info")
    s.add_parser("accounts")
    c = s.add_parser("chats"); c.add_argument("--account", action="append"); c.add_argument("--limit", type=int, default=25); c.add_argument("--cursor")
    cs = s.add_parser("search-chats"); cs.add_argument("query"); cs.add_argument("--account", action="append"); cs.add_argument("--unread", action="store_true"); cs.add_argument("--limit", type=int, default=25)
    m = s.add_parser("messages"); m.add_argument("chat_id"); m.add_argument("--cursor"); m.add_argument("--direction", choices=["before", "after"])
    ms = s.add_parser("search-messages"); ms.add_argument("query"); ms.add_argument("--chat", action="append"); ms.add_argument("--limit", type=int, default=20)
    sd = s.add_parser("send"); sd.add_argument("chat_id"); sd.add_argument("text"); sd.add_argument("--reply-to"); sd.add_argument("--approved", action="store_true", help="REQUIRED: the owner has approved this exact message")
    a = p.parse_args()

    if a.cmd == "info": out(call("GET", "/v1/info"))
    elif a.cmd == "accounts": out(call("GET", "/v1/accounts"))
    elif a.cmd == "chats": out(call("GET", "/v1/chats", {"accountIDs": a.account, "limit": a.limit, "cursor": a.cursor}))
    elif a.cmd == "search-chats": out(call("GET", "/v1/chats/search", {"query": a.query, "accountIDs": a.account, "unreadOnly": "true" if a.unread else None, "limit": a.limit}))
    elif a.cmd == "messages": out(call("GET", f"/v1/chats/{urllib.parse.quote(a.chat_id, safe='')}/messages", {"cursor": a.cursor, "direction": a.direction}))
    elif a.cmd == "search-messages": out(call("GET", "/v1/messages/search", {"query": a.query, "chatIDs": a.chat, "limit": a.limit}))
    elif a.cmd == "send":
        if not a.approved:
            print(f"REFUSED: not sending without --approved.\nWould send to {a.chat_id}:\n---\n{a.text}\n---", file=sys.stderr); sys.exit(2)
        body = {"text": a.text}
        if a.reply_to: body["replyToMessageID"] = a.reply_to
        out(call("POST", f"/v1/chats/{urllib.parse.quote(a.chat_id, safe='')}/messages", body=body))

if __name__ == "__main__": main()
