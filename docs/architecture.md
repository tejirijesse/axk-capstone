# Architecture

AXK Network's capstone layer: verify a commodity lot at source, hold the buyer's payment until delivery,
pay the cooperative's members, and let anyone check the result. Four Soroban contracts on Stellar
testnet do the enforcement; a Frappe app gives each role a screen and a public verification page.

## System schematic

```mermaid
flowchart LR
  subgraph Users["People"]
    C["Cooperative manager"]
    I["Inspector"]
    B["Buyer"]
    P["Anyone with a lot ref / QR"]
  end

  subgraph Frappe["Frappe v15 site · axk.localhost"]
    direction TB
    UI["/trade role screens<br/>(trade.js)"]
    PUB["/trace public verification<br/>/chain explorer"]
    API["trade_api.py<br/>access guard"]
    CH["chain.py<br/>custodial signer"]
    LIVE["stellar_live.py<br/>event reader"]
    DT[("AXK Chain Trade<br/>MariaDB")]
    SEED[("axk_network DocTypes<br/>synthetic seed")]
  end

  subgraph Keys["Server keystore"]
    KS["stellar-cli identities<br/>coop · inspector · buyer · verifier"]
  end

  subgraph Stellar["Stellar testnet (Soroban)"]
    REG["Lot registry"]
    ESC["Escrow"]
    SPL["Splitter"]
    ATT["Attestation"]
    TOK["RWF test token (SAC)"]
  end

  RPC["Soroban RPC"]

  C & I & B --> UI --> API --> CH
  CH -- "sign + submit" --> KS --> RPC
  API --> DT
  P --> PUB
  PUB --> DT
  PUB --> LIVE --> RPC
  PUB --> SEED
  RPC --> REG & ESC & SPL & ATT & TOK
  ESC -- "approved_cooperative(lot_id)" --> REG
  ESC -- "transfer" --> TOK
  SPL -- "transfer" --> TOK
```

| Layer | What it does | Where |
|---|---|---|
| Contracts | Enforce the rules: no inspection, no escrow; payee fixed by the registry; write-once records | `contracts/` |
| Signing | Builds and signs each role's transaction with a server-held testnet key, via `stellar-cli` argument lists (no shell) | `frappe_app/axk_capstone/axk_capstone/chain.py` |
| API | Validates input, enforces who may sign, stores every transaction hash | `trade_api.py` |
| Screens | Cooperative, Inspector, Buyer, lot timeline | `www/trade/`, `public/js/trade.js` |
| Public | Lot search, read-only verification page with QR, chain explorer | `www/trace/`, `www/chain.*`, `stellar_live.py` |

## One verified trade

```mermaid
sequenceDiagram
  autonumber
  actor Coop as Cooperative
  actor Insp as Inspector
  actor Buyer
  participant App as Frappe (trade_api + chain.py)
  participant Reg as Lot registry
  participant Esc as Escrow
  participant Spl as Splitter
  participant Att as Attestation
  participant Tok as RWF token

  Coop->>App: register lot (commodity, grade, kg, origin)
  App->>Reg: register_lot(coop, sha256(ref), sha256(record))
  Reg-->>App: lot_id = sha256(coop ‖ ref)
  Buyer->>App: pay before inspection
  App->>Esc: create(trade, lot_id, …)
  Esc->>Reg: approved_cooperative(lot_id)
  Reg-->>Esc: none
  Esc-->>App: Error #10 LotNotApproved (no money moves)
  Insp->>App: pass · grade A · 3,850 kg · report
  App->>Reg: inspect(lot_id, inspector, true, A, 3850, sha256(report))
  Buyer->>App: pay into escrow
  App->>Esc: create(trade, lot_id, buyer, token, amount, deadline)<br/>signed by buyer AND verifier
  Esc->>Reg: approved_cooperative(lot_id)
  Reg-->>Esc: cooperative address (becomes the payee)
  Esc->>Tok: transfer buyer → escrow
  Buyer->>App: confirm delivery
  App->>Esc: release(trade)  [verifier]
  Esc->>Tok: transfer escrow → cooperative
  App->>Spl: configure(trade, 40/40/20)  [coordinator]
  App->>Spl: distribute(trade, token, coop, amount)  [cooperative]
  Spl->>Tok: transfer coop → members
  App->>Att: attest(trade, sha256(settlement record))
```

