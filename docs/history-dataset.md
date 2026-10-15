# The optional history dataset

The lower half of `/chain` — the five-year history charts and the hash-chain explorer — reads a **synthetic**
dataset: 646 lots, 5,258 verification events, 549 orders and 176 escrows generated to show what the system
records over time. It is not real trade data and not research evidence; every row is tagged
`axk_synthetic_seed = 1` and every screen that shows it says so.

## Why it is optional

The dataset is stored in DocTypes (`Lot`, `Verification Event`, `AXK Order`, `Escrow Contract`) that belong to
AXK Network's platform app, which is not open source. Everything else in this project — all six trade screens,
`/trace`, and the live Stellar sections of `/chain` — runs on a plain Frappe site without it.

When the DocTypes are missing, the explorer's history sections say so and the rest of the page works normally.

## If you have the platform app

```bash
make seed         # import axk_seed/data into the site
make seed-purge   # remove only the synthetic rows
```

## Help wanted

Roadmap item **PUB-4** moves this dataset into `axk_capstone`'s own DocTypes so anyone can load it on a plain
Frappe site. The generator (`axk_seed/generate_axk_seed.py`) and the importer
(`axk_seed/import_to_axk_network.py`) are already in this repository; the work is defining the DocTypes and
pointing the importer and `frappe_app/axk_capstone/axk_capstone/api.py` at them.
