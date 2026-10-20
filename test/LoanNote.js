const { expect } = require("chai");
const { ethers } = require("hardhat");
const { loadFixture } = require("@nomicfoundation/hardhat-toolbox/network-helpers");

describe("LoanNote", function () {
  const borrowerId = ethers.keccak256(ethers.toUtf8Bytes("salt:firebase-uid-123"));
  const principal = 30000000n; // 300,000.00 EUR in cents
  const aprBps = 400; // 4.00%
  const termMonths = 300; // 25 years

  const State = { Approved: 0, Funded: 1, Closed: 2 };

  async function deployFixture() {
    const [admin, minter, stranger, bank] = await ethers.getSigners();
    const loanNote = await (await ethers.getContractFactory("LoanNote")).deploy();
    await loanNote.waitForDeployment();

    const MINTER_ROLE = await loanNote.MINTER_ROLE();
    await loanNote.grantRole(MINTER_ROLE, minter.address);

    return { loanNote, admin, minter, stranger, bank, MINTER_ROLE };
  }

  async function mintOne(loanNote, minter, bank) {
    return loanNote
      .connect(minter)
      .mintLoan(bank.address, borrowerId, principal, aprBps, termMonths);
  }

  describe("Deployment and roles", function () {
    it("gives the deployer the admin and minter roles", async function () {
      const { loanNote, admin, MINTER_ROLE } = await loadFixture(deployFixture);
      expect(await loanNote.hasRole(MINTER_ROLE, admin.address)).to.equal(true);
      expect(await loanNote.hasRole(await loanNote.DEFAULT_ADMIN_ROLE(), admin.address)).to.equal(true);
    });

    it("supports the ERC-721 interface", async function () {
      const { loanNote } = await loadFixture(deployFixture);
      expect(await loanNote.supportsInterface("0x80ac58cd")).to.equal(true);
    });
  });

  describe("Minting", function () {
    it("mints a note with the correct loan data", async function () {
      const { loanNote, minter, bank } = await loadFixture(deployFixture);
      await mintOne(loanNote, minter, bank);

      const loan = await loanNote.getLoan(1);
      expect(loan.principalCents).to.equal(principal);
      expect(loan.aprBps).to.equal(aprBps);
      expect(loan.termMonths).to.equal(termMonths);
      expect(loan.borrowerId).to.equal(borrowerId);
      expect(loan.state).to.equal(State.Approved);
      expect(await loanNote.ownerOf(1)).to.equal(bank.address);
    });

    it("emits a LoanMinted event", async function () {
      const { loanNote, minter, bank } = await loadFixture(deployFixture);
      await expect(mintOne(loanNote, minter, bank))
        .to.emit(loanNote, "LoanMinted")
        .withArgs(1, borrowerId, principal, aprBps, termMonths);
    });

    it("increments token IDs", async function () {
      const { loanNote, minter, bank } = await loadFixture(deployFixture);
      await mintOne(loanNote, minter, bank);
      await mintOne(loanNote, minter, bank);
      expect(await loanNote.ownerOf(2)).to.equal(bank.address);
    });

    it("rejects minting from an account without MINTER_ROLE", async function () {
      const { loanNote, stranger, bank } = await loadFixture(deployFixture);
      await expect(
        loanNote.connect(stranger).mintLoan(bank.address, borrowerId, principal, aprBps, termMonths)
      ).to.be.revertedWithCustomError(loanNote, "AccessControlUnauthorizedAccount");
    });

    it("rejects invalid loan terms", async function () {
      const { loanNote, minter, bank } = await loadFixture(deployFixture);
      const mint = (id, p, apr, term) =>
        loanNote.connect(minter).mintLoan(bank.address, id, p, apr, term);

      await expect(mint(ethers.ZeroHash, principal, aprBps, termMonths)).to.be.revertedWith("Borrower ID required");
      await expect(mint(borrowerId, 0, aprBps, termMonths)).to.be.revertedWith("Principal must be greater than 0");
      await expect(mint(borrowerId, principal, 0, termMonths)).to.be.revertedWith("APR must be between 1 and 10000 bps");
      await expect(mint(borrowerId, principal, 10001, termMonths)).to.be.revertedWith("APR must be between 1 and 10000 bps");
      await expect(mint(borrowerId, principal, aprBps, 0)).to.be.revertedWith("Term must be greater than 0");
    });
  });

  describe("Lifecycle state", function () {
    it("moves Approved -> Funded -> Closed and emits events", async function () {
      const { loanNote, minter, bank } = await loadFixture(deployFixture);
      await mintOne(loanNote, minter, bank);

      await expect(loanNote.connect(minter).updateState(1, State.Funded))
        .to.emit(loanNote, "LoanStateChanged")
        .withArgs(1, State.Approved, State.Funded);
      expect((await loanNote.getLoan(1)).state).to.equal(State.Funded);

      await loanNote.connect(minter).updateState(1, State.Closed);
      expect((await loanNote.getLoan(1)).state).to.equal(State.Closed);
    });

    it("rejects skipping a state", async function () {
      const { loanNote, minter, bank } = await loadFixture(deployFixture);
      await mintOne(loanNote, minter, bank);
      await expect(loanNote.connect(minter).updateState(1, State.Closed)).to.be.revertedWith(
        "Invalid state transition"
      );
    });

    it("rejects moving past Closed", async function () {
      const { loanNote, minter, bank } = await loadFixture(deployFixture);
      await mintOne(loanNote, minter, bank);
      await loanNote.connect(minter).updateState(1, State.Funded);
      await loanNote.connect(minter).updateState(1, State.Closed);
      await expect(loanNote.connect(minter).updateState(1, State.Closed)).to.be.revertedWith(
        "Invalid state transition"
      );
    });

    it("rejects state changes from an account without MINTER_ROLE", async function () {
      const { loanNote, minter, stranger, bank } = await loadFixture(deployFixture);
      await mintOne(loanNote, minter, bank);
      await expect(
        loanNote.connect(stranger).updateState(1, State.Funded)
      ).to.be.revertedWithCustomError(loanNote, "AccessControlUnauthorizedAccount");
    });

    it("rejects reading or updating a token that does not exist", async function () {
      const { loanNote, minter } = await loadFixture(deployFixture);
      await expect(loanNote.getLoan(99)).to.be.revertedWithCustomError(loanNote, "ERC721NonexistentToken");
      await expect(loanNote.connect(minter).updateState(99, State.Funded)).to.be.revertedWithCustomError(
        loanNote,
        "ERC721NonexistentToken"
      );
    });
  });
});
