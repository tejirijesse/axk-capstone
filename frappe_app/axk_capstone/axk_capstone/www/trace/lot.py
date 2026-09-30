import frappe

from axk_capstone.verify import public_lot, qr_svg
from axk_capstone.web import page

no_cache = 1


def _public_origin():
    """The origin the visitor actually used. Behind a tunnel or proxy that is the forwarded
    host and scheme; frappe.utils.get_url would add the local dev port (:8000) instead."""
    req = frappe.request
    host = req.headers.get("X-Forwarded-Host") or req.headers.get("Host") or req.host
    proto = (req.headers.get("X-Forwarded-Proto") or req.scheme or "http").split(",")[0].strip()
    return f"{proto}://{host}"


def get_context(context):
    ref = (frappe.form_dict.get("ref") or "").strip()[:128]
    page(context, "verify", (ref or "Lot") + " · Verify · AXK")
    context.lot = public_lot(ref) if ref else None
    if context.lot:
        context.share_url = _public_origin() + "/trace/lot?ref=" + frappe.utils.quote(ref)
        context.qr = qr_svg(context.share_url)
    return context
