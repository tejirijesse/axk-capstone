import frappe

DEMO_ROLE = "AXK Capstone Demo"


def ensure_roles():
    """Role that may use the trade screens after signing in (reviewers, supervisor)."""
    if not frappe.db.exists("Role", DEMO_ROLE):
        frappe.get_doc({"doctype": "Role", "role_name": DEMO_ROLE, "desk_access": 0}).insert(ignore_permissions=True)
        frappe.db.commit()
