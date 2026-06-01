# Thanatos Intel

Crypto intelligence & compliance tools for Frappe/ERPNext.

## Features

### Token Liquidity Testing
- **Comprehensive liquidity analysis** of cryptocurrency tokens
- **Multi-source data aggregation** (DEX Screener, Uniswap Subgraph)
- **Real-world slippage estimation** for swap operations
- **Risk assessment** with clear pass/fail verdict
- **Full audit trail** of all tests performed

### Supported Chains
- Polygon (Primary support)
- Ethereum (Coming soon)
- Arbitrum (Coming soon)
- Base (Coming soon)

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

- **DEX Screener API** - Primary source for liquidity data
- **Uniswap V3 Subgraph** - Secondary source for deeper analysis
- **Manual Input** - For known token data

## API Endpoints

### Quick Test

```bash
GET /api/method/thanatos_intel.crypto_liquidity_test.doctype.token_liquidity_test.token_liquidity_test.run_quick_test
?token_address=0x...&blockchain=Polygon&amount=100
```

**Response:**
```json
{
  "symbol": "OES",
  "name": "One Ecosystem Token",
  "price": 44.46,
  "liquidity": 12500000,
  "volume_24h": 585.40,
  "slippage_pct": 0.45,
  "liquidity_status": "Adequate",
  "is_liquidizable": true,
  "risk_assessment": "✅ LIQUIDIZABLE - Adequate liquidity detected",
  "data_sources": "DEX Screener"
}
```

## DocTypes

### Token Liquidity Test
Main document type for storing test results and analysis.

**Fields:**
- Token Address & Metadata
- Test Configuration (amount, target token)
- Results (price, liquidity, slippage)
- Risk Assessment & Verdict
- Metadata (analyst, timestamp, notes)

### Blockchain (Master)
Reference list of supported blockchains.

### Token (Master)
Reference list of known tokens and their properties.

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

## Security

- **No wallet integration** - pure analysis tool
- **No private keys** - read-only operations
- **Public API only** - no authenticated endpoints
- **Full audit trail** - all tests logged

## License

MIT
