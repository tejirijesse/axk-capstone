# Security

What the system guarantees, how, and what it does not. Contract guarantees are each pinned by a named
test in `contracts/*/src/test.rs` (65 tests); the ones that matter on-chain were also exercised on
testnet (`docs/deployments.md`).

## Roles and keys

| Role | Signs | Can it move money? |
|---|---|---|
| Cooperative | `register_lot`, `distribute` (paying its own members) | Only its own balance |
| Inspector | `inspect` — once per lot, never its own lot | No |
| Buyer | `create` (with the verifier) | Only into escrow for an approved lot |
| Verifier (AXK) | co-signs `create`, signs `release` | Can release to the fixed payee, never elsewhere |
| Registry admin | `add_inspector`, `remove_inspector` | No |
| Splitter coordinator | `configure` (write-once split) | No |
| Attester | `attest` (write-once digest) | No |

On testnet one account holds registry admin, verifier, coordinator and attester for convenience; the
inspector, cooperative and buyer are separate accounts, which the separation-of-duties checks require.
In production these are four separately custodied keys, so compromising one does not hand over the
others.

## Contract guarantees

| # | Guarantee | Enforced by | Test |
|---|---|---|---|
| 1 | No money moves for a lot that has not passed inspection | escrow asks `approved_cooperative(lot_id)` before any signature or transfer | `an_uninspected_lot_cannot_be_funded`, `a_rejected_lot_cannot_be_funded` |
| 2 | The payee is the cooperative that registered the lot; nobody can name another | `create` has no destination parameter | `the_payee_is_the_cooperative_that_registered_the_lot` |
| 3 | A release cannot redirect money | `release` takes only a trade id | `there_is_no_way_to_name_a_destination_at_release` |
| 4 | A real lot's id cannot be squatted | `lot_id = sha256(cooperative ‖ lot_ref)` | `the_lot_id_is_bound_to_the_cooperative` |
| 5 | A cooperative cannot approve its own produce | `inspect` refuses when inspector = owner | `a_cooperative_cannot_inspect_its_own_lot` |
| 6 | A failed lot cannot be re-inspected into a pass | inspection is write-once | `a_lot_is_inspected_once` |
| 7 | One inspected lot cannot be sold twice | escrow keeps one live trade per lot | `a_lot_cannot_back_two_live_escrows`, `a_sold_lot_cannot_be_sold_again` |
| 8 | A buyer's refund does not depend on AXK | `refund` needs no signature after the deadline | `refund_demands_no_signature_at_all` |
| 9 | A trade id cannot be squatted | `create` needs buyer **and** verifier | `a_stranger_cannot_squat_a_trade_id` |
| 10 | Roles cannot be claimed after deployment | set in the constructor, in the deploy transaction | `the_*_is_set_in_the_deploy_transaction` |
| 11 | A split cannot be rewritten or hijacked | write-once, coordinator only | `a_split_cannot_be_rewritten_once_agreed`, `a_stranger_cannot_record_a_division_that_pays_themselves` |
| 12 | Every stroop is accounted for | rounding remainder goes to the last share | `a_rounding_remainder_is_paid_out_not_dropped` |
| 13 | A settled trade's record cannot be rewritten | attestation is write-once, attester only | `an_attestation_cannot_be_overwritten`, `only_the_attester_may_write` |
| 14 | Records expire neither before nor during a trade | TTL extended on write and read; deadline capped at 150 days | `a_deadline_beyond_the_records_own_lifetime_is_refused` |

## Application controls

- **Who may sign.** Every write endpoint calls `_guard()`: a signed-in System Manager, or demo mode
  (`axk_demo_mode: 1` in site config) **and** a loopback request. Tested: `127.0.0.1` allowed;
  `192.168.1.40` and `10.0.0.5` refused; loopback with demo mode off refused.
- **No command injection.** `chain.py` runs `stellar-cli` with argument lists and no shell. User input
  never reaches the chain as text: commodity and grade come from fixed lists, quantities are numbers,
  free text (notes, variety) is only ever hashed.
- **Input validation.** Commodity and grade from fixed lists; quantity 1–100,000 kg; reject reason
  must be one of six structured reasons; state transitions checked server-side before signing
  (only `Registered` can be inspected, only `Approved` funded, only `Funded` settled).
- **Honest failure.** If a transaction is refused, the database change is rolled back and the
  contract's error is shown (e.g. "Lot has not passed inspection"). Settlement saves each
  transaction hash as it lands, so a failure part-way leaves an accurate record.
- **XSS.** All server data is inserted with `textContent`; public pages are Jinja-escaped.
- **Privacy.** Only SHA-256 digests and account addresses go on-chain. The public `/trace` page shows
  statuses, commodity, grade, weight, district, the cooperative's registered name, addresses, digests
  and transaction hashes — never inspector or buyer names, notes, or farmer data (checked on the page).
- **Synthetic data is labelled.** The five-year history is generated seed data; every row carries
  `axk_synthetic_seed = 1` and every screen showing it says so.

## Known limits

- **Not audited.** Testnet is a correctness rehearsal, not a security result.
- **Custodial keys in a local keystore.** Demo keys are stellar-cli identities on the server, not an
  HSM or KMS. Production needs a managed key store and per-role custody.
- **The oracle problem is narrowed, not solved.** The contracts guarantee that a named, authorised,
  independent inspector vouched for the lot; they cannot guarantee the inspector told the truth.
  Accountability comes from the signed, permanent record and the separation of duties.
- **Event history is short.** Soroban RPC keeps about a week of events; long-term history needs an
  indexer.
- **Demo mode is for demonstration only.** It must be off (`axk_demo_mode: 0`) on any shared host.