## State machines

### Lot (lot registry)

```mermaid
stateDiagram-v2
  [*] --> Registered: register_lot · cooperative signs
  Registered --> Approved: inspect(passed=true) · authorised inspector ≠ cooperative
  Registered --> Rejected: inspect(passed=false) · reason required in the app
  Approved --> [*]
  Rejected --> [*]
  note right of Rejected
    Write-once. A fixed lot is registered again
    under a new reference; the rejection stays.
  end note
```

### Escrow (per trade)

```mermaid
stateDiagram-v2
  [*] --> Funded: create · buyer + verifier sign · lot Approved · lot not already in escrow
  Funded --> Released: release · verifier signs · pays the lot's cooperative
  Funded --> Refunded: refund · anyone, after the deadline
  Released --> [*]
  Refunded --> [*]
  note right of Refunded
    Refund frees the lot for another buyer.
    Release keeps it: the lot is sold.
  end note
```

### AXK Chain Trade (the app's record of one lot)

```mermaid
stateDiagram-v2
  [*] --> Registered
  Registered --> Approved: inspection passed
  Registered --> Rejected: inspection rejected
  Approved --> Funded: buyer pays into escrow
  Funded --> Settled: delivery confirmed → release, split, distribute, attest
  Funded --> Refunded: deadline passed
```

## Data model

```mermaid
erDiagram
  AXK_CHAIN_TRADE {
    string lot_ref PK
    string status
    string commodity
    float  quantity_kg
    string lot_record "canonical JSON"
    string lot_digest "sha256, on-chain"
    string chain_lot_id "sha256(coop ‖ ref)"
    string report_record
    string report_digest "sha256, on-chain"
    string reject_reason
    float  amount_rwf
    string trade_id
    string settlement_record
    string attest_digest "sha256, on-chain"
    string register_tx
    string inspect_tx
    string fund_tx
    string release_tx
    string split_tx
    string distribute_tx
    string attest_tx
  }
  LOT_REGISTRY_LOT {
    bytes32 lot_id PK
    address cooperative
    bytes32 lot_ref
    bytes32 digest
    enum status "Registered|Approved|Rejected"
  }
  LOT_REGISTRY_INSPECTION {
    bytes32 lot_id PK
    address inspector
    bool passed
    symbol grade
    i128 quantity_kg
    bytes32 report_digest
  }
  ESCROW_TRADE {
    bytes32 trade_id PK
    bytes32 lot_id FK
    address buyer
    address destination "from registry"
    i128 amount
    u64 deadline
    enum status "Funded|Released|Refunded"
  }
  ATTESTATION {
    bytes32 trade_id PK
    bytes32 digest
  }
  AXK_CHAIN_TRADE ||--|| LOT_REGISTRY_LOT : "chain_lot_id"
  LOT_REGISTRY_LOT ||--o| LOT_REGISTRY_INSPECTION : "inspected once"
  LOT_REGISTRY_LOT ||--o{ ESCROW_TRADE : "one live at a time"
  ESCROW_TRADE ||--o| ATTESTATION : "settled"
```

Only the right-hand side lives on-chain, and it holds digests and addresses, never the records.
The canonical JSON records stay in Frappe; anyone holding one can hash it and ask the contract
`matches(id, digest)`.

## Data sources on screen

| Screen | Source | Real or synthetic |
|---|---|---|
| `/trade/*`, `/trace/*` | AXK Chain Trade + Stellar testnet | **Real testnet transactions** |
| `/chain` · settlement, verified-before-paid | Soroban RPC events | **Real testnet transactions** |
| `/chain` · hash-chain explorer, five-year history | `axk_network` DocTypes, `axk_seed` | **Synthetic**, labelled on the page |
