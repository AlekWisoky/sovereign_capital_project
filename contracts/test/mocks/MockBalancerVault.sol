// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "./MockERC20.sol";

interface IBalancerFlashLoanReceiver {
    function receiveFlashLoan(address[] calldata tokens, uint256[] calldata amounts, uint256[] calldata feeAmounts, bytes calldata userData) external;
}

contract MockBalancerVault {
    enum SwapKind { GIVEN_IN, GIVEN_OUT }
    struct SingleSwap {
        bytes32 poolId;
        SwapKind kind;
        address assetIn;
        address assetOut;
        uint256 amount;
        bytes userData;
    }
    struct FundManagement {
        address sender;
        bool fromInternalBalance;
        address recipient;
        bool toInternalBalance;
    }

    uint256 public feeBps = 10;
    uint256 public outBps = 10000;

    function setFeeBps(uint256 bps) external {
        feeBps = bps;
    }

    function setOutBps(uint256 bps) external {
        outBps = bps;
    }

    function swap(
        SingleSwap calldata singleSwap,
        FundManagement calldata funds,
        uint256 limit,
        uint256
    ) external returns (uint256 amountCalculated) {
        MockERC20(singleSwap.assetIn).transferFrom(funds.sender, address(this), singleSwap.amount);
        amountCalculated = singleSwap.amount * outBps / 10000;
        require(amountCalculated >= limit, "vault_min_out");
        MockERC20(singleSwap.assetOut).mint(funds.recipient, amountCalculated);
    }

    function flashLoan(
        address recipient,
        address[] calldata tokens,
        uint256[] calldata amounts,
        bytes calldata userData
    ) external {
        require(tokens.length == 1 && amounts.length == 1, "single_only");
        uint256[] memory feeAmounts = new uint256[](1);
        feeAmounts[0] = amounts[0] * feeBps / 10000;
        MockERC20(tokens[0]).mint(recipient, amounts[0]);
        IBalancerFlashLoanReceiver(recipient).receiveFlashLoan(tokens, amounts, feeAmounts, userData);
    }
}
