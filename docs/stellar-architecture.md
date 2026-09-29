# Architecture

## The problem this solves

A cooperative in Rwanda ships a container of coffee to a roaster in Germany. The buyer pays. Somewhere between that payment and a farmer collecting money in a village, four things have to happen: the delivery has to be verified, the money has to be held until it is, it has to be split between the cooperative, its members and whoever financed the season, and each member has to be able to turn their share into cash.

Stellar is a good fit for the last two. Payments settle in seconds for a fraction of a cent, USDC is a real dollar rather than a volatile token, and the SEP standards mean the cash-out leg is an integration rather than a bilateral negotiation with every payout provider in every country.

## Where the boundary sits

Not everything belongs on a ledger.

**On chain:** custody of funds in escrow, the split, and a digest of the settled trade record. These are the parts where being able to prove what happened, without trusting AXK, is the whole point.

**Off chain:** the trade documents, quality grades, inspection photographs, KYC records and the buyer relationship. Putting any of it on a public ledger would leak commercially sensitive terms and personal data, and none of it needs to be there. What goes on chain is a hash over a canonical serialisation of the record, so a lender can verify the record they were shown is the record that settled, without the ledger carrying the contents.

## Components

```
 AXK platform                          this repository
┌──────────────────────┐              ┌────────────────────────────┐
│ trade record         │              │ packages/anchors           │
│ verification         │─────────────▶│  SEP-10 authentication     │
│ escrow state machine │              │  SEP-24 cash-in / cash-out │
│ buyer + coop UI      │              │  transaction watcher       │
└──────────────────────┘              │  HTTP API, CLI             │
                                      └────────────┬───────────────┘
                                                   │
                                      ┌────────────▼───────────────┐
                                      │ contracts (design stage)   │
                                      │  escrow                    │
                                      │  splitter                  │
                                      │  attestation registry      │
                                      └────────────────────────────┘
```

The platform owns the trade. This repository owns everything that speaks to Stellar or to an anchor, so those parts can be reviewed on their own.

## Custodial accounts, and why

Producers do not hold keys.

A farmer with a seed phrase is a farmer one lost phone away from losing a season's income, with nobody to call. So AXK holds the Stellar account and identifies each user by an integer memo on the transaction. This is the model MoneyGram's custodial integration is built around, and it is what makes the cash-out leg reachable for someone who has never used a wallet.

The trade-off is real and worth stating: custody means AXK can, technically, move user funds. That is a licensing question before it is an engineering one, and it is why balances held on behalf of cooperatives are a treasury and controls problem, not just a key-storage one.

The contracts are designed so that escrowed funds are not in that position. Funds locked for a specific trade are released to a destination fixed when the escrow was created, so even a compromised AXK operator cannot redirect them.

## The two failure modes that actually cost money

Most of the care in `packages/anchors` is spent on these.

**Paying twice.** The cash-out flow watches an anchor transaction and submits a USDC payment when the anchor asks for it. If the process crashes between submitting that payment and recording that it was submitted, a naive implementation pays again on restart. An in-memory flag does not help, because the memory is gone. So before sending, the client re-reads the transaction from the anchor and checks whether `stellar_transaction_id` is already stamped on it. The anchor's record is the authority, not ours.

**Paying into a closed window.** The anchor gives a deadline in `user_action_required_by`, typically thirty minutes. USDC sent after it passes is not returned and no cash is handed over at the other end. The client refuses to send once the deadline is behind it.

Both decisions live in `decideSend`, a pure function with no network and no ambient clock, so they are tested directly rather than inferred from an integration run.

## What is deliberately not here yet

**Routing.** With one anchor there is nothing to route between. When there are two or more, the choice is not round-robin: an anchor is only a substitute for another if it serves that producer's country, currency, instrument and KYC tier. Treating rails as interchangeable is how someone gets paid into a channel they cannot collect from.

**Failover on ambiguity.** A request that times out has not necessarily failed. Retrying a payment on a second rail because the first went quiet is how you pay twice across two providers, which is worse than paying twice on one because reconciliation has to span both. A rail has to be confirmed not to have settled before anything is retried elsewhere.

Neither is written yet, and both are named here so the omission is visible rather than discovered.

## Standards in use

| SEP | Use |
|---|---|
| SEP-1 | Anchor discovery through `stellar.toml` |
| SEP-9 | Standard KYC field names passed to the anchor |
| SEP-10 | Authentication, custodial, one account with a memo per user |
| SEP-24 | Interactive deposit and withdrawal, with the anchor hosting KYC |

SEP-6, SEP-12, SEP-31 and SEP-38 are planned. See [roadmap.md](roadmap.md).
