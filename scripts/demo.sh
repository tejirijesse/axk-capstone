#!/usr/bin/env bash
# End-to-end verified trade on Stellar testnet:
#   deploy contracts -> issue RWF test token -> cooperative registers the lot
#   -> buyer cannot pay yet -> inspector approves the lot -> buyer funds escrow (buyer + verifier sign)
#   -> verifier releases to the lot's cooperative -> splitter pays members -> attest the settled trade
#
# Usage: scripts/demo.sh            full run (deploys fresh contracts)
#        LOT=AXK-KGL-COFFEE-0002 scripts/demo.sh
set -euo pipefail

# rustup from Homebrew is keg-only; make cargo findable without a shell restart
export PATH="/opt/homebrew/opt/rustup/bin:$HOME/.cargo/bin:$PATH"
for tool in cargo stellar; do
  command -v "$tool" >/dev/null || { echo "missing $tool — see README 'Setup'"; exit 1; }
done

NET=testnet
LOT="${LOT:-AXK-KGL-COFFEE-$(date +%Y%m%d%H%M%S)}"
AMOUNT=2500000000000          # 250,000 RWF (token has 7 decimals)
DIR="$(cd "$(dirname "$0")/.." && pwd)"
WASM="$DIR/contracts/target/wasm32v1-none/release"
OUT="$DIR/scripts/.demo-state.env"
EXPLORER="https://stellar.expert/explorer/testnet"

step() { printf '\n\033[1;32m== %s\033[0m\n' "$*"; }
addr() { stellar keys address "axk-$1"; }
invoke() { stellar contract invoke --network "$NET" "$@"; }
tx_link() { grep -o 'https://stellar.expert[^ ]*' || true; }

step "Build contracts"
(cd "$DIR/contracts" && stellar contract build >/dev/null)

step "Accounts (created and funded by friendbot if missing)"
for k in verifier inspector buyer coop member1 member2 issuer; do
  stellar keys address "axk-$k" >/dev/null 2>&1 || stellar keys generate "axk-$k" --network "$NET" --fund >/dev/null
  printf '  %-9s %s\n' "$k" "$(addr $k)"
done

step "Deploy lot registry, escrow, splitter, attestation"
echo "  (verifier also holds registry admin, coordinator and attester on testnet; the inspector is a separate account)"
V=$(addr verifier)
REGISTRY=$(stellar contract deploy --wasm "$WASM/axk_lot_registry.wasm" --source axk-verifier --network "$NET" -- --admin "$V" 2>/dev/null)
ESCROW=$(stellar contract deploy --wasm "$WASM/axk_escrow.wasm" --source axk-verifier --network "$NET" -- --verifier "$V" --registry "$REGISTRY" 2>/dev/null)
SPLITTER=$(stellar contract deploy --wasm "$WASM/axk_splitter.wasm" --source axk-verifier --network "$NET" -- --coordinator "$V" 2>/dev/null)
ATTEST=$(stellar contract deploy --wasm "$WASM/axk_attestation.wasm" --source axk-verifier --network "$NET" -- --attester "$V" 2>/dev/null)
printf '  registry    %s\n  escrow      %s\n  splitter    %s\n  attestation %s\n' "$REGISTRY" "$ESCROW" "$SPLITTER" "$ATTEST"
invoke --id "$REGISTRY" --source axk-verifier -- add_inspector --inspector axk-inspector 2>&1 | tx_link

step "RWF test token (local-currency stand-in, no real value)"
ASSET="RWF:$(addr issuer)"
TOKEN=$(stellar contract id asset --asset "$ASSET" --network "$NET")
stellar contract asset deploy --asset "$ASSET" --source axk-issuer --network "$NET" >/dev/null 2>&1 || true
for k in buyer coop member1 member2; do
  stellar tx new change-trust --line "$ASSET" --source "axk-$k" --network "$NET" >/dev/null 2>&1 || true
done
stellar tx new payment --destination "$(addr buyer)" --asset "$ASSET" --amount "$AMOUNT" \
  --source axk-issuer --network "$NET" >/dev/null
echo "  token $TOKEN"

TID=$(printf '%s' "$LOT" | shasum -a 256 | cut -d' ' -f1)
LOT_REF=$(printf 'lot:%s' "$LOT" | shasum -a 256 | cut -d' ' -f1)
LOT_RECORD=$(printf '{"lot":"%s","commodity":"Coffee (parchment)","grade":"A","quantity_kg":3850,"origin":"Huye, Southern Province","cooperative":"%s"}' "$LOT" "$(addr coop)")
LOT_DIGEST=$(printf '%s' "$LOT_RECORD" | shasum -a 256 | cut -d' ' -f1)
REPORT_DIGEST=$(printf 'inspection-report:%s:grade A:3850kg:moisture 11.8%%' "$LOT" | shasum -a 256 | cut -d' ' -f1)
DEADLINE=$(( $(date +%s) + 30 * 86400 ))
echo "  lot $LOT -> trade_id $TID"

step "1. Cooperative registers the lot (digest of the lot record)"
LOT_ID=$(invoke --id "$REGISTRY" --source axk-coop -- register_lot \
  --cooperative axk-coop --lot_ref "$LOT_REF" --digest "$LOT_DIGEST" 2>/dev/null | tr -d '"')
