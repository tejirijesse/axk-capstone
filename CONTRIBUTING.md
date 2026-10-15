# Contributing

Thank you for helping. AXK Capstone is a verification and settlement layer for cross-border agricultural trade
on Stellar. It works end to end today, and [ROADMAP.md](ROADMAP.md) lists what comes next, track by track, from
starter tasks to contract work.

## Ways to help

- **Pick a roadmap item.** Comment on its issue (or open one quoting the ID, e.g. `BUY-1`) before you start.
- **Report a bug** with the bug template: what you did, what you expected, what happened.
- **Improve the docs.** If a step confused you, it will confuse the next person.
- **Translate** the screens (Kinyarwanda, French, Swahili — roadmap I18N-1).
- **Review pull requests.** A second pair of eyes on contract changes is especially valuable.

## Two ways to run it

| | Offline simulation | Full stack (real Stellar testnet) |
|---|---|---|
| Command | `make run` | `make run-frappe` |
| Needs | Python 3 only | Frappe v15 bench, MariaDB, Redis, Rust, stellar-cli |
| Blockchain | **None.** Hashes are computed locally and labelled *simulated* | Every action is a real testnet transaction |
| Good for | UI work, layout, copy, quick look | Anything touching `chain.py`, the API, or contracts |

The simulation exists so UI contributors can start in two minutes. It must stay clearly labelled as a simulation
and must never link its hashes to a block explorer (see *Data honesty* below).

### Full stack setup

1. **Contracts:** `make toolchain && make test && make build` (Rust, the `wasm32v1-none` target, stellar-cli).
2. **Frappe:** install a [Frappe v15 bench](https://frappeframework.com/docs/user/en/installation). ERPNext is
   not required.
3. **App:** `make install-app` (links `frappe_app/axk_capstone` into the bench and installs it on the site).
4. **Contracts on testnet:** `make demo` deploys fresh contracts and creates funded testnet accounts, then
   `make contracts-config` points the site at them.
5. **Run:** `make run-frappe` and open `http://localhost:8000/trade`. For local development set
   `bench --site <site> set-config axk_demo_mode 1`; demo mode only ever accepts requests made directly on your
   own machine.

The detailed setup, including macOS notes, is in the [README](README.md#quickstart--setup).

## Making a change

1. **Branch** from `main`: `feat/buy-1-refund-button`, `fix/port-seal-message`, `docs/ubuntu-setup`.
2. **Keep it focused.** One roadmap item or one bug per pull request.
3. **Match the code around you.** Same naming, same comment density, same patterns. Rust: `cargo fmt` and
   `cargo clippy`. Python: follow PEP 8 and the existing style. JavaScript: plain DOM, no framework, insert
   server data with `textContent`, never `innerHTML`.
4. **Test.**
   - Contracts: `make test-contracts`. Every new guarantee gets a test named for what it guarantees
     (`a_rejected_lot_cannot_be_funded`, not `test_create_2`).
   - Flow: `make test-python` runs the end-to-end suite against whatever is serving `localhost:8000`.
   - UI: try the screen on desktop and at phone width.
5. **Update docs** when behaviour changes: the README, `docs/`, and the roadmap item's status.
6. **Commit** with [Conventional Commits](https://www.conventionalcommits.org/):
   `feat(buy): add refund after deadline`, `fix(port): reject mismatched seal`, `docs: ubuntu setup`.
7. **Open a pull request** with the template filled in, linking the issue.

## Rules that are not negotiable

**Data honesty.** This project is about trustworthy records, so the project itself must be trustworthy.
- Never record or display a transaction hash that is not on-chain as if it were. If a chain call fails, the step
  fails and nothing is saved.
- Simulated and synthetic data is always labelled as such on screen.
- Never present demo or synthetic data as research findings.

**Keys and secrets.**
- Never commit a secret key, seed phrase, `.env` file, or password. Testnet keys live in the stellar-cli keystore
  on your own machine.
- Testnet only. Nothing in this repository is audited for mainnet; do not point it at real funds.

**Contracts.** Changes to `contracts/` need a design note in the issue first, tests for every new rule, and a
maintainer's review. Preserve the existing guarantees in [docs/security.md](docs/security.md) — for example,
escrow release must never accept a destination address.

## Continuous integration

A workflow that runs the contract tests and builds on every pull request is roadmap item DEV-1. Proposed file
`.github/workflows/contracts.yml`:

```yaml
name: contracts
on:
  push: { paths: ["contracts/**", ".github/workflows/contracts.yml"] }
  pull_request: { paths: ["contracts/**", ".github/workflows/contracts.yml"] }
jobs:
  test-and-build:
    runs-on: ubuntu-latest
    defaults: { run: { working-directory: contracts } }
    steps:
      - uses: actions/checkout@v4
      - uses: dtolnay/rust-toolchain@stable
        with: { targets: wasm32v1-none }
      - uses: Swatinem/rust-cache@v2
        with: { workspaces: contracts }
      - run: cargo test --locked
      - run: cargo build --locked --release --target wasm32v1-none
```

## Licence

By contributing you agree that your contribution is licensed under the [MIT License](LICENSE), the same as the
rest of the project.

## Code of conduct

Everyone taking part is expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
