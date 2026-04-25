# Solidity Security Audit Packet (Executor + Convert/Withdraw)

This repo includes an **audit packet** to support a formal third-party review.

> This file is **not** a substitute for a professional security audit.

## Scope
- `contracts/src/*` (executor, router adapters, withdraw/convert path)
- Any contract that can:
  - initiate flash loans
  - route swaps
  - move funds to external addresses

## Threat Model (high level)
1) **Flashloan callback abuse**
2) **Approval / allowance hijack**
3) **Slippage / minOut bypass**
4) **Reentrancy** (esp. around withdraw)
5) **Owner key compromise**
6) **Upgrade / proxy misuse**
7) **Event ambiguity** (analytics vs truth)

## Required Properties
- Only authorized entrypoints can execute trade routes.
- Withdrawals require explicit authorization and are not callable by untrusted parties.
- Conversion paths enforce minOut and are immune to token decimal confusion.
- No unexpected external calls before state changes (or guard with reentrancy lock).

## Tooling
### Foundry
```bash
cd contracts
forge test -vvv
forge coverage
```

### Slither
Install slither and run:
```bash
pip install slither-analyzer
cd contracts
slither . --config-file audit/slither.config.json
```

## Manual Review Checklist
- [ ] Ownership model (owner/multisig) and privileged methods
- [ ] Reentrancy guards on withdraw functions
- [ ] Token approvals minimized and reset when possible
- [ ] Slippage checks enforced in correct units
- [ ] Flashloan premium repayment always guaranteed or reverts
- [ ] Pausable/emergency stop available and owner-controlled
- [ ] Events include enough data to reconstruct flows

## Deliverables for a Formal Audit
- Contract sources + build instructions
- Deployment addresses and chain configs
- ABI + bytecode hashes
- Known invariants and constraints
- This audit packet + threat model
