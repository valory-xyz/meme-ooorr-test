// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {ERC20} from "../lib/solmate/src/tokens/ERC20.sol";

contract Meme is ERC20 {
    constructor(
        string memory _name,
        string memory _symbol,
        uint8 _decimals,
        uint256 _totalSupply
    ) ERC20(_name, _symbol, _decimals) {
        _mint(msg.sender, _totalSupply);
    }

    function burn(uint256 amount) external {
        _burn(msg.sender, amount);
    }
}
