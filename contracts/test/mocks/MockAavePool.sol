// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "./MockERC20.sol";

interface IAaveFlashLoanReceiver {
    function executeOperation(address asset, uint256 amount, uint256 premium, address initiator, bytes calldata params) external returns (bool);
}

contract MockAavePool {
    uint256 public premiumBps = 9;

    function setPremiumBps(uint256 bps) external {
        premiumBps = bps;
    }

    function flashLoanSimple(
        address receiverAddress,
        address asset,
        uint256 amount,
        bytes calldata params,
        uint16
    ) external {
        uint256 premium = amount * premiumBps / 10000;
        MockERC20(asset).mint(receiverAddress, amount);
        bool ok = IAaveFlashLoanReceiver(receiverAddress).executeOperation(asset, amount, premium, receiverAddress, params);
        require(ok, "callback_failed");
        MockERC20(asset).transferFrom(receiverAddress, address(this), amount + premium);
    }
}
