# Contracts

Soroban contracts for holding, splitting and attesting a settled trade. Written in Rust, building to wasm, covered by 39 tests.

**Deployed to testnet, and nowhere else.** They pass their tests, compile to wasm, and have been exercised on-chain — see [../docs/deployments.md](../docs/deployments.md) for IDs and what was actually run. They have not been audited. Do not put value near them yet.

```bash
cargo test                                        # 39 tests
cargo build --release --target wasm32-unknown-unknown
```

## Escrow

Holds a buyer's payment against one trade until delivery is verified.

```
__constructor(verifier)
create(trade_id, buyer, destination, token, amount, deadline)   // buyer + verifier
release(trade_id)     // verifier only
refund(trade_id)      // after the deadline, by anyone
get(trade_id)
```

**The destination is fixed at creation and `release` takes no address.** That is the guarantee the contract exists for. A compromised verifier can stall a release or let the deadline run out, but has no parameter through which to send the money somewhere else. `there_is_no_way_to_name_a_destination_at_release` exists to fail if anyone ever adds one.

**Refund needs no signature.** Once the deadline passes, anyone can trigger the return to the buyer. If it required a privileged caller, a buyer's money would depend on AXK still being around to sign for it. `refund_demands_no_signature_at_all` asserts the authorisation set is empty.

**A deadline already in the past is rejected at creation**, otherwise an escrow is refundable the instant it is funded while looking settled. A deadline further out than the record's own lifetime is rejected too: the entry is kept alive for 180 days and refreshed on use, so a 300-day trade nobody touches could be archived before its deadline, which is exactly the stranded money the TTL handling exists to prevent.

**Creating a trade takes the verifier's signature as well as the buyer's.** `trade_id` is caller-supplied and can only be occupied once, so with the buyer's signature alone anyone could fund a one-stroop trade under a real trade's id, block it permanently, and take their stroop back at the deadline.

**The verifier is set in the deploy transaction.** A separate `init` call left a window in which a stranger could claim the role on a freshly deployed instance and then refuse to release anything on it.

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
