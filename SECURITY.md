# Security policy

## Status

AXK Capstone runs on **Stellar testnet only**. The contracts have **not been audited**. Do not use them with
real funds. The road to mainnet is in [ROADMAP.md](ROADMAP.md#10--toward-mainnet).

What the contracts guarantee, and the test that pins each guarantee, is in
[docs/security.md](docs/security.md).

## Reporting a vulnerability

Please report security problems **privately**, not in a public issue:

- Use GitHub's private vulnerability reporting (**Security → Report a vulnerability** on the repository), or
- contact a maintainer listed in [GOVERNANCE.md](GOVERNANCE.md).

Include what you found, how to reproduce it (a failing test is ideal), and the impact. We aim to acknowledge
reports within 7 days and will credit you in the fix unless you prefer otherwise.

## Especially interesting

- Any way to move escrowed funds to anyone other than the lot's registered cooperative.
- Funding escrow for a lot that has not passed inspection, or selling one lot twice.
- An inspection by someone who is not an authorised inspector, or by the lot's own cooperative.
- Overwriting a write-once record (lot, inspection, split, attestation).
- Getting the application to sign a transaction for a request that is not allowed to (see the access guard in
  `frappe_app/axk_capstone/axk_capstone/trade_api.py`).
- Any path where the application records a transaction hash that is not on-chain.

## Out of scope

- Findings that need a stolen server key or a compromised machine.
- Testnet availability or Friendbot limits.
- The offline simulation (`scripts/server.py`), which by design signs nothing.
