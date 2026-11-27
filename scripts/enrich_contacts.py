#!/usr/bin/env python3
"""Enrich CRM contacts with phone/email found on the public web.

Priority order: highest deal value first, placeholder-phone contacts only.
For each company: DuckDuckGo HTML search -> fetch top result pages ->
regex-extract Indian phone numbers and emails -> write back to the CRM
(phone, email, and a provenance note). Tags the contact `enriched`.

Idempotent: skips contacts already tagged `enriched` or having a real phone.

Usage:
  python3 scripts/enrich_contacts.py [--limit 25] [--delay 2.5] [--dry-run]

Env: same scripts/.env.sync as sync_trade_enrichment.py (or process env).
"""
import argparse, html, json, os, re, sys, time, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(HERE, ".env.sync")
if os.path.exists(ENV_FILE):
    for line in open(ENV_FILE):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

BASE = os.environ["SUPABASE_URL"].rstrip("/") + "/rest/v1/"
KEY = os.environ["SUPABASE_SECRET_KEY"]
UID = os.environ["CRM_USER_ID"]
ACC = os.environ["CRM_ACCOUNT_ID"]

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0 Safari/537.36"}

PHONE_RE = re.compile(r"(?:\+91[\-\s]?|0091[\-\s]?|0)?([6-9]\d{4}[\-\s]?\d{5})")
LANDLINE_RE = re.compile(r"\b(0\d{2,4}[\-\s]?\d{6,8})\b")
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
BAD_EMAIL = re.compile(r"(example\.|sentry|wixpress|@2x|@3x|\.png$|\.jpg$|"
                       r"godaddy|domain|no-?reply|@sentry)", re.I)
JUNK_PHONES = {"1800", "1860"}  # toll-free prefixes kept, but validate length


def sb(method, path, body=None, prefer=None):
    h = {"apikey": KEY, "Authorization": "Bearer " + KEY,
         "Content-Type": "application/json"}
    if prefer:
        h["Prefer"] = prefer
    r = urllib.request.Request(BASE + path,
                               data=json.dumps(body).encode() if body is not None else None,
                               headers=h, method=method)
    resp = urllib.request.urlopen(r)
    t = resp.read().decode()
    return json.loads(t) if t else None


def fetch(url, timeout=15):
    r = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(r, timeout=timeout).read().decode("utf-8", "ignore")


def bing_results(query, n=6):
    # DDG html/lite endpoints serve bot-detection pages to datacenter/CLI
    # clients; Bing's plain-HTML SERP still works with a browser UA.
    url = "https://www.bing.com/search?q=" + urllib.parse.quote(query)
    page = fetch(url)
    links = re.findall(r'<li class="b_algo"[^>]*>.*?<h2[^>]*>\s*<a[^>]*href="([^"]+)"',
                       page, re.S)
    return [html.unescape(l) for l in links][:n]


def clean_phone(p):
    d = re.sub(r"\D", "", p)
    if d.startswith("91") and len(d) == 12:
        d = d[2:]
    if len(d) == 10 and d[0] in "6789":
        return "+91 " + d[:5] + " " + d[5:]
    return None


def extract(text):
    phones, emails = set(), set()
    for m in PHONE_RE.finditer(text):
        p = clean_phone(m.group(1))
        if p:
            phones.add(p)
    for m in LANDLINE_RE.finditer(text):
        d = re.sub(r"\D", "", m.group(1))
        if 10 <= len(d) <= 12:
            phones.add(d)
    for e in EMAIL_RE.findall(text):
        if not BAD_EMAIL.search(e) and len(e) < 60:
            emails.add(e.lower())
    return sorted(phones)[:3], sorted(emails)[:3]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=25)
    ap.add_argument("--delay", type=float, default=2.5)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    # contacts with placeholder phone, joined to deal value, richest first
    enriched_tag = sb("GET", "tags?name=eq.enriched&select=id")
    if enriched_tag:
        et = enriched_tag[0]["id"]
    elif not args.dry_run:
        et = sb("POST", "tags?select=id",
                [{"user_id": UID, "account_id": ACC, "name": "enriched",
                  "color": "#64748b"}], prefer="return=representation")[0]["id"]
    else:
        et = None
    skip = set()
    if et:
        off = 0
        while True:
            b = sb("GET", f"contact_tags?tag_id=eq.{et}&select=contact_id&limit=1000&offset={off}")
            skip |= {x["contact_id"] for x in b}
            if len(b) < 1000:
                break
            off += 1000

    deals = sb("GET", "deals?select=contact_id,value&order=value.desc&limit=10000")
    seen, queue = set(), []
    for d in deals:
        c = d["contact_id"]
        if c in seen or c in skip:
            continue
        seen.add(c)
        queue.append((c, d["value"]))
    contacts = {}
    off = 0
    while True:
        b = sb("GET", f"contacts?select=id,name,phone&phone=like.NA-*&limit=1000&offset={off}")
        for c in b:
            contacts[c["id"]] = c
        if len(b) < 1000:
            break
        off += 1000
    queue = [(c, v) for c, v in queue if c in contacts][:args.limit]
    print(f"enriching {len(queue)} contacts (skipping {len(skip)} already enriched)")

    found = 0
    for c, val in queue:
        name = contacts[c]["name"]
        try:
            results = bing_results(f'"{name}" contact phone email')
            phones, emails, src = [], [], None
            for u in results:
                if any(b in u for b in ("linkedin.com", "facebook.com", "youtube.com")):
                    continue
                try:
                    p, e = extract(fetch(u))
                except Exception:
                    continue
                if p or e:
                    phones, emails, src = p, e, u
                    break
            print(f"  {name[:45]:47s} -> {phones or '-'} {emails or ''}")
            if (phones or emails) and not args.dry_run:
                patch = {}
                if phones:
                    patch["phone"] = phones[0]
                if emails:
                    patch["email"] = emails[0]
                try:
                    sb("PATCH", f"contacts?id=eq.{c}", patch)
                except Exception:
                    if "phone" in patch:  # unique phone collision: keep email
                        sb("PATCH", f"contacts?id=eq.{c}", {k: v for k, v in patch.items() if k != "phone"})
                sb("POST", "contact_notes", [{
                    "contact_id": c, "user_id": UID, "account_id": ACC,
                    "note_text": f"Contact info (auto-research): "
                                 f"phones: {', '.join(phones) or '—'} | "
                                 f"emails: {', '.join(emails) or '—'} | source: {src}"}])
                if et:
                    sb("POST", "contact_tags", [{"contact_id": c, "tag_id": et}])
            if phones or emails:
                found += 1
        except Exception as ex:
            print(f"  {name[:45]:47s} -> ERROR {ex}")
        time.sleep(args.delay)
    print(f"done: {found}/{len(queue)} enriched")


if __name__ == "__main__":
    main()
