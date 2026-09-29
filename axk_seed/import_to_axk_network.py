"""
Import the synthetic AXK seed dataset into a local axk_network (Frappe v15) site.

Differs from the generic import_axk_seed.py in three ways:

1. Maps seed columns onto the real axk_network DocTypes (Lot.lot_reference, Lot.quantity,
   Verification Event.event_ref, Escrow Contract.tx_hash_fund, ...). Seed columns with no
   equivalent are kept as Custom Fields in a "Capstone dataset" section, so nothing the
   capstone dashboard needs (completion time, trust scores, hash chain) is lost.
2. Writes rows with db_insert(), which skips validate/on_submit and every doc_event hook.
   Saving these DocTypes normally anchors to Xahau and runs AI screening; 10k synthetic
   rows must not do either.
3. Tags every row axk_synthetic_seed = 1, so screens and queries can label the data and
   `purge=True` removes exactly what this script added.

The data is synthetic. It exists to populate demo screens. It is not pilot evidence.

Run from the bench directory:
    bench --site axk.localhost execute axk_network.capstone_seed.run \
        --kwargs "{'path': '/abs/path/axk_seed/data'}"
Options: dry_run=True, purge=True, only=['Lot', ...], limit=50
"""

import csv
import os
import re

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

SYNTH = "axk_synthetic_seed"
EXTRA_CURRENCIES = ["RWF", "UGX", "CDF", "TZS"]

# (doctype, csv file, id column, column used as the record's creation timestamp)
ORDER = [
    ("Cooperative", "cooperative.csv", "coop_id", "onboarded_at"),
    ("Harvest Record", "harvest_record.csv", "harvest_id", "intake_date"),
    ("Lot", "lot.csv", "lot_id", "aggregation_date"),
    ("Verification Event", "verification_event.csv", "event_id", "timestamp"),
    ("AXK Order", "axk_order.csv", "order_id", "order_date"),
    ("Escrow Contract", "escrow_contract.csv", "escrow_id", "created_at"),
]

# seed column -> existing DocType field
FIELD_MAP = {
    "Cooperative": {"registration_no": "registration_number", "onboarded_at": "created_at"},
    "Harvest Record": {},
    "Lot": {
        "lot_id": "lot_reference",
        "commodity": "commodity_type",
        "quantity_kg": "quantity",
        "moisture_pct": "moisture_content",
        "unit_price_rwf": "unit_price",
        "content_hash": "document_hash",
        "anchor_tx_hash": "xrpl_tx_hash",
        "anchored_at": "xrpl_anchored_at",
    },
    "Verification Event": {
        "event_id": "event_ref",
        "verifier_name": "actor_name",
        "quantity_kg_measured": "quantity_actor",
        "grade_assigned": "grade_actor",
        "anchor_tx_hash": "xrpl_tx_hash",
        "timestamp": "confirmed_at",
    },
    "AXK Order": {
        "order_id": "order_ref",
        "quantity_kg": "quantity",
        "escrow_contract": "escrow",
    },
    "Escrow Contract": {
        "escrow_id": "escrow_ref",
        "amount_usd": "usd_equivalent",
        "fund_tx_hash": "tx_hash_fund",
        "release_tx_hash": "tx_hash_release",
        "fee_amount": "platform_fee",
    },
}

# Seed columns whose value is translated into an existing Select; the raw value is kept
# in a custom field named seed_<column>.
TRANSLATED = {
    "Lot": {"status"},
    "Verification Event": {"event_type"},
    "AXK Order": {"status"},
    "Escrow Contract": {"status", "release_condition"},
}

