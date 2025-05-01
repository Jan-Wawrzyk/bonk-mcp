import asyncio
import traceback
from typing import Dict, List, Optional, Union
import json
import base58
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.system_program import TransferParams, transfer
from solders.transaction import VersionedTransaction
from solders.message import MessageV0
from solana.transaction import Transaction
from solders.hash import Hash
from mcp.types import TextContent, Tool, ImageContent, EmbeddedResource
from bonk_mcp.settings import KEYPAIR, TOKEN_DECIMAL, SOL_DECIMAL
from spl.token.client import Token
from spl.token.constants import TOKEN_PROGRAM_ID
import solana.rpc.types as RPCTypes
from solana.rpc.commitment import Commitment
from spl.token.instructions import get_associated_token_address, create_associated_token_account
import asyncio


class SolTransferTool:
    """Tool for transferring SOL to another wallet"""

    def __init__(self):
        self.name = "sol-transfer"
        self.description = "Transfer SOL to another wallet"
        self.input_schema = {
            "type": "object",
            "properties": {
                "recipient": {
                    "type": "string",
                    "description": "Recipient's wallet address"
                },
                "amount": {
                    "type": "number",
                    "description": "Amount of SOL to transfer"
                }
            },
            "required": ["recipient", "amount"]
        }

    async def execute(self, arguments: Dict) -> List[TextContent | ImageContent | EmbeddedResource]:
        """
        Execute the SOL transfer tool

        Args:
            arguments: Dictionary with transfer parameters

        Returns:
            List of content items with the result
        """
        try:
            # Extract parameters
            recipient = arguments.get("recipient")
            amount = arguments.get("amount")

            # Validate parameters
            if not recipient or amount is None:
                return [TextContent(
                    type="text",
                    text="Error: Missing required parameters. Please provide recipient and amount."
                )]

            if amount <= 0:
                return [TextContent(
                    type="text",
                    text="Error: Amount must be greater than 0."
                )]

            # Convert SOL to lamports using decimal from settings
            lamports = int(amount * (10 ** SOL_DECIMAL))

            # Transfer SOL
            result = await self._transfer_sol(recipient, lamports)

            return [TextContent(
                type="text",
                text=result
            )]

        except Exception as e:
            error_msg = f"Error transferring SOL: {traceback.format_exc()}"
            print(error_msg)
            return [TextContent(
                type="text",
                text=error_msg
            )]

    async def _transfer_sol(self, recipient_address: str, lamports: int) -> str:
        """
        Transfer SOL to recipient

        Args:
            recipient_address: Recipient's wallet address
            lamports: Amount in lamports to transfer

        Returns:
            Transaction result or error message
        """
        try:
            # Ensure we have a wallet
            if not KEYPAIR:
                return "Error: Missing keypair. Please set the KEYPAIR in your settings."

            # Parse keypair and recipient
            keypair_bytes = base58.b58decode(KEYPAIR)
            wallet = Keypair.from_bytes(keypair_bytes)

            try:
                recipient = Pubkey.from_string(recipient_address)
            except ValueError:
                return f"Error: Invalid recipient address: {recipient_address}"

            # Create transfer instruction
            transfer_ix = transfer(
                TransferParams(
                    from_pubkey=wallet.pubkey(),
                    to_pubkey=recipient,
                    lamports=lamports
                )
            )

            # Get recent blockhash
            from bonk_mcp.core.jupiter import client  # Import client from jupiter
            blockhash_resp = await client.get_latest_blockhash()
            if not blockhash_resp or not blockhash_resp.value:
                return "Error: Failed to get recent blockhash"

            recent_blockhash = blockhash_resp.value.blockhash

            # Create transaction
            message = MessageV0.try_compile(
                payer=wallet.pubkey(),
                instructions=[transfer_ix],
                address_lookup_table_accounts=[],
                recent_blockhash=recent_blockhash
            )

            transaction = VersionedTransaction(
                message,
                [wallet]
            )

            # Send transaction
            from bonk_mcp.core.jupiter import client  # Import client from jupiter
            tx_resp = await client.send_transaction(
                transaction,
                opts=RPCTypes.TxOpts(
                    skip_preflight=False,
                    max_retries=3,
                    preflight_commitment=Commitment("confirmed")
                )
            )

            if not tx_resp or not tx_resp.value:
                return "Error: Failed to send transaction"

            tx_id = str(tx_resp.value)

            # Format SOL amount
            sol_amount = lamports / (10 ** SOL_DECIMAL)

            # Return success message
            return (
                f"✅ SOL Transfer Successful\n\n"
                f"Amount: {sol_amount} SOL\n"
                f"Recipient: {recipient_address}\n"
                f"Transaction: https://solscan.io/tx/{tx_id}"
            )

        except Exception as e:
            error_details = traceback.format_exc()
            print(f"Error during SOL transfer: {error_details}")
            return f"Error transferring SOL: {str(e)}"

    def get_tool_definition(self) -> Tool:
        """Get the tool definition for MCP"""
        return Tool(
            name=self.name,
            description=self.description,
            inputSchema=self.input_schema
        )


