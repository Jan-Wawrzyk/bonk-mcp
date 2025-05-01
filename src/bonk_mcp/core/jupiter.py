import traceback
from typing import Optional, Dict, Any, List, Tuple
import aiohttp
import base64
from dataclasses import dataclass
from enum import Enum
from solders.pubkey import Pubkey
from solders.transaction import VersionedTransaction
from solders.keypair import Keypair
from bonk_mcp.settings import client, UNIT_PRICE, UNIT_BUDGET
from solders.message import MessageV0
from solana.rpc.types import TxOpts
from solders.instruction import Instruction, AccountMeta
from solders.address_lookup_table_account import AddressLookupTableAccount
from solders.compute_budget import set_compute_unit_limit, set_compute_unit_price
from solana.transaction import Transaction


class SwapMode(Enum):
    """Jupiter swap modes"""
    EXACT_IN = "ExactIn"
    EXACT_OUT = "ExactOut"


@dataclass
class QuoteRequest:
    """Jupiter quote request parameters"""
    input_mint: str
    output_mint: str
    amount: int
    slippage_bps: int = 50  # Default 0.5%
    swap_mode: SwapMode = SwapMode.EXACT_IN
    fee_account: Optional[str] = None
    max_accounts: Optional[int] = None


@dataclass
class SwapRequest:
    """Jupiter swap request parameters"""
    quote_response: Dict[str, Any]
    user_public_key: str
    wrap_unwrap_sol: bool = True
    fee_account: Optional[str] = None


