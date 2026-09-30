import frappe

from axk_capstone.verify import public_lot, qr_svg
from axk_capstone.web import page

no_cache = 1


def get_context(context):
    ref = (frappe.form_dict.get("ref") or "").strip()[:128]
    page(context, "verify", (ref or "Lot") + " · Verify · AXK")
    context.lot = public_lot(ref) if ref else None
    if context.lot:
        context.share_url = frappe.utils.get_url("/trace/lot?ref=" + frappe.utils.quote(ref))
        context.qr = qr_svg(context.share_url)
    return context
