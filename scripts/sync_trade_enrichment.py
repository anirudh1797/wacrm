#!/usr/bin/env python3
"""Sync trade-schema lead data into the wacrm CRM (idempotent).

Run:  python3 scripts/sync_trade_enrichment.py
Env:  reads SUPABASE_URL / SUPABASE_SECRET_KEY from scripts/.env.sync
      (or the process environment).

What it does, in order:
  1. Pulls trade.v_leads; creates CRM contacts for any company_id not
     yet present (dedupe key: phone = "NA-<company_id>").
  2. Ensures tags exist and are linked: buyer/seller, ds:<dataset>,
     ct:<country> (lane-inferred when missing), st:<state> when
     derivable from address/port.
  3. Writes the per-contact details note (role, HS codes, lane, value,
     address) and Products note for NEW contacts only.
  4. Refreshes Activity notes for ALL contacts: deletes existing
     "Activity: ..." notes and re-inserts from current shipments data.
"""
import json, os, re, sys, urllib.request, urllib.error
from collections import defaultdict
from datetime import date

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

HS4 = {"0904": "Pepper", "0906": "Cinnamon", "0907": "Cloves",
       "0908": "Nutmeg, mace & cardamoms",
       "0909": "Spice seeds (cumin, coriander, anise…)",
       "0910": "Turmeric, ginger & other spices", "1101": "Wheat / meslin flour",
       "2103": "Sauces & seasonings", "2104": "Soups, broths & preparations",
       "5109": "Yarn (wool / fine animal hair)", "7404": "Copper waste & scrap"}

STATES = ["ANDHRA PRADESH","ARUNACHAL PRADESH","ASSAM","BIHAR","CHHATTISGARH","GOA",
          "GUJARAT","HARYANA","HIMACHAL PRADESH","JHARKHAND","KARNATAKA","KERALA",
          "MADHYA PRADESH","MAHARASHTRA","MANIPUR","MEGHALAYA","MIZORAM","NAGALAND",
          "ODISHA","PUNJAB","RAJASTHAN","SIKKIM","TAMIL NADU","TELANGANA","TRIPURA",
          "UTTAR PRADESH","UTTARAKHAND","WEST BENGAL","DELHI","PUDUCHERRY",
          "CHANDIGARH","JAMMU AND KASHMIR","LADAKH"]
ALIAS = {"TAMILNADU":"TAMIL NADU","GUJRAT":"GUJARAT","ORISSA":"ODISHA",
         "UTTARANCHAL":"UTTARAKHAND","PONDICHERRY":"PUDUCHERRY","NEW DELHI":"DELHI",
         "BANGALORE":"KARNATAKA","BENGALURU":"KARNATAKA","MUMBAI":"MAHARASHTRA",
         "CHENNAI":"TAMIL NADU","KOLKATA":"WEST BENGAL","HYDERABAD":"TELANGANA",
         "AHMEDABAD":"GUJARAT","SURAT":"GUJARAT","RAJKOT":"GUJARAT",
         "COIMBATORE":"TAMIL NADU","MADURAI":"TAMIL NADU","KOCHI":"KERALA",
         "ERODE":"TAMIL NADU","SALEM":"TAMIL NADU","TUTICORIN":"TAMIL NADU",
         "PUNE":"MAHARASHTRA","NAGPUR":"MAHARASHTRA","LUDHIANA":"PUNJAB",
         "KANPUR":"UTTAR PRADESH","NOIDA":"UTTAR PRADESH","GURUGRAM":"HARYANA",
         "GURGAON":"HARYANA","JAIPUR":"RAJASTHAN","INDORE":"MADHYA PRADESH",
         "VISAKHAPATNAM":"ANDHRA PRADESH","GUWAHATI":"ASSAM","JAMNAGAR":"GUJARAT",
         "GANDHIDHAM":"GUJARAT","MUNDRA":"GUJARAT","VADODARA":"GUJARAT",
         "BARODA":"GUJARAT","MEHSANA":"GUJARAT","UNJHA":"GUJARAT"}
STATE_PAT = re.compile(r"\b(" + "|".join(map(re.escape, list(ALIAS) + STATES)) + r")\b")
PORTS = {"MUNDRA":"GUJARAT","HAZIRA":"GUJARAT","KANDLA":"GUJARAT","PIPAVAV":"GUJARAT",
         "NHAVA SHEVA":"MAHARASHTRA","JNPT":"MAHARASHTRA","MUMBAI":"MAHARASHTRA",
         "CHENNAI":"TAMIL NADU","TUTICORIN":"TAMIL NADU","KATTUPALLI":"TAMIL NADU",
         "ENNORE":"TAMIL NADU","COCHIN":"KERALA","VISAKHAPATNAM":"ANDHRA PRADESH",
         "KOLKATA":"WEST BENGAL","HALDIA":"WEST BENGAL","MANGALORE":"KARNATAKA",
         "PARADIP":"ODISHA","KRISHNAPATNAM":"ANDHRA PRADESH","TUGHLAKABAD":"DELHI",
         "DADRI":"UTTAR PRADESH","LUDHIANA":"PUNJAB"}
