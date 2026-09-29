#![cfg(test)]

use super::*;
use soroban_sdk::{
    testutils::Address as _,
    token::{StellarAssetClient, TokenClient},
    vec, Env,
};

struct Fixture<'a> {
    env: Env,
    splitter: SplitterClient<'a>,
    token: TokenClient<'a>,
    source: Address,
    coordinator: Address,
    coop: Address,
    farmer: Address,
    lender: Address,
}

fn setup() -> Fixture<'static> {
    let env = Env::default();
    env.mock_all_auths();

    let issuer = Address::generate(&env);
    let asset = env.register_stellar_asset_contract_v2(issuer);
    let token = TokenClient::new(&env, &asset.address());
    let minter = StellarAssetClient::new(&env, &asset.address());

    let source = Address::generate(&env);
    minter.mint(&source, &1_000_000);
    let coordinator = Address::generate(&env);

    Fixture {
        splitter: SplitterClient::new(&env, &env.register(Splitter, (coordinator.clone(),))),
        token,
        source,
        coordinator,
        coop: Address::generate(&env),
        farmer: Address::generate(&env),
        lender: Address::generate(&env),
        env,
    }
}

fn trade_id(env: &Env, n: u8) -> BytesN<32> {
    let mut bytes = [0u8; 32];
    bytes[31] = n;
    BytesN::from_array(env, &bytes)
}

#[test]
fn the_parts_sum_to_exactly_the_whole() {
    let f = setup();
    let id = trade_id(&f.env, 1);
    f.splitter.configure(&id, &vec![
        &f.env,
        Share { party: f.lender.clone(), bps: 2_000 },
        Share { party: f.farmer.clone(), bps: 5_000 },
        Share { party: f.coop.clone(), bps: 3_000 },
    ]);

    f.splitter.distribute(&id, &f.token.address, &f.source, &1_000);

    assert_eq!(f.token.balance(&f.lender), 200);
    assert_eq!(f.token.balance(&f.farmer), 500);
    assert_eq!(f.token.balance(&f.coop), 300);
    assert_eq!(
        f.token.balance(&f.lender) + f.token.balance(&f.farmer) + f.token.balance(&f.coop),
        1_000,
    );
}

#[test]
fn a_rounding_remainder_is_paid_out_not_dropped() {
    // 1000 split three ways at 3333/3333/3334 bps does not divide evenly. The
    // stroops that fall off the division have to land somewhere, or the source
    // balance drifts by a little on every settlement.
    let f = setup();
    let id = trade_id(&f.env, 2);
    f.splitter.configure(&id, &vec![
        &f.env,
        Share { party: f.lender.clone(), bps: 3_333 },
        Share { party: f.farmer.clone(), bps: 3_333 },
        Share { party: f.coop.clone(), bps: 3_334 },
    ]);

    let before = f.token.balance(&f.source);
    f.splitter.distribute(&id, &f.token.address, &f.source, &1_001);

    let paid = f.token.balance(&f.lender) + f.token.balance(&f.farmer) + f.token.balance(&f.coop);
    assert_eq!(paid, 1_001, "the parts did not sum to the whole");
    assert_eq!(before - f.token.balance(&f.source), 1_001);
}

#[test]
fn the_smallest_divisible_amount_still_balances() {
    let f = setup();
    let id = trade_id(&f.env, 3);
    f.splitter.configure(&id, &vec![
        &f.env,
        Share { party: f.farmer.clone(), bps: 9_999 },
        Share { party: f.coop.clone(), bps: 1 },
    ]);

    f.splitter.distribute(&id, &f.token.address, &f.source, &1);

    assert_eq!(f.token.balance(&f.farmer) + f.token.balance(&f.coop), 1);
}

#[test]
fn shares_that_do_not_total_the_whole_are_refused() {
    let f = setup();
    for (n, a, b) in [(4u8, 5_000i128, 4_000i128), (5, 6_000, 5_000)] {
        assert_eq!(
            f.splitter.try_configure(&trade_id(&f.env, n), &vec![
                &f.env,
                Share { party: f.farmer.clone(), bps: a },
                Share { party: f.coop.clone(), bps: b },
            ]),
            Err(Ok(Error::SharesDoNotSumToWhole)),
        );
    }
}

