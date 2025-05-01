import asyncio
import traceback
from typing import Dict, List, Optional
import json
import aiohttp
import uuid
from bonk_mcp.settings import BIRDEYE_API_KEY
from mcp.types import TextContent, Tool, ImageContent, EmbeddedResource


class BirdEyeTrendingTokensTool:
    """Tool for fetching trending tokens from BirdEye"""

    def __init__(self):
        self.name = "birdeye-trending-tokens"
        self.description = "Get trending tokens on Solana from BirdEye"
        self.input_schema = {
            "type": "object",
            "properties": {},
            "required": []
        }

    async def execute(self, arguments: Dict) -> List[TextContent | ImageContent | EmbeddedResource]:
        """
        Execute the BirdEye trending tokens tool

        Args:
            arguments: Dictionary (not used)

        Returns:
            List of content items with the result
        """
        return await self._get_trending_tokens()

    def _parse_token_data(self, token_data: List[Dict]) -> List[Dict]:
        """
        Parse token data from the BirdEye API response

        Args:
            token_data: List of token objects from the API response

        Returns:
            List of parsed token objects with standardized fields
        """
        parsed_tokens = []

        for token in token_data:
            # Extract relevant fields
            parsed_token = {
                "name": token.get("name", "Unknown"),
                "symbol": token.get("symbol", "Unknown"),
                "address": token.get("address", ""),
                "price": token.get("price", 0),
                "price_change_24h": token.get("price24hChangePercent", 0),
                "volume_24h": token.get("volume24hUSD", 0),
                "liquidity": token.get("liquidity", 0),
                "marketcap": token.get("marketcap", 0),
                "rank": token.get("rank", 0),
                "logo_url": token.get("logoURI", "")
            }
            parsed_tokens.append(parsed_token)

        return parsed_tokens

    async def _get_trending_tokens(self) -> List[TextContent]:
        """
        Get trending tokens on Solana from BirdEye

        Returns:
            List of content items with trending token information
        """
        try:
            # Ensure we have a valid API key
            if not BIRDEYE_API_KEY:
                return [TextContent(
                    type="text",
                    text="Error: Missing BirdEye API key. Please set the BIRDEYE_API_KEY in your settings."
                )]

            # Prepare headers for BirdEye API request - ensure all keys and values are strings
            headers = {
                "accept": "application/json",
                # Convert to string to ensure it's not None
                "X-API-KEY": str(BIRDEYE_API_KEY),
                "x-chain": "solana"
            }

            # Make request to BirdEye API using the public API endpoint that works
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://public-api.birdeye.so/defi/token_trending?sort_by=rank&sort_type=asc&offset=0&limit=20",
                    headers=headers
                ) as response:
                    if response.status != 200:
                        return [TextContent(
                            type="text",
                            text=f"Error: Failed to fetch trending tokens. Status code: {response.status}"
                        )]

                    # Parse response
                    result = await response.json()
                    if not result.get("success"):
                        return [TextContent(
                            type="text",
                            text=f"Error: BirdEye API returned error: {result.get('statusCode', 'Unknown error')}"
                        )]

                    # Extract token data
                    tokens = result.get("data", {}).get("tokens", [])
                    if not tokens:
                        return [TextContent(
                            type="text",
                            text="No trending tokens found."
                        )]

                    # Parse token data
                    parsed_tokens = self._parse_token_data(tokens)

                    # Format response
                    table_rows = []
                    for i, token in enumerate(parsed_tokens):
                        name = token["name"]
                        symbol = token["symbol"]
                        price = token["price"]
                        price_change = token["price_change_24h"]
                        volume = token["volume_24h"]
                        liquidity = token["liquidity"]
                        token_address = token["address"]
                        marketcap = token["marketcap"]
                        rank = token["rank"]

                        # Format price change with color indicator
                        price_change_str = f"{price_change:.2f}%" if price_change < 100 else f"{price_change:.1f}%"
                        if price_change > 10000:
                            price_change_str = f"{price_change/1000:.1f}k%"

                        # Add row to table
                        table_rows.append(
                            f"{rank}. {name} ({symbol})\n"
                            f"   Price: ${price:.6f} ({price_change_str} 24h)\n"
                            f"   Volume 24h: ${volume:,.0f}\n"
                            f"   Liquidity: ${liquidity:,.0f}\n"
                            f"   Market Cap: ${marketcap:,.0f}\n"
                            f"   Address: {token_address}\n"
                        )

                    # Build full response
                    response_text = (
                        f"🔥 Trending Tokens on Solana (via BirdEye)\n\n"
                        f"{''.join(table_rows)}"
                    )

                    return [TextContent(
                        type="text",
                        text=response_text
                    )]

        except Exception as e:
            error_msg = f"Error fetching trending tokens: {traceback.format_exc()}"
            print(error_msg)
            return [TextContent(
                type="text",
                text=error_msg
            )]

    def get_tool_definition(self) -> Tool:
        """Get the tool definition for MCP"""
        return Tool(
            name=self.name,
            description=self.description,
            inputSchema=self.input_schema
        )


