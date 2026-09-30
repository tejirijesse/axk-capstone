"""Drives the capstone contracts on Stellar testnet for AXK Chain Trade records.

Custodial signing, matching AXK's Stellar design: the server holds one testnet identity per
role in the stellar-cli keystore and signs on the participant's behalf. The CLI is used rather
than hand-built transactions because escrow funding needs two signatures in one transaction
(buyer and verifier), and the CLI assembles and signs those auth entries correctly.

Every command is an argument list run without a shell; nothing user-typed is interpolated into
a command string. Free-text fields never reach the chain at all: only their SHA-256 digests do.
"""

import hashlib
import json
import re
import subprocess
import frappe
from frappe.utils import add_to_date, get_datetime, now_datetime

EXPLORER = "https://stellar.expert/explorer/testnet"
DECIMALS = 10**7
ESCROW_TERM_DAYS = 30

# Demo personas: which keystore identity signs for which role. Names are fictional.
PERSONAS = {
    "coop": {"identity": "axk-coop", "name": "Koperative Twisungane (demo)", "role": "Cooperative"},
    "inspector": {"identity": "axk-inspector", "name": "Inspector J. Mukamana (demo)", "role": "Inspector"},
    "buyer": {"identity": "axk-buyer", "name": "Goma Grain Traders (demo)", "role": "Buyer"},
    "verifier": {"identity": "axk-verifier", "name": "AXK verifier service", "role": "Verifier"},
    "member1": {"identity": "axk-member1", "name": "Member 1", "role": "Cooperative member"},
    "member2": {"identity": "axk-member2", "name": "Member 2", "role": "Cooperative member"},
    "issuer": {"identity": "axk-issuer", "name": "RWF test issuer", "role": "Token issuer"},
}
SPLIT_BPS = [("member1", 4000), ("member2", 4000), ("coop", 2000)]

TX_RE = re.compile(r"/tx/([0-9a-f]{64})")
ERR_RE = re.compile(r"Error\(Contract, #(\d+)\)")
CONTRACT_ERRORS = {
    "registry": {1: "Lot already registered", 2: "No such lot", 3: "Not an authorised inspector",
                 4: "Lot already inspected", 5: "Quantity must be positive", 6: "Inspector owns this lot"},
    "escrow": {3: "Trade already exists", 4: "No such trade", 5: "Trade is not funded",
               6: "Refund deadline not reached", 7: "Deadline in the past", 8: "Amount must be positive",
               9: "Deadline too far", 10: "Lot has not passed inspection", 11: "Lot is already in escrow"},
}


class ChainError(Exception):
    pass


def conf():
    c = frappe.conf.get("axk_stellar") or {}
    missing = [k for k in ("registry", "escrow", "splitter", "attestation", "token") if not c.get(k)]
    if missing:
        raise ChainError(f"axk_stellar site config is missing {', '.join(missing)}")
    return c


