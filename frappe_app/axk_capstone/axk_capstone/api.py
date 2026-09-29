"""Chain explorer data endpoints.

Two sources, never mixed:
- `live_chain`   real Stellar testnet events for the capstone contracts
- `ledger_*`     the synthetic seed history in axk_network (rows tagged axk_synthetic_seed)
"""

import frappe

from axk_capstone import stellar_live

SYNTH = "axk_synthetic_seed"

CHANNEL_GROUPS = [
    ("AXK escrow", ("AXK escrow",)),
    ("Mobile money", ("MTN MoMo", "Airtel Money")),
    ("Cash", ("Cash on delivery",)),
    ("Bank transfer", ("Bank transfer",)),
    ("PAPSS", ("PAPSS",)),
]


def _group(channel):
    for name, prefixes in CHANNEL_GROUPS:
        if channel and channel.startswith(prefixes):
            return name
    return "Other"


@frappe.whitelist(allow_guest=True)
def live_chain():
    try:
        return stellar_live.fetch()
    except Exception as e:  # network down, RPC limits: the page still renders the ledger half
        frappe.log_error(title="axk_capstone live_chain", message=frappe.get_traceback())
        return {"error": f"Stellar testnet unavailable: {e.__class__.__name__}"}


@frappe.whitelist(allow_guest=True)
def ledger_overview():
    sql = frappe.db.sql
    lots = sql(f"select count(*), sum(xrpl_tx_hash is not null and xrpl_tx_hash != '') from tabLot where {SYNTH}=1")[0]
    events = sql(f"select count(*), sum(anchor_chain='xahau') from `tabVerification Event` where {SYNTH}=1")[0]
    esc = dict(sql(f"select status, count(*) from `tabEscrow Contract` where {SYNTH}=1 group by status"))
    settled_usd = sql(f"select coalesce(sum(total_usd),0) from `tabAXK Order` where {SYNTH}=1 and seed_status='Settled'")[0][0]

    # Hash-chain link integrity per lot (full recomputation happens in the browser, per lot).
    rows = sql(f"""select lot, prev_hash, event_hash from `tabVerification Event`
                   where {SYNTH}=1 order by lot, sequence_no""")
    intact, last_lot, prev, ok = 0, None, None, True
    for lot, p, h in rows:
        if lot != last_lot:
            if last_lot is not None and ok:
                intact += 1
            last_lot, ok, prev = lot, p == "0" * 64, h
            continue
        ok = ok and p == prev
        prev = h
    if last_lot is not None and ok:
        intact += 1

    # Settled orders only: unsettled rows store completion_time_hours as 0.
    completion = {}
    for ch, hours, baseline, n in sql(f"""select settlement_channel, completion_time_hours, baseline_recall_hours, 1
                                          from `tabAXK Order` where {SYNTH}=1 and seed_status='Settled'"""):
        k = "AXK escrow" if ch.startswith("AXK escrow") else "Other channels"
        c = completion.setdefault(k, [0.0, 0])
        c[0] += hours
        c[1] += 1
        b = completion.setdefault("Recalled baseline", [0.0, 0])
        b[0] += baseline
        b[1] += 1
    completion_rows = [
        {"label": k, "hours": round(completion[k][0] / completion[k][1], 1), "n": completion[k][1]}
        for k in ("AXK escrow", "Other channels", "Recalled baseline") if k in completion
    ]

    monthly = sql(f"""select date_format(confirmed_at, %s) m,
                             sum(anchor_chain='xahau'), sum(anchor_chain!='xahau')
                      from `tabVerification Event` where {SYNTH}=1 group by m order by m""", ("%Y-%m",))

    share = {}
    for year, ch, n in sql(f"""select year(order_date), settlement_channel, count(*) from `tabAXK Order`
                               where {SYNTH}=1 and seed_status='Settled' group by 1, 2"""):
        share.setdefault(str(year), {}).setdefault(_group(ch), 0)
        share[str(year)][_group(ch)] += n

    lot_options = sql(f"""select l.name, l.commodity_type, l.cooperative_name, count(v.name) n, max(l.status)
                          from tabLot l join `tabVerification Event` v on v.lot = l.name
                          where l.{SYNTH}=1 group by l.name order by l.aggregation_date desc limit 60""")

    return {
        "synthetic": True,
        "tiles": {
            "lots": lots[0], "lots_anchored": int(lots[1] or 0),
            "events": events[0], "events_anchored": int(events[1] or 0),
            "chains_intact": intact,
            "escrows": sum(esc.values()), "escrows_released": esc.get("Released", 0),
            "settled_usd": float(settled_usd),
        },
        "completion": completion_rows,
        "monthly": [{"month": m, "anchored": int(a), "offchain": int(o)} for m, a, o in monthly],
        "channel_groups": [g for g, _ in CHANNEL_GROUPS],
        "share": [{"year": y, **share[y]} for y in sorted(share)],
        "escrow_status": esc,
        "lots": [{"name": n, "commodity": c, "coop": co, "events": e, "status": s}
                 for n, c, co, e, s in lot_options],
    }


@frappe.whitelist(allow_guest=True)
def lot_chain(lot):
    if not frappe.db.exists("Lot", {"name": lot, SYNTH: 1}):
        frappe.throw("Unknown lot", frappe.DoesNotExistError)
    lot_doc = frappe.db.get_value("Lot", lot, ["name", "commodity_type", "cooperative_name", "grade",
                                               "quantity", "status", "document_hash"], as_dict=True)
    events = frappe.db.sql("""select name, sequence_no, seed_event_type, event_type, confirmed_at, actor_name,
                                     verifier_role, location, result, prev_hash, event_hash, evidence_hash,
                                     canonical_payload, anchor_chain, xrpl_tx_hash
                              from `tabVerification Event` where lot=%s order by sequence_no""", lot, as_dict=True)
    for e in events:
        e.confirmed_at = str(e.confirmed_at)
    return {"lot": lot_doc, "events": events, "synthetic": True}