class BirdEyeTopTradersTool:
    """Tool for fetching top traders/gainers from BirdEye"""

    def __init__(self):
        self.name = "birdeye-top-traders"
        self.description = "Get top traders on Solana from BirdEye (showing today's data)"
        self.input_schema = {
            "type": "object",
            "properties": {},
            "required": []
        }

    async def execute(self, arguments: Dict) -> List[TextContent | ImageContent | EmbeddedResource]:
        """
        Execute the BirdEye top traders tool

        Args:
            arguments: Dictionary with optional parameters (ignored, using hardcoded values)

        Returns:
            List of content items with the result
        """
        # Using hardcoded values: type=today, limit=10
        return await self._get_top_traders("today", 10)

    async def _get_address_details(self, addresses: List[str]) -> Dict[str, Dict]:
        """
        Get token details for a list of addresses

        Args:
            addresses: List of token addresses

        Returns:
            Dictionary mapping addresses to their details
        """
        if not BIRDEYE_API_KEY:
            return {}

        headers = {
            "accept": "application/json",
            "X-API-KEY": str(BIRDEYE_API_KEY),
            "x-chain": "solana"
        }

        address_details = {}

        try:
            # Create a comma-separated list of addresses
            address_str = ",".join(addresses)

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"https://public-api.birdeye.so/defi/tokens?tokens={address_str}",
                    headers=headers
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        if result.get("success") and result.get("data"):
                            tokens = result.get("data", {}).get("tokens", {})
                            address_details = tokens
        except Exception:
            # Silently fail - we'll show addresses without details if this fails
            pass

        return address_details

    async def _get_top_traders(self, time_period: str, limit: int) -> List[TextContent]:
        """
        Get top traders on Solana from BirdEye

        Args:
            time_period: Time period for PnL calculation (1D, 1W, 1M)
            limit: Number of traders to return

        Returns:
            List of content items with top traders information
        """
        try:
            # Ensure we have a valid API key
            if not BIRDEYE_API_KEY:
                return [TextContent(
                    type="text",
                    text="Error: Missing BirdEye API key. Please set the BIRDEYE_API_KEY in your settings."
                )]

            # Prepare headers for BirdEye API request
            headers = {
                "accept": "application/json",
                "X-API-KEY": str(BIRDEYE_API_KEY),
                "x-chain": "solana"
            }

            # Make request to BirdEye API using hardcoded values
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://public-api.birdeye.so/trader/gainers-losers?type=today&sort_by=PnL&sort_type=desc&offset=0&limit=10",
                    headers=headers
                ) as response:
                    if response.status != 200:
                        response_text = await response.text()
                        return [TextContent(
                            type="text",
                            text=f"Error: Failed to fetch top traders. Status code: {response.status}\nDetails: {response_text}"
                        )]

                    # Parse response
                    result = await response.json()
                    if not result.get("success"):
                        return [TextContent(
                            type="text",
                            text=f"Error: BirdEye API returned error: {result.get('statusCode', 'Unknown error')}"
                        )]

                    # Extract trader data
                    traders = result.get("data", {}).get("items", [])
                    if not traders:
                        return [TextContent(
                            type="text",
                            text="No top traders found."
                        )]

                    # Extract addresses for lookup
                    addresses = [trader.get("address")
                                 for trader in traders if trader.get("address")]

                    # Get token details for addresses
                    address_details = await self._get_address_details(addresses)

                    # Format response
                    table_rows = []
                    for i, trader in enumerate(traders):
                        address = trader.get("address", "")
                        pnl = trader.get("pnl", 0)
                        volume = trader.get("volume", 0)
                        trade_count = trader.get("trade_count", 0)

                        # Get token details if available
                        token_details = address_details.get(address, {})
                        name = token_details.get("name", "Unknown")
                        symbol = token_details.get("symbol", "Unknown")

                        # Only show token name/symbol if we have details
                        wallet_display = f"{name} ({symbol})" if token_details else address

                        # Add row to table
                        table_rows.append(
                            f"{i+1}. {wallet_display}\n"
                            f"   PnL: ${pnl:,.2f}\n"
                            f"   Volume: ${volume:,.2f}\n"
                            f"   Trades: {trade_count:,}\n"
                            f"   Address: {address}\n"
                        )

                    # Build full response
                    response_text = (
                        f"💰 Top Traders on Solana ({time_period}) (via BirdEye)\n\n"
                        f"{''.join(table_rows)}"
                    )

                    return [TextContent(
                        type="text",
                        text=response_text
                    )]

        except Exception as e:
            error_msg = f"Error fetching top traders: {traceback.format_exc()}"
            print(error_msg)
            return [TextContent(
                type="text",
                text=error_msg
            )]

    def get_tool_definition(self) -> Tool:
        """Get the tool definition for MCP"""
        return Tool(
            name=self.name,
            description=self.description,
            inputSchema=self.input_schema
        )


# Create instances for export
birdeye_trending_tokens_tool = BirdEyeTrendingTokensTool()
birdeye_top_traders_tool = BirdEyeTopTradersTool()
