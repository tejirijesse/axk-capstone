#![cfg(test)]

use super::*;
use soroban_sdk::{testutils::Address as _, Address, Env};

fn bytes(env: &Env, n: u8) -> BytesN<32> {
    let mut b = [0u8; 32];
    b[31] = n;
    BytesN::from_array(env, &b)
}

fn setup() -> (Env, RegistryClient<'static>, Address) {
    let env = Env::default();
    env.mock_all_auths();
    let attester = Address::generate(&env);
    let client = RegistryClient::new(&env, &env.register(Registry, (attester.clone(),)));
    (env, client, attester)
}

#[test]
fn a_digest_can_be_recorded_and_read_back() {
    let (env, registry, _attester) = setup();
    let trade = bytes(&env, 1);
    let digest = bytes(&env, 42);

    registry.attest(&trade, &digest);

    assert_eq!(registry.get(&trade).digest, digest);
}

#[test]
fn an_attestation_cannot_be_overwritten() {
    // The whole value of the record. If AXK could amend it, it would prove only
    // what AXK last chose to say.
    let (env, registry, _attester) = setup();
    let trade = bytes(&env, 1);
    registry.attest(&trade, &bytes(&env, 42));

    assert_eq!(
        registry.try_attest(&trade, &bytes(&env, 99)),
        Err(Ok(Error::AlreadyAttested)),
    );
    assert_eq!(registry.get(&trade).digest, bytes(&env, 42));
}

#[test]
fn matches_is_true_only_for_the_recorded_digest() {
    let (env, registry, _attester) = setup();
    let trade = bytes(&env, 1);
    registry.attest(&trade, &bytes(&env, 42));

    assert!(registry.matches(&trade, &bytes(&env, 42)));
    assert!(!registry.matches(&trade, &bytes(&env, 43)));
}

#[test]
fn matches_is_false_for_a_trade_that_was_never_attested() {
    // False, not a panic. A lender checking an unknown trade should get "no",
    // not an error they have to interpret.
    let (env, registry, _attester) = setup();
    assert!(!registry.matches(&bytes(&env, 7), &bytes(&env, 42)));
}

#[test]
fn reading_an_unknown_trade_is_an_error() {
    let (env, registry, _attester) = setup();
    assert_eq!(registry.try_get(&bytes(&env, 7)), Err(Ok(Error::NoSuchTrade)));
}

#[test]
fn the_ledger_position_is_recorded_with_the_digest() {
    let (env, registry, _attester) = setup();
    let trade = bytes(&env, 1);
    registry.attest(&trade, &bytes(&env, 42));

    let a = registry.get(&trade);
    assert_eq!(a.ledger, env.ledger().sequence());
    assert_eq!(a.timestamp, env.ledger().timestamp());
}

#[test]
fn only_the_attester_may_write() {
    // The finding this permission exists for: trade ids are public from the
    // moment an escrow is funded, and the record is write-once, so an open
    // registry lets anyone race a junk digest in and block the real one
    // forever. Being unable to forge a record is no use if you can stop it
    // existing.
    let (env, registry, attester) = setup();
    registry.attest(&bytes(&env, 1), &bytes(&env, 42));

    let auths = env.auths();
    assert_eq!(auths.first().map(|(a, _)| a.clone()), Some(attester));
}

#[test]
fn a_stranger_cannot_pre_empt_a_trade_id() {
    let env = Env::default();
    let attester = Address::generate(&env);
    let registry = RegistryClient::new(&env, &env.register(Registry, (attester.clone(),)));

    // No auth mocked for anyone: the write must not go through.
    let stranger_write = registry.try_attest(&bytes(&env, 1), &bytes(&env, 99));
    assert!(stranger_write.is_err(), "an unauthorised attestation was accepted");
}
