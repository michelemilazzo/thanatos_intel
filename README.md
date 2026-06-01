# Thanatos Intel

Crypto intelligence & compliance tools for Frappe/ERPNext.

## Features

### Token Liquidity Testing
- **Comprehensive liquidity analysis** of cryptocurrency tokens
- **Multi-source data aggregation** (DEX Screener, Uniswap Subgraph, CoinGecko)
- **Real-world slippage estimation** for swap operations
- **Risk assessment** with clear pass/fail verdict
- **Full audit trail** of all tests performed
- **Analytics report** with historical data and trend analysis
- **Webhook support** for compliance & monitoring

### Supported Chains
- ✅ Polygon (Primary support)
- ✅ Ethereum
- ✅ Arbitrum
- ✅ Base

## Installation

```bash
cd /path/to/frappe-bench
bench get-app thanatos_intel https://github.com/OneKeyMaybe/thanatos_intel.git
bench install-app thanatos_intel
```

## Usage

### Token Liquidity Test

1. Navigate to **Thanatos Intel** → **Token Liquidity Test**
2. Fill in the form:
   - **Blockchain**: Select target chain (Polygon)
   - **Token Address**: Paste contract address (e.g., 0xb85cfa8fe...)
   - **Test Amount**: Amount to simulate (default 100)
   - **Target Token**: Swap target (default USDT)
3. Click **"Run Test Now"** button
4. System will:
   - Fetch current token price
   - Query pool liquidity
   - Calculate slippage impact
   - Generate risk assessment

### Verdict Interpretation

- **✅ LIQUIDIZABLE**: Token has adequate liquidity, low slippage expected
- **⚠️ LOW LIQUIDITY**: Significant slippage, use with caution
- **❌ ILLIQUID**: Token has insufficient liquidity, not recommended for trading

## Data Sources

- **DEX Screener API** - Primary: real-time liquidity & volume
- **Uniswap V3 Subgraph** - Secondary: chain-specific pool data (Polygon, Ethereum, Arbitrum, Base)
- **CoinGecko API** - Fallback: market cap & 24h volume
- **Automatic fallback chain** if primary source fails

## Reports

### Token Liquidity Analytics
Comprehensive report with filtering and analytics.

**Features:**
- Filter by date range, blockchain, liquidity status
- View all tests with full metadata
- Export to CSV for external analysis
- Analyst tracking for accountability
- Verdict & risk level summarization

**Access:** Frappe Desk → Thanatos Intel → Token Liquidity Analytics

## API Endpoints

### Quick Test (Multi-source)

```bash
GET /api/method/thanatos_intel.crypto_liquidity_test.api.get_token_data
?token_address=0x...&blockchain=Polygon&amount=100
```

**Response:**
```json
{
  "symbol": "OES",
  "name": "One Ecosystem Token",
  "chain": "Polygon",
  "price": 44.46,
  "liquidity": 12500000,
  "volume_24h": 585.40,
  "slippage_pct": 0.45,
  "liquidity_status": "Adequate",
  "is_liquidizable": true,
  "risk_assessment": "✅ LIQUIDIZABLE - Adequate liquidity detected",
  "data_sources": ["DEX Screener"]
}
```

### Token Data (any chain)

**Request:**
```bash
GET /api/method/thanatos_intel.crypto_liquidity_test.api.get_token_data
?token_address=0x1234...&blockchain=Arbitrum&amount=500
```

**Tries data sources in order:**
1. DEX Screener (fastest)
2. Uniswap Subgraph (most accurate per-chain)
3. CoinGecko (reliable fallback)

Returns same response format with `data_sources` array showing which sources were tried.

## DocTypes

### Token Liquidity Test
Main document type for storing test results and analysis.

**Fields:**
- Token Address & Metadata
- Test Configuration (amount, target token)
- Results (price, liquidity, slippage)
- Risk Assessment & Verdict
- Metadata (analyst, timestamp, notes)

### Token Test Audit Log
Automatic audit trail for compliance and monitoring.

**Fields:**
- Test reference
- Token & blockchain info
- Verdict (PASS/FAIL)
- Risk level (Low/Medium/High)
- Full test data (JSON)
- Analyst & timestamp

### Blockchain (Master)
Reference list of supported blockchains with RPC URLs.

**Supported:**
- Polygon (137)
- Ethereum (1)
- Arbitrum (42161)
- Base (8453)

### Token (Master)
Reference list of known tokens and their properties.

**Included defaults:**
- USDT, USDC (stablecoins)
- WETH, WMATIC (wrapped tokens)

## Development

### Backend Architecture
- `/doctype/token_liquidity_test/` - Main test DocType
- API methods use public blockchain explorer APIs
- No private keys stored or used

### Frontend
- Vue-based form UI
- Real-time verdict banners
- Color-coded risk indicators

### Testing
```bash
bench --site <sitename> execute thanatos_intel.crypto_liquidity_test.doctype.token_liquidity_test.token_liquidity_test.run_quick_test
```

## Audit Trail & Compliance

Every token test is automatically logged to **Token Test Audit Log** with:
- Full test data (JSON) for forensic analysis
- Analyst identification for accountability
- Verdict (PASS/FAIL) and risk level classification
- Immutable timestamps
- Blockchain + symbol + amount for context

**Use cases:**
- Compliance audits
- Risk management review
- Analyst performance tracking
- Post-mortem analysis on failed trades

## Security

- **No wallet integration** - pure analysis tool
- **No private keys** - read-only operations
- **Public API only** - no authenticated credentials stored
- **Full immutable audit trail** - all tests logged automatically
- **Read-only access** to audit logs (System Manager only)
- **JSON data** for external compliance systems

## License

MIT
