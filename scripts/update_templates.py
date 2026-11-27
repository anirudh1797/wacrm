#!/usr/bin/env python3
import json, os, urllib.request

BASE = os.environ["SUPABASE_URL"].rstrip("/") + "/rest/v1/"
KEY = os.environ["SUPABASE_SECRET_KEY"]

templates = [
  {"name":"copper-buyer-first-contact",
   "body":"Subject: Copper scrap volumes from {{country}} – {{trade_value}} deal\n\nHi {{company}},\n\nI track Indian exporters to global scrap markets. Your name appears on a {{hs_code}} shipment to Vietnam last month (≈{{trade_value}} FOB).\n\nAre you seeking new buyers for regular loads? I can match you with vetted recyclers.\n\nBest,\n{{sender_name}}\n{{sender_company}}"},
  {"name":"turmeric-supplier-first",
   "body":"Subject: Turmeric sourcing – {{country}} volumes available\n\nHi {{company}},\n\nYour listings show turmeric exports to Dubai/Oman in Q3. The market is tight right now; I have pre-approved buyers for 500kg+ lots.\n\nWould a 10-min intro call help align supply?\n\nRegards,\n{{sender_name}}"},
]

for t in templates:
    req = urllib.request.Request(f"{BASE}message_templates?name=eq.{t['name']}",
        json.dumps({"body_text":t["body"]}).encode(),
        headers={"apikey":KEY,"Authorization":f"Bearer {KEY}","Content-Type":"application/json"},
        method="PATCH")
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        print(t["name"], "→ updated (204)")
    except urllib.error.HTTPError as e:
        print(t["name"], "→ ERROR", e.code, e.read().decode()[:200])