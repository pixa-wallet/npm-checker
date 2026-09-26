# PackageProof Pro

PackageProof Pro is an Algorand x402 v2-paid dependency firewall for npm and PyPI. It returns an auditable `allow`, `review`, or `block` verdict using registry intelligence, static analysis, optional E2B sandbox detonation, and an optional OpenRouter explanation layer.

## API

- `GET /` — machine-readable service and payment manifest
- `GET /health` — runtime and Algorand payment configuration
- `POST /v1/analyze-package` — paid package risk assessment
- `POST /v1/analyze-manifest` — free manifest analysis
- `GET /v1/reports/{report_id}` — free report retrieval

`POST /v1/analyze-package` uses the official `x402-avm` Python SDK, x402 v2 `exact` payments, Algorand USDC, GoPlausible's facilitator, and the Bazaar discovery extension. Payment configuration fails closed when enabled but incomplete.

## Local development

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e . pytest pytest-asyncio ruff
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m uvicorn packageproof.main:app --reload --port 8000
```

Keep `X402_ENABLED=false` for ordinary unit tests. To validate the real TestNet challenge, set:

```env
X402_ENABLED=true
X402_NETWORK=testnet
PAY_TO_ADDRESS=<58-character TestNet address>
FACILITATOR_URL=https://facilitator.goplausible.xyz
X402_CHALLENGE_TAG=x402-global-challenge
```

The service automatically selects TestNet USDC ASA `10458941`. `X402_ASSET_ID` is only a safety assertion; when set, startup rejects an ID that does not match the selected network.

## Paid TestNet check

The buyer mnemonic is needed only by the local test client. Never deploy it to the server or commit it.

```powershell
$env:ALGORAND_MNEMONIC="<disposable TestNet mnemonic>"
$env:AVM_ADDRESS="<derived TestNet address>"
.\.venv\Scripts\python.exe scripts/live_x402_paid_check.py `
  --service package `
  --url http://127.0.0.1:8000/v1/analyze-package
```

The script enforces a 0.10 USDC maximum, defaults to TestNet, verifies that the mnemonic derives the expected address, and requires an explicit `--allow-mainnet` flag for any MainNet payment.

## MainNet cutover

```env
ENVIRONMENT=production
X402_ENABLED=true
X402_NETWORK=mainnet
PAY_TO_ADDRESS=<MainNet account opted into USDC ASA 31566704>
FACILITATOR_URL=https://facilitator.goplausible.xyz
X402_ASSET_ID=31566704
X402_CHALLENGE_TAG=x402-global-challenge
```

Deploy behind public HTTPS, settle one real MainNet payment through GoPlausible, and confirm the resource appears in Bazaar and the challenge leaderboard. If both repository services use one `payTo`, expose them as routes under one root domain; the challenge rules prohibit reusing one merchant address across different domains.

## Verification

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest -q
```

The project is Railway-ready. Set the Railway service root directory to `proofX`, configure environment variables from `.env.example`, and persist `/app/data` if SQLite reports must survive redeploys.