class TokenTransferTool:
    """Tool for transferring SPL tokens to another wallet"""

    def __init__(self):
        self.name = "token-transfer"
        self.description = "Transfer SPL tokens to another wallet (automatically creates token account if needed)"
        self.input_schema = {
            "type": "object",
            "properties": {
                "token_mint": {
                    "type": "string",
                    "description": "Token mint address"
                },
                "recipient": {
                    "type": "string",
                    "description": "Recipient's wallet address"
                },
                "amount": {
                    "type": "number",
                    "description": "Amount of tokens to transfer"
                }
            },
            "required": ["token_mint", "recipient", "amount"]
        }
        # Token decimal mapping for common tokens
        self.token_decimals = {
            # Map common tokens to their decimals (used as fallback)
            "So11111111111111111111111111111111111111112": SOL_DECIMAL,
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": 6,  # USDC
            "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB": 6   # USDT
        }

    async def execute(self, arguments: Dict) -> List[TextContent | ImageContent | EmbeddedResource]:
        """
        Execute the token transfer tool

        Args:
            arguments: Dictionary with transfer parameters

        Returns:
            List of content items with the result
        """
        try:
            # Extract parameters
            token_mint = arguments.get("token_mint")
            recipient = arguments.get("recipient")
            amount = arguments.get("amount")

            # Validate parameters
            if not token_mint or not recipient or amount is None:
                return [TextContent(
                    type="text",
                    text="Error: Missing required parameters. Please provide token_mint, recipient, and amount."
                )]

            if amount <= 0:
                return [TextContent(
                    type="text",
                    text="Error: Amount must be greater than 0."
                )]

            # Get token decimals - use value from settings or token-specific value if known
            # Otherwise default to TOKEN_DECIMAL from settings
            decimals = self.token_decimals.get(token_mint, TOKEN_DECIMAL)

            # Convert to raw amount based on decimals
            raw_amount = int(amount * (10 ** decimals))

            # Transfer tokens
            result = await self._transfer_token(token_mint, recipient, raw_amount, decimals)

            return [TextContent(
                type="text",
                text=result
            )]

        except Exception as e:
            error_msg = f"Error transferring tokens: {traceback.format_exc()}"
            print(error_msg)
            return [TextContent(
                type="text",
                text=error_msg
            )]

    async def _transfer_token(self, token_mint: str, recipient_address: str, amount: int, decimals: int) -> str:
        """
        Transfer SPL tokens to recipient

        Args:
            token_mint: Token mint address
            recipient_address: Recipient's wallet address
            amount: Raw token amount to transfer
            decimals: Token decimals

        Returns:
            Transaction result or error message
        """
        try:
            # Ensure we have a wallet
            if not KEYPAIR:
                return "Error: Missing keypair. Please set the KEYPAIR in your settings."

            # Parse keypair and addresses
            keypair_bytes = base58.b58decode(KEYPAIR)
            wallet = Keypair.from_bytes(keypair_bytes)

            try:
                mint_pubkey = Pubkey.from_string(token_mint)
                recipient_pubkey = Pubkey.from_string(recipient_address)
            except ValueError as ve:
                return f"Error: Invalid address format: {str(ve)}"

            # Get recent blockhash
            from bonk_mcp.core.jupiter import client  # Import client from jupiter
            blockhash_resp = await client.get_latest_blockhash()
            if not blockhash_resp or not blockhash_resp.value:
                return "Error: Failed to get recent blockhash"

            recent_blockhash = blockhash_resp.value.blockhash

            # Calculate token accounts
            source_token_account = get_associated_token_address(
                wallet.pubkey(),
                mint_pubkey
            )

            destination_token_account = get_associated_token_address(
                recipient_pubkey,
                mint_pubkey
            )

            # Check if destination token account exists
            account_info = await client.get_account_info(destination_token_account)

            # Import token program instructions directly to avoid the potential issues with the Token class
            from spl.token.instructions import (
                transfer_checked as token_transfer_checked,
                TransferCheckedParams
            )

            # Start collecting instructions for the transaction
            instructions = []

            # Create destination token account if it doesn't exist
            account_created = False
            if not account_info.value or not account_info.value.data:
                # Add instruction to create the associated token account
                from spl.token.instructions import create_associated_token_account_instruction
                create_account_ix = create_associated_token_account_instruction(
                    payer=wallet.pubkey(),
                    owner=recipient_pubkey,
                    mint=mint_pubkey,
                    associated_token_account=destination_token_account
                )
                instructions.append(create_account_ix)
                account_created = True

            # Add token transfer instruction
            transfer_ix = token_transfer_checked(
                TransferCheckedParams(
                    program_id=TOKEN_PROGRAM_ID,
                    source=source_token_account,
                    mint=mint_pubkey,
                    dest=destination_token_account,
                    owner=wallet.pubkey(),
                    amount=amount,
                    decimals=decimals,
                    signers=[]
                )
            )
            instructions.append(transfer_ix)

            # Create and send versioned transaction
            message = MessageV0.try_compile(
                payer=wallet.pubkey(),
                instructions=instructions,
                address_lookup_table_accounts=[],
                recent_blockhash=recent_blockhash
            )

            transaction = VersionedTransaction(
                message,
                [wallet]
            )

            # Send transaction using the client
            tx_resp = await client.send_transaction(
                transaction,
                opts=RPCTypes.TxOpts(
                    skip_preflight=False,
                    max_retries=3,
                    preflight_commitment=Commitment("confirmed")
                )
            )

            if not tx_resp or not tx_resp.value:
                return "Error: Failed to send transaction"

            tx_id = str(tx_resp.value)

            # Format token amount
            token_amount = amount / (10 ** decimals)

            # Get token name/symbol if possible
            token_name = None
            try:
                from bonk_mcp.tools.jupiter import TOKEN_DICTIONARY
                for ticker, addr in TOKEN_DICTIONARY.items():
                    if addr.lower() == token_mint.lower():
                        token_name = ticker
                        break
            except ImportError:
                pass

            token_display = token_name if token_name else f"tokens ({token_mint[:8]}...{token_mint[-4:]})"

            # Return success message with account creation info
            account_created_msg = "✅ Created destination token account\n" if account_created else ""

            return (
                f"✅ Token Transfer Successful\n\n"
                f"{account_created_msg}"
                f"Amount: {token_amount} {token_display}\n"
                f"Recipient: {recipient_address}\n"
                f"Transaction: https://solscan.io/tx/{tx_id}"
            )

        except Exception as e:
            error_details = traceback.format_exc()
            print(f"Error during token transfer: {error_details}")
            return f"Error transferring tokens: {str(e)}"

    def get_tool_definition(self) -> Tool:
        """Get the tool definition for MCP"""
        return Tool(
            name=self.name,
            description=self.description,
            inputSchema=self.input_schema
        )


# Create instances for export
sol_transfer_tool = SolTransferTool()
token_transfer_tool = TokenTransferTool()
