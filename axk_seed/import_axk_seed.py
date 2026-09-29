"""
AXK seed importer for Frappe / ERPNext.

Usage (from your bench directory):

    bench --site <your-site> execute axk_seed.import_axk_seed.run --kwargs '{"path": "/abs/path/to/axk_seed/data", "dry_run": true}'
    bench --site <your-site> execute axk_seed.import_axk_seed.run --kwargs '{"path": "/abs/path/to/axk_seed/data"}'

Or drop this file into an app (e.g. apps/axk/axk/seed/import_axk_seed.py) and call
    bench --site <site> execute axk.seed.import_axk_seed.run --kwargs '{"path": "..."}'

Or paste into `bench --site <site> console`:
    >>> exec(open("/abs/path/import_axk_seed.py").read()); run("/abs/path/axk_seed/data")

What it does
- Imports in dependency order: Cooperative → Harvest Record → Lot → Verification Event → AXK Order → Escrow Contract
- Renames CSV columns through FIELD_MAP (csv_column → doctype_fieldname). Edit FIELD_MAP to match your DocTypes.
- Sets each document's `name` from the ID column (works when autoname is "prompt", "field:<id_field>", or when
  you set NAME_FROM_ID = True and the DocType allows explicit names).
- Skips rows that already exist (idempotent re-runs). Use truncate=True to wipe the six DocTypes first.
- Never touches the chain. `anchor_tx_hash` etc. are stored as plain data.
"""

import csv, os
import frappe

ORDER = [
    ("Cooperative", "cooperative.csv", "coop_id"),
    ("Harvest Record", "harvest_record.csv", "harvest_id"),
    ("Lot", "lot.csv", "lot_id"),
    ("Verification Event", "verification_event.csv", "event_id"),
    ("AXK Order", "axk_order.csv", "order_id"),
    ("Escrow Contract", "escrow_contract.csv", "escrow_id"),
]

# csv column  ->  DocType fieldname. Identity mapping by default; override only what differs.
# Example: FIELD_MAP["Lot"] = {"quantity_kg": "net_weight_kg", "grade": "quality_grade"}
FIELD_MAP = {
    "Cooperative": {},
    "Harvest Record": {},
    "Lot": {},
    "Verification Event": {},
    "AXK Order": {},
    "Escrow Contract": {},
}

# Columns in the CSV that your DocType does NOT have and should be dropped instead of failing.
DROP = {
    "Cooperative": set(),
    "Harvest Record": set(),
    "Lot": set(),
    "Verification Event": set(),
    "AXK Order": set(),
    "Escrow Contract": set(),
}

NAME_FROM_ID = True          # set doc.name = ID column
LINK_BY_NAME = True          # Link fields carry the target's name (our IDs); nothing to translate
BATCH_COMMIT = 250


def _coerce(meta, fieldname, value):
    """Cast CSV strings to what the DocType expects; blanks become None."""
    if value is None or value == "":
        return None
    df = meta.get_field(fieldname)
    if not df:
        return value
    ft = df.fieldtype
    if ft in ("Int", "Check"):
        return int(float(value))
    if ft in ("Float", "Currency", "Percent"):
        return float(value)
    if ft in ("Date", "Datetime", "Data", "Small Text", "Text", "Long Text", "Link", "Select", "Code", "Text Editor"):
        return value
    return value


def _existing_fields(doctype):
    meta = frappe.get_meta(doctype)
    return {df.fieldname for df in meta.fields} | {"name"}


def run(path, dry_run=False, truncate=False, only=None, limit=None):
    """
    path:      folder containing the six CSV files
    dry_run:   validate + count only, no inserts
    truncate:  delete existing records of the six DocTypes first (reverse dependency order)
    only:      list of DocTypes to import (still in dependency order)
    limit:     max rows per DocType (quick smoke test)
    """
    only = set(only) if only else None
    if truncate and not dry_run:
        for dt, _, _ in reversed(ORDER):
            if only and dt not in only:
                continue
            frappe.db.delete(dt)
            frappe.db.commit()
            print(f"truncated {dt}")

    report = {}
    for dt, fname, id_col in ORDER:
        if only and dt not in only:
            continue
        fpath = os.path.join(path, fname)
        if not frappe.db.exists("DocType", dt):
            print(f"!! DocType '{dt}' is missing on this site — skipped ({fname}). "
                  f"For Harvest Record, install doctype/harvest_record.json first.")
            report[dt] = "missing doctype"
            continue
        if not os.path.exists(fpath):
            print(f"!! {fpath} not found — skipped")
            report[dt] = "missing file"
            continue

        meta = frappe.get_meta(dt)
        fields = _existing_fields(dt)
        fmap = FIELD_MAP.get(dt, {})
        drop = DROP.get(dt, set())
        inserted = skipped = unknown_cols = 0
        unknown = set()

        with open(fpath, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        if limit:
            rows = rows[:limit]

        for i, row in enumerate(rows, 1):
            doc = {"doctype": dt}
            for col, val in row.items():
                if col in drop:
                    continue
                fn = fmap.get(col, col)
                if fn not in fields:
                    unknown.add(col)
                    continue
                doc[fn] = _coerce(meta, fn, val)
            name = row[id_col]
            if NAME_FROM_ID:
                doc["name"] = name
            if frappe.db.exists(dt, name):
                skipped += 1
                continue
            if dry_run:
                inserted += 1
                continue
            d = frappe.get_doc(doc)
            d.flags.ignore_permissions = True
            d.flags.ignore_mandatory = False
            try:
                d.insert(ignore_if_duplicate=True)
                inserted += 1
            except Exception as e:
                print(f"   row {i} ({name}) failed: {e}")
            if i % BATCH_COMMIT == 0:
                frappe.db.commit()
        if not dry_run:
            frappe.db.commit()
        if unknown:
            print(f"   {dt}: CSV columns not on DocType (ignored): {sorted(unknown)}  → add to FIELD_MAP or DROP")
        print(f"{'[dry-run] ' if dry_run else ''}{dt}: {inserted} inserted, {skipped} already existed, {len(rows)} in file")
        report[dt] = {"inserted": inserted, "skipped": skipped, "unknown_columns": sorted(unknown)}
    return report
