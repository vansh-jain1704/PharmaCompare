# Pharmacy partner feed API

How a pharmacy's own system can send PharmaCompare price and stock reports. **No pharmacy is connected today and none is polled.** This is a
receiver: until a partner is given a key and uses it, the pharmacy tables stay empty and the app says "No live pharmacy price or stock feed is
connected". Nothing in it is a live connection to a pharmacy: a report is shown as "reported N hours ago" with the pharmacy and the feed's name.

## Giving a partner access

```
python database/manage_partner_keys.py create --source-key acme_pharmacy --name "Acme Pharmacy feed" --label "main server"
python database/manage_partner_keys.py list
python database/manage_partner_keys.py revoke 3
```

`create` makes the feed (kind `pharmacy_feed`) if it is new and prints the key **once**. Only a SHA-256 hash is stored, so a lost key is replaced
(create a new one, revoke the old), not recovered. Send the key over a safe channel. A revoked key stops working at once.

## The request

`POST /api/feeds/offers` with the header `X-Partner-Key: pck_...` and a JSON body:

```json
{"rows": [{"pharmacy": "Acme Pharmacy", "city": "Davanagere", "medicine_id": 58235, "price": 31.5, "availability": "in_stock",
           "quantity": 12, "observed_at": "2026-10-18 10:30"}],
 "dry_run": false}
```

A product is named by `medicine_id`, or by exact `medicine_name` (add `manufacturer` / `pack_size` if the name is ambiguous). `availability` is
`in_stock`, `limited`, `out_of_stock` or blank; `price` may be blank when only stock is reported. `dry_run: true` validates and stores nothing.

## What is accepted

Exactly what a CSV feed accepts (`app/services/feed_import_service.py`): every row needs a pharmacy, an `observed_at` that is not in the future, one
unambiguous catalogue product, and a price and/or a recognised stock status. A row that fails is returned with its reason and **nothing about it is
stored**; the other rows still go in. Sending the same report twice adds nothing.

```json
{"read": 2, "imported": 1, "duplicates": 0, "pharmacies": 1, "dry_run": false,
 "rejected": [{"row": 2, "reason": "stock status 'plenty' is not recognised (use in_stock, limited, out_of_stock or leave it blank)"}]}
```

## Limits and safety

- A bad, unknown, revoked or missing key all get the same `401`, so the route cannot be used to find out which keys exist.
- At most `PARTNER_FEED_MAX_ROWS` (500) rows and `PARTNER_FEED_MAX_BYTES` (300 000) bytes per request (`400` / `413`), and
  `PARTNER_FEED_REQUESTS_PER_MINUTE` (30) requests per key (`429` with `Retry-After`). The rate window is held in the server process, so it is a
  guard against a runaway client, not a quota that survives a restart or covers several server processes.
- A key can report only into its own feed, and only as real data (`pharmacy_feed`). A body cannot choose another source or mark itself as demo data.
- The key is never written to a log or echoed in a response.

## What a reader sees

Reports appear on the medicine's detail with the pharmacy, city, the age of the report, the feed's name and its price and stock, separately from the
dataset's reference price. Stock older than `OFFER_STOCK_MAX_AGE_HOURS` (48) and a price older than `OFFER_PRICE_MAX_AGE_DAYS` (7) are marked as old.
The About page lists each feed with when its newest report was observed and when data last arrived.

## What this does not do

It does not fetch anything from a pharmacy, does not know a pharmacy's real inventory, and does not make PharmaCompare "real-time": that needs a
partner who sends reports, and reports are only as fresh as the partner's last push. Receiving a request is the whole of the integration.
