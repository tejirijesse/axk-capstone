# Roadmap

AXK Capstone works end to end today: a lot is registered, inspected, paid into escrow, moved by a carrier,
cleared at the port, settled and split to members — every step a Stellar testnet transaction. This roadmap is
how it grows from a working prototype into infrastructure people can rely on.

It is organised the way a trade moves, so you can pick the part of the chain you care about and improve it step
by step. Each item says why it matters, where the code lives, and what "done" looks like.

| Level | Meaning |
|---|---|
| 🟢 **Starter** | One area, a few files, no contract changes. A good first contribution. |
| 🟡 **Intermediate** | Touches the API and the screens, or adds a feature end to end. |
| 🔴 **Advanced** | Contract changes, security-sensitive work, or a new integration. Discuss in an issue first. |

Before starting, comment on the matching issue (or open one quoting the item ID) so two people do not build the
same thing. Contract (🔴) items need a short design note in the issue before code.

---

## 1 · Cooperative — `/trade/coop`

The cooperative registers what it is selling and gets paid. Today it registers one lot at a time and the member
split is fixed.

| ID | Level | Item | Where | Done when |
|---|---|---|---|---|
| COOP-1 | 🟢 | **Withdraw a lot before inspection.** A cooperative that made a mistake can withdraw an uninspected lot; it is marked *Withdrawn*, never deleted. | `trade_api.py`, `trade.js` (`renderCoop`), `AXK Chain Trade` status options | A withdrawn lot leaves the inspector queue and shows *Withdrawn* on `/trace` |
| COOP-2 | 🟢 | **Show each member's payout** on the lot page (amount and account per share). | `trade.js` (`renderLot`), `chain.py` (`SPLIT_BPS`) | The lot page lists every member payment with its transaction |
| COOP-3 | 🟡 | **Configurable split per cooperative** instead of the fixed 40/40/20. | `chain.py` (`SPLIT_BPS`, `settle`), new Cooperative settings | Two cooperatives with different splits settle correctly; shares still total 10,000 bps |
| COOP-4 | 🟡 | **Build a lot from harvest records.** Select farmer intake records; their IDs and weights go into the lot record (and so into its digest). | `chain.py` (`register_lot`), `trade.js` | The lot record lists harvest IDs; `/trace` shows "aggregated from N harvest records" |
| COOP-5 | 🟡 | **Member statements:** a printable season statement per member (deliveries and payments, each linked to its transaction). | new page under `www/trade/` | A statement prints cleanly with the cooperative's name and transaction links |

## 2 · Inspector — `/trade/inspect`

The inspector is the trust anchor: escrow refuses money for anything they have not passed.

| ID | Level | Item | Where | Done when |
|---|---|---|---|---|
| INSP-1 | 🟢 | **Evidence photos.** Attach photos to an inspection; their SHA-256 hashes go into the report record (and so the report digest). | `chain.py` (`inspect_lot`), `trade.js` (`inspectionForm`) | Changing a photo after signing makes the report fail its on-chain check |
| INSP-2 | 🟢 | **Configurable rejection reasons** (today a fixed list of six). | `chain.py` (`REJECT_REASONS`), site settings | Reasons are editable without code; old inspections keep their original reason text |
| INSP-3 | 🟡 | **Inspector management screen** for the registry admin: add and remove inspectors (`add_inspector` / `remove_inspector`). | new admin page, `chain.py` | Adding an inspector shows the transaction; a removed inspector is refused by the contract |
| INSP-4 | 🟡 | **Calibration samples:** occasional known-grade lots to measure how consistently inspectors grade. | new DocType + report | A report shows each inspector's agreement rate |
| INSP-5 | 🔴 | **Quorum inspection** for high-value lots: N of M inspectors must pass. | `contracts/lot_registry` | Contract tests for quorum reached / not reached / duplicate signer |

## 3 · Buyer and escrow — `/trade/buy`

