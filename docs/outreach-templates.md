---
contentType: Reference
title: Outreach templates for CRM leads
category: Messaging
---

# Outreach templates for CRM leads

Templates use these variables (available via the Data panel when composing):

| Variable | Source column |
| --- | --- |
| `{{company}}` | Contact company name |
| `{{product}}` | Trade lane product from `deals.product` |
| `{{country}}` | `contacts.country_name` |
| `{{hs_code}}` | Deal hs_code |
| `{{trade_value}}` | Formatted deal value |
| `{{sender_name}}` | Your name from `accounts.rep_name` |
| `{{sender_company}}` | Your business name from env `ACCOUNT_NAME` |

## Email templates

### 1. Buyer first touch (copper scrap exporters)

```
Subject: Copper scrap volumes from {{country}} – {{trade_value}} deal

Hi {{company}},

I track Indian exporters to global scrap markets. Your name appears on a {{hs_code}} shipment to Vietnam last month (≈{{trade_value}} FOB).

Are you seeking new buyers for regular loads? I can match you with vetted recyclers.

Best,
{{sender_name}}
{{sender_company}}
```

### 2. Supplier first touch (turmeric exporters)

```
Subject: Turmeric sourcing – {{country}} volumes available

Hi {{company}},

Your listings show turmeric exports to Dubai/Oman in Q3. The market is tight right now; I have pre-approved buyers for 500kg+ lots.

Would a 10-min intro call help align supply?

Regards,
{{sender_name}}
{{sender_company}}
```

### 3. Follow-up (no reply after 3 days)

```
Subject: Re: {{company}} copper/turmeric volumes

Hi {{company}},

Quick check – still exploring buyers for {{product}} exports?

If timing shifted, let me know and I’ll pause outreach.

{{sender_name}}
```

## WhatsApp templates (24h commerce session)

### 4. WhatsApp text (short, under 120 chars)

```
{{company}} – saw {{product}} export {{trade_value}} to VN last month. Buyers ready next 30 days. Reply YES for 3 contacts.
```

### 5. Activity open (after a new shipment lands)

```
Congrats on the {{trade_value}} {{product}} load to {{country}} this week! I track similar volumes – would you like introductions to regular buyers before the next cycle?
```

---

## How to use in the CRM

5. In a contact’s detail view, open the **Messages** tab, pick the template, then swap variables with the Data panel values.
6. Choose **Category**: `Marketing` (promotional), `Utility` (transactional), or `Authentication` (OTP). The 5 templates below map as:
   - `copper-buyer-first-contact` → Marketing
   - `turmeric-supplier-first` → Utility  
   - Follow-up → Marketing
   - WhatsApp text → Utility
   - Activity open → Utility

Templates saved as **draft** stay local – they appear in the compose window but require Meta Business Manager approval before WhatsApp sending. Use them immediately for manual outreach and batch emails; submit to Meta later for automated flows.