#![cfg(test)]

use super::*;
use axk_lot_registry::{LotRegistry, LotRegistryClient};
use soroban_sdk::{
    symbol_short,
    testutils::{Address as _, Ledger},
    token::{StellarAssetClient, TokenClient},
    Env,
};

const DAY: u64 = 86_400;

struct Fixture<'a> {
    env: Env,
    escrow: EscrowClient<'a>,
    registry: LotRegistryClient<'a>,
    token: TokenClient<'a>,
    buyer: Address,
    /// The cooperative that registered the lot, and so the only possible payee.
    destination: Address,
    verifier: Address,
    inspector: Address,
    lot: BytesN<32>,
}

fn setup() -> Fixture<'static> {
    let env = Env::default();
    env.mock_all_auths();

    let issuer = Address::generate(&env);
    let asset = env.register_stellar_asset_contract_v2(issuer.clone());
    let token = TokenClient::new(&env, &asset.address());
    let minter = StellarAssetClient::new(&env, &asset.address());

    let buyer = Address::generate(&env);
    let destination = Address::generate(&env);
    let verifier = Address::generate(&env);
    let inspector = Address::generate(&env);
    let admin = Address::generate(&env);
    minter.mint(&buyer, &1_000);

    let registry = LotRegistryClient::new(&env, &env.register(LotRegistry, (admin,)));
    registry.add_inspector(&inspector);
    let lot = inspected_lot(&env, &registry, &destination, &inspector, 1, true);

    let escrow = EscrowClient::new(&env, &env.register(Escrow, (verifier.clone(), registry.address.clone())));

    Fixture { env, escrow, registry, token, buyer, destination, verifier, inspector, lot }
}

fn inspected_lot(
    env: &Env,
    registry: &LotRegistryClient,
    coop: &Address,
    inspector: &Address,
    n: u8,
    passed: bool,
) -> BytesN<32> {
    let lot = registry.register_lot(coop, &trade_id(env, 100 + n), &trade_id(env, 200 + n));
    registry.inspect(&lot, inspector, &passed, &symbol_short!("A"), &3_850, &trade_id(env, 250));
    lot
}

fn trade_id(env: &Env, n: u8) -> BytesN<32> {
    let mut bytes = [0u8; 32];
    bytes[31] = n;
    BytesN::from_array(env, &bytes)
}

fn fund(f: &Fixture, id: &BytesN<32>, amount: i128) {
    let deadline = f.env.ledger().timestamp() + 30 * DAY;
    f.escrow.create(id, &f.lot, &f.buyer, &f.token.address, &amount, &deadline);
}

#[test]
fn funds_move_from_the_buyer_into_the_contract() {
    let f = setup();
    let id = trade_id(&f.env, 1);
    fund(&f, &id, 250);

    assert_eq!(f.token.balance(&f.buyer), 750);
    assert_eq!(f.token.balance(&f.escrow.address), 250);
    assert_eq!(f.escrow.get(&id).status, Status::Funded);
}

#[test]
fn release_pays_the_destination_fixed_at_creation() {
    let f = setup();
    let id = trade_id(&f.env, 1);
    fund(&f, &id, 250);

    f.escrow.release(&id);

    assert_eq!(f.token.balance(&f.destination), 250);
    assert_eq!(f.token.balance(&f.escrow.address), 0);
    assert_eq!(f.escrow.get(&id).status, Status::Released);
}

#[test]
fn there_is_no_way_to_name_a_destination_at_release() {
    // The guarantee this contract exists for. `release` takes only a trade id,
    // so a compromised verifier has no parameter through which to redirect
    // funds. If this ever stops compiling because release gained an address
    // argument, that is the regression.
    let f = setup();
    let id = trade_id(&f.env, 1);
    fund(&f, &id, 250);

    let attacker = Address::generate(&f.env);
    f.escrow.release(&id);

    assert_eq!(f.token.balance(&attacker), 0);
    assert_eq!(f.token.balance(&f.destination), 250);
}

#[test]
fn release_twice_is_refused() {
    let f = setup();
    let id = trade_id(&f.env, 1);
    fund(&f, &id, 250);
    f.escrow.release(&id);

    assert_eq!(f.escrow.try_release(&id), Err(Ok(Error::NotFunded)));
    assert_eq!(f.token.balance(&f.destination), 250);
}

#[test]
fn a_released_trade_cannot_then_be_refunded() {
    let f = setup();
    let id = trade_id(&f.env, 1);
    fund(&f, &id, 250);
    f.escrow.release(&id);

    f.env.ledger().set_timestamp(f.env.ledger().timestamp() + 60 * DAY);

    assert_eq!(f.escrow.try_refund(&id), Err(Ok(Error::NotFunded)));
    assert_eq!(f.token.balance(&f.buyer), 750);
}

#[test]
fn a_refunded_trade_cannot_then_be_released() {
    let f = setup();
    let id = trade_id(&f.env, 1);
    fund(&f, &id, 250);

    f.env.ledger().set_timestamp(f.env.ledger().timestamp() + 60 * DAY);
    f.escrow.refund(&id);

    assert_eq!(f.escrow.try_release(&id), Err(Ok(Error::NotFunded)));
    assert_eq!(f.token.balance(&f.destination), 0);
    assert_eq!(f.token.balance(&f.buyer), 1_000);
}

#[test]
fn refund_before_the_deadline_is_refused() {
    let f = setup();
    let id = trade_id(&f.env, 1);
    fund(&f, &id, 250);

    assert_eq!(f.escrow.try_refund(&id), Err(Ok(Error::DeadlineNotReached)));
    assert_eq!(f.token.balance(&f.escrow.address), 250);
}

#[test]
fn refund_after_the_deadline_returns_the_buyer_their_money() {
    let f = setup();
    let id = trade_id(&f.env, 1);
    fund(&f, &id, 250);

    f.env.ledger().set_timestamp(f.env.ledger().timestamp() + 31 * DAY);
    f.escrow.refund(&id);

    assert_eq!(f.token.balance(&f.buyer), 1_000);
    assert_eq!(f.escrow.get(&id).status, Status::Refunded);
}

#[test]
fn a_second_escrow_cannot_reuse_a_trade_id() {
    let f = setup();
    let id = trade_id(&f.env, 1);
    fund(&f, &id, 250);

    let deadline = f.env.ledger().timestamp() + 30 * DAY;
    assert_eq!(
        f.escrow.try_create(&id, &f.lot, &f.buyer, &f.token.address, &100, &deadline),
        Err(Ok(Error::TradeExists)),
    );
    assert_eq!(f.token.balance(&f.escrow.address), 250);
}

#[test]
fn a_zero_or_negative_amount_is_refused() {
    let f = setup();
    let deadline = f.env.ledger().timestamp() + 30 * DAY;
    for (n, amount) in [(2u8, 0i128), (3, -100)] {
        assert_eq!(
            f.escrow.try_create(
                &trade_id(&f.env, n), &f.lot, &f.buyer,
                &f.token.address, &amount, &deadline,
            ),
            Err(Ok(Error::AmountNotPositive)),
        );
    }
}

#[test]
fn a_deadline_already_past_is_refused() {
    // Otherwise the escrow is refundable the moment it is funded, which is a
    // way to lock a buyer's money into a contract that immediately gives it
    // back and leaves the trade looking settled.
    let f = setup();
    f.env.ledger().set_timestamp(1_000);
    let deadline = f.env.ledger().timestamp();
    assert_eq!(
        f.escrow.try_create(
            &trade_id(&f.env, 4), &f.lot, &f.buyer,
            &f.token.address, &100, &deadline,
        ),
        Err(Ok(Error::DeadlineInPast)),
    );
}

#[test]
fn a_deadline_beyond_the_records_own_lifetime_is_refused() {
    // The record is kept alive for 180 days and only refreshed when something
    // reads it. A trade nobody touches until a 300-day deadline could have its
    // entry archived before then, which is the money stranded behind an
    // unreadable record that the TTL handling exists to prevent.
    let f = setup();
    let deadline = f.env.ledger().timestamp() + 300 * DAY;
    assert_eq!(
        f.escrow.try_create(
            &trade_id(&f.env, 5), &f.lot, &f.buyer,
            &f.token.address, &100, &deadline,
        ),
        Err(Ok(Error::DeadlineTooFar)),
    );
}

