# AL (Agentic Lender) - Core & Ledger

Firebase data layer, Core API and Solidity smart contracts for the Agentic Lender mortgage platform (MTU Year 3 group project).

AL-Core & Ledger sits between the client apps (AL-Mobile, AL-Web), the AL-AI Engine and the blockchain. It provides:

- **Firebase Authentication** with role-based custom claims (`borrower`, `broker`, `underwriter`)
- **Cloud Firestore** for application data, protected by role-based security rules
- **Core API (Flask)** that reads and writes application data using the Firebase Admin SDK
- **Smart contracts (Solidity, Hardhat)** that represent approved loans as ERC-721 loan notes
- **Local blockchain node** running in Docker

Personal data stays off-chain. Only a pseudonymous borrower ID, loan terms and hashes are stored on the blockchain.

## Repository contents

| Path | Purpose |
|---|---|
| `app.py` | Flask API: store and read loan applications in Firestore |
| `assign_roles.py` | Sets the `role` custom claim on Firebase users |
| `firestore.rules` | Firestore security rules (role-based access) |
| `requirements.txt` | Python dependencies |
| `contracts/LoanNote.sol` | ERC-721 loan note with role-restricted minting and lifecycle state |
| `test/LoanNote.js` | Hardhat unit tests for `LoanNote` |
| `ignition/modules/LoanNote.js` | Hardhat Ignition deployment module |
| `hardhat.config.js` | Hardhat config (Solidity 0.8.28, EVM target Cancun) |
| `Dockerfile`, `docker-compose.yml`, `.dockerignore` | Local Hardhat blockchain node on port 8545 |

## Prerequisites

- Python 3.10+
- Node.js (LTS) and npm
- Docker Desktop
- Access to the Firebase project `agentic-lender` (ask Conor to add you)

## Secrets: read this first

The Firebase service account key gives full admin access to the project.

- **Never commit it or share it in chat.** `serviceAccountKey.json` and `.env` are listed in `.gitignore`.
- To get a key: Firebase console, **Settings, Service accounts, Generate new private key**.
- Save it as `serviceAccountKey.json` in the repo root, or point to it with an environment variable:

```powershell
$env:GOOGLE_APPLICATION_CREDENTIALS="C:\path\to\your-key.json"
```

Mobile and Web developers do not need this key. They use their own client config (`google-services.json` for Android, `firebaseConfig` for Web) from **Settings, General, Your apps**.

## Run the Core API

```powershell
pip install -r requirements.txt
python app.py
```

The API runs on `http://localhost:5000`.

| Method | Route | Description |
|---|---|---|
| GET | `/health` | Health check |
| POST | `/applications` | Create an application (`borrowerId`, `loanAmount`, `propertyValue`) |
| GET | `/applications` | List applications |
| GET | `/applications/<id>` | Read one application |

Example (PowerShell):

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:5000/applications -ContentType "application/json" -Body '{"borrowerId":"test123","loanAmount":300000,"propertyValue":400000}'
```

> Current status: this is a test API. It does not yet verify Firebase ID tokens or roles, so do not expose it publicly. Token verification is planned for Sprint 2.

## Assign user roles

Create the user in **Firebase console, Authentication, Users** first, then:

```powershell
python assign_roles.py                              # sets the three default test accounts
python assign_roles.py someone@example.com broker   # sets one user's role
```

Valid roles: `borrower`, `broker`, `underwriter`. Users must sign out and back in before the new role appears in their token.

## Firestore security rules

Copy the contents of `firestore.rules` into **Firebase console, Firestore Database, Rules**, then click **Publish**.

Summary of the rules:

- Borrowers read and edit only their own applications, and only while the status is `Draft`
- Brokers read only applications assigned to them (`brokerId`)
- Underwriters read all applications
- Fields written by the Core API (`valuation`, `aiResult`, `decision`, `tokenId`, `txHash`, `brokerId`) cannot be written by clients
- Everything else is denied

The Core API uses the Firebase Admin SDK, which bypasses these rules.

## Smart contracts and tests

```powershell
npm install
npx hardhat compile
npx hardhat test
```

`LoanNote` has 12 unit tests covering minting, access control, validation and lifecycle state changes (Approved, Funded, Closed).

## Run the local blockchain node

Start Docker Desktop, then:

```powershell
docker compose up -d --build     # start the node in the background
docker compose logs              # view the logs
docker compose down              # stop the node
```

The node listens on `http://localhost:8545` (chain ID 31337). Deploy a contract to it:

```powershell
npx hardhat ignition deploy ./ignition/modules/LoanNote.js --network localhost
```

The chain is in-memory, so it resets every time the node restarts. Redeploy contracts after a restart. The accounts and private keys the node prints are Hardhat's public test accounts. Never use them on a real network.

## Troubleshooting (Windows)

- **"running scripts is disabled" when running npm:** run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once.
- **`docker` not recognised:** restart VS Code or your PC after installing Docker Desktop.
- **Compile error mentioning `mcopy`:** the EVM target must be `cancun` (already set in `hardhat.config.js`).
- **Firestore "permission denied" in the apps:** the user probably has no role claim yet, or has not signed out and back in since it was set.

## Roadmap

- Core API: Firebase token verification, role checks and borrower role assignment after sign-up
- `AuditRegistry` contract storing SHA-256 hashes of credit memos, valuations and approvals
- Settlement service (Web3.py) that mints the loan note and records the audit hash on underwriter approval
- AI Engine dispatch from the Core API
- Possible enhancement: deployment to a public testnet (Polygon Amoy)

## Team

AL-Core & Ledger: Conor Dwyer. Other subsystems: AL-Mobile (Oisin McCarthy), AL-Web (Emmet Casey), AL-AI Engine (Ben Geary).
