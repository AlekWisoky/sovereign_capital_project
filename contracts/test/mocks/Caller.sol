// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

contract Caller {
    function call(address target, bytes calldata data) external returns (bool ok, bytes memory ret) {
        (ok, ret) = target.call(data);
    }
}