LOT_STATUS = {
    "Closed": "Settled", "Rejected": "Flagged", "Delivered": "Delivered", "Listed": "Listed",
    "Reserved": "Sold", "Aggregated": "Registered", "Inspected": "Verified", "In Transit": "In Transit",
}
VE_TYPE = {
    "cooperative_intake": "Harvest Intake", "weighbridge": "Collection", "quality_grading": "Processing",
    "moisture_test": "Processing", "warehouse_receipt": "Collection", "certificate_of_origin": "Transport",
    "phytosanitary_certificate": "Transport", "border_exit": "Transport", "border_entry": "Transport",
    "buyer_receipt": "Delivery", "dispute_inspection": "Delivery",
}
ESCROW_STATUS = {
    "Created": "Pending", "Release Pending": "Locked", "Released": "Released",
    "Refunded": "Cancelled", "Disputed": "Disputed",
}
LINKS = {
    "cooperative": "Cooperative", "lot": "Lot", "order": "AXK Order",
    "escrow_contract": "Escrow Contract", "corridor": "Corridor",
}
# Records still in progress stay as drafts so they can be worked on in the demo.
OPEN_LOT = {"Listed", "Reserved", "Aggregated", "Inspected", "In Transit"}
OPEN_ORDER = {"Confirmed", "In Transit", "Delivered"}


def _fieldtype(col):
    if col in LINKS:
        return "Link"
    if col == "notes" or col.endswith("_reason") or col == "harvest_record_ids":
        return "Small Text"
    if col.endswith("_at") or col in ("dispatch_date",):
        return "Datetime"
    if col.endswith("_date"):
        return "Date"
    if re.search(r"(_count|_year|sequence_no|ledger_index|dispute_flag)$", col):
        return "Int"
    if re.search(r"(_pct|_kg|_ha$|_hours|_tonnes|_rwf|_usd|^gps_|fx_rate|trust_score|amount)", col):
        return "Float"
    return "Data"


def _custom_name(dt, col):
    if col in TRANSLATED.get(dt, ()):
        return f"seed_{col}"
    if col == "timestamp":
        return "event_timestamp"
    return col


def _plan(dt, header):
    """Return {csv column: target fieldname} and the custom fields to create."""
    meta = frappe.get_meta(dt)
    existing = {df.fieldname for df in meta.fields}
    fmap = FIELD_MAP.get(dt, {})
    target, customs = {}, []
    last = "capstone_section"
    for col in header:
        if col in fmap:
            target[col] = fmap[col]
            continue
        if col in existing and col not in TRANSLATED.get(dt, ()):
            target[col] = col
            continue
        name = _custom_name(dt, col)
        target[col] = name
        if name not in existing:
            ft = _fieldtype(col)
            cf = {"fieldname": name, "label": col.replace("_", " ").title(), "fieldtype": ft,
                  "insert_after": last, "read_only": 0}
            if ft == "Link":
                cf["options"] = LINKS[col]
            customs.append(cf)
            last = name
    # translated columns also keep their raw value
    for col in TRANSLATED.get(dt, ()):
        name = f"seed_{col}"
        if name not in existing and not any(c["fieldname"] == name for c in customs):
            customs.append({"fieldname": name, "label": f"Seed {col}", "fieldtype": "Data",
                            "insert_after": last})
            last = name
    return target, customs


def _ensure_schema(dt, header):
    target, customs = _plan(dt, header)
    head = [
        {"fieldname": "capstone_section", "label": "Capstone dataset", "fieldtype": "Section Break",
         "collapsible": 1, "insert_after": frappe.get_meta(dt).fields[-1].fieldname},
        {"fieldname": SYNTH, "label": "Synthetic seed record", "fieldtype": "Check",
         "read_only": 1, "insert_after": "capstone_section", "in_standard_filter": 1},
    ]
    have = {df.fieldname for df in frappe.get_meta(dt).fields}
    todo = [c for c in head if c["fieldname"] not in have] + customs
    if todo:
        create_custom_fields({dt: todo}, update=True)
        frappe.clear_cache(doctype=dt)
    return target


