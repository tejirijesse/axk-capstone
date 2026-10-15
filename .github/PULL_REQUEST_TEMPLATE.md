## What and why

<!-- What this changes and the problem it solves. Link the issue: Closes #… / Roadmap: BUY-1 -->

## How it was tested

<!-- Commands run and what you saw. For flow changes: full stack or simulation? Include a lot reference or testnet tx hash. -->

- [ ] `make test-contracts` passes (if contracts or the flow changed)
- [ ] `make test-python` passes against the server I changed
- [ ] Checked the screen on desktop and at phone width (if UI changed)

## Checklist

- [ ] One focused change; matches the style of the surrounding code
- [ ] No secret keys, seed phrases, passwords or `.env` files
- [ ] Nothing records or shows a transaction hash that is not on-chain; simulated or synthetic data is labelled
- [ ] Docs updated (README, `docs/`, roadmap status) if behaviour changed
- [ ] Contract changes: design note in the issue, a test for every new rule, existing guarantees preserved