| ID | Level | Item | Where | Done when |
|---|---|---|---|---|
| BUY-1 | 🟢 | **Refund button.** The escrow contract already lets anyone refund after the deadline; no screen offers it. | `trade_api.py`, `chain.py` (call `refund`), `trade.js` | After the deadline a *Refund* button returns the money; the lot shows *Refunded* and can be sold again |
| BUY-2 | 🟢 | **Deadline countdown** on funded purchases ("refundable in 23 days"). | `trade.js` (`renderBuy`) | Countdown shown; turns into the refund action at zero |
| BUY-3 | 🟡 | **Pay from your own wallet** (Freighter). The buyer signs the escrow payment in their wallet; the site never holds their key. This is how mainnet must work. | `trade.js`, new `wallet.js`, `trade_api.py` (build the transaction, verifier co-signs, submit) | A buyer funds escrow from Freighter on testnet; the transaction shows the buyer's own address |
| BUY-4 | 🔴 | **Disputes.** Buyer opens a dispute before release; a named arbiter resolves it (release or refund). | `contracts/escrow` | New contract states and tests; the release-without-destination guarantee still holds |
| BUY-5 | 🔴 | **Milestone releases** (e.g. 30% at port clearance, 70% on delivery). | `contracts/escrow`, `chain.py` | Each milestone releases only its share, to the fixed payee |

## 4 · Logistics — `/trade/logistics`

Today the carrier's dispatch is recorded as an attestation (a digest of the waybill). Custody is where real
supply chains most often break, so this track has the most room to grow.

| ID | Level | Item | Where | Done when |
|---|---|---|---|---|
| LOG-1 | 🟢 | **Validate dispatch input:** plate and seal formats, required fields, clear errors. | `trade_api.py` (`dispatch_logistics`), `trade.js` | Invalid input is refused with a message before anything is signed |
| LOG-2 | 🟡 | **Multi-leg custody:** truck → warehouse → truck, each handoff its own waybill, linked in order. | `chain.py`, `AXK Chain Trade` (child table for legs), `trade.js` | `/trace` shows every leg in order with its digest |
| LOG-3 | 🟡 | **Checkpoints:** location and time captured at border posts and hashed into the leg record. | `chain.py`, `trade.js` | Each checkpoint appears on the timeline and is covered by a digest |
| LOG-4 | 🔴 | **Two-party handoff on-chain:** both the giver and the receiver sign a custody transfer (one-sided custody records are what fail audits). | new `contracts/custody` | Contract tests: a handoff is complete only with both signatures |

## 5 · Port and terminal — `/trade/port`

| ID | Level | Item | Where | Done when |
|---|---|---|---|---|
| PORT-1 | 🟢 | **Seal-mismatch flow:** when the seal on arrival does not match the waybill, record a discrepancy instead of clearing. | `chain.py` (`receive_port`), `trade.js` | A mismatched seal blocks clearance and shows on `/trace` as a discrepancy |
| PORT-2 | 🟡 | **Customs documents:** attach the clearance documents; hash them into the port receipt. | `chain.py`, `trade.js` | Document hashes appear in the receipt record and are checkable |
| PORT-3 | 🟡 | **Dwell-time alerts:** flag containers waiting at the terminal longer than a threshold. | new report / scheduled job | Over-threshold lots are listed with how long they have waited |
| PORT-4 | 🔴 | **Customs single-window integration** (a real or sandbox customs API). | new integration module | Clearance references are fetched, not typed |

## 6 · Settlement and cash-out

