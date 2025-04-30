import asyncio
from typing import Dict, List, Optional
import json
import base58

from mcp.types import TextContent, Tool, ImageContent, EmbeddedResource
from solders.keypair import Keypair
from solders.pubkey import Pubkey

from bonk_mcp.core.letsbonk import create_buy_tx, derive_pdas
from bonk_mcp.utils import send_and_confirm_transaction, calculate_tokens_receive, get_token_account_balance
from bonk_mcp.settings import KEYPAIR


class TokenBuyerTool:
    """Tool for buying tokens on Solana using the Raydium launchpad"""

    def __init__(self):
        self.name = "buy-token"
        self.description = "Buy tokens on Solana using the Raydium launchpad"
        self.input_schema = {
            "type": "object",
            "properties": {
                "token_address": {"type": "string", "description": "Token mint address to buy"},
                "amount_sol": {"type": "number", "description": "Amount of SOL to spend"},
                "slippage": {"type": "number", "description": "Maximum slippage percentage (default: 5%)"}
            },
            "required": ["token_address", "amount_sol"]
        }

    async def execute(self, arguments: Dict) -> List[TextContent | ImageContent | EmbeddedResource]:
        """
        Execute the token buying tool with the provided arguments

        Args:
            arguments: Dictionary containing buy configuration

        Returns:
            List of content items with the result
        """
        # Extract arguments
        token_address = arguments.get("token_address")
        amount_sol = arguments.get("amount_sol")
        slippage = arguments.get("slippage", 5)  # Default to 5% slippage

        # Validate required arguments
        if not token_address or not amount_sol:
            return [TextContent(
                type="text",
                text="Error: Missing required parameters. Please provide token_address and amount_sol."
            )]

        # Get the payer keypair from settings
        if not KEYPAIR:
            return [TextContent(
                type="text",
                text="Error: No keypair configured in settings. Please set the KEYPAIR environment variable."
            )]

        try:
            # Convert the private key to a Keypair
            private_key_bytes = base58.b58decode(KEYPAIR)
            payer_keypair = Keypair.from_bytes(private_key_bytes)
        except Exception as e:
            return [TextContent(
                type="text",
                text=f"Error: Invalid keypair format. {str(e)}"
            )]

        try:
            # Convert token address string to Pubkey
            mint_pubkey = Pubkey.from_string(token_address)

            # Get quote vault balance
            pdas = await derive_pdas(mint_pubkey)
            quote_vote_address = pdas["quote_vault"]
            quote_vault_balance = await get_token_account_balance(
                quote_vote_address)

            # Calculate minimum tokens to receive based on slippage
            token_info = calculate_tokens_receive(
                amount_sol, previous_sol=float(quote_vault_balance)+30, slippage=slippage)
            minimum_amount_out = token_info["token_amount"]

            # Create buy transaction
            print(
                f"Creating buy transaction for {amount_sol} SOL worth of tokens...")
            print(
                f"Minimum tokens to receive: {minimum_amount_out} (with {slippage}% slippage)")

            buy_txn, additional_signers = await create_buy_tx(
                payer_keypair=payer_keypair,
                mint_pubkey=mint_pubkey,
                amount_in=amount_sol,
                minimum_amount_out=minimum_amount_out
            )

            # Send the transaction
            print("Sending buy transaction...")
            tx_hash = await send_and_confirm_transaction(
                buy_txn,
                payer_keypair,
                *additional_signers,
                skip_preflight=True,
                confirm=False
            )

            if not tx_hash:
                return [TextContent(
                    type="text",
                    text="Error: Failed to send transaction."
                )]

            # Format successful response
            response_text = (
                f"🚀 Successfully purchased tokens!\n\n"
                f"Token Mint: {mint_pubkey}\n"
                f"SOL Spent: {amount_sol}\n"
                f"Estimated Tokens Received: {token_info['token_amount']}\n"
                f"Slippage: {slippage}%\n"
                f"Transaction hash: {tx_hash}\n"
            )

            return [TextContent(
                type="text",
                text=response_text
            )]

        except Exception as e:
            error_msg = f"Error processing buy transaction: {str(e)}"
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


# Create instance for export
token_buyer_tool = TokenBuyerTool()
