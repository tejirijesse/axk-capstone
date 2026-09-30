import frappe

from axk_capstone.verify import search
from axk_capstone.web import page

no_cache = 1


def get_context(context):
    page(context, "verify", "Verify a lot · AXK")
    context.q = (frappe.form_dict.get("q") or "").strip()[:128]
    context.results = search(context.q) if context.q else []
    if len(context.results) == 1 and context.q:
        frappe.local.flags.redirect_location = "/trace/lot?ref=" + frappe.utils.quote(context.results[0].lot_ref)
        raise frappe.Redirect
    context.recent = frappe.get_all("AXK Chain Trade", fields=["lot_ref", "status", "commodity", "cooperative_name"],
                                    order_by="modified desc", limit=8)
    return context
