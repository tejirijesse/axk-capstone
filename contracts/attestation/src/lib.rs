#![no_std]

//! Write-once record that a trade settled.
//!
//! Stores a digest over a canonical serialisation of the trade record, never
//! the record itself. A lender shown a trade can hash it and confirm it matches
//! what settled, without AXK vouching for it and without the ledger carrying
//! commercially sensitive terms or anybody's personal data.
//!
//! Write-once is the point. An attestation that could be amended later would
//! prove only what AXK last chose to say. Write-once also means the first write
//! wins, which is why writing is restricted rather than open: an open registry
//! of write-once records is one an attacker can fill with junk ahead of you.

use soroban_sdk::{contract, contracterror, contractimpl, contracttype, Address, BytesN, Env};

const DAY_LEDGERS: u32 = 17_280;
const TTL_THRESHOLD: u32 = DAY_LEDGERS * 120;
const TTL_EXTEND: u32 = DAY_LEDGERS * 180;

#[contracterror]
#[derive(Copy, Clone, Debug, Eq, PartialEq, PartialOrd, Ord)]
#[repr(u32)]
pub enum Error {
    AlreadyAttested = 1,
    NoSuchTrade = 2,
}

#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Attestation {
    pub digest: BytesN<32>,
    pub ledger: u32,
    pub timestamp: u64,
}

#[contracttype]
#[derive(Clone)]
enum Key {
    Attester,
    Trade(BytesN<32>),
}

#[contract]
pub struct Registry;

#[contractimpl]
impl Registry {
    /// Set in the deploy transaction, so the role cannot be claimed by a
    /// stranger between deployment and first use.
    pub fn __constructor(env: Env, attester: Address) {
        env.storage().instance().set(&Key::Attester, &attester);
    }

    pub fn attester(env: Env) -> Address {
        env.storage().instance().get(&Key::Attester).unwrap()
    }

    /// Records a digest against a trade. Fails if the trade already has one.
    ///
    /// Writing is restricted to the attester. An earlier version let anyone
    /// write, on the reasoning that a wrong digest from a stranger proves
    /// nothing. That was wrong: the record is write-once, and `trade_id` is
    /// public from the moment the escrow is funded, so anyone could race a junk
    /// attestation in first and permanently block the real one. Being unable to
    /// forge a record is no use if you can stop it existing.
    pub fn attest(env: Env, trade_id: BytesN<32>, digest: BytesN<32>) -> Result<(), Error> {
        Self::attester(env.clone()).require_auth();

        let key = Key::Trade(trade_id);
        if env.storage().persistent().has(&key) {
            return Err(Error::AlreadyAttested);
        }
        env.storage().persistent().set(
            &key,
            &Attestation {
                digest,
                ledger: env.ledger().sequence(),
                timestamp: env.ledger().timestamp(),
            },
        );
        env.storage()
            .persistent()
            .extend_ttl(&key, TTL_THRESHOLD, TTL_EXTEND);
        Ok(())
    }

    pub fn get(env: Env, trade_id: BytesN<32>) -> Result<Attestation, Error> {
        env.storage()
            .persistent()
            .get(&Key::Trade(trade_id))
            .ok_or(Error::NoSuchTrade)
    }

    /// True when `digest` is the one recorded for this trade. The check a
    /// lender runs after hashing the record they were shown.
    pub fn matches(env: Env, trade_id: BytesN<32>, digest: BytesN<32>) -> bool {
        match Self::get(env, trade_id) {
            Ok(a) => a.digest == digest,
            Err(_) => false,
        }
    }
}

mod test;
