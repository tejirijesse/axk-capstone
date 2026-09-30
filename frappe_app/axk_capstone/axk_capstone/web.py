"""Shared context for the AXK Trade pages."""

import os

import frappe

_PUBLIC = os.path.join(os.path.dirname(__file__), "public")

NAV = [
    ("overview", "/trade", "Overview"),
    ("coop", "/trade/coop", "Cooperative"),
    ("inspect", "/trade/inspect", "Inspector"),
    ("buy", "/trade/buy", "Buyer"),
    ("verify", "/trace", "Verify"),
    ("chain", "/chain", "Chain explorer"),
]


def _stamp(rel):
    try:
        return int(os.path.getmtime(os.path.join(_PUBLIC, rel)))
    except OSError:
        return 0


def page(context, active, title):
    context.title = title
    context.no_breadcrumbs = True
    context.show_sidebar = False
    context.axk_nav = NAV
    context.axk_active = active
    context.axk_network = (frappe.conf.get("axk_stellar") or {}).get("network", "testnet")
    context.axk_demo = bool(frappe.conf.get("axk_demo_mode"))
    context.css_v = _stamp("css/axk.css")
    context.chain_css_v = _stamp("css/chain.css")
    context.js_v = _stamp("js/trade.js")
    context.chain_js_v = _stamp("js/chain.js")
    return context
