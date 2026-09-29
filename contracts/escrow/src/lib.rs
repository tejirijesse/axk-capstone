#![no_std]

//! Holds a buyer's payment against one trade until delivery is verified.
//!
//! The destination is fixed when the escrow is created. Nothing afterwards can
//! change it, which is the only guarantee here worth having: a compromised
//! verifier or admin can stall a release or let the deadline pass, but cannot
//! send the money somewhere else.

use soroban_sdk::{
    contract, contracterror, contractimpl, contracttype, token, Address, BytesN, Env,
};

/// Ledgers close about every five seconds. An escrow's own deadlines run to
/// ninety days, so its record has to outlive them by a margin or the money is
/// stranded behind an archived entry.
const DAY_LEDGERS: u32 = 17_280;
const TRADE_TTL_THRESHOLD: u32 = DAY_LEDGERS * 120;
const TRADE_TTL_EXTEND: u32 = DAY_LEDGERS * 180;

/// A deadline has to stay inside the window the record is kept alive for.
/// The extension above is 180 days and is refreshed on reads, but a trade
/// nobody reads gets only the one applied at `create`, so a deadline beyond
/// that could outlive its own record and strand the money it guards.
const MAX_TERM_SECONDS: u64 = 150 * 86_400;

#[contracterror]
#[derive(Copy, Clone, Debug, Eq, PartialEq, PartialOrd, Ord)]
#[repr(u32)]
pub enum Error {
    NotInitialised = 2,
    TradeExists = 3,
    NoSuchTrade = 4,
    NotFunded = 5,
    DeadlineNotReached = 6,
    DeadlineInPast = 7,
    AmountNotPositive = 8,
    DeadlineTooFar = 9,
}

#[contracttype]
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Status {
    Funded = 0,
    Released = 1,
    Refunded = 2,
}

#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Trade {
    pub buyer: Address,
    pub destination: Address,
    pub token: Address,
    pub amount: i128,
    pub deadline: u64,
    pub status: Status,
}

#[contracttype]
#[derive(Clone)]
enum Key {
    Verifier,
    Trade(BytesN<32>),
}

#[contract]
pub struct Escrow;

#[contractimpl]
impl Escrow {
    /// Runs inside the deploy transaction, so there is no window in which a
    /// stranger can claim the verifier role on a freshly deployed instance.
    pub fn __constructor(env: Env, verifier: Address) {
        env.storage().instance().set(&Key::Verifier, &verifier);
    }

    pub fn verifier(env: Env) -> Result<Address, Error> {
        env.storage()
            .instance()
            .get(&Key::Verifier)
            .ok_or(Error::NotInitialised)
    }

    /// Funds an escrow.
    ///
    /// Both the buyer and the verifier sign: the buyer because the money leaves
    /// their account, the verifier because `trade_id` is caller-supplied and a
    /// trade id can only be occupied once. Without the second signature anyone
    /// could fund a one-stroop trade under the id of a real one and block it,
    /// then take their stroop back at the deadline.
    pub fn create(
        env: Env,
        trade_id: BytesN<32>,
        buyer: Address,
        destination: Address,
        token_id: Address,
        amount: i128,
        deadline: u64,
    ) -> Result<(), Error> {
        if amount <= 0 {
            return Err(Error::AmountNotPositive);
        }
        let now = env.ledger().timestamp();
        if deadline <= now {
            return Err(Error::DeadlineInPast);
        }
        if deadline - now > MAX_TERM_SECONDS {
            return Err(Error::DeadlineTooFar);
        }
        let key = Key::Trade(trade_id);
        if env.storage().persistent().has(&key) {
            return Err(Error::TradeExists);
        }
        buyer.require_auth();
        Self::verifier(env.clone())?.require_auth();

        // State first, then the external call. `release` and `refund` already
        // do this; `create` did not, which left the one path where a token
        // contract is called before the trade exists in storage.
        env.storage().persistent().set(
            &key,
            &Trade {
                buyer: buyer.clone(),
                destination,
                token: token_id.clone(),
                amount,
                deadline,
                status: Status::Funded,
            },
        );
        env.storage()
            .persistent()
            .extend_ttl(&key, TRADE_TTL_THRESHOLD, TRADE_TTL_EXTEND);

        token::Client::new(&env, &token_id).transfer(
            &buyer,
            &env.current_contract_address(),
            &amount,
        );
        Ok(())
    }

    /// Pays the destination recorded at creation. The caller does not get to
    /// name it, so a compromised verifier cannot redirect the money.
    pub fn release(env: Env, trade_id: BytesN<32>) -> Result<(), Error> {
        Self::verifier(env.clone())?.require_auth();

        let key = Key::Trade(trade_id);
        let mut trade: Trade = env
            .storage()
            .persistent()
            .get(&key)
            .ok_or(Error::NoSuchTrade)?;
        if trade.status != Status::Funded {
            return Err(Error::NotFunded);
        }

        trade.status = Status::Released;
        env.storage().persistent().set(&key, &trade);
        env.storage()
            .persistent()
            .extend_ttl(&key, TRADE_TTL_THRESHOLD, TRADE_TTL_EXTEND);

        token::Client::new(&env, &trade.token).transfer(
            &env.current_contract_address(),
            &trade.destination,
            &trade.amount,
        );
        Ok(())
    }

    /// Returns the money to the buyer once the deadline has passed.
    ///
    /// Deliberately callable by anyone. If it required a privileged caller, a
    /// buyer's refund would depend on AXK still being around to sign for it.
    pub fn refund(env: Env, trade_id: BytesN<32>) -> Result<(), Error> {
        let key = Key::Trade(trade_id);
        let mut trade: Trade = env
            .storage()
            .persistent()
            .get(&key)
            .ok_or(Error::NoSuchTrade)?;
        if trade.status != Status::Funded {
            return Err(Error::NotFunded);
        }
        if env.ledger().timestamp() < trade.deadline {
            return Err(Error::DeadlineNotReached);
        }

        trade.status = Status::Refunded;
        env.storage().persistent().set(&key, &trade);
        env.storage()
            .persistent()
            .extend_ttl(&key, TRADE_TTL_THRESHOLD, TRADE_TTL_EXTEND);

        token::Client::new(&env, &trade.token).transfer(
            &env.current_contract_address(),
            &trade.buyer,
            &trade.amount,
        );
        Ok(())
    }

    pub fn get(env: Env, trade_id: BytesN<32>) -> Result<Trade, Error> {
        let key = Key::Trade(trade_id);
        let trade: Trade = env
            .storage()
            .persistent()
            .get(&key)
            .ok_or(Error::NoSuchTrade)?;
        env.storage()
            .persistent()
            .extend_ttl(&key, TRADE_TTL_THRESHOLD, TRADE_TTL_EXTEND);
        Ok(trade)
    }
}

mod test;
