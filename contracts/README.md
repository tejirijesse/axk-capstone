# Contracts

Soroban contracts for verifying a commodity lot and then holding, splitting and attesting payment for it. Written in Rust, building to wasm, covered by 65 tests.

**Deployed to testnet, and nowhere else.** They pass their tests, compile to wasm, and have been exercised on-chain — see [../docs/deployments.md](../docs/deployments.md) for IDs and what was actually run. They have not been audited. Do not put value near them yet.

```bash
cargo test                                        # 65 tests
cargo build --release --target wasm32-unknown-unknown
```

## Lot registry

Records that a lot exists and that an authorised inspector examined it. This is the verification half of the trade, and the escrow will not take money for a lot that has not passed through it.

```
__constructor(admin)
add_inspector(inspector) / remove_inspector(inspector)          // admin only
lot_id(cooperative, lot_ref) -> BytesN<32>
register_lot(cooperative, lot_ref, digest) -> lot_id             // cooperative signs, write-once
inspect(lot_id, inspector, passed, grade, quantity_kg, report_digest)   // authorised inspector, once
get(lot_id) / get_inspection(lot_id)
approved_cooperative(lot_id) -> Option<Address>                  // what the escrow asks
matches(lot_id, digest) -> bool
```

**The lot id is bound to the cooperative.** It is `sha256(cooperative ‖ lot_ref)`, not the bare reference. If a stranger could register a real lot's reference under their own address first and get it inspected by mistake, the buyer would pay the stranger. With the address folded in, the same reference from a stranger is a different lot. `the_lot_id_is_bound_to_the_cooperative`.

**Only digests go on-chain.** The cooperative commits to a hash of the lot record (commodity, grade, weight, origin, harvest records); the inspector commits to a hash of their report. A buyer or lender shown either document hashes it and checks `matches`, without the ledger carrying personal or commercial data.

**Inspection is write-once.** A failed lot stays failed. Re-inspecting until someone passes it is exactly what an inspection record has to make visible, not allow. A cooperative that fixes a rejected lot registers it again under a new reference, and the rejection remains on the ledger. `a_lot_is_inspected_once`.

**A cooperative cannot inspect its own lot**, even if it also holds an inspector licence. Separation of duties is enforced by the contract, not by policy. `a_cooperative_cannot_inspect_its_own_lot`.

**Removing an inspector stops future inspections and leaves past ones standing.** They were valid when signed; rewriting them would be rewriting history. `a_removed_inspector_cannot_inspect_again`.

## Escrow

Holds a buyer's payment for one inspected lot until delivery is verified.

```
__constructor(verifier, registry)
create(trade_id, lot_id, buyer, token, amount, deadline)        // buyer + verifier; lot must be approved
release(trade_id)     // verifier only
refund(trade_id)      // after the deadline, by anyone
get(trade_id)
lot_trade(lot_id) -> Option<trade_id>
```

**Money only moves for an inspected lot, and only to the cooperative that owns it.** `create` asks the lot registry `approved_cooperative(lot_id)`. An unregistered, uninspected or rejected lot is refused with `LotNotApproved` before any signature is checked or any token moves. There is no destination parameter: the payee is whoever registered the inspected lot, so neither the buyer nor AXK can name a different one. `an_uninspected_lot_cannot_be_funded`, `a_rejected_lot_cannot_be_funded`, `the_payee_is_the_cooperative_that_registered_the_lot`.

**A lot backs one live escrow at a time.** A second escrow for a lot that is funded or already sold is refused with `LotInEscrow`, so the same inspected lot cannot be sold to two buyers. A refund frees the lot. `a_lot_cannot_back_two_live_escrows`, `a_sold_lot_cannot_be_sold_again`, `a_refund_frees_the_lot_for_another_buyer`.

**The destination is fixed at creation and `release` takes no address.** That is the guarantee the contract exists for. A compromised verifier can stall a release or let the deadline run out, but has no parameter through which to send the money somewhere else. `there_is_no_way_to_name_a_destination_at_release` exists to fail if anyone ever adds one.

