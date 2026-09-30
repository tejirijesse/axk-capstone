"""Endpoints behind the Cooperative, Inspector and Buyer screens.

Every write signs a Stellar transaction with a server-held key, so access is narrow:
- a signed-in System Manager, or
- demo mode (site config `axk_demo_mode: 1`) AND a request from this machine (loopback).
Demo mode exists so the capstone can be demonstrated without sharing credentials; it never
accepts a request from the network.
"""

import frappe
from zoneinfo import ZoneInfo

from frappe.utils import cint, flt, get_datetime, get_system_timezone, getdate, nowdate

from axk_capstone import chain

DT = "AXK Chain Trade"
LOOPBACK = {"127.0.0.1", "::1"}
COMMODITIES = ["Coffee (parchment)", "Maize (dry grain)", "Beans (dry)", "Irish Potato",
               "Rice (paddy)", "Cassava (dried chips)", "Sorghum", "Wheat"]
GRADES = ["A", "B", "C"]
PRICE_RWF_PER_KG = {"Coffee (parchment)": 3400, "Maize (dry grain)": 420, "Beans (dry)": 780,
                    "Irish Potato": 300, "Rice (paddy)": 560, "Cassava (dried chips)": 350,
                    "Sorghum": 450, "Wheat": 520}


def _guard():
    if frappe.session.user != "Guest" and "System Manager" in frappe.get_roles():
        return
    if cint(frappe.conf.get("axk_demo_mode")) and frappe.local.request_ip in LOOPBACK:
        return
    frappe.throw("Sign in as a System Manager to use the trade screens.", frappe.PermissionError)


def _fail(doc, e):
    frappe.db.rollback()
    if doc and doc.name and frappe.db.exists(DT, doc.name):
        frappe.db.set_value(DT, doc.name, "last_error", str(e)[:500])
        frappe.db.commit()
    frappe.throw(str(e), title="Stellar transaction refused")


def _iso(dt):
    """Frappe stores naive datetimes in the system time zone; send them with their offset so
    the browser shows the same instant as the chain explorer, whatever its own zone is."""
    if not dt:
        return ""
    return get_datetime(dt).replace(tzinfo=ZoneInfo(get_system_timezone())).isoformat()


def _row(d):
    return {
        "name": d.name, "lot_ref": d.lot_ref, "status": d.status, "commodity": d.commodity,
        "variety": d.variety, "declared_grade": d.declared_grade, "quantity_kg": d.quantity_kg,
        "origin": d.origin, "harvest_date": str(d.harvest_date or ""), "cooperative_name": d.cooperative_name,
        "inspected_grade": d.inspected_grade, "inspected_quantity_kg": d.inspected_quantity_kg,
        "moisture_pct": d.moisture_pct, "passed": d.passed, "inspector_name": d.inspector_name,
        "buyer_name": d.buyer_name, "amount_rwf": d.amount_rwf,
        "price_rwf": round((d.inspected_quantity_kg or d.quantity_kg or 0) * PRICE_RWF_PER_KG.get(d.commodity, 500)),
        "registered_at": _iso(d.registered_at), "inspected_at": _iso(d.inspected_at),
        "funded_at": _iso(d.funded_at), "settled_at": _iso(d.settled_at),
        "reject_reason": d.reject_reason,
        "modified": _iso(d.modified),
    }


FIELDS = ["name", "lot_ref", "status", "commodity", "variety", "declared_grade", "quantity_kg", "origin",
          "harvest_date", "cooperative_name", "inspected_grade", "inspected_quantity_kg", "moisture_pct",
          "passed", "inspector_name", "buyer_name", "amount_rwf", "registered_at", "inspected_at",
          "funded_at", "settled_at", "reject_reason", "modified"]


@frappe.whitelist(allow_guest=True)
def overview():
    _guard()
    rows = [_row(frappe._dict(r)) for r in frappe.get_all(DT, fields=FIELDS, order_by="modified desc")]
    counts = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return {"lots": rows, "counts": counts, "commodities": COMMODITIES, "grades": GRADES,
            "prices": PRICE_RWF_PER_KG, "reject_reasons": chain.REJECT_REASONS,
            "network": chain.conf().get("network")}


@frappe.whitelist(allow_guest=True)
def personas():
    _guard()
    out = []
    for key in ("coop", "inspector", "buyer"):
        p = chain.PERSONAS[key]
        try:
            bal = chain.balance_rwf(key)
        except chain.ChainError:
            bal = None  # e.g. the inspector holds no RWF trustline
        out.append({"key": key, "name": p["name"], "role": p["role"], "address": chain.address(key), "rwf": bal})
    return out


