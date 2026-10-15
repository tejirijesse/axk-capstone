# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Open-source scaffolding: contribution guide, code of conduct, security policy, governance, roadmap,
  issue and pull request templates.
- The optional five-year history on `/chain` now explains itself when not installed instead of failing.

### Changed
- `axk_capstone` no longer requires AXK's private platform app; it runs on a plain Frappe v15 site.
- The standalone runner is labelled an **offline simulation** everywhere: it never claims to sign on Stellar
  and never links its locally computed hashes to a block explorer.

### Fixed
- Logistics and port steps no longer record an invented transaction hash when the chain call fails; the step
  fails and nothing is saved.

## [0.1.0] - 2026-10-15

### Added
- Soroban contracts: lot registry (inspection gate), escrow (payee from the registry, one live escrow per lot),
  splitter (exact 40/40/20 payouts), attestation (write-once digests). 65 tests.
- Frappe app `axk_capstone`: Cooperative, Inspector, Buyer, Logistics and Port screens; lot timeline;
  public `/trace` with QR; `/chain` explorer with live testnet flow and an in-browser hash-chain verifier.
- `scripts/demo.sh`: deploys fresh contracts and runs a verified trade on Stellar testnet.
- Offline simulation (`scripts/server.py`) and an end-to-end test suite (`scripts/test_trade.py`).