#[test]
fn create_demands_the_verifier_signature_as_well_as_the_buyer() {
    // trade_id is caller-supplied and can only be occupied once, so without the
    // verifier's signature anyone could fund a one-stroop trade under a real
    // trade's id, block it permanently, and reclaim their stroop at the
    // deadline. Both signatures are asked for.
    let f = setup();
    fund(&f, &trade_id(&f.env, 1), 250);

    let auths = f.env.auths();
    assert!(auths.iter().any(|(a, _)| a == &f.buyer), "the buyer was not asked to sign");
    assert!(auths.iter().any(|(a, _)| a == &f.verifier), "the verifier was not asked to sign");
}

#[test]
fn a_stranger_cannot_squat_a_trade_id() {
    // No mocked auths here: the lot is inspected and approved, so the missing
    // signatures are the only thing standing between a squatter and the trade id.
    let env = Env::default();
    let issuer = Address::generate(&env);
    let asset = env.register_stellar_asset_contract_v2(issuer);
    let token = TokenClient::new(&env, &asset.address());
    let verifier = Address::generate(&env);
    let squatter = Address::generate(&env);
    let coop = Address::generate(&env);
    let inspector = Address::generate(&env);
    let admin = Address::generate(&env);
    let registry = LotRegistryClient::new(&env, &env.register(LotRegistry, (admin,)));
    env.mock_all_auths();
    registry.add_inspector(&inspector);
    let lot = inspected_lot(&env, &registry, &coop, &inspector, 1, true);
    env.set_auths(&[]);
    let escrow = EscrowClient::new(&env, &env.register(Escrow, (verifier, registry.address.clone())));

    let deadline = env.ledger().timestamp() + 30 * DAY;
    let result = escrow.try_create(&trade_id(&env, 1), &lot, &squatter, &token.address, &1, &deadline);
    // A host-level auth failure, not a contract error: the lot check passed and the
    // signatures are what refused it.
    assert!(matches!(result, Err(Err(_))), "expected an auth failure, got {:?}", result);
    assert_eq!(escrow.lot_trade(&lot), None, "a stranger occupied the lot");
}

#[test]
fn the_verifier_is_set_in_the_deploy_transaction() {
    // A separate init() left a window in which a stranger could claim the
    // verifier role on a freshly deployed instance and grief every trade on it.
    let f = setup();
    assert_eq!(f.escrow.verifier(), f.verifier);
}

#[test]
fn create_demands_the_buyer_signature_specifically() {
    let f = setup();
    f.env.auths();
    fund(&f, &trade_id(&f.env, 1), 250);
    let auths = f.env.auths();
    assert_eq!(auths.first().map(|(a, _)| a.clone()), Some(f.buyer.clone()));
}

#[test]
fn an_unknown_trade_id_is_an_error_not_a_panic() {
    let f = setup();
    let unknown = trade_id(&f.env, 9);
    assert_eq!(f.escrow.try_get(&unknown), Err(Ok(Error::NoSuchTrade)));
    assert_eq!(f.escrow.try_release(&unknown), Err(Ok(Error::NoSuchTrade)));
    assert_eq!(f.escrow.try_refund(&unknown), Err(Ok(Error::NoSuchTrade)));
}

#[test]
fn release_demands_the_verifier_signature_specifically() {
    // mock_all_auths approves everything, so the assertion that matters is not
    // "did it succeed" but "whose authorisation did it ask for". If release
    // ever stops requiring the verifier, this is what catches it.
    let f = setup();
    let id = trade_id(&f.env, 1);
    fund(&f, &id, 250);

    f.escrow.release(&id);

    let auths = f.env.auths();
    assert_eq!(auths.first().map(|(addr, _)| addr.clone()), Some(f.verifier.clone()));
}

#[test]
fn refund_demands_no_signature_at_all() {
    // A buyer's refund must not depend on AXK still existing to sign for it.
    let f = setup();
    let id = trade_id(&f.env, 1);
    fund(&f, &id, 250);
    f.env.ledger().set_timestamp(f.env.ledger().timestamp() + 31 * DAY);

    f.escrow.refund(&id);

    assert!(f.env.auths().is_empty(), "refund required an authorisation");
}