**Refund needs no signature.** Once the deadline passes, anyone can trigger the return to the buyer. If it required a privileged caller, a buyer's money would depend on AXK still being around to sign for it. `refund_demands_no_signature_at_all` asserts the authorisation set is empty.

**A deadline already in the past is rejected at creation**, otherwise an escrow is refundable the instant it is funded while looking settled. A deadline further out than the record's own lifetime is rejected too: the entry is kept alive for 180 days and refreshed on use, so a 300-day trade nobody touches could be archived before its deadline, which is exactly the stranded money the TTL handling exists to prevent.

**Creating a trade takes the verifier's signature as well as the buyer's.** `trade_id` is caller-supplied and can only be occupied once, so with the buyer's signature alone anyone could fund a one-stroop trade under a real trade's id, block it permanently, and take their stroop back at the deadline.

**The verifier is set in the deploy transaction.** A separate `init` call left a window in which a stranger could claim the role on a freshly deployed instance and then refuse to release anything on it.

**The registry is fixed in the deploy transaction**, alongside the verifier, so nobody can later point an escrow at a registry that approves everything.

The state machine is `Funded → Released` or `Funded → Refunded`, and nothing else. Releasing twice, refunding a released trade, and releasing a refunded one are each tested and each refused.

## Splitter

Divides a released payment between the cooperative, its members and any financier.

```
__constructor(coordinator)
configure(trade_id, shares)   // coordinator only; basis points totalling exactly 10,000
distribute(trade_id, token, from, amount)
shares(trade_id)
```

**The parts sum to exactly the whole.** Integer division leaves a remainder, and a remainder that is dropped or left in the contract is a balance that drifts by a stroop per settlement until someone reconciles a year of it by hand. The remainder goes to the last share. `a_rounding_remainder_is_paid_out_not_dropped` splits 1,001 three ways at 3333/3333/3334 and asserts the payments total 1,001 exactly.

**A share of zero or below is refused**, not just a total that misses. Otherwise `10000 + 0` and `12000 + -2000` both total correctly while describing a split that is not one.

**A configured split cannot be rewritten**, so it cannot change after the parties agreed to it.

**Configuring is restricted to the coordinator.** This was left open when the same hole was closed in the attestation registry, and the second QA pass caught it in the sibling contract. It was the worse of the two: an attestation an attacker files first is a denial of service, but a *split* an attacker files first pays them the money, because `distribute` is authorised by the account paying out rather than by any party to the trade. Write-once plus an unrestricted write is the pair to look for.

## Attestation registry

```
attest(trade_id, digest)
get(trade_id)
matches(trade_id, digest) -> bool
```

Stores a digest over a canonical serialisation of the trade record, never the record. A lender shown a trade hashes it and calls `matches`, confirming it is the record that settled without AXK vouching for it and without the ledger carrying commercial terms or personal data.

**Write-once, and restricted to the attester.** An attestation that could be amended would prove only what AXK last chose to say.

Writing was open in the first version, on the reasoning that a wrong digest from a stranger proves nothing. That reasoning was wrong and QA caught it: `trade_id` is public from the moment an escrow is funded, and the record is write-once, so anyone could race a junk attestation in first and block the real one permanently. Being unable to forge a record is no use to an attacker who can stop it existing. The attester is set in the deploy transaction.

`matches` on an unknown trade returns false rather than raising, so a lender checking an unrecognised trade gets an answer rather than an error.

## Storage lifetime

Soroban archives persistent entries that are not used. An escrow's own deadlines run to ninety days, so every entry is written with a TTL extension well beyond that, and reads extend it again. Without this an escrow could outlive its own record and strand the buyer's money behind an archived entry.

## What is still owed

The canonicalisation these digests are taken over has to be published and stable before the attestation means anything to an outside party. That is a specification problem, not a contract one, and it is not solved yet.

The splitter's `amount` has no on-chain link to what the escrow actually released. The two contracts are independent, so a backend bug could distribute a figure that looks correct and is not. Binding them is a design decision not yet made.

Beyond that: testnet deployment, a STRIDE threat model over the contracts and the privileged accounts, monitoring derived from it, and an external audit with findings remediated. Pause and upgrade controls are not implemented; both are admin powers and belong in the threat model before they exist in code.
