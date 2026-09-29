#![cfg(test)]

use super::*;
use soroban_sdk::{
    symbol_short,
    testutils::{Address as _, Events},
    Env, IntoVal,
};

struct Fixture<'a> {
    env: Env,
    registry: LotRegistryClient<'a>,
    admin: Address,
    coop: Address,
    inspector: Address,
}

fn setup() -> Fixture<'static> {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let coop = Address::generate(&env);
    let inspector = Address::generate(&env);
    let registry = LotRegistryClient::new(&env, &env.register(LotRegistry, (admin.clone(),)));
    registry.add_inspector(&inspector);
    Fixture { env, registry, admin, coop, inspector }
}

fn bytes(env: &Env, n: u8) -> BytesN<32> {
    let mut b = [0u8; 32];
    b[31] = n;
    BytesN::from_array(env, &b)
}

fn register(f: &Fixture, n: u8) -> BytesN<32> {
    f.registry.register_lot(&f.coop, &bytes(&f.env, n), &bytes(&f.env, 100 + n))
}

fn pass(f: &Fixture, id: &BytesN<32>) -> LotStatus {
    f.registry.inspect(id, &f.inspector, &true, &symbol_short!("A"), &3_850, &bytes(&f.env, 200))
}

#[test]
fn a_registered_lot_starts_uninspected() {
    let f = setup();
    let id = register(&f, 1);
    let lot = f.registry.get(&id);
    assert_eq!(lot.cooperative, f.coop);
    assert_eq!(lot.status, LotStatus::Registered);
    assert!(f.registry.try_get_inspection(&id).is_err());
    assert_eq!(f.registry.approved_cooperative(&id), None);
}

#[test]
fn the_lot_id_is_bound_to_the_cooperative() {
    // The same reference registered by a stranger is a different lot, so a real lot's id
    // cannot be squatted and a squatter's lot can never be the one the buyer is paying for.
    let f = setup();
    let stranger = Address::generate(&f.env);
    let real = register(&f, 1);
    let squat = f.registry.register_lot(&stranger, &bytes(&f.env, 1), &bytes(&f.env, 101));
    assert_ne!(real, squat);
    assert_eq!(f.registry.get(&real).cooperative, f.coop);
    assert_eq!(f.registry.get(&squat).cooperative, stranger);
    assert_eq!(real, f.registry.lot_id(&f.coop, &bytes(&f.env, 1)));
}

#[test]
fn registration_is_write_once() {
    let f = setup();
    register(&f, 1);
    assert_eq!(
        f.registry.try_register_lot(&f.coop, &bytes(&f.env, 1), &bytes(&f.env, 99)),
        Err(Ok(Error::LotExists)),
    );
}

#[test]
fn registration_demands_the_cooperative_signature() {
    let f = setup();
    register(&f, 1);
    assert_eq!(f.env.auths().first().map(|(a, _)| a.clone()), Some(f.coop.clone()));
}

#[test]
fn a_passed_inspection_approves_the_lot() {
    let f = setup();
    let id = register(&f, 1);
    assert_eq!(pass(&f, &id), LotStatus::Approved);
    assert_eq!(f.registry.get(&id).status, LotStatus::Approved);
    let insp = f.registry.get_inspection(&id);
    assert_eq!(insp.inspector, f.inspector);
    assert_eq!(insp.quantity_kg, 3_850);
    assert_eq!(insp.grade, symbol_short!("A"));
    assert_eq!(f.registry.approved_cooperative(&id), Some(f.coop.clone()));
}

#[test]
fn a_failed_inspection_rejects_the_lot() {
    let f = setup();
    let id = register(&f, 1);
    let status = f.registry.inspect(&id, &f.inspector, &false, &symbol_short!("C"), &3_850, &bytes(&f.env, 200));
    assert_eq!(status, LotStatus::Rejected);
    assert_eq!(f.registry.approved_cooperative(&id), None);
}

#[test]
fn a_lot_is_inspected_once() {
    // Otherwise a failed lot could be re-inspected until someone passes it.
    let f = setup();
    let id = register(&f, 1);
    f.registry.inspect(&id, &f.inspector, &false, &symbol_short!("C"), &3_850, &bytes(&f.env, 200));
    assert_eq!(
        f.registry.try_inspect(&id, &f.inspector, &true, &symbol_short!("A"), &3_850, &bytes(&f.env, 201)),
        Err(Ok(Error::AlreadyInspected)),
    );
    assert_eq!(f.registry.get(&id).status, LotStatus::Rejected);
}