// ---------------------------------------------------------------------------
// Verification before settlement: the lot registry gate
// ---------------------------------------------------------------------------

#[test]
fn an_uninspected_lot_cannot_be_funded() {
    let f = setup();
    let fresh = f.registry.register_lot(&f.destination, &trade_id(&f.env, 50), &trade_id(&f.env, 51));
    let deadline = f.env.ledger().timestamp() + 30 * DAY;
    assert_eq!(
        f.escrow.try_create(&trade_id(&f.env, 1), &fresh, &f.buyer, &f.token.address, &100, &deadline),
        Err(Ok(Error::LotNotApproved)),
    );
    assert_eq!(f.token.balance(&f.buyer), 1_000, "money moved for an uninspected lot");
}

#[test]
fn a_rejected_lot_cannot_be_funded() {
    let f = setup();
    let rejected = inspected_lot(&f.env, &f.registry, &f.destination, &f.inspector, 2, false);
    let deadline = f.env.ledger().timestamp() + 30 * DAY;
    assert_eq!(
        f.escrow.try_create(&trade_id(&f.env, 1), &rejected, &f.buyer, &f.token.address, &100, &deadline),
        Err(Ok(Error::LotNotApproved)),
    );
}

#[test]
fn an_unregistered_lot_cannot_be_funded() {
    let f = setup();
    let deadline = f.env.ledger().timestamp() + 30 * DAY;
    assert_eq!(
        f.escrow.try_create(&trade_id(&f.env, 1), &trade_id(&f.env, 77), &f.buyer, &f.token.address, &100, &deadline),
        Err(Ok(Error::LotNotApproved)),
    );
}

#[test]
fn the_payee_is_the_cooperative_that_registered_the_lot() {
    // There is no destination parameter to get wrong or to abuse: the escrow asks the
    // registry who owns the inspected lot and records that as the payee.
    let f = setup();
    let id = trade_id(&f.env, 1);
    fund(&f, &id, 250);
    assert_eq!(f.escrow.get(&id).destination, f.destination);
    assert_eq!(f.escrow.get(&id).lot_id, f.lot);
}

#[test]
fn a_lot_cannot_back_two_live_escrows() {
    // Otherwise one inspected lot could be sold to two buyers.
    let f = setup();
    fund(&f, &trade_id(&f.env, 1), 250);
    let deadline = f.env.ledger().timestamp() + 30 * DAY;
    assert_eq!(
        f.escrow.try_create(&trade_id(&f.env, 2), &f.lot, &f.buyer, &f.token.address, &100, &deadline),
        Err(Ok(Error::LotInEscrow)),
    );
    assert_eq!(f.escrow.lot_trade(&f.lot), Some(trade_id(&f.env, 1)));
}

#[test]
fn a_sold_lot_cannot_be_sold_again() {
    let f = setup();
    let id = trade_id(&f.env, 1);
    fund(&f, &id, 250);
    f.escrow.release(&id);
    let deadline = f.env.ledger().timestamp() + 30 * DAY;
    assert_eq!(
        f.escrow.try_create(&trade_id(&f.env, 2), &f.lot, &f.buyer, &f.token.address, &100, &deadline),
        Err(Ok(Error::LotInEscrow)),
    );
}

#[test]
fn a_refund_frees_the_lot_for_another_buyer() {
    let f = setup();
    let first = trade_id(&f.env, 1);
    fund(&f, &first, 250);
    f.env.ledger().set_timestamp(f.env.ledger().timestamp() + 31 * DAY);
    f.escrow.refund(&first);
    assert_eq!(f.escrow.lot_trade(&f.lot), None);

    let second = trade_id(&f.env, 2);
    fund(&f, &second, 250);
    assert_eq!(f.escrow.lot_trade(&f.lot), Some(second));
}

#[test]
fn the_registry_is_set_in_the_deploy_transaction() {
    let f = setup();
    assert_eq!(f.escrow.registry(), f.registry.address);
}
