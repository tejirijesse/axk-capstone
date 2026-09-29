# AXK Network — Verification & Settlement Layer

**Capstone project · BSE Software Engineering (Low-Level / Blockchain track) · African Leadership University · 2026**
Oghenetejiri Jesse · Supervisor: Junior Turatsinze

A cryptographic verification-and-settlement layer for cross-border agricultural commodity trade in East Africa. A cooperative lists a commodity lot, an inspector attests to its quality, quantity and provenance on-chain, the buyer's payment is held in a smart-contract escrow, and the funds are released and split to the cooperative's members only once delivery is verified. A tamper-evident digest of every settled trade is written to the ledger so a lender or regulator can check a record without trusting AXK.

Pilot scope: Kigali cooperatives trading on the Rwanda–DRC / Rwanda–Uganda corridor.

- **Repository:** https://github.com/tejirijesse/axk-capstone
- **Demo video:** _to be added_

---

## Architecture

```
 Web app (Coop · Buyer · Inspector)        Stellar testnet (Soroban)
 ─────────────────────────────────         ──────────────────────────────
  register lot ───────────────────────────▶ Lot registry  Registered
  inspect & sign ─────────────────────────▶ Lot registry  Approved / Rejected
  fund escrow ──── only if Approved ──────▶ Escrow        Funded (payee = lot's cooperative)
  confirm delivery → verifier releases ───▶ Escrow        Released ──▶ Splitter
  attest settled trade ───────────────────▶ Attestation   write-once digest
  dashboard ◀──────────────── contract events / RPC reads
```

| Component | Path | Status |
|---|---|---|
| Lot / inspection registry | `contracts/lot_registry` | Done · 18 tests · on testnet |
| Escrow contract (inspection-gated) | `contracts/escrow` | Done · 27 tests · on testnet |
| Payment splitter | `contracts/splitter` | Done · 12 tests · on testnet |
| Attestation registry | `contracts/attestation` | Done · 8 tests · on testnet |
| Chain explorer (live testnet flow, hash-chain verifier, history) | `frappe_app/axk_capstone` → `/chain` | Done |
| Role screens (Coop · Inspector · Buyer) | `frappe_app/axk_capstone` | In progress |
| System schematic & state diagrams | `docs/design/` | In progress |

Contract design notes and the security rationale for each guarantee are in [contracts/README.md](contracts/README.md). Testnet contract IDs and what was exercised on-chain are in [docs/deployments.md](docs/deployments.md).

## Tech stack

| Layer | Technology |
|---|---|
| Smart contracts | Rust, Soroban (`soroban-sdk` 22), target `wasm32v1-none` |
| Chain | Stellar testnet |
| Tooling | `stellar-cli` 28, `cargo` |
| Frontend | Next.js, Freighter wallet, `@stellar/stellar-sdk` |

## Setup

Requires macOS or Linux, Rust (via `rustup`), and `stellar-cli`.

```bash
# toolchain (macOS)
brew install rustup stellar-cli
rustup default stable
rustup target add wasm32v1-none

# clone
git clone https://github.com/tejirijesse/axk-capstone.git
cd axk-capstone/contracts

# test and build
cargo test                 # 65 tests
stellar contract build     # wasm output in target/wasm32v1-none/release/
```

### Deploy to testnet

```bash
stellar keys generate dev --network testnet --fund
# or run the whole verified trade end to end (deploys fresh contracts):
../scripts/demo.sh
```

## Designs

_Screenshots, system schematic and state diagrams will be added to `docs/design/`._

## Deployment plan

| Stage | Target |
|---|---|
| Contracts | Stellar testnet (current). Mainnet only after an external audit and with the verifier, coordinator and attester roles held by three separately custodied accounts. |
| Frontend | Vercel |
| Cash-out | Stellar SEP-24 anchor (MoneyGram sandbox) for local-currency payout; production onboarding is outside capstone scope. |

## Provenance

The escrow, splitter and attestation contracts originate in AXK Network, the author's venture (`AXKNETWORK/axk-stellar`, MIT) and are included here as the settlement core of this capstone.

## License

MIT — see [LICENSE](LICENSE).
