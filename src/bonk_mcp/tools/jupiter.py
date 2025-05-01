import asyncio
import traceback
from typing import Dict, List, Optional
import json
import base64
import base58
from solders.keypair import Keypair
from mcp.types import TextContent, Tool, ImageContent, EmbeddedResource
from bonk_mcp.settings import KEYPAIR
from bonk_mcp.core.jupiter import JupiterSwapClient, SwapMode, QuoteRequest


# Map of token tickers to their mint addresses
TOKEN_DICTIONARY = {
    # Native SOL
    "SOL": "So11111111111111111111111111111111111111112",
    # Popular tokens
    "BONK": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
    "BONKAI": "hqYtLoxviwGENvogcJ5324YTbYqW5H9LHtmQu5Jbonk",
    "USDC": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "USDT": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
    "PYTH": "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3",
    "JTO": "jtojtomepa8beP8AuQc6eXt5FriJwfFMwQx2v2f9XCE",
    "WIF": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
    "ORCA": "orcaEKTdK7LKz57vaAYr9QeNsVEPfiu6QeMU1kektZE",
    "MSOL": "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So",
    "JITOSOL": "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn",
    "BSOL": "bSo13r4TkiE4KumL71LsHTPpL2euBYLFx6h9HP3piy1"
}


class JupiterSwapTool:
    """Tool for swapping tokens using Jupiter on Solana"""

    def __init__(self):
        self.name = "jupiter-swap"
        self.description = "Swap tokens on Solana using Jupiter"
        self.input_schema = {
            "type": "object",
            "properties": {
                "input_mint": {
                    "type": "string",
                    "description": "The mint address of the input token"
                },
                "output_mint": {
                    "type": "string",
                    "description": "The mint address of the output token"
                },
                "amount": {
                    "type": "number",
                    "description": "The amount of input tokens to swap"
                },
                "slippage_bps": {
                    "type": "number",
                    "description": "Slippage tolerance in basis points (e.g., 1000 = 10%)",
                    "default": 1000
                }
            },
            "required": ["input_mint", "output_mint", "amount"]
        }
        self.jupiter_client = JupiterSwapClient()

    async def execute(self, arguments: Dict) -> List[TextContent | ImageContent | EmbeddedResource]:
        """
        Execute the Jupiter swap tool

        Args:
            arguments: Dictionary with swap parameters

        Returns:
            List of content items with the result
        """
        try:
            # Extract parameters
            input_mint = arguments.get("input_mint")
            output_mint = arguments.get("output_mint")
            amount = arguments.get("amount")
            slippage_bps = arguments.get("slippage_bps", 100)  # Default 1%

            # Validate parameters
            if not input_mint or not output_mint or not amount:
                return [TextContent(
                    type="text",
                    text="Error: Missing required parameters. Please provide input_mint, output_mint, and amount."
                )]

            # Convert amount to the smallest unit (lamports/tokens with decimals)
            # Note: This assumes amount is in the token's native units (e.g., SOL, not lamports)
            # For proper implementation, we would need to query token metadata or use a hardcoded mapping
            # For this version, we'll assume 9 decimals (like SOL) for simplicity
            decimals = 9
            amount_raw = int(float(amount) * (10 ** decimals))

            # Get swap quote
            result = await self._execute_swap(
                input_mint=input_mint,
                output_mint=output_mint,
                amount=amount_raw,
                slippage_bps=slippage_bps
            )

            return [TextContent(
                type="text",
                text=result
            )]

        except Exception as e:
            error_msg = f"Error executing Jupiter swap: {traceback.format_exc()}"
            print(error_msg)
            return [TextContent(
                type="text",
                text=error_msg
            )]

    async def _execute_swap(
        self,
        input_mint: str,
        output_mint: str,
        amount: int,
        slippage_bps: int = 100
    ) -> str:
        """
        Get a quote and execute a token swap

        Args:
            input_mint: Mint address of the token to swap from
            output_mint: Mint address of the token to swap to
            amount: Amount to swap (in raw units)
            slippage_bps: Slippage tolerance in basis points

        Returns:
            Transaction result or error message
        """
        try:
            # Ensure we have a wallet
            if not KEYPAIR:
                return "Error: Missing keypair. Please set the KEYPAIR in your settings."

            # Create keypair from string
            keypair_bytes = base58.b58decode(KEYPAIR)
            wallet = Keypair.from_bytes(keypair_bytes)

            # Preview the swap to get a quote
            preview_response = await self.jupiter_client.preview_swap(
                input_mint=input_mint,
                output_mint=output_mint,
                amount=amount,
                slippage_bps=slippage_bps
            )

            if not preview_response:
                return "Error: Failed to get quote for the swap."

            quote = preview_response['quote']
            formatted = preview_response['formatted']

            # Try to find ticker names from the dictionary for display
            input_ticker = self._get_ticker_for_mint(
                input_mint) or f"{input_mint[:8]}...{input_mint[-4:]}"
            output_ticker = self._get_ticker_for_mint(
                output_mint) or f"{output_mint[:8]}...{output_mint[-4:]}"

            # Display quote information
            quote_info = (
                f"🔄 Jupiter Swap Quote\n\n"
                f"Input: {formatted['in_amount'] / (10 ** 9):.9f} {input_ticker}\n"
                f"Output: {formatted['out_amount'] / (10 ** 9):.9f} {output_ticker}\n"
                f"Price Impact: {formatted['price_impact']:.2f}%\n"
                f"Slippage Tolerance: {slippage_bps / 100:.2f}%\n"
            )

            # Execute the swap
            tx_signature = await self.jupiter_client.execute_swap(
                wallet=wallet,
                quote=quote
            )

            if not tx_signature:
                return f"{quote_info}\nError: Failed to execute the swap."

            # Return success message with transaction information
            return (
                f"{quote_info}\n"
                f"✅ Swap executed successfully!\n"
                f"Transaction: https://solscan.io/tx/{tx_signature}"
            )

        except Exception as e:
            error_details = traceback.format_exc()
            print(f"Error during swap execution: {error_details}")
            return f"Error executing swap: {traceback.format_exc()}"

    def _get_ticker_for_mint(self, mint_address: str) -> Optional[str]:
        """
        Get ticker symbol for a mint address

        Args:
            mint_address: Token mint address

        Returns:
            Ticker symbol or None if not found
        """
        for ticker, address in TOKEN_DICTIONARY.items():
            if address.lower() == mint_address.lower():
                return ticker
        return None

    def get_tool_definition(self) -> Tool:
        """Get the tool definition for MCP"""
        return Tool(
            name=self.name,
            description=self.description,
            inputSchema=self.input_schema
        )