def _extend_currency(dt):
    df = frappe.get_meta(dt).get_field("currency")
    if not df or df.fieldtype != "Select":
        return
    opts = [o for o in (df.options or "").split("\n") if o]
    missing = [c for c in EXTRA_CURRENCIES if c not in opts]
    if missing:
        make_property_setter(dt, "currency", "options", "\n".join(opts + missing), "Text",
                             validate_fields_for_doctype=False)


def _ensure_masters(path):
    coops = list(csv.DictReader(open(os.path.join(path, "cooperative.csv"), encoding="utf-8")))
    orders = list(csv.DictReader(open(os.path.join(path, "axk_order.csv"), encoding="utf-8")))
    lots = list(csv.DictReader(open(os.path.join(path, "lot.csv"), encoding="utf-8")))
    dest = {"RW-DRC": "DR Congo", "RW-UG": "Uganda", "RW-TZ": "Tanzania", "Domestic": "Rwanda"}
    for name in sorted({r["corridor"] for r in coops + orders}):
        if not frappe.db.exists("Corridor", name):
            frappe.get_doc({"doctype": "Corridor", "corridor_name": name, "status": "Active",
                            "origin_country": "Rwanda", "destination_country": dest[name.split(" ")[0]],
                            "anchor_chain": "xahau"}).db_insert()
    for name in sorted({r["commodity"] for r in lots + orders}):
        if not frappe.db.exists("Commodity", name):
            frappe.get_doc({"doctype": "Commodity", "commodity_code": name, "commodity_name": name,
                            "status": "Active"}).db_insert()
    for g in ("A", "B", "C"):
        if not frappe.db.exists("Grade Preference", g):
            frappe.get_doc({"doctype": "Grade Preference", "grade_name": g}).db_insert()
    frappe.db.commit()
    return {r["coop_id"]: r for r in coops}


def _coerce(meta, fieldname, value):
    if value in (None, ""):
        return None
    df = meta.get_field(fieldname)
    ft = df.fieldtype if df else "Data"
    if ft in ("Int", "Check"):
        return int(float(value))
    if ft in ("Float", "Currency", "Percent"):
        return float(value)
    return value


def _derive(dt, row, doc, coops):
    """Fill required / translated fields that have no 1:1 seed column."""
    if dt == "Cooperative":
        doc["country"] = "Rwanda"
        doc["region"] = row["district"]
    elif dt == "Lot":
        coop = coops.get(row["cooperative"], {})
        doc["corridor"] = coop.get("corridor")
        doc["cooperative_name"] = coop.get("cooperative_name")
        doc["unit"] = "kg"
        doc["currency"] = "RWF"
        doc["status"] = LOT_STATUS.get(row["status"], "Registered")
        if row.get("anchor_tx_hash"):
            doc["xrpl_explorer_url"] = None  # synthetic hash: no explorer link
        doc["docstatus"] = 0 if row["status"] in OPEN_LOT else 1
    elif dt == "Verification Event":
        doc["event_type"] = VE_TYPE.get(row["event_type"], "Collection")
        doc["unit"] = "kg"
        if row.get("gps_lat"):
            doc["gps_actor"] = f"{row['gps_lat']},{row['gps_lng']}"
        if row["result"] == "fail":
            doc["status"] = "Flag"
        elif row["anchor_chain"] == "xahau":
            doc["status"] = "XRPL Notarized"
            doc["notarized_at"] = row["timestamp"]
        else:
            doc["status"] = "Two Party Confirmed"
        doc["docstatus"] = 1
    elif dt == "AXK Order":
        s = row["status"]
        doc["status"] = "Settled" if s == "Settled" else ("Escrow Created" if row["escrow_contract"] else "Draft")
        ch = row["settlement_channel"]
        doc["payment_rail"] = ("mobile_money" if ("MoMo" in ch or "Airtel" in ch)
                               else "crypto_direct" if "escrow" in ch else None)
        doc["release_mode"] = "Single Release"
        doc["docstatus"] = 0 if s in OPEN_ORDER else (2 if s == "Cancelled" else 1)
    elif dt == "Escrow Contract":
        doc["status"] = ESCROW_STATUS.get(row["status"], "Pending")
        doc["release_condition"] = "Delivery Confirmed"
        doc["release_mode"] = "Single Release"