echo "  on-chain lot_id $LOT_ID"
invoke --id "$REGISTRY" --source axk-verifier --send=no -- get --lot_id "$LOT_ID"

step "2. Buyer tries to fund before inspection (must be refused)"
if invoke --id "$ESCROW" --source axk-verifier --auto-sign -- create \
    --trade_id "$TID" --lot_id "$LOT_ID" --buyer axk-buyer \
    --token_id "$TOKEN" --amount "$AMOUNT" --deadline "$DEADLINE" >/dev/null 2>&1; then
  echo "  UNEXPECTED: escrow accepted money for an uninspected lot"; exit 1
else
  echo "  refused: LotNotApproved"
fi

step "3. The cooperative tries to inspect its own lot (must be refused)"
if invoke --id "$REGISTRY" --source axk-coop -- inspect --lot_id "$LOT_ID" --inspector axk-coop \
    --passed true --grade A --quantity_kg 3850 --report_digest "$REPORT_DIGEST" >/dev/null 2>&1; then
  echo "  UNEXPECTED: a non-inspector approved a lot"; exit 1
else
  echo "  refused: NotAnInspector"
fi

step "4. Inspector signs the inspection: passed, grade A, 3,850 kg"
invoke --id "$REGISTRY" --source axk-inspector -- inspect --lot_id "$LOT_ID" --inspector axk-inspector \
  --passed true --grade A --quantity_kg 3850 --report_digest "$REPORT_DIGEST" 2>&1 | tx_link
invoke --id "$REGISTRY" --source axk-verifier --send=no -- get_inspection --lot_id "$LOT_ID"

step "5. Buyer funds escrow for the inspected lot (buyer AND verifier sign; payee comes from the registry)"
invoke --id "$ESCROW" --source axk-verifier --auto-sign -- create \
  --trade_id "$TID" --lot_id "$LOT_ID" --buyer axk-buyer \
  --token_id "$TOKEN" --amount "$AMOUNT" --deadline "$DEADLINE" 2>&1 | tail -3 | tx_link
invoke --id "$ESCROW" --source axk-verifier --send=no -- get --trade_id "$TID"

step "6. Stranger tries to release (must be refused)"
if invoke --id "$ESCROW" --source axk-buyer -- release --trade_id "$TID" >/dev/null 2>&1; then
  echo "  UNEXPECTED: release succeeded without the verifier"; exit 1
else
  echo "  refused, as designed"
fi

step "7. Verifier confirms delivery and releases to the lot's cooperative"
invoke --id "$ESCROW" --source axk-verifier -- release --trade_id "$TID" 2>&1 | tx_link
invoke --id "$ESCROW" --source axk-verifier --send=no -- get --trade_id "$TID"

step "8. Coordinator records the split: member1 40%, member2 40%, cooperative 20%"
SHARES=$(printf '[{"party":"%s","bps":"4000"},{"party":"%s","bps":"4000"},{"party":"%s","bps":"2000"}]' \
  "$(addr member1)" "$(addr member2)" "$(addr coop)")
invoke --id "$SPLITTER" --source axk-verifier -- configure --trade_id "$TID" --shares "$SHARES" 2>&1 | tx_link

step "9. Cooperative distributes the payment"
invoke --id "$SPLITTER" --source axk-coop -- distribute \
  --trade_id "$TID" --token_id "$TOKEN" --from axk-coop --amount "$AMOUNT" 2>&1 | tx_link

step "10. Attest the settled trade (write-once digest)"
RECORD=$(printf '{"lot":"%s","lot_id":"%s","trade_id":"%s","amount":"%s","token":"%s","buyer":"%s","coop":"%s"}' \
  "$LOT" "$LOT_ID" "$TID" "$AMOUNT" "$TOKEN" "$(addr buyer)" "$(addr coop)")
DIGEST=$(printf '%s' "$RECORD" | shasum -a 256 | cut -d' ' -f1)
invoke --id "$ATTEST" --source axk-verifier -- attest --trade_id "$TID" --digest "$DIGEST" 2>&1 | tx_link
printf '  matches(real record)     = %s\n' "$(invoke --id "$ATTEST" --source axk-verifier --send=no -- matches --trade_id "$TID" --digest "$DIGEST")"
FAKE=$(printf '%s' "${RECORD/250/999}" | shasum -a 256 | cut -d' ' -f1)
printf '  matches(tampered record) = %s\n' "$(invoke --id "$ATTEST" --source axk-verifier --send=no -- matches --trade_id "$TID" --digest "$FAKE")"

step "Final RWF balances"
for k in buyer coop member1 member2; do
  printf '  %-8s %s\n' "$k" "$(invoke --id "$TOKEN" --source axk-verifier --send=no -- balance --id "$(addr $k)")"
done

cat > "$OUT" <<EOF
REGISTRY=$REGISTRY
LOT_ID=$LOT_ID
ESCROW=$ESCROW
SPLITTER=$SPLITTER
ATTEST=$ATTEST
TOKEN=$TOKEN
LOT=$LOT
TRADE_ID=$TID
DIGEST=$DIGEST
EOF

step "Explorer"
echo "  registry    $EXPLORER/contract/$REGISTRY"
echo "  escrow      $EXPLORER/contract/$ESCROW"
echo "  splitter    $EXPLORER/contract/$SPLITTER"
echo "  attestation $EXPLORER/contract/$ATTEST"
echo "  state saved to scripts/.demo-state.env"
