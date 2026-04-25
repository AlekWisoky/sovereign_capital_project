// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "./MockERC20.sol";

contract MockSwapRouterV3 {
    struct ExactInputSingleParams {
        address tokenIn;
        address tokenOut;
        uint24 fee;
        address recipient;
        uint256 deadline;
        uint256 amountIn;
        uint256 amountOutMinimum;
        uint160 sqrtPriceLimitX96;
    }

    uint256 public outBps = 10000;
    bool public shouldRevert;

    function setOutBps(uint256 bps) external {
        outBps = bps;
    }

    function setShouldRevert(bool v) external {
        shouldRevert = v;
    }

    function exactInputSingle(ExactInputSingleParams calldata params) external payable returns (uint256 amountOut) {
        if (shouldRevert) revert("swap_revert");
        MockERC20(params.tokenIn).transferFrom(msg.sender, address(this), params.amountIn);
        amountOut = params.amountIn * outBps / 10000;
        require(amountOut >= params.amountOutMinimum, "router_min_out");
        MockERC20(params.tokenOut).mint(params.recipient, amountOut);
    }
}