def _store_canonical_payloads(path):
    """Keep the exact bytes each event_hash was computed over.

    event_hash = sha256(prev_hash + canonical_payload + evidence_hash). The payload has to be
    stored verbatim: rebuilding it from DocType fields fails for ~4% of events, because Float
    columns round values such as 16.099999999999998 and turn blanks into 0.
    """
    import json

    create_custom_fields({"Verification Event": [{
        "fieldname": "canonical_payload", "label": "Canonical Payload (hashed)",
        "fieldtype": "Long Text", "read_only": 1, "insert_after": "event_hash"}]}, update=True)
    with open(os.path.join(path, "verification_event.json"), encoding="utf-8") as f:
        events = json.load(f)
    for j in events:
        payload = {"lot": j["lot"], "seq": j["sequence_no"], "type": j["event_type"], "ts": j["timestamp"],
                   "org": j["verifier_org"], "loc": j["location"], "qty": j["quantity_kg_measured"],
                   "moist": j["moisture_pct"], "grade": j["grade_assigned"], "result": j["result"]}
        canon = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        frappe.db.sql("update `tabVerification Event` set canonical_payload=%s where name=%s",
                      (canon, j["event_id"]))
    frappe.db.commit()


def purge():
    for dt, *_ in reversed(ORDER):
        if frappe.db.has_column(dt, SYNTH):
            n = frappe.db.count(dt, {SYNTH: 1})
            frappe.db.delete(dt, {SYNTH: 1})
            print(f"purged {n} synthetic {dt}")
    frappe.db.commit()


def run(path, dry_run=False, purge=False, only=None, limit=None):
    if purge:
        globals()["purge"]()
        return
    frappe.flags.in_import = True
    coops = _ensure_masters(path) if not dry_run else {}
    report = {}
    for dt, fname, id_col, created_col in ORDER:
        if only and dt not in only:
            continue
        if not frappe.db.exists("DocType", dt):
            print(f"!! {dt} missing on this site, skipped")
            continue
        with open(os.path.join(path, fname), newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        if limit:
            rows = rows[:limit]
        header = list(rows[0].keys())
        if dry_run:
            target, customs = _plan(dt, header)
            print(f"[dry-run] {dt}: {len(rows)} rows, {len(customs)} custom fields to add: "
                  f"{[c['fieldname'] for c in customs]}")
            continue

        target = _ensure_schema(dt, header)
        if dt in ("Lot", "AXK Order", "Escrow Contract"):
            _extend_currency(dt)
        meta = frappe.get_meta(dt)
        existing = set(frappe.get_all(dt, pluck="name"))
        inserted = failed = 0
        for i, row in enumerate(rows, 1):
            name = row[id_col]
            if name in existing:
                continue
            doc = {"doctype": dt, "name": name, SYNTH: 1}
            for col, val in row.items():
                doc[target[col]] = _coerce(meta, target[col], val)
            _derive(dt, row, doc, coops)
            ts = row.get(created_col) or None
            try:
                d = frappe.get_doc(doc)
                if ts:
                    d.creation = d.modified = ts
                d.owner = d.modified_by = "Administrator"
                d.db_insert()
                inserted += 1
            except Exception as e:
                failed += 1
                if failed <= 5:
                    print(f"   {dt} {name} failed: {e}")
            if i % 500 == 0:
                frappe.db.commit()
        frappe.db.commit()
        if dt == "Verification Event":
            _store_canonical_payloads(path)
        print(f"{dt}: {inserted} inserted, {failed} failed, {len(rows)} in file")
        report[dt] = {"inserted": inserted, "failed": failed}
    return report
