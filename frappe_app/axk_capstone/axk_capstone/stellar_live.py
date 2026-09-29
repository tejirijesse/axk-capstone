"""Read settlement activity for the capstone's RWF test token straight from Stellar testnet.

Every demo trade moves the same Stellar Asset Contract (RWF, issued by the capstone issuer
account), so its `mint` and `transfer` events are the complete money trail: buyer funds
escrow, escrow releases to the cooperative, the splitter pays members out.

Soroban RPC keeps roughly a week of events and scans a bounded window per request, so the
reader starts a fixed distance behind the latest ledger and pages forward with the cursor.
"""

import frappe
from stellar_sdk import SorobanServer, scval
from stellar_sdk.soroban_rpc import EventFilter, EventFilterType

RPC_URL = "https://soroban-testnet.stellar.org"
EXPLORER = "https://stellar.expert/explorer/testnet"
TOKEN_DECIMALS = 7
LOOKBACK_LEDGERS = 100_000  # ~5.8 days at 5 s per ledger
CACHE_KEY = "axk_capstone:live_chain"
CACHE_SECONDS = 60
MAX_PAGES = 60

# Public keys of the demo accounts created by scripts/demo.sh. Not secrets.
DEFAULT_LABELS = {
    "GBG4YO7N2NFNJPSI67LLT2G7BIKT7NW7KUL5THZFZYXHBV5GESBWE7G2": ("buyer", "Buyer"),
    "GAKRLYCYTWNB33KNFO2ZG6YVICDXXTKRMTH5MPO5DAQ2VWLEFL734ZSN": ("coop", "Cooperative"),
    "GCL5ZO2WVQWYL4YQKDJXEBNELQGLWME5B3LNHKXXOSRPZMONSXYQD4RV": ("member1", "Member 1"),
    "GCLEO73Z3CPY7TP6V3XRVBR2J7JNJNYLOPVOOMR5OVAPN7XVGDSJYVCA": ("member2", "Member 2"),
    "GAH6RUPCSQP3Z6JCAG2UYORY4C63NBSQAOAYQR6O4I2JBD2XVDPLAJMP": ("verifier", "Verifier"),
    "GC6C2LMTFAFPSSZFX62MA6AW5O7AAW3UKOWNTAZCLK75MTEQDBDQZKRH": ("issuer", "RWF issuer"),
}
DEFAULT_TOKEN = "CDDUVE7DTM77ETPECHPVWIGPL2CBZ4WJNSG5REN36X6GEBZMIRE3XQG7"


def _config():
    conf = frappe.conf.get("axk_stellar") or {}
    labels = dict(DEFAULT_LABELS)
    for addr, v in (conf.get("labels") or {}).items():
        labels[addr] = tuple(v)
    return conf.get("token") or DEFAULT_TOKEN, labels


def _addr(v):
    """scval.to_native returns Address objects for account/contract topics."""
    return getattr(v, "address", None) or str(v)


def _party(addr, labels):
    addr = _addr(addr)
    if addr in labels:
        key, name = labels[addr]
        return {"key": key, "name": name, "address": addr}
    if addr.startswith("C"):
        # Any contract that holds RWF between funding and release is an escrow instance.
        return {"key": "escrow", "name": "Escrow contract", "address": addr}
    return {"key": "other", "name": addr[:4] + "…" + addr[-4:], "address": addr}


def _classify(kind, frm, to):
    if kind == "mint":
        return "Token issued"
    if frm["key"] == "buyer" and to["key"] == "escrow":
        return "Escrow funded"
    if frm["key"] == "escrow":
        return "Escrow released"
    if frm["key"] == "coop":
        return "Split payout"
    return "Transfer"


def fetch():
    cached = frappe.cache().get_value(CACHE_KEY)
    if cached:
        return cached

    token, labels = _config()
    server = SorobanServer(RPC_URL)
    health = server.get_health()
    start = max(health.oldest_ledger, health.latest_ledger - LOOKBACK_LEDGERS)
    flt = [EventFilter(event_type=EventFilterType.CONTRACT, contract_ids=[token])]

    # Each request scans a bounded ledger range and may come back empty with a cursor that
    # has moved forward, so keep paging until the cursor stops advancing.
    events, cursor = [], None
    for _ in range(MAX_PAGES):
        if cursor:
            page = server.get_events(filters=flt, cursor=cursor, limit=200)
        else:
            page = server.get_events(start_ledger=start, filters=flt, limit=200)
        events.extend(page.events)
        if not page.cursor or page.cursor == cursor:
            break
        cursor = page.cursor

    rows = []
    for e in events:
        topic = [scval.to_native(t) for t in e.topic]
        kind = str(topic[0])
        if kind not in ("mint", "transfer"):
            continue
        if kind == "mint":
            # SAC mint topics (protocol 23+): ["mint", to, asset]; the issuer is implicit.
            issuer = str(topic[2]).split(":")[-1]
            frm = _party(issuer, labels)
            to = _party(topic[1], labels)
        else:
            # ["transfer", from, to, asset]
            frm = _party(topic[1], labels)
            to = _party(topic[2], labels)
        amount = int(scval.to_native(e.value)) / 10**TOKEN_DECIMALS
        rows.append({
            "ledger": e.ledger,
            "time": e.ledger_close_at.isoformat(),
            "tx": e.transaction_hash,
            "tx_url": f"{EXPLORER}/tx/{e.transaction_hash}",
            "kind": _classify(kind, frm, to),
            "from": frm,
            "to": to,
            "amount": amount,
        })

    result = {
        "network": "Stellar testnet",
        "rpc": RPC_URL,
        "token": token,
        "token_url": f"{EXPLORER}/contract/{token}",
        "latest_ledger": health.latest_ledger,
        "window_start_ledger": start,
        "events": rows,
    }
    frappe.cache().set_value(CACHE_KEY, result, expires_in_sec=CACHE_SECONDS)
    return result
