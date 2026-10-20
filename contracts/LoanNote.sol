// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {ERC721} from "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";

/// @title LoanNote
/// @notice Represents an approved mortgage/HELOC as an ERC-721 digital loan note.
/// @dev No personal data is stored on-chain: only a pseudonymous borrower ID
///      (e.g. a salted hash of the Firebase UID) and the loan terms.
contract LoanNote is ERC721, AccessControl {
    bytes32 public constant MINTER_ROLE = keccak256("MINTER_ROLE");

    /// Mirrors the AL lifecycle after underwriter approval.
    enum LoanState {
        Approved,
        Funded,
        Closed
    }

    struct Loan {
        uint256 principalCents; // principal in euro cents, avoids decimals
        uint32 aprBps; // APR in basis points (100 bps = 1%)
        uint16 termMonths;
        bytes32 borrowerId; // pseudonymous borrower identifier
        LoanState state;
    }

    uint256 private _nextTokenId = 1;
    mapping(uint256 => Loan) private _loans;

    event LoanMinted(
        uint256 indexed tokenId,
        bytes32 indexed borrowerId,
        uint256 principalCents,
        uint32 aprBps,
        uint16 termMonths
    );

    event LoanStateChanged(uint256 indexed tokenId, LoanState oldState, LoanState newState);

    constructor() ERC721("Agentic Lender Loan Note", "ALLN") {
        _grantRole(DEFAULT_ADMIN_ROLE, msg.sender);
        _grantRole(MINTER_ROLE, msg.sender);
    }

    /// @notice Mint a loan note. Only callable by the settlement service (MINTER_ROLE).
    function mintLoan(
        address to,
        bytes32 borrowerId,
        uint256 principalCents,
        uint32 aprBps,
        uint16 termMonths
    ) external onlyRole(MINTER_ROLE) returns (uint256 tokenId) {
        require(borrowerId != bytes32(0), "Borrower ID required");
        require(principalCents > 0, "Principal must be greater than 0");
        require(aprBps > 0 && aprBps <= 10000, "APR must be between 1 and 10000 bps");
        require(termMonths > 0, "Term must be greater than 0");

        tokenId = _nextTokenId++;
        _loans[tokenId] = Loan(principalCents, aprBps, termMonths, borrowerId, LoanState.Approved);
        _mint(to, tokenId);

        emit LoanMinted(tokenId, borrowerId, principalCents, aprBps, termMonths);
    }

    /// @notice Move a loan to the next lifecycle state (Approved -> Funded -> Closed).
    function updateState(uint256 tokenId, LoanState newState) external onlyRole(MINTER_ROLE) {
        _requireOwned(tokenId);

        LoanState oldState = _loans[tokenId].state;
        require(uint8(newState) == uint8(oldState) + 1, "Invalid state transition");

        _loans[tokenId].state = newState;
        emit LoanStateChanged(tokenId, oldState, newState);
    }

    function getLoan(uint256 tokenId) external view returns (Loan memory) {
        _requireOwned(tokenId);
        return _loans[tokenId];
    }

    function supportsInterface(
        bytes4 interfaceId
    ) public view override(ERC721, AccessControl) returns (bool) {
        return super.supportsInterface(interfaceId);
    }
}
