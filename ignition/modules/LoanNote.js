const { buildModule } = require("@nomicfoundation/hardhat-ignition/modules");

module.exports = buildModule("LoanNoteModule", (m) => {
  const loanNote = m.contract("LoanNote");
  return { loanNote };
});
