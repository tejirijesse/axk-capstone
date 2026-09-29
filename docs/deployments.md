# Deployments

## Capstone testnet deployment (29 September 2026)

Deployed by `scripts/demo.sh` with `stellar-cli 28.0.0`. Each run deploys a fresh set; these are from the
run that exercised the inspection-gated flow. The latest IDs are always in `scripts/.demo-state.env`.

| Contract | ID |
|---|---|
| Lot registry | `CA2STYORR2OUWD3I5AT7X5ECD7ZDQWI5B4YUQDIIXWORDEGH3ZWANFQ6` |
| Escrow (inspection-gated) | `CCAJENWOAQEEUOMEOBRUGBFWBRUNUAE424DUE7RDPFYNK4LPEOCC5E2P` |
| Splitter | `CAU6RIFFOLYJA54IJCEKBDYSPLPGNRUNYGO76H4KZTNNQYX7W2QUQYZT` |
| Attestation registry | `CAEC6KYYAI5KIH6I44AGG447L5277NUPZMMV57GFK72CKOBLV2BJIUZV` |
| RWF test token (SAC) | `CDDUVE7DTM77ETPECHPVWIGPL2CBZ4WJNSG5REN36X6GEBZMIRE3XQG7` |

Roles: registry admin, escrow verifier, splitter coordinator and attester are one testnet account
(`GAH6…LAJMP`); the inspector (`GCPK…3AHJ`) and cooperative (`GAKR…734ZSN`) are separate accounts, which is
what the separation-of-duties checks need.

### What was exercised on-chain

| Check | Result |
|---|---|
| Cooperative registers lot `AXK-HUYE-COFFEE-LOT-0101` | lot_id bound to the cooperative, status `Registered` |
| Buyer funds before inspection | `Error(Contract, #10)` — `LotNotApproved`; no RWF moved |
| Cooperative inspects its own lot | `Error(Contract, #3)` — `NotAnInspector` |
| Inspector approves: grade A, 3,850 kg | [tx](https://stellar.expert/explorer/testnet/tx/231ed00a97a2f31c8d07f1952c677d0aeab2b3dbfc886ae6b1c5450bf68ca59c) |
| Buyer + verifier fund escrow; payee read from the registry | [tx](https://stellar.expert/explorer/testnet/tx/dbce793772b67d79c6b0bc60c087b60fae29018a25b21745210d6c0740cb9d01), destination = the lot's cooperative |
| Stranger releases | refused, needs the verifier |
| Verifier releases | [tx](https://stellar.expert/explorer/testnet/tx/7a5033f56258d2b07811ec15ab8181a99f357a4ee91ca87f6854cb3b8f29787e) |
| Split 40/40/20 and distribute | [tx](https://stellar.expert/explorer/testnet/tx/10b962c650555e51e667313c4ac2c65ef05a886bf479894b923c4676f910f91f) |
| Attest settled trade; `matches` real / tampered | [tx](https://stellar.expert/explorer/testnet/tx/2562d242f08fb4af513974c587934f414dee7fd946360627ba649dceaf72b323); `true` / `false` |
| Second escrow on the sold lot | `Error(Contract, #11)` — `LotInEscrow` |
| Re-inspect the approved lot | `Error(Contract, #4)` — `AlreadyInspected` |

Two-party funding (buyer and verifier signing one transaction) ran on-chain here, which the upstream deployment
below lists as covered only by unit tests.

---

## Upstream AXK deployment (August 2026)

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