class TokenLookupTool:
    """Tool for looking up token mint addresses by ticker symbol"""

    def __init__(self):
        self.name = "token-lookup"
        self.description = "Lookup token mint addresses by ticker symbol"
        self.input_schema = {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Token ticker symbol (e.g., SOL, BONK, USDC)"
                }
            },
            "required": ["ticker"]
        }

    async def execute(self, arguments: Dict) -> List[TextContent | ImageContent | EmbeddedResource]:
        """
        Execute the token lookup tool

        Args:
            arguments: Dictionary with lookup parameters

        Returns:
            List of content items with the result
        """
        try:
            # Extract parameters
            ticker = arguments.get("ticker")

            # Validate parameters
            if not ticker:
                return [TextContent(
                    type="text",
                    text="Error: Missing ticker parameter."
                )]

            # Look up the token
            upper_ticker = ticker.upper()
            if upper_ticker in TOKEN_DICTIONARY:
                mint_address = TOKEN_DICTIONARY[upper_ticker]
                return [TextContent(
                    type="text",
                    text=f"✅ Found token: {upper_ticker}\nMint Address: {mint_address}"
                )]
            else:
                # If exact match not found, try to find partial matches
                partial_matches = [
                    (t, addr) for t, addr in TOKEN_DICTIONARY.items()
                    if upper_ticker in t
                ]

                if partial_matches:
                    matches_text = "\n".join([
                        f"- {t}: {a}" for t, a in partial_matches
                    ])
                    return [TextContent(
                        type="text",
                        text=f"⚠️ Token '{ticker}' not found. Here are some possible matches:\n\n{matches_text}"
                    )]

                # If no matches at all, show available tokens
                available_tokens = ", ".join(sorted(TOKEN_DICTIONARY.keys()))
                return [TextContent(
                    type="text",
                    text=f"❌ Token '{ticker}' not found. Available tokens: {available_tokens}"
                )]

        except Exception as e:
            error_msg = f"Error looking up token: {traceback.format_exc()}"
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
jupiter_swap_tool = JupiterSwapTool()
token_lookup_tool = TokenLookupTool()
