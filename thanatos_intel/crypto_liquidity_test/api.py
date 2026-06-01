"""
API module for Thanatos Intel crypto liquidity testing
Multi-source data aggregation: DEX Screener, Uniswap Subgraph, CoinGecko
"""

import frappe
import requests
import json
from frappe import _


class TokenDataAggregator:
    """Aggregate token data from multiple sources"""

    SOURCES = {
        "dex_screener": "https://api.dexscreener.com/latest/dex/tokens",
        "uniswap_subgraph": "https://api.thegraph.com/subgraphs/name/uniswap/uniswap-v3",
        "coingecko": "https://api.coingecko.com/api/v3/simple/token_price",
    }

    CHAIN_CONFIGS = {
        "Polygon": {
            "id": "polygon",
            "chain_id": 137,
            "rpc": "https://polygon-rpc.com",
            "explorer": "https://polygonscan.com",
            "dex_screener_id": "polygon",
        },
        "Ethereum": {
            "id": "ethereum",
            "chain_id": 1,
            "rpc": "https://eth.public-rpc.com",
            "explorer": "https://etherscan.io",
            "dex_screener_id": "ethereum",
        },
        "Arbitrum": {
            "id": "arbitrum",
            "chain_id": 42161,
            "rpc": "https://arb1.arbitrum.io/rpc",
            "explorer": "https://arbiscan.io",
            "dex_screener_id": "arbitrum",
        },
        "Base": {
            "id": "base",
            "chain_id": 8453,
            "rpc": "https://mainnet.base.org",
            "explorer": "https://basescan.org",
            "dex_screener_id": "base",
        },
    }

    def __init__(self, token_address, blockchain, amount=100):
        self.token_address = token_address.lower()
        self.blockchain = blockchain
        self.amount = float(amount)
        self.result = self._default_result()

    def _default_result(self):
        return {
            "symbol": "",
            "name": "",
            "price": 0,
            "liquidity": 0,
            "volume_24h": 0,
            "slippage_pct": 0,
            "liquidity_status": "No Data",
            "is_liquidizable": False,
            "risk_assessment": "",
            "data_sources": [],
            "chain": self.blockchain,
        }

    def aggregate(self):
        """Try multiple data sources in order"""
        sources_tried = []

        # Try DEX Screener
        try:
            dex_result = self._fetch_dex_screener()
            if dex_result:
                self.result.update(dex_result)
                sources_tried.append("DEX Screener")
                self.result["data_sources"] = sources_tried
                return self.result
        except Exception as e:
            frappe.log_error(f"DEX Screener error: {str(e)}", "Token Aggregator")

        # Try Uniswap Subgraph
        try:
            uniswap_result = self._fetch_uniswap_subgraph()
            if uniswap_result:
                self.result.update(uniswap_result)
                sources_tried.append("Uniswap Subgraph")
                self.result["data_sources"] = sources_tried
                return self.result
        except Exception as e:
            frappe.log_error(f"Uniswap Subgraph error: {str(e)}", "Token Aggregator")

        # Try CoinGecko
        try:
            coingecko_result = self._fetch_coingecko()
            if coingecko_result:
                self.result.update(coingecko_result)
                sources_tried.append("CoinGecko")
                self.result["data_sources"] = sources_tried
                return self.result
        except Exception as e:
            frappe.log_error(f"CoinGecko error: {str(e)}", "Token Aggregator")

        # No data found
        self.result["risk_assessment"] = "Unable to fetch liquidity data from any source"
        self.result["data_sources"] = sources_tried if sources_tried else ["None"]
        return self.result

    def _fetch_dex_screener(self):
        """Fetch from DEX Screener API"""
        try:
            response = requests.get(
                f"{self.SOURCES['dex_screener']}/{self.token_address}",
                timeout=10
            )

            if response.status_code != 200:
                return None

            data = response.json()
            if not data.get("pairs"):
                return None

            pair = data["pairs"][0]
            result = {
                "symbol": pair.get("baseToken", {}).get("symbol", "???"),
                "name": pair.get("baseToken", {}).get("name", "Unknown"),
                "price": float(pair.get("priceUsd", 0)),
                "liquidity": float(pair.get("liquidity", {}).get("usd", 0)),
                "volume_24h": float(pair.get("volume", {}).get("h24", 0)),
            }

            self._calculate_verdict(result)
            return result
        except Exception:
            return None

    def _fetch_uniswap_subgraph(self):
        """Fetch from Uniswap V3 Subgraph"""
        try:
            chain_config = self.CHAIN_CONFIGS.get(self.blockchain, {})
            subgraph_url = f"{self.SOURCES['uniswap_subgraph']}-{chain_config.get('id', 'polygon')}"

            query = """
            {
              tokenDayDatas(
                first: 1
                orderBy: date
                orderDirection: desc
                where: {token: "%s"}
              ) {
                priceUSD
                volume
                liquidity
              }
            }
            """ % self.token_address

            response = requests.post(
                subgraph_url,
                json={"query": query},
                timeout=10
            )

            if response.status_code != 200:
                return None

            data = response.json()
            if not data.get("data", {}).get("tokenDayDatas"):
                return None

            token_data = data["data"]["tokenDayDatas"][0]
            result = {
                "symbol": "???",  # Subgraph doesn't provide symbol
                "name": "Unknown",
                "price": float(token_data.get("priceUSD", 0)),
                "liquidity": float(token_data.get("liquidity", 0)),
                "volume_24h": float(token_data.get("volume", 0)),
            }

            self._calculate_verdict(result)
            return result
        except Exception:
            return None

    def _fetch_coingecko(self):
        """Fetch from CoinGecko (fallback)"""
        try:
            params = {
                "contract_addresses": self.token_address,
                "vs_currencies": "usd",
                "include_market_cap": "true",
                "include_24hr_vol": "true",
            }

            response = requests.get(
                self.SOURCES["coingecko"],
                params=params,
                timeout=10
            )

            if response.status_code != 200:
                return None

            data = response.json()
            if self.token_address not in data:
                return None

            token_data = data[self.token_address]
            if "usd" not in token_data:
                return None

            result = {
                "symbol": "???",
                "name": "Unknown",
                "price": float(token_data.get("usd", 0)),
                "liquidity": float(token_data.get("usd_market_cap", 0)) * 0.1,  # Estimate
                "volume_24h": float(token_data.get("usd_24h_vol", 0)),
            }

            self._calculate_verdict(result)
            return result
        except Exception:
            return None

    def _calculate_verdict(self, result):
        """Calculate slippage and risk verdict"""
        price = result.get("price", 0)
        liquidity = result.get("liquidity", 0)
        volume_24h = result.get("volume_24h", 0)

        test_value = self.amount * price

        if liquidity == 0:
            result["liquidity_status"] = "Insufficient"
            result["is_liquidizable"] = False
            result["slippage_pct"] = 100
            result["risk_assessment"] = "❌ ZERO LIQUIDITY - Token is not tradable"
        elif test_value > liquidity * 0.1:
            result["liquidity_status"] = "Insufficient"
            result["is_liquidizable"] = False
            slippage = (test_value / liquidity) * 100 * 10
            result["slippage_pct"] = min(slippage, 100)
            result[
                "risk_assessment"
            ] = f"❌ ILLIQUID - Test amount ${test_value:,.0f} is {test_value/liquidity:.1%} of pool. Extreme slippage."
        elif test_value > liquidity * 0.01:
            result["liquidity_status"] = "Low"
            result["is_liquidizable"] = False
            slippage = (test_value / liquidity) * 100 * 5
            result["slippage_pct"] = min(slippage, 50)
            result[
                "risk_assessment"
            ] = f"⚠️ LOW LIQUIDITY - Significant slippage expected ({slippage:.1f}%)"
        elif volume_24h < 1000:
            result["liquidity_status"] = "Low"
            result["is_liquidizable"] = False
            slippage = (test_value / liquidity) * 100
            result["slippage_pct"] = slippage
            result[
                "risk_assessment"
            ] = f"⚠️ LOW VOLUME - 24h volume ${volume_24h:,.0f}, likely low liquidity"
        else:
            result["liquidity_status"] = "Adequate"
            result["is_liquidizable"] = True
            slippage = (test_value / liquidity) * 100 * 0.5
            result["slippage_pct"] = min(slippage, 5)
            result[
                "risk_assessment"
            ] = "✅ LIQUIDIZABLE - Adequate liquidity & volume detected"


@frappe.whitelist()
def get_token_data(token_address, blockchain="Polygon", amount=100):
    """API endpoint for token liquidity analysis"""
    aggregator = TokenDataAggregator(token_address, blockchain, amount)
    return aggregator.aggregate()
