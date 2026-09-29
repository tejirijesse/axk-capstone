# AXK Network — Five-Year Seed Dataset (Sep 2021 → Sep 2026)

Synthetic but internally consistent operating history for the AXK Frappe site.
Every record references real records upstream; every Verification Event is hash-chained
to the previous event on its lot; every settled order has a completion time you can
put on a chart.

| DocType | Records | What it is |
|---|---|---|
| Cooperative | 42 | Rwandan cooperatives across 17 districts, each tied to a corridor |
| Harvest Record | 3,400 | Farmer-level intake (member no., plot, kg, moisture, season) |
| Lot | 646 | 1–9 harvest records aggregated, graded, priced, hashed, anchored |
| Verification Event | 5,258 | 4–10 events per lot, SHA-256 hash chain from cooperative intake to buyer receipt |
| AXK Order | 549 | Cross-border and Kigali sales with FX, settlement channel, completion time, trust scores |
| Escrow Contract | 176 | Xahau (and a few Stellar testnet) escrows with fund/release/refund tx hashes |

Growth ramps 2021 → 2025 (paper ledger years → AXK app years). Anchoring switches
from `offchain` to `xahau` on 2024-06-01. Escrow settlement appears in 2024 and
becomes the majority channel by 2026 — which is the story the capstone dashboard
should be able to tell from this data alone.

## Files

```
data/
  cooperative.csv / .json
  harvest_record.csv / .json
  lot.csv / .json
  verification_event.csv / .json
  axk_order.csv / .json
  escrow_contract.csv / .json
  SUMMARY.json                 counts, per-year volumes, status mix, mean completion hours
doctype/harvest_record.json    DocType definition for the missing Harvest Record
generate_axk_seed.py           deterministic generator (seed 20260929) — edit FIELDS to rename columns
import_axk_seed.py             bench importer with FIELD_MAP / DROP overrides
```

## Import — three steps

**1. Install the missing DocType**

Copy `doctype/harvest_record.json` into your app at
`apps/<app>/<app>/<module>/doctype/harvest_record/harvest_record.json`
(set `"module"` inside the file to your module name), create an empty
`harvest_record.py` and `__init__.py` beside it, then:

```bash
bench --site <site> migrate
```

Or, faster for a demo: Desk → DocType → New → import the JSON via *Import* (Custom DocType).

**2. Align field names**

Run a dry run first. It prints every CSV column that does not exist on the target DocType:

```bash
bench --site <site> execute import_axk_seed.run \
  --kwargs '{"path": "/abs/path/axk_seed/data", "dry_run": true}'
```

Fix each mismatch in `FIELD_MAP` (rename) or `DROP` (ignore) in `import_axk_seed.py`.
Link fields (`cooperative`, `lot`, `order`, `escrow_contract`) carry our IDs, so the
target DocTypes should autoname from their ID field (`field:coop_id`, `field:lot_id` …)
or accept explicit names.

**3. Import**

```bash
bench --site <site> execute import_axk_seed.run \
  --kwargs '{"path": "/abs/path/axk_seed/data"}'
```

Idempotent: existing names are skipped. Add `"truncate": true` to wipe the six
DocTypes first, `"limit": 50` for a smoke test, `"only": ["Cooperative","Lot"]` to
import a subset.

If `execute` cannot find the module, run it from `bench --site <site> console`:

```python
exec(open("/abs/path/axk_seed/import_axk_seed.py").read()); run("/abs/path/axk_seed/data")
```

## What the data can prove on screen

- **Transaction completion time** (`AXK Order.completion_time_hours`): mean ≈ 92 h on
  AXK escrow vs ≈ 229 h on other channels vs ≈ 447 h recalled baseline. That is the
  capstone's primary outcome variable, already populated.
- **Trust** (`trust_score_pre` / `trust_score_post`, 1–5): escrow-settled orders show a
  larger post-trade lift.
- **Tamper evidence**: `Verification Event.prev_hash` → `event_hash` chains verify from
  `0000…` genesis for all 646 lots (the generator asserts this). Change one field and
  the chain breaks — good demo moment.
- **Anchoring**: `anchor_chain`, `anchor_tx_hash`, `anchor_ledger_index` on Lot,
  Verification Event and Escrow Contract. Hashes are synthetic; the Stellar rows are
  marked `network = testnet` and can be swapped for real testnet tx hashes once the
  contracts are connected.
- **Corridors**: Rubavu–Goma, Rusizi–Bukavu, Cyanika, Gatuna/Katuna, Kagitumba,
  Rusumo, plus domestic Kigali baseline. Buyers in Goma, Bukavu, Kisoro, Kabale,
  Mbarara, Kampala, Mwanza, Kigali. Currencies CDF, UGX, TZS, RWF, USD with
  year-by-year FX.

## Realism choices (so you can defend them)

- Prices: 2021 base RWF/kg × annual food-inflation index (2022 +21%, 2023 +43% cumulative)
  × seasonal factor (cheapest at harvest, +25% in lean months) × grade (A/B/C).
  Cross-border buyers pay an 8–22% premium over Kigali farmgate.
- Seasons: A (Jan–Mar harvest), B (Jun–Aug), C (marshland, Sep–Oct).
- Moisture tolerances per commodity; lots above tolerance are graded C or rejected;
  rejected lots stop at `quality_grading` with a fail reason.
- Settlement channel mix shifts by year from cash/SWIFT toward MoMo, PAPSS and AXK escrow.
- Escrow notes describe the actual mechanism: Xahau `EscrowCreate` with a
  crypto-condition whose preimage is the `buyer_receipt` event hash; Stellar rows note a
  Soroban contract released on an oracle signature.

## Regenerating

```bash
python3 generate_axk_seed.py       # stdlib only, ~2 s
```

Edit `FIELDS` at the top to rename columns, `YEAR_WEIGHT` to change the growth curve,
`N_HARVEST` for volume, `SEED` for a different but equally consistent history.
