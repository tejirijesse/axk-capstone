"""Public, read-only verification. No login, no personal data.

What is public: statuses, commodity, grade, weight, district-level origin, the cooperative's
registered name, Stellar account addresses, record digests and transaction hashes.
What is never public: the records themselves beyond those fields, inspector and buyer names,
notes, and anything about individual farmers.
"""

import io

import frappe

from axk_capstone import chain

DT = "AXK Chain Trade"
PUBLIC_FIELDS = ["name", "lot_ref", "status", "commodity", "declared_grade", "quantity_kg", "origin",
                 "cooperative_name", "cooperative_account", "chain_lot_id", "lot_digest", "register_tx",
                 "registered_at", "passed", "inspected_grade", "inspected_quantity_kg", "moisture_pct",
                 "reject_reason", "inspector_account", "report_digest", "inspect_tx", "inspected_at",
                 "buyer_account", "amount_rwf", "trade_id", "fund_tx", "funded_at", "release_tx",
                 "split_tx", "distribute_tx", "attest_digest", "attest_tx", "settled_at",
                 "registry", "escrow", "splitter", "attestation", "token"]
TX_FIELDS = ["register_tx", "inspect_tx", "fund_tx", "release_tx", "split_tx", "distribute_tx", "attest_tx"]


def search(q):
    """Resolve a lot reference, on-chain lot id, trade id, record digest or transaction hash."""
    q = (q or "").strip()
    if len(q) < 4:
        return []
    ors = [["lot_ref", "=", q], ["chain_lot_id", "=", q], ["trade_id", "=", q],
           ["lot_digest", "=", q], ["report_digest", "=", q], ["attest_digest", "=", q]]
    ors += [[f, "=", q] for f in TX_FIELDS]
    hits = frappe.get_all(DT, or_filters=ors, fields=["lot_ref", "status", "commodity", "cooperative_name"], limit=10)
    if not hits and len(q) >= 6:
        literal = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        hits = frappe.get_all(DT, filters={"lot_ref": ["like", f"%{literal}%"]},
                              fields=["lot_ref", "status", "commodity", "cooperative_name"], limit=10)
    return hits


def public_lot(ref):
    rows = frappe.get_all(DT, filters={"lot_ref": ref}, fields=PUBLIC_FIELDS, limit=1)
    if not rows:
        return None
    d = rows[0]
    steps = [
        ("Registered by the cooperative", d.register_tx, d.registered_at),
        ("Inspected" + (" · passed" if d.passed else " · rejected" if d.inspect_tx else ""), d.inspect_tx, d.inspected_at),
        ("Payment locked in escrow", d.fund_tx, d.funded_at),
        ("Released to the cooperative", d.release_tx, None),
        ("Split to members recorded", d.split_tx, None),
        ("Members paid", d.distribute_tx, None),
        ("Settlement attested", d.attest_tx, d.settled_at),
    ]
    d.steps = [{"label": l, "tx": t, "url": chain.tx_url(t), "at": a} for l, t, a in steps]
    d.explorer = chain.EXPLORER
    return d


def qr_svg(url):
    import qrcode
    import qrcode.image.svg

    img = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=2)
    buf = io.BytesIO()
    img.save(buf)
    return buf.getvalue().decode("utf-8").split("?>", 1)[-1]