#[test]
fn only_an_authorised_inspector_can_inspect() {
    let f = setup();
    let id = register(&f, 1);
    let stranger = Address::generate(&f.env);
    assert_eq!(
        f.registry.try_inspect(&id, &stranger, &true, &symbol_short!("A"), &3_850, &bytes(&f.env, 200)),
        Err(Ok(Error::NotAnInspector)),
    );
    assert_eq!(f.registry.approved_cooperative(&id), None);
}

#[test]
fn inspect_demands_the_inspectors_signature_specifically() {
    let f = setup();
    let id = register(&f, 1);
    pass(&f, &id);
    assert_eq!(f.env.auths().first().map(|(a, _)| a.clone()), Some(f.inspector.clone()));
}

#[test]
fn a_cooperative_cannot_inspect_its_own_lot() {
    // Separation of duties: even a cooperative that also holds an inspector licence
    // cannot approve its own produce.
    let f = setup();
    f.registry.add_inspector(&f.coop);
    let id = register(&f, 1);
    assert_eq!(
        f.registry.try_inspect(&id, &f.coop, &true, &symbol_short!("A"), &3_850, &bytes(&f.env, 200)),
        Err(Ok(Error::InspectorOwnsLot)),
    );
}

#[test]
fn a_zero_or_negative_quantity_is_refused() {
    let f = setup();
    let id = register(&f, 1);
    for q in [0i128, -5] {
        assert_eq!(
            f.registry.try_inspect(&id, &f.inspector, &true, &symbol_short!("A"), &q, &bytes(&f.env, 200)),
            Err(Ok(Error::QuantityNotPositive)),
        );
    }
}

#[test]
fn inspecting_an_unknown_lot_is_an_error_not_a_panic() {
    let f = setup();
    let unknown = bytes(&f.env, 9);
    assert_eq!(
        f.registry.try_inspect(&unknown, &f.inspector, &true, &symbol_short!("A"), &1, &bytes(&f.env, 200)),
        Err(Ok(Error::NoSuchLot)),
    );
    assert_eq!(f.registry.try_get(&unknown), Err(Ok(Error::NoSuchLot)));
    assert_eq!(f.registry.approved_cooperative(&unknown), None);
}

#[test]
fn a_removed_inspector_cannot_inspect_again() {
    let f = setup();
    let first = register(&f, 1);
    pass(&f, &first);
    f.registry.remove_inspector(&f.inspector);
    let second = register(&f, 2);
    assert_eq!(
        f.registry.try_inspect(&second, &f.inspector, &true, &symbol_short!("A"), &1, &bytes(&f.env, 200)),
        Err(Ok(Error::NotAnInspector)),
    );
    // The inspection signed while authorised still stands.
    assert_eq!(f.registry.get(&first).status, LotStatus::Approved);
}

#[test]
fn managing_inspectors_demands_the_admin_signature() {
    let f = setup();
    let newcomer = Address::generate(&f.env);
    f.registry.add_inspector(&newcomer);
    assert_eq!(f.env.auths().first().map(|(a, _)| a.clone()), Some(f.admin.clone()));
    f.registry.remove_inspector(&newcomer);
    assert_eq!(f.env.auths().first().map(|(a, _)| a.clone()), Some(f.admin.clone()));
}

#[test]
fn without_signatures_nothing_is_written() {
    let env = Env::default();
    let admin = Address::generate(&env);
    let coop = Address::generate(&env);
    let stranger = Address::generate(&env);
    let registry = LotRegistryClient::new(&env, &env.register(LotRegistry, (admin,)));
    assert!(registry.try_add_inspector(&stranger).is_err(), "a stranger appointed an inspector");
    assert!(
        registry.try_register_lot(&coop, &bytes(&env, 1), &bytes(&env, 2)).is_err(),
        "a lot was registered without the cooperative's signature",
    );
}

#[test]
fn the_admin_is_set_in_the_deploy_transaction() {
    let f = setup();
    assert_eq!(f.registry.admin(), f.admin);
}

#[test]
fn matches_is_true_only_for_the_registered_digest() {
    let f = setup();
    let id = register(&f, 1);
    assert!(f.registry.matches(&id, &bytes(&f.env, 101)));
    assert!(!f.registry.matches(&id, &bytes(&f.env, 102)));
    assert!(!f.registry.matches(&bytes(&f.env, 9), &bytes(&f.env, 101)));
}

#[test]
fn inspection_is_published_as_an_event() {
    let f = setup();
    let id = register(&f, 1);
    pass(&f, &id);
    let last = f.env.events().all().last().unwrap();
    assert_eq!(last.0, f.registry.address);
    assert_eq!(last.1, (symbol_short!("lot"), symbol_short!("inspect")).into_val(&f.env));
}