| ID | Level | Item | Where | Done when |
|---|---|---|---|---|
| SET-1 | 🟡 | **Settlement retries:** if settlement stops part-way (e.g. testnet timeout), resume from the last confirmed step. `settle` already saves each step's hash as it lands. | `chain.py` (`settle`), `trade.js` | A *Resume settlement* action completes a half-settled trade without repeating steps |
| SET-2 | 🔴 | **Cash-out to mobile money** through a Stellar SEP-24 anchor (AXK's `axk-stellar` repository has a MoneyGram client). | new integration | A member can withdraw their share to cash in a sandbox |

## 7 · Public trace and explorer — `/trace`, `/chain`

| ID | Level | Item | Where | Done when |
|---|---|---|---|---|
| PUB-1 | 🟢 | **Copy buttons** for hashes and IDs on `/trace`. | `www/trace/lot.html` | One click copies a full hash |
| PUB-2 | 🟢 | **Scan a QR with the camera** from `/trace` on a phone. | `www/trace/index.html` | Scanning a lot's printed QR opens its page |
| PUB-3 | 🟡 | **"Check a document" on `/trace`:** drop a record file; the browser hashes it and compares with the on-chain digest. | `www/trace/lot.html`, small JS | A matching file shows ✓; an edited file shows ✕ |
| PUB-4 | 🟡 | **Open history dataset:** move the optional five-year history into `axk_capstone`'s own DocTypes so it no longer depends on AXK's private platform app. See [docs/history-dataset.md](docs/history-dataset.md). | `axk_seed/`, `api.py`, new DocTypes | `make seed` works on a plain Frappe site |
| PUB-5 | 🟡 | **Event indexer:** store contract events so the explorer's history outlives the RPC's ~7-day window. | `stellar_live.py`, new DocType + scheduled job | The explorer shows events older than a week |

## 8 · Platform and developer experience

| ID | Level | Item | Where | Done when |
|---|---|---|---|---|
| DEV-1 | 🟢 | **Continuous integration:** run contract tests and builds on every pull request (a ready workflow is in [CONTRIBUTING.md](CONTRIBUTING.md#continuous-integration)). | `.github/workflows/` | A failing test blocks the PR |
| DEV-2 | 🟢 | **Ubuntu setup guide**, tested on a fresh Ubuntu 22.04/24.04 machine. | `docs/setup-ubuntu.md` | Someone new reaches a settled trade by following it alone |
| DEV-3 | 🟡 | **Docker Compose** for MariaDB, Redis and the bench, so setup is one command on any OS. | `docker/` | `docker compose up` serves `/trade` |
| DEV-4 | 🟡 | **Public sandbox mode:** anyone can try the flow on testnet with no account, protected by a bot check (Cloudflare Turnstile) and per-visitor limits instead of logins. | `trade_api.py` (`_guard`, `_throttle`) | A visitor completes a trade without signing up; abuse limits hold under a load test |
| DEV-5 | 🟡 | **Python unit tests** for the access guard and the state rules (only inspected lots can be funded, and so on), run with `bench run-tests`. | `axk_capstone/tests/` | Tests cover every rule in `trade_api.py` |
| DEV-6 | 🟢 | **Keep the offline simulation in step** with the real app when screens change. | `scripts/server.py` | Every real screen works in the simulation and is labelled *simulated* |

## 9 · Reach: languages and accessibility

| ID | Level | Item | Where | Done when |
|---|---|---|---|---|
| I18N-1 | 🟢 | **Kinyarwanda, French and Swahili** for the trade screens. | `trade.js` strings, translation files | A language switch changes every label |
| A11Y-1 | 🟢 | **Accessibility pass:** keyboard navigation, focus order, contrast, screen-reader labels (axe audit). | `axk.css`, `trade.js` | No critical axe findings on any screen |
| MOB-1 | 🟡 | **Low-bandwidth mobile view** for cooperative and inspector screens. | `axk.css`, `trade.js` | Usable on a 3-year-old Android over 3G |

## 10 · Toward mainnet

These are the gates before real money. None of them is a weekend task, and each needs maintainers' sign-off.

1. External audit of all four contracts.
2. Non-custodial signing for every party (BUY-3 generalised), or a regulated custodian.
3. Role keys (registry admin, verifier, coordinator, attester) in separate custody, admin actions behind multi-signature.
4. A regulated stablecoin instead of the RWF test token, and licensed cash-out (SET-2).
5. Monitoring and alerting on failed or stuck transactions.

The public sandbox (DEV-4) is **testnet-only by design** and must never be pointed at mainnet.