DS_TO_PIPE = {"7404-copper-india-import-us-germany":"Copper Scrap",
              "turmeric-india-export":"Turmeric",
              "spice-india-export-2026":"Spices (General)",
              "wheat-floor-india2usa":"Wheat Flour",
              "hotpod-buyer-india-210390":"Hotpod (Sauces & Soups)",
              "hotpod-base-210410":"Hotpod (Sauces & Soups)",
              "supplier-210390":"Hotpod (Sauces & Soups)",
              "supplier-210410":"Hotpod (Sauces & Soups)"}
PIPE_STAGES = [("New","#3b82f6"),("Contacted","#a855f7"),("Qualified","#eab308"),
               ("Negotiation","#f97316"),("Won","#22c55e"),("Lost","#ef4444")]


def req(method, path, body=None, schema=None, prefer=None):
    h = {"apikey": KEY, "Authorization": "Bearer " + KEY,
         "Content-Type": "application/json"}
    if schema:
        h["Content-Profile" if method in ("POST", "PATCH") else "Accept-Profile"] = schema
    if prefer:
        h["Prefer"] = prefer
    r = urllib.request.Request(BASE + path,
                               data=json.dumps(body).encode() if body is not None else None,
                               headers=h, method=method)
    try:
        resp = urllib.request.urlopen(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{method} {path} -> {e.code}: {e.read().decode()[:300]}")
    t = resp.read().decode()
    return json.loads(t) if t else None


def paged(table, select, schema=None, page=1000, extra=""):
    out, off = [], 0
    while True:
        b = req("GET", f"{table}?select={select}&limit={page}&offset={off}{extra}", schema=schema)
        out += b
        if len(b) < page:
            return out
        off += page


def find_state(addr):
    if not addr:
        return None
    m = STATE_PAT.findall(addr.upper())
    return ALIAS.get(m[-1], m[-1]) if m else None


def port_state(p):
    if not p:
        return None
    p = p.upper()
    for k, v in PORTS.items():
        if k in p:
            return v
    return None


def main():
    # ---- 1. leads -------------------------------------------------------
    leads = paged("v_leads", "*", schema="trade", extra="&order=company_id")
    seen = {}
    for l in leads:
        s = seen.setdefault(l["company_id"], l)
        if s is not l:
            s.setdefault("_extra_datasets", set()).add(l["dataset"])
    uniq = list(seen.values())

    existing = paged("contacts", "id,phone", extra="&phone=like.NA-*")
    cid = {c["phone"]: c["id"] for c in existing}
    new_leads = [l for l in uniq if f"NA-{l['company_id']}" not in cid]

    if new_leads:
        rows = [{"user_id": UID, "account_id": ACC, "phone": f"NA-{l['company_id']}",
                 "name": l["name"], "company": l["name"]} for l in new_leads]
        for i in range(0, len(rows), 500):
            for c in req("POST", "contacts?select=id,phone", rows[i:i+500],
                         prefer="return=representation"):
                cid[c["phone"]] = c["id"]
    print(f"contacts: {len(uniq)} leads, {len(new_leads)} new inserted")

    # ---- 2. tags ---------------------------------------------------------
    tag_id = {t["name"]: t["id"] for t in paged("tags", "id,name")}

    def country_of(l):
        c = (l.get("country") or "").strip()
        if c and c != "UNKNOWN":
            return c
        if l["role"] == "buyer" and l.get("destination_countries"):
            return l["destination_countries"][0].strip().upper()
        if l["role"] == "seller" and l.get("origin_countries"):
            return l["origin_countries"][0].strip().upper()
        return None

    wanted = {"buyer", "seller"}
    wanted |= {f"ds:{d}" for l in uniq for d in ({l["dataset"]} | l.get("_extra_datasets", set()))}
    wanted |= {f"ct:{country_of(l)}" for l in uniq if country_of(l)}
    state_of = {}
    for l in uniq:
        st = find_state(l.get("address")) if (l.get("country") or "").strip() == "INDIA" else None
        state_of[l["company_id"]] = st
        if st:
            wanted.add(f"st:{st}")
    missing = [{"user_id": UID, "account_id": ACC, "name": w,
                "color": "#14b8a6" if w.startswith("ct:") else
                         "#f59e0b" if w.startswith("st:") else
                         "#a855f7" if w.startswith("ds:") else
                         "#22c55e" if w == "buyer" else "#3b82f6"}
               for w in sorted(wanted) if w not in tag_id]
    if missing:
        for t in req("POST", "tags?select=id,name", missing, prefer="return=representation"):
            tag_id[t["name"]] = t["id"]

    # existing links to avoid dupes
    cur_links = paged("contact_tags", "contact_id,tag_id")
    have = {(x["contact_id"], x["tag_id"]) for x in cur_links}
    links = []
    for l in uniq:
        c = cid[f"NA-{l['company_id']}"]
        cand = [tag_id[l["role"]]]
        cand += [tag_id[f"ds:{d}"] for d in ({l["dataset"]} | l.get("_extra_datasets", set()))]
        cy = country_of(l)
        if cy:
            cand.append(tag_id[f"ct:{cy}"])
        if state_of[l["company_id"]]:
            cand.append(tag_id[f"st:{state_of[l['company_id']]}"])
        for t in cand:
            if (c, t) not in have:
                links.append({"contact_id": c, "tag_id": t})
                have.add((c, t))
    for i in range(0, len(links), 1000):
        req("POST", "contact_tags", links[i:i+1000])
    print(f"tags: {len(tag_id)} total, {len(links)} new links")

    # ---- 3. notes for NEW contacts only ---------------------------------
    notes = []
    for l in new_leads:
        c = cid[f"NA-{l['company_id']}"]
        notes.append({"contact_id": c, "user_id": UID, "account_id": ACC,
                      "note_text": (f"Role: {l['role']} | Country: {country_of(l) or '—'} | "
                                    f"Dataset: {l['dataset']}\n"
                                    f"HS codes: {', '.join(l.get('hs_codes') or [])} | "
                                    f"Lane: {', '.join(l.get('origin_countries') or [])} → "
                                    f"{', '.join(l.get('destination_countries') or [])}\n"
                                    f"Total trade value: ${l.get('total_value') or 0:,.2f}\n"
                                    f"Address: {l.get('address') or '—'}")})
        prods = [f"{HS4.get(h[:4], 'HS ' + h[:4])} (HS {h})" for h in (l.get("hs_codes") or [])[:5]]
        if prods:
            notes.append({"contact_id": c, "user_id": UID, "account_id": ACC,
                          "note_text": "Products: " + " · ".join(prods)})
    for i in range(0, len(notes), 500):
        req("POST", "contact_notes", notes[i:i+500])
    print(f"notes: {len(notes)} detail/product notes for new contacts")

    # ---- 4. Activity notes refresh --------------------------------------
    ship = paged("shipments", "shipper_id,consignee_id,notify_party_id,shipment_date",
                 schema="trade")
    act = defaultdict(lambda: {"n": 0, "first": None, "last": None})
    for s in ship:
        for f in ("shipper_id", "consignee_id", "notify_party_id"):
            k = s.get(f)
            if not k:
                continue
            a = act[k]
            a["n"] += 1
            d = s.get("shipment_date")
            if d:
                a["first"] = min(a["first"], d) if a["first"] else d
                a["last"] = max(a["last"], d) if a["last"] else d

    # delete old Activity notes (only for our account, only that prefix)
    old = paged("contact_notes", "id", extra=f"&account_id=eq.{ACC}&note_text=like.Activity:*")
    for i in range(0, len(old), 500):
        ids = ",".join(x["id"] for x in old[i:i+500])
        req("DELETE", f"contact_notes?id=in.({ids})")

    anotes = []
    for l in uniq:
        a = act.get(l["company_id"])
        if not a or not a["first"]:
            continue
        f0 = date.fromisoformat(a["first"]); t0 = date.fromisoformat(a["last"])
        span = max((t0 - f0).days / 30.44, 0.5)
        freq = a["n"] / span
        ft = f"{freq:.1f}/month" if freq < 30 else f"{freq * 7:.0f}/week"
        anotes.append({"contact_id": cid[f"NA-{l['company_id']}"], "user_id": UID,
                       "account_id": ACC,
                       "note_text": f"Activity: {a['n']} shipments | {a['first']} → {a['last']} (~{ft})"})
    for i in range(0, len(anotes), 500):
        req("POST", "contact_notes", anotes[i:i+500])
    print(f"activity: refreshed {len(anotes)} notes (deleted {len(old)} stale)")

    # ---- 5. deals for NEW contacts --------------------------------------
    if new_leads:
        pipes = {p["name"]: p["id"] for p in paged("pipelines", "id,name")}
        new_stage = {}
        for pname in set(DS_TO_PIPE.values()):
            if pname not in pipes:
                p = req("POST", "pipelines?select=id",
                        [{"user_id": UID, "account_id": ACC, "name": pname}],
                        prefer="return=representation")[0]
                pipes[pname] = p["id"]
                req("POST", "pipeline_stages",
                    [{"pipeline_id": p["id"], "name": nm, "position": i, "color": c}
                     for i, (nm, c) in enumerate(PIPE_STAGES)])
            st = req("GET", f"pipeline_stages?pipeline_id=eq.{pipes[pname]}&name=eq.New&select=id")
            new_stage[pname] = st[0]["id"]
        deals = [{"user_id": UID, "account_id": ACC,
                  "pipeline_id": pipes[DS_TO_PIPE[l["dataset"]]],
                  "stage_id": new_stage[DS_TO_PIPE[l["dataset"]]],
                  "contact_id": cid[f"NA-{l['company_id']}"], "title": l["name"],
                  "value": round(l.get("total_value") or 0, 2), "currency": "USD",
                  "notes": f"{l['role']} · {l['dataset']}"}
                 for l in new_leads if l["dataset"] in DS_TO_PIPE]
        for i in range(0, len(deals), 500):
            req("POST", "deals", deals[i:i+500])
        print(f"deals: {len(deals)} created for new contacts")

    print("sync complete")


if __name__ == "__main__":
    main()
