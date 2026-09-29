# Deployments

## Testnet

Deployed 16 August 2026 with `stellar-cli 27.1.0`, built from the workspace at
`contracts/` targeting `wasm32v1-none`.

| Contract | ID |
|---|---|
| Escrow | `CAPUM7EV3YYPZFO7D2YEB3R6KF7EKYWI7HBZPKQFGOY4UZFUNHU3MWGN` |
| Splitter | `CCYURA2NMODRUMOEBXW7CXRRURTQFMIKAH7VG7NXIDYOUKKG3QZMH2CG` |
| Attestation registry | `CBNLKHDYDDK2FQ2WAPMZMA3YYZMBIXWDWL4GAXRAWYIZ5HNWCL3B4RO5` |

All three privileged roles — the escrow's `verifier`, the splitter's
`coordinator`, the registry's `attester` — are set to
`GAOGSUAQG2QEEEHMIMPI6L4ESU3VBSNLN4IQMLVLWSUQQ3OBJDHACPDL`.

**One account holding all three roles is a testnet convenience and nothing to
copy.** In production they are three separate accounts with different custody,
because they authorise different things and compromising one should not hand
over the others. Deciding what actually holds them belongs in the threat model,
which is not written yet.

The escrow smoke test used a throwaway asset, `AXKT` issued by
`GDHCC6AACKXWE6DYKFIBZUEHFL4VJ3VQ7GGLU4DNYUCKEVQHFQCWXTMH`, whose contract is
`CBL2IWAUUBS6SNAKCTTQXMVNIFS73BR24FJJ7U524JUWZOIGVRWEQD4O`. It is not USDC and
carries no value.

### What was exercised on-chain

Unit tests run against a mocked authoriser, so the point of doing this on
testnet was the paths where mocking is exactly what hides a bug.

| Check | Result |
|---|---|
| Constructor roles readable on all three | verifier, coordinator and attester all return the deployer |
| `attest` then `matches` | digest stored, `matches` true for it and false for another |
| `attest` twice on one trade | `Error(Contract, #1)` — `AlreadyAttested` |
| `attest` from a stranger | refused; the call demands the attester's signature |
| `configure` from a stranger, paying themselves 100% | refused; demands the coordinator's signature |
| `configure` from the coordinator | 2000/5000/3000 stored and read back in order |
| `configure` twice on one trade | `Error(Contract, #4)` — `AlreadyConfigured` |
| `create` | 250 moved buyer → contract, balances `750` / `250`, status `Funded` |
| `release` from a stranger | refused; demands the verifier's signature |
| `release` from the verifier | 250 paid to the destination fixed at creation, contract left at `0`, status `Released` |
| `release` twice | `Error(Contract, #5)` — `NotFunded` |

The two refusals worth naming are the ones the second QA pass found: a stranger
cannot file an attestation, and a stranger cannot record a split. The splitter
one was the fund-theft path — `distribute` is authorised by the account paying
out rather than by any party to the trade, so a division an attacker got in
first would have been honoured.

### Not covered here

`create` was signed by one account acting as both buyer and verifier, because
the CLI signs with a single key and the two-party case needs auth entries built
and signed separately. That both signatures are demanded is covered by
`create_demands_the_verifier_signature_as_well_as_the_buyer` and
`a_stranger_cannot_squat_a_trade_id` in the unit tests, not on-chain.

`refund` after a deadline is untested on testnet — the shortest deadline worth
setting is longer than this exercise. `distribute` is untested on-chain, so the
splitter has moved no money outside unit tests.

Nothing here has been audited. Testnet is a correctness rehearsal, not a
security result.

## Mainnet

Nothing deployed.
