/// Session spends revert unless they stay inside the agent caps.
/// The Ready session may call `spend` only. `register_session` and `revoke_session`
/// are owner calls, so a stolen session key cannot raise the caps.
use starknet::ContractAddress;

#[starknet::interface]
trait ISpendingPolicy<TContractState> {
    fn register_session(
        ref self: TContractState,
        token: ContractAddress,
        recipient: ContractAddress,
        max_per_call: u256,
        daily_limit: u256,
        expires_at: u64,
        session_public_key: felt252,
    );
    fn spend(ref self: TContractState, amount: u256);
    fn revoke_session(ref self: TContractState);
}

#[starknet::interface]
trait IErc20<TContractState> {
    fn transfer(ref self: TContractState, recipient: ContractAddress, amount: u256) -> bool;
}

#[starknet::contract]
mod SpendingPolicy {
    use starknet::storage::{StoragePointerReadAccess, StoragePointerWriteAccess};
    use starknet::{ContractAddress, get_block_timestamp, get_caller_address};
    use super::{IErc20Dispatcher, IErc20DispatcherTrait};

    const DAY: u64 = 86400;

    #[storage]
    struct Storage {
        owner: ContractAddress,
        token: ContractAddress,
        recipient: ContractAddress,
        max_per_call: u256,
        daily_limit: u256,
        expires_at: u64,
        session_public_key: felt252,
        revoked: bool,
        day_index: u64,
        spent_today: u256,
    }

    #[constructor]
    fn constructor(ref self: ContractState, owner: ContractAddress) {
        self.owner.write(owner);
        self.revoked.write(true);
    }

    #[abi(embed_v0)]
    impl SpendingPolicyImpl of super::ISpendingPolicy<ContractState> {
        fn register_session(
            ref self: ContractState,
            token: ContractAddress,
            recipient: ContractAddress,
            max_per_call: u256,
            daily_limit: u256,
            expires_at: u64,
            session_public_key: felt252,
        ) {
            assert(get_caller_address() == self.owner.read(), 'owner');
            assert(max_per_call > 0 && max_per_call <= daily_limit, 'per_call');
            assert(expires_at > get_block_timestamp(), 'expired');
            assert(token.into() != 0 && recipient.into() != 0, 'token');
            self.token.write(token);
            self.recipient.write(recipient);
            self.max_per_call.write(max_per_call);
            self.daily_limit.write(daily_limit);
            self.expires_at.write(expires_at);
            self.session_public_key.write(session_public_key);
            self.revoked.write(false);
            self.day_index.write(get_block_timestamp() / DAY);
            self.spent_today.write(0);
        }

        fn spend(ref self: ContractState, amount: u256) {
            assert(get_caller_address() == self.owner.read(), 'owner');
            assert(!self.revoked.read(), 'revoked');
            let now = get_block_timestamp();
            assert(now < self.expires_at.read(), 'expired');
            assert(amount > 0 && amount <= self.max_per_call.read(), 'per_call');
            let day = now / DAY;
            let mut spent = self.spent_today.read();
            if day != self.day_index.read() {
                spent = 0;
                self.day_index.write(day);
            }
            let next = spent + amount;
            assert(next <= self.daily_limit.read(), 'daily');
            self.spent_today.write(next);
            let token = IErc20Dispatcher { contract_address: self.token.read() };
            let ok = token.transfer(self.recipient.read(), amount);
            assert(ok, 'transfer');
        }

        fn revoke_session(ref self: ContractState) {
            assert(get_caller_address() == self.owner.read(), 'owner');
            self.revoked.write(true);
        }
    }
}