#[test]
fn a_zero_or_negative_share_is_refused() {
    // Without this, 10000 + 0 and 12000 + -2000 both total correctly while
    // describing a split that is not one.
    let f = setup();
    assert_eq!(
        f.splitter.try_configure(&trade_id(&f.env, 6), &vec![
            &f.env,
            Share { party: f.farmer.clone(), bps: 10_000 },
            Share { party: f.coop.clone(), bps: 0 },
        ]),
        Err(Ok(Error::ShareNotPositive)),
    );
    assert_eq!(
        f.splitter.try_configure(&trade_id(&f.env, 7), &vec![
            &f.env,
            Share { party: f.farmer.clone(), bps: 12_000 },
            Share { party: f.coop.clone(), bps: -2_000 },
        ]),
        Err(Ok(Error::ShareNotPositive)),
    );
}

#[test]
fn an_empty_split_is_refused() {
    let f = setup();
    assert_eq!(
        f.splitter.try_configure(&trade_id(&f.env, 8), &vec![&f.env]),
        Err(Ok(Error::NoShares)),
    );
}

#[test]
fn a_split_cannot_be_rewritten_once_agreed() {
    let f = setup();
    let id = trade_id(&f.env, 9);
    f.splitter.configure(&id, &vec![
        &f.env,
        Share { party: f.farmer.clone(), bps: 5_000 },
        Share { party: f.coop.clone(), bps: 5_000 },
    ]);
    assert_eq!(
        f.splitter.try_configure(&id, &vec![
            &f.env,
            Share { party: f.lender.clone(), bps: 10_000 },
        ]),
        Err(Ok(Error::AlreadyConfigured)),
    );
}

#[test]
fn the_coordinator_is_set_in_the_deploy_transaction() {
    let f = setup();
    assert_eq!(f.splitter.coordinator(), f.coordinator);
}

#[test]
fn configure_demands_the_coordinator_signature_specifically() {
    // mock_all_auths approves everything, so the question is not whether the
    // call succeeded but whose authorisation it asked for. An unrestricted
    // configure is fund theft, not just a nuisance: the split is write-once and
    // the trade id is public, so a stranger who records their own division
    // first is paid it, because distribute is authorised by the account paying
    // out and not by any party to the trade.
    let f = setup();
    let id = trade_id(&f.env, 12);
    f.splitter.configure(&id, &vec![
        &f.env,
        Share { party: f.farmer.clone(), bps: 10_000 },
    ]);

    let auths = f.env.auths();
    assert_eq!(auths.first().map(|(a, _)| a.clone()), Some(f.coordinator.clone()));
}

#[test]
fn a_stranger_cannot_record_a_division_that_pays_themselves() {
    // The same check from the caller's side: with auth actually enforced rather
    // than mocked, an attacker's configure fails, so the real split still fits
    // in the trade id and the money goes where the parties agreed.
    let env = Env::default();
    let coordinator = Address::generate(&env);
    let attacker = Address::generate(&env);
    let splitter = SplitterClient::new(&env, &env.register(Splitter, (coordinator.clone(),)));
    let id = trade_id(&env, 13);

    let hostile = vec![&env, Share { party: attacker.clone(), bps: 10_000 }];
    assert!(
        splitter.try_configure(&id, &hostile).is_err(),
        "a stranger configured the split",
    );

    env.mock_all_auths();
    splitter.configure(&id, &vec![&env, Share { party: attacker.clone(), bps: 10_000 }]);
    assert_eq!(splitter.shares(&id).len(), 1);
}

#[test]
fn distributing_an_unconfigured_trade_is_refused() {
    let f = setup();
    assert_eq!(
        f.splitter.try_distribute(&trade_id(&f.env, 10), &f.token.address, &f.source, &100),
        Err(Ok(Error::NotConfigured)),
    );
}

#[test]
fn a_zero_or_negative_amount_is_refused() {
    let f = setup();
    let id = trade_id(&f.env, 11);
    f.splitter.configure(&id, &vec![
        &f.env,
        Share { party: f.farmer.clone(), bps: 10_000 },
    ]);
    for amount in [0i128, -500] {
        assert_eq!(
            f.splitter.try_distribute(&id, &f.token.address, &f.source, &amount),
            Err(Ok(Error::AmountNotPositive)),
        );
    }
    assert_eq!(f.token.balance(&f.farmer), 0);
}