def sha256_hex(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _run(args, contract=None, timeout=90):
    c = conf()
    cmd = [c.get("stellar_bin") or "stellar", *args]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise ChainError("Stellar testnet did not answer in time") from e
    out = (p.stdout or "") + (p.stderr or "")
    if p.returncode != 0:
        m = ERR_RE.search(out)
        if m and contract in CONTRACT_ERRORS:
            code = int(m.group(1))
            raise ChainError(CONTRACT_ERRORS[contract].get(code, f"Contract error #{code}"))
        tail = out.strip().splitlines()[-1] if out.strip() else "unknown error"
        raise ChainError(tail[:300])
    tx = TX_RE.search(out)
    return (p.stdout or "").strip(), (tx.group(1) if tx else None)


def invoke(contract_key, fn, source, args, send=True, extra=None):
    c = conf()
    cmd = ["contract", "invoke", "--id", c[contract_key], "--source", source,
           "--network", c.get("network", "testnet")]
    if extra:
        cmd += extra
    if not send:
        cmd.append("--send=no")
    cmd += ["--", fn]
    for k, v in args.items():
        cmd += [f"--{k}", str(v)]
    return _run(cmd, contract="registry" if contract_key == "registry" else "escrow" if contract_key == "escrow" else None)


def address(persona):
    key = f"axk_capstone:addr:{persona}"
    cached = frappe.cache().get_value(key)
    if cached:
        return cached
    out, _ = _run(["keys", "address", PERSONAS[persona]["identity"]])
    frappe.cache().set_value(key, out.strip())
    return out.strip()


BALANCE_TTL = 20


def balance_rwf(persona):
    key = f"axk_capstone:bal:{persona}"
    cached = frappe.cache().get_value(key)
    if cached is not None:
        return cached
    out, _ = invoke("token", "balance", PERSONAS["verifier"]["identity"], {"id": address(persona)}, send=False)
    value = int(out.strip().strip('"') or 0) / DECIMALS
    frappe.cache().set_value(key, value, expires_in_sec=BALANCE_TTL)
    return value


def forget_balances():
    for p in PERSONAS:
        frappe.cache().delete_value(f"axk_capstone:bal:{p}")


def tx_url(h):
    return f"{EXPLORER}/tx/{h}" if h else None


# ---------------------------------------------------------------------------
# lifecycle
# ---------------------------------------------------------------------------

def _stamp_contracts(doc):
    c = conf()
    for k in ("registry", "escrow", "splitter", "attestation", "token"):
        doc.set(k, c[k])


def register_lot(doc):
    """Cooperative commits to the lot record's digest in the lot registry."""
    _stamp_contracts(doc)
    doc.cooperative_name = PERSONAS["coop"]["name"]
    doc.cooperative_account = address("coop")
    record = {
        "lot_ref": doc.lot_ref, "commodity": doc.commodity, "variety": doc.variety or "",
        "declared_grade": doc.declared_grade, "quantity_kg": doc.quantity_kg, "origin": doc.origin,
        "harvest_date": str(doc.harvest_date or ""), "cooperative": doc.cooperative_account,
    }
    doc.lot_record = canonical(record)
    doc.lot_digest = sha256_hex(doc.lot_record)
    lot_ref_hash = sha256_hex("lot:" + doc.lot_ref)
    out, tx = invoke("registry", "register_lot", PERSONAS["coop"]["identity"],
                     {"cooperative": PERSONAS["coop"]["identity"], "lot_ref": lot_ref_hash, "digest": doc.lot_digest})
    doc.chain_lot_id = out.strip('"')
    doc.register_tx = tx
    doc.registered_at = now_datetime()
    doc.status = "Registered"


REJECT_REASONS = [
    "Moisture above tolerance", "Weight below declared", "Foreign matter or defects",
    "Grade below declared", "Pest or mould damage", "Documents missing or inconsistent",
]


def inspect_lot(doc, passed, grade, quantity_kg, moisture_pct, notes, reject_reason=None):
    """Authorised inspector signs one pass/fail inspection against the lot."""
    grade = re.sub(r"[^A-Za-z0-9_]", "", grade or "")[:9] or "NA"
    doc.inspector_name = PERSONAS["inspector"]["name"]
    doc.inspector_account = address("inspector")
    report = {
        "lot_ref": doc.lot_ref, "chain_lot_id": doc.chain_lot_id, "passed": bool(passed), "grade": grade,
        "quantity_kg": quantity_kg, "moisture_pct": moisture_pct, "notes": notes or "",
        "reject_reason": None if passed else reject_reason,
        "inspector": doc.inspector_account, "inspected_at": str(now_datetime()),
    }
    doc.report_record = canonical(report)
    doc.report_digest = sha256_hex(doc.report_record)
    _, tx = invoke("registry", "inspect", PERSONAS["inspector"]["identity"], {
        "lot_id": doc.chain_lot_id, "inspector": PERSONAS["inspector"]["identity"],
        "passed": "true" if passed else "false", "grade": grade,
        "quantity_kg": int(round(quantity_kg)), "report_digest": doc.report_digest,
    })
    doc.passed = 1 if passed else 0
    doc.inspected_grade = grade
    doc.inspected_quantity_kg = quantity_kg
    doc.moisture_pct = moisture_pct
    doc.inspection_notes = notes
    doc.reject_reason = None if passed else reject_reason
    doc.inspect_tx = tx
    doc.inspected_at = now_datetime()
    doc.status = "Approved" if passed else "Rejected"


def fund_escrow(doc, amount_rwf):
    """Buyer locks payment in escrow. Buyer and verifier both sign; the payee comes from the registry."""
    c = conf()
    doc.buyer_name = PERSONAS["buyer"]["name"]
    doc.buyer_account = address("buyer")
    doc.trade_id = sha256_hex("trade:" + doc.lot_ref + ":" + str(now_datetime()))
    deadline = add_to_date(now_datetime(), days=ESCROW_TERM_DAYS)
    _, tx = invoke("escrow", "create", PERSONAS["verifier"]["identity"], {
        "trade_id": doc.trade_id, "lot_id": doc.chain_lot_id, "buyer": PERSONAS["buyer"]["identity"],
        "token_id": c["token"], "amount": int(round(amount_rwf * DECIMALS)),
        "deadline": int(get_datetime(deadline).timestamp()),
    }, extra=["--auto-sign"])
    doc.amount_rwf = amount_rwf
    doc.fund_tx = tx
    doc.funded_at = now_datetime()
    doc.deadline = deadline
    doc.status = "Funded"


def _checkpoint(doc):
    doc.save(ignore_permissions=True)
    frappe.db.commit()


def settle(doc):
    """Delivery confirmed: verifier releases, coordinator records the split, cooperative pays
    members, and the settled trade is attested. Each step's hash is saved as it lands, so a
    failure part-way leaves an accurate record of what did happen."""
    c = conf()
    amount = int(round(doc.amount_rwf * DECIMALS))
    if not doc.release_tx:
        _, doc.release_tx = invoke("escrow", "release", PERSONAS["verifier"]["identity"], {"trade_id": doc.trade_id})
        _checkpoint(doc)
    if not doc.split_tx:
        shares = [{"party": address(p), "bps": str(b)} for p, b in SPLIT_BPS]
        _, doc.split_tx = invoke("splitter", "configure", PERSONAS["verifier"]["identity"],
                                 {"trade_id": doc.trade_id, "shares": json.dumps(shares)})
        _checkpoint(doc)
    if not doc.distribute_tx:
        _, doc.distribute_tx = invoke("splitter", "distribute", PERSONAS["coop"]["identity"], {
            "trade_id": doc.trade_id, "token_id": c["token"], "from": PERSONAS["coop"]["identity"], "amount": amount})
        _checkpoint(doc)
    if not doc.attest_tx:
        record = {
            "lot_ref": doc.lot_ref, "chain_lot_id": doc.chain_lot_id, "lot_digest": doc.lot_digest,
            "report_digest": doc.report_digest, "trade_id": doc.trade_id, "amount": str(amount),
            "token": c["token"], "buyer": doc.buyer_account, "cooperative": doc.cooperative_account,
            "release_tx": doc.release_tx, "distribute_tx": doc.distribute_tx,
        }
        doc.settlement_record = canonical(record)
        doc.attest_digest = sha256_hex(doc.settlement_record)
        _, doc.attest_tx = invoke("attestation", "attest", PERSONAS["verifier"]["identity"],
                                  {"trade_id": doc.trade_id, "digest": doc.attest_digest})
    doc.settled_at = now_datetime()
    doc.status = "Settled"


def matches_on_chain(doc):
    """Ask the contracts whether the stored records still hash to what was committed."""
    result = {}
    if doc.chain_lot_id:
        out, _ = invoke("registry", "matches", PERSONAS["verifier"]["identity"],
                        {"lot_id": doc.chain_lot_id, "digest": sha256_hex(doc.lot_record)}, send=False)
        result["lot_record"] = out.strip() == "true"
    if doc.attest_tx:
        out, _ = invoke("attestation", "matches", PERSONAS["verifier"]["identity"],
                        {"trade_id": doc.trade_id, "digest": sha256_hex(doc.settlement_record)}, send=False)
        result["settlement_record"] = out.strip() == "true"
    return result


def top_up_buyer(amount_rwf):
    """Testnet only: the RWF test issuer pays the buyer so demos never run dry."""
    _run(["tx", "new", "payment", "--destination", address("buyer"),
          "--asset", "RWF:" + address("issuer"), "--amount", str(int(amount_rwf * DECIMALS)),
          "--source", PERSONAS["issuer"]["identity"], "--network", conf().get("network", "testnet")])