@frappe.whitelist(allow_guest=True)
def lot(name):
    _guard()
    d = frappe.get_doc(DT, name)
    steps = [
        ("Registered by cooperative", d.register_tx, d.registered_at),
        ("Inspected" + (" · passed" if d.passed else " · rejected" if d.inspect_tx else ""), d.inspect_tx, d.inspected_at),
        ("Escrow funded by buyer", d.fund_tx, d.funded_at),
        ("Released to cooperative", d.release_tx, None),
        ("Split recorded 40 / 40 / 20", d.split_tx, None),
        ("Members paid", d.distribute_tx, None),
        ("Settlement attested", d.attest_tx, d.settled_at),
    ]
    data = _row(d)
    data.update({
        "chain_lot_id": d.chain_lot_id, "lot_digest": d.lot_digest, "lot_record": d.lot_record,
        "report_digest": d.report_digest, "report_record": d.report_record, "inspection_notes": d.inspection_notes,
        "reject_reason": d.reject_reason, "trade_id": d.trade_id, "attest_digest": d.attest_digest,
        "inspect_tx": d.inspect_tx, "attest_tx": d.attest_tx, "settlement_record": d.settlement_record,
        "cooperative_account": d.cooperative_account, "inspector_account": d.inspector_account,
        "buyer_account": d.buyer_account, "deadline": _iso(d.deadline), "last_error": d.last_error,
        "contracts": {k: d.get(k) for k in ("registry", "escrow", "splitter", "attestation", "token")},
        "explorer": chain.EXPLORER,
        "steps": [{"label": l, "tx": t, "url": chain.tx_url(t), "at": _iso(a)} for l, t, a in steps],
    })
    return data


@frappe.whitelist(allow_guest=True, methods=["POST"])
def register_lot(commodity, quantity_kg, declared_grade, origin, variety=None, harvest_date=None):
    _guard()
    if commodity not in COMMODITIES:
        frappe.throw("Unknown commodity")
    if declared_grade not in GRADES:
        frappe.throw("Grade must be A, B or C")
    qty = flt(quantity_kg)
    if qty <= 0 or qty > 100_000:
        frappe.throw("Quantity must be between 1 and 100,000 kg")
    origin = (origin or "").strip()[:80]
    if not origin:
        frappe.throw("Origin is required")
    seq = frappe.db.count(DT) + 1
    code = "".join(w[0] for w in commodity.replace("(", "").split()[:2]).upper()
    doc = frappe.new_doc(DT)
    doc.lot_ref = f"AXK-LIVE-{code}-{nowdate().replace('-', '')}-{seq:04d}"
    while frappe.db.exists(DT, doc.lot_ref):
        seq += 1
        doc.lot_ref = f"AXK-LIVE-{code}-{nowdate().replace('-', '')}-{seq:04d}"
    doc.update({"commodity": commodity, "variety": (variety or "").strip()[:60], "declared_grade": declared_grade,
                "quantity_kg": qty, "origin": origin, "harvest_date": getdate(harvest_date) if harvest_date else None})
    try:
        chain.register_lot(doc)
        doc.insert(ignore_permissions=True)
    except chain.ChainError as e:
        _fail(None, e)
    frappe.db.commit()
    chain.forget_balances()
    return lot(doc.name)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def inspect_lot(name, passed, grade, quantity_kg, moisture_pct=None, notes=None, reject_reason=None):
    _guard()
    doc = frappe.get_doc(DT, name)
    if cint(passed) != 1 and reject_reason not in chain.REJECT_REASONS:
        frappe.throw("Choose a rejection reason from the list")
    if doc.status != "Registered":
        frappe.throw(f"{doc.lot_ref} is {doc.status}, not awaiting inspection")
    qty = flt(quantity_kg)
    if qty <= 0:
        frappe.throw("Measured quantity must be positive")
    try:
        chain.inspect_lot(doc, cint(passed) == 1, grade, qty, flt(moisture_pct) if moisture_pct not in (None, "") else None,
                          (notes or "").strip()[:500], reject_reason)
        doc.last_error = None
        doc.save(ignore_permissions=True)
    except chain.ChainError as e:
        _fail(doc, e)
    frappe.db.commit()
    chain.forget_balances()
    return lot(doc.name)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def fund_lot(name, amount_rwf):
    _guard()
    doc = frappe.get_doc(DT, name)
    if doc.status != "Approved":
        frappe.throw(f"{doc.lot_ref} is {doc.status}; only inspected, approved lots can be funded")
    amount = flt(amount_rwf)
    if amount <= 0:
        frappe.throw("Amount must be positive")
    try:
        chain.fund_escrow(doc, amount)
        doc.last_error = None
        doc.save(ignore_permissions=True)
    except chain.ChainError as e:
        _fail(doc, e)
    frappe.db.commit()
    chain.forget_balances()
    return lot(doc.name)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def confirm_delivery(name):
    _guard()
    doc = frappe.get_doc(DT, name)
    if doc.status != "Funded":
        frappe.throw(f"{doc.lot_ref} is {doc.status}; only funded trades can be settled")
    try:
        chain.settle(doc)
        doc.last_error = None
        doc.save(ignore_permissions=True)
    except chain.ChainError as e:
        _fail(doc, e)
    frappe.db.commit()
    chain.forget_balances()
    return lot(doc.name)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def verify_lot(name):
    _guard()
    doc = frappe.get_doc(DT, name)
    try:
        return chain.matches_on_chain(doc)
    except chain.ChainError as e:
        frappe.throw(str(e))


@frappe.whitelist(allow_guest=True, methods=["POST"])
def top_up_buyer(amount_rwf=500000):
    _guard()
    amount = min(flt(amount_rwf), 5_000_000)
    try:
        chain.top_up_buyer(amount)
    except chain.ChainError as e:
        frappe.throw(str(e))
    chain.forget_balances()
    return personas()