class JupiterSwapClient:
    """Jupiter API client"""

    def __init__(self, api_version: str = "v6"):
        self.base_url = f"https://quote-api.jup.ag/{api_version}"
        self.headers = {
            "accept": "application/json",
            "content-type": "application/json"
        }

    async def get_quote(self, request: QuoteRequest) -> Dict[str, Any]:
        """Get a quote for swapping tokens"""
        try:
            # Build query parameters
            params = {
                "inputMint": request.input_mint,
                "outputMint": request.output_mint,
                "amount": str(request.amount),
                "slippageBps": request.slippage_bps,
                "swapMode": request.swap_mode.value
            }

            # Add optional parameters
            if request.fee_account:
                params["feeAccount"] = request.fee_account
            if request.max_accounts:
                params["maxAccounts"] = request.max_accounts

            # Make request
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/quote",
                    params=params,
                    headers=self.headers
                ) as response:
                    if response.status != 200:
                        error_data = await response.text()
                        raise Exception(f"Jupiter API error: {error_data}")

                    return await response.json()

        except Exception as e:
            print(f"Error getting Jupiter quote: {str(e)}")
            return None

    async def get_swap_instructions(self, request: SwapRequest) -> Optional[List[Instruction]]:
        """Get swap instructions from Jupiter"""
        try:
            # Prepare request body
            body = {
                "quoteResponse": request.quote_response,
                "userPublicKey": request.user_public_key,
                "wrapAndUnwrapSol": request.wrap_unwrap_sol,
                "useComputeBudgetProgram": False  # Tell Jupiter not to add compute budget
            }
            if request.fee_account:
                body["feeAccount"] = request.fee_account

            # Get swap instructions
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/swap-instructions",
                    json=body,
                    headers=self.headers
                ) as response:
                    if response.status != 200:
                        error_data = await response.text()
                        raise Exception(f"Jupiter API error: {error_data}")

                    data = await response.json()
                    if data.get('error'):
                        raise Exception(
                            f"Failed to get swap instructions: {data['error']}")

                    # Convert instructions
                    instructions = []

                    # Add our own compute budget instructions
                    instructions.append(set_compute_unit_price(UNIT_PRICE))
                    instructions.append(set_compute_unit_limit(UNIT_BUDGET))

                    # Add setup instructions if needed
                    if data.get('setupInstructions'):
                        instructions.extend([
                            convert_to_instruction(ix)
                            for ix in data['setupInstructions']
                        ])

                    # Add main swap instruction
                    if data.get('swapInstruction'):
                        instructions.append(
                            convert_to_instruction(data['swapInstruction'])
                        )

                    # Add cleanup instruction if needed
                    if data.get('cleanupInstruction'):
                        instructions.append(
                            convert_to_instruction(data['cleanupInstruction'])
                        )

                    return instructions

        except Exception as e:
            print(f"Error getting swap instructions: {traceback.format_exc()}")
            return None

    async def get_address_lookup_tables(
        self,
        addresses: List[str]
    ) -> List[AddressLookupTableAccount]:
        """Get address lookup table accounts"""
        lookup_tables = []

        # Skip if no addresses
        if not addresses:
            return lookup_tables

        try:
            # Get account infos
            pubkeys = [Pubkey.from_string(addr) for addr in addresses]
            account_infos = await client.get_multiple_accounts(pubkeys)

            # Create lookup table accounts
            for i, info in enumerate(account_infos.value):
                if info and info.data:
                    try:
                        lookup_tables.append(
                            AddressLookupTableAccount(
                                key=pubkeys[i],
                                state=info.data
                            )
                        )
                        print(f"Added lookup table: {pubkeys[i]}")
                    except Exception as e:
                        print(
                            f"Failed to create lookup table for {pubkeys[i]}: {str(e)}")
                        continue

            print(f"Found {len(lookup_tables)} lookup tables")
            return lookup_tables

        except Exception as e:
            print(f"Error getting lookup tables: {str(e)}")
            return []

    async def preview_swap(
        self,
        input_mint: str,
        output_mint: str,
        amount: int,
        slippage_bps: int = 1000,
        swap_mode: SwapMode = SwapMode.EXACT_IN
    ) -> Optional[Dict[str, Any]]:
        """
        Preview a swap with detailed quote information

        Returns:
            Dictionary containing quote details and formatted amounts
        """
        try:
            quote_request = QuoteRequest(
                input_mint=input_mint,
                output_mint=output_mint,
                amount=amount,
                slippage_bps=slippage_bps,
                swap_mode=swap_mode
            )
            quote = await self.get_quote(quote_request)
            if not quote:
                raise Exception("Failed to get quote")

            # Format amounts for better readability
            in_amount = int(quote['inAmount'])
            out_amount = int(quote['outAmount'])
            price_impact = float(quote['priceImpactPct'])

            return {
                "quote": quote,
                "formatted": {
                    "in_amount": in_amount,
                    "out_amount": out_amount,
                    "price_impact": price_impact,
                    "route_plan": quote['routePlan'],
                    "fee_amount": int(quote['routePlan'][0]['swapInfo']['feeAmount']),
                    "slippage_bps": quote['slippageBps']
                }
            }

        except Exception as e:
            print(f"Error previewing swap: {str(e)}")
            return None

    async def execute_swap(
        self,
        wallet: Keypair,
        quote: Dict[str, Any]
    ) -> Optional[str]:
        """
        Execute a token swap using a quote

        Args:
            wallet: Keypair for signing and paying for the transaction
            quote: Quote response from get_quote or preview_swap

        Returns:
            Transaction signature if successful, None if failed
        """
        try:
            # Get swap instructions
            swap_request = SwapRequest(
                quote_response=quote,
                user_public_key=str(wallet.pubkey())
            )
            instructions = await self.get_swap_instructions(swap_request)
            if not instructions:
                raise Exception("Failed to get swap instructions")

            # Get address lookup tables if needed
            lookup_tables = []
            if quote.get('addressLookupTableAddresses'):
                lookup_tables = await self.get_address_lookup_tables(
                    quote['addressLookupTableAddresses']
                )
            # Create versioned transaction
            message = MessageV0.try_compile(
                payer=wallet.pubkey(),
                instructions=instructions,
                address_lookup_table_accounts=lookup_tables,
                recent_blockhash=(await client.get_latest_blockhash()).value.blockhash
            )

            transaction = VersionedTransaction(
                message,
                [wallet]
            )

            # Send transaction with retries
            txid = await client.send_transaction(
                transaction,
                opts=TxOpts(
                    skip_preflight=True,
                    max_retries=3,
                    preflight_commitment="confirmed"
                )
            )

            return str(txid.value)

        except Exception as e:
            print(f"Error executing swap: {traceback.format_exc()}")
            return None

    async def create_swap_transaction(
        self,
        wallet: Keypair,
        quote: Dict[str, Any]
    ) -> Optional[Transaction]:
        """Create swap transaction without sending"""
        try:
            # Get swap instructions
            swap_request = SwapRequest(
                quote_response=quote,
                user_public_key=str(wallet.pubkey())
            )
            instructions = await self.get_swap_instructions(swap_request)
            if not instructions:
                raise Exception("Failed to get swap instructions")

            # Create regular transaction instead of versioned
            recent_blockhash = (await client.get_latest_blockhash()).value.blockhash
            transaction = Transaction(recent_blockhash=recent_blockhash)

            # Add instructions
            for ix in instructions:
                transaction.add(ix)

            # Set fee payer
            transaction.fee_payer = wallet.pubkey()

            return transaction

        except Exception as e:
            print(f"Error creating swap transaction: {traceback.format_exc()}")
            return None


def convert_to_instruction(ix_data: dict) -> Instruction:
    """Convert Jupiter instruction format to Solders Instruction"""
    accounts = [
        AccountMeta(
            pubkey=Pubkey.from_string(acc['pubkey']),
            is_signer=acc['isSigner'],
            is_writable=acc['isWritable']
        ) for acc in ix_data['accounts']
    ]

    program_id = Pubkey.from_string(ix_data['programId'])
    data = base64.b64decode(ix_data['data'])

    return Instruction(program_id, data, accounts)
