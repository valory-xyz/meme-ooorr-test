// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

contract CustomERC20 is ERC20, Ownable {
    constructor(
        string memory name_,
        string memory symbol_,
        address[] memory holders_,
        uint256[] memory allocations_,
        uint256 initialSupply
    ) ERC20(name_, symbol_) {
        require(holders_.length == allocations_.length, "Holders and allocations length mismatch");
        
        for (uint256 i = 0; i < holders_.length; i++) {
            _mint(holders_[i], allocations_[i]);
        }

        _mint(msg.sender, initialSupply - totalSupply());
    }
}
