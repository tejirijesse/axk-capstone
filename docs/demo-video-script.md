# Demo video script (target 8 minutes, limit 10)

The brief asks for demonstration over description, so the introduction is 30 seconds and everything else
is the product working. Talking points are cues, not lines to read.

## Before recording

- [ ] `make run` in one terminal; open http://axk.localhost:8000/trade
- [ ] `make demo` in a second terminal **within the last few days** — the explorer only sees ~7 days of testnet events
- [ ] If `make demo` deployed new contracts: `make contracts-config`, then reload the pages
- [ ] Buyer wallet has at least 500,000 RWF (Buyer screen → *Top up* if not)
- [ ] Browser at 1280×800 or larger, zoom 100%, notifications off
- [ ] A second tab on https://stellar.expert/explorer/testnet to show transactions opening
- [ ] Terminal font large enough to read

## Shot list

| Time | Screen | Do | Say |
|---|---|---|---|
| 0:00–0:30 | `/trade` overview | Nothing — let the page sit | One line on the problem: buyers can't verify goods across a border and payment is slow and untrusted. This layer puts verification and settlement in one workflow on Stellar. Name the three roles on screen. |
| 0:30–1:15 | Terminal | `make test` | 65 contract tests across four Soroban contracts. Point at the lot registry and escrow suites. |
| 1:15–2:15 | `/trade/coop` | Register a lot: coffee, grade A, 3,850 kg, Huye | Only a SHA-256 digest goes on-chain. The id is bound to the cooperative's address, so nobody can squat a real lot. Click the transaction link in the toast; Stellar Expert opens. |
| 2:15–2:45 | `/trade/buy` | Show the lot is **not** listed | Uninspected lots never appear, and the escrow contract refuses payment for them anyway (`LotNotApproved`, recorded in `docs/deployments.md`). |
| 2:45–4:00 | `/trade/inspect` | Use `j`/`k` to move, `r` to show reject reasons, then `a`, adjust moisture, **Sign: pass** | Oldest lot first. A rejection needs a structured reason and is permanent. A cooperative cannot inspect its own lot. Signed once, on-chain. |
| 4:00–5:00 | `/trade/buy` | Lot now listed with "Inspected by…". **Pay into escrow** 250,000 RWF | Buyer and AXK verifier both sign. There is no payee field: the escrow asks the registry who owns this inspected lot. Balance drops. |
| 5:00–6:00 | `/trade/buy` | **Confirm delivery** | Four transactions: release, record the 40/40/20 split, pay members, attest. |
| 6:00–6:45 | `/trade/lot?name=…` | Scroll the seven-step timeline; **Check records against the chain**; **Download record** | Every payment traces back to release, escrow, inspection and registration. The browser re-hashes the records and the contracts confirm the match. |
| 6:45–7:15 | *Public page ↗* → `/trace/lot` | Show verdict, QR, privacy note | This is what a buyer's own customer sees, no login. Hashes and statuses are public; names and farmer data never are. |
| 7:15–8:15 | `/chain` | Money-flow diagram, *Verified before paid* table; scroll to the hash-chain explorer, **Verify chain**, then **Tamper with an event** | Live testnet data. In the hash chain, changing one weight breaks that event and every event after it. Say that the history charts below are synthetic demo data. |
| 8:15–8:30 | `/trade` | Back to overview | Close: verified at source, paid safely, split fairly, checkable by anyone. |

## If something goes wrong on camera

- **"Stellar testnet did not answer in time"**: testnet is slow; retry once. The record is only saved when the transaction succeeds.
- **Buyer can't pay**: *Top up* on the Buyer screen, or pay a smaller amount.
- **Explorer shows no live events**: run `make demo` again; the RPC keeps about a week.
