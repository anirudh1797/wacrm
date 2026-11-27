# Trade-data → CRM sync

`sync_trade_enrichment.py` mirrors Eximpedia lead data from the Supabase
`trade` schema into the CRM (`public` schema). Idempotent — safe to run
repeatedly.

Per run it:

1. Creates CRM contacts for new `trade.v_leads` companies
   (dedupe key: phone = `NA-<company_id>`).
2. Ensures tags + links: `buyer`/`seller`, `ds:<dataset>`,
   `ct:<country>` (lane-inferred when missing), `st:<state>`
   (address/port-derived, India only).
3. Writes detail + product notes for **new** contacts.
4. Refreshes **Activity** notes for all contacts from current
   `trade.shipments` (deletes stale `Activity: *` notes first).
5. Creates deals for new contacts in the matching product pipeline
   (creates the pipeline + stages if missing).

## Setup

```bash
cp scripts/.env.sync.example scripts/.env.sync   # fill in values
chmod 600 scripts/.env.sync
python3 scripts/sync_trade_enrichment.py          # stdlib only
```

## Scheduling (Hermes cron)

Wrapper lives at `~/.hermes/profiles/deep/scripts/wacrm-trade-sync.sh`:

```bash
#!/bin/bash
exec /usr/bin/env python3 <abs-path>/scripts/sync_trade_enrichment.py
```

Created with:

```bash
hermes cron create "every day at 7am" --name wacrm-trade-sync \
  --no-agent --script wacrm-trade-sync.sh --deliver origin
```

Manage: `hermes cron list` / `hermes cron runs` / `hermes cron pause wacrm-trade-sync`.
