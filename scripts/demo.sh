#!/usr/bin/env bash
# End-to-end trade on Stellar testnet:
#   deploy contracts -> issue RWF test token -> buyer funds escrow (buyer + verifier sign)
#   -> verifier releases to the cooperative -> splitter pays members -> attest the settled trade
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
for k in verifier buyer coop member1 member2 issuer; do
  stellar keys address "axk-$k" >/dev/null 2>&1 || stellar keys generate "axk-$k" --network "$NET" --fund >/dev/null
  printf '  %-9s %s\n' "$k" "$(addr $k)"
done

step "Deploy escrow, splitter, attestation (verifier holds all three roles on testnet)"
V=$(addr verifier)
ESCROW=$(stellar contract deploy --wasm "$WASM/axk_escrow.wasm" --source axk-verifier --network "$NET" -- --verifier "$V" 2>/dev/null)
SPLITTER=$(stellar contract deploy --wasm "$WASM/axk_splitter.wasm" --source axk-verifier --network "$NET" -- --coordinator "$V" 2>/dev/null)
ATTEST=$(stellar contract deploy --wasm "$WASM/axk_attestation.wasm" --source axk-verifier --network "$NET" -- --attester "$V" 2>/dev/null)
printf '  escrow      %s\n  splitter    %s\n  attestation %s\n' "$ESCROW" "$SPLITTER" "$ATTEST"

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
DEADLINE=$(( $(date +%s) + 30 * 86400 ))
echo "  lot $LOT -> trade_id $TID"

step "1. Buyer funds escrow (signed by buyer AND verifier)"
invoke --id "$ESCROW" --source axk-verifier --auto-sign -- create \
  --trade_id "$TID" --buyer axk-buyer --destination axk-coop \
  --token_id "$TOKEN" --amount "$AMOUNT" --deadline "$DEADLINE" 2>&1 | tail -3 | tx_link
invoke --id "$ESCROW" --source axk-verifier --send=no -- get --trade_id "$TID"

step "2. Stranger tries to release (must be refused)"
if invoke --id "$ESCROW" --source axk-buyer -- release --trade_id "$TID" >/dev/null 2>&1; then
  echo "  UNEXPECTED: release succeeded without the verifier"; exit 1
else
  echo "  refused, as designed"
fi

step "3. Verifier confirms delivery and releases to the cooperative"
invoke --id "$ESCROW" --source axk-verifier -- release --trade_id "$TID" 2>&1 | tx_link
invoke --id "$ESCROW" --source axk-verifier --send=no -- get --trade_id "$TID"

step "4. Coordinator records the split: member1 40%, member2 40%, cooperative 20%"
SHARES=$(printf '[{"party":"%s","bps":"4000"},{"party":"%s","bps":"4000"},{"party":"%s","bps":"2000"}]' \
  "$(addr member1)" "$(addr member2)" "$(addr coop)")
invoke --id "$SPLITTER" --source axk-verifier -- configure --trade_id "$TID" --shares "$SHARES" 2>&1 | tx_link

step "5. Cooperative distributes the payment"
invoke --id "$SPLITTER" --source axk-coop -- distribute \
  --trade_id "$TID" --token_id "$TOKEN" --from axk-coop --amount "$AMOUNT" 2>&1 | tx_link

step "6. Attest the settled trade (write-once digest)"
RECORD=$(printf '{"lot":"%s","trade_id":"%s","amount":"%s","token":"%s","buyer":"%s","coop":"%s"}' \
  "$LOT" "$TID" "$AMOUNT" "$TOKEN" "$(addr buyer)" "$(addr coop)")
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
ESCROW=$ESCROW
SPLITTER=$SPLITTER
ATTEST=$ATTEST
TOKEN=$TOKEN
LOT=$LOT
TRADE_ID=$TID
DIGEST=$DIGEST
EOF

step "Explorer"
echo "  escrow      $EXPLORER/contract/$ESCROW"
echo "  splitter    $EXPLORER/contract/$SPLITTER"
echo "  attestation $EXPLORER/contract/$ATTEST"
echo "  state saved to scripts/.demo-state.env"
