import struct
import traceback
import aiohttp
import json
from typing import Optional, Tuple, Dict

from solana.transaction import Transaction
from solana.rpc.types import TokenAccountOpts, TxOpts
from spl.token.instructions import (
    create_associated_token_account,
    get_associated_token_address
)
from solders.pubkey import Pubkey
from solders.instruction import Instruction
from solders.keypair import Keypair
from solders.compute_budget import set_compute_unit_limit, set_compute_unit_price

from bonk_mcp.settings import (
    client,
    UNIT_PRICE,
    UNIT_BUDGET,
    TOKEN_PROGRAM,
    SOL_DECIMAL,
    WSOL_TOKEN
)

from solders.system_program import CreateAccountParams, create_account
from solana.rpc.api import RPCException
from spl.token.instructions import initialize_account, close_account, CloseAccountParams, InitializeAccountParams


def buffer_from_string(string_data: str) -> bytes:
    """Convert string to buffer with length prefix"""
    str_bytes = string_data.encode('utf-8')
    length = len(str_bytes)
    return struct.pack('<I', length) + str_bytes


async def setup_transaction(payer_pubkey: Pubkey) -> Transaction:
    """Create and setup a new transaction with compute budget"""
    txn = Transaction(
        recent_blockhash=(await client.get_latest_blockhash()).value.blockhash,
        fee_payer=payer_pubkey
    )

    txn.add(set_compute_unit_price(UNIT_PRICE))
    txn.add(set_compute_unit_limit(UNIT_BUDGET))

    return txn


async def create_or_get_token_account(owner: Pubkey, mint: Pubkey) -> Tuple[Pubkey, Optional[Instruction]]:
    """Create or retrieve token account"""
    try:
        account_data = await client.get_token_accounts_by_owner(owner, TokenAccountOpts(mint))
        return account_data.value[0].pubkey, None
    except:
        token_account = get_associated_token_address(owner, mint)
        token_account_ix = create_associated_token_account(owner, owner, mint)
        return token_account, token_account_ix


async def send_and_confirm_transaction(txn: Transaction, *signers, skip_preflight: bool = True, confirm: bool = False) -> bool:
    """Send and confirm a transaction"""
    try:
        txn_sig = await client.send_transaction(
            txn,
            *signers,
            opts=TxOpts(skip_preflight=skip_preflight, max_retries=3)
        )
        print("Transaction Signature:", txn_sig.value)

        # Wait for confirmation
        if confirm:
            status = await client.confirm_transaction(txn_sig.value)
            return status
        else:
            return True
    except Exception as e:
        print(f"Transaction error: {traceback.format_exc()}")
        return False


async def download_image(image_url: str) -> Optional[bytes]:
    """
    Download image from a URL

    Args:
        image_url: URL of the image to download

    Returns:
        Image data as bytes if successful, None if failed
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(image_url) as response:
                if response.status == 200:
                    return await response.read()
                else:
                    print(f"Failed to download image: {response.status}")
                    return None
    except Exception as e:
        print(f"Error downloading image: {str(e)}")
        return None


async def prepare_ipfs(
    name: str = "",
    symbol: str = "",
    description: str = "",
    twitter: str = "",
    telegram: str = "",
    website: str = "",
    image_url: str = None,
    image_data: bytes = None,
    file: Optional[str] = None
) -> Optional[str]:
    """
    Prepare IPFS metadata for a token using gated.chat APIs

    Args:
        name: Token name
        symbol: Token symbol/ticker
        description: Token description
        twitter: Twitter handle/URL (optional)
        telegram: Telegram group URL (optional)
        website: Website URL (optional)
        image_url: Direct URL to image (if already available)
        image_data: Raw image data bytes (if already downloaded)
        file: Path to local image file (if available)

    Returns:
        IPFS URI if successful, None if failed
    """
    try:
        # Step 1: Get or upload image
        # If we already have a valid Pinata URL, use it directly
        if image_url and image_url.startswith("https://sapphire-working-koi-276.mypinata.cloud/ipfs/"):
            print(f"Using provided Pinata image URL: {image_url}")
        else:
            # Otherwise, we need to upload an image
            # Priority: image_data > file > image_url
            data_to_upload = None

            if image_data:
                # Use provided image data directly
                data_to_upload = image_data
                print("Using provided image data for upload")
            elif file:
                # Read from local file
                try:
                    with open(file, "rb") as f:
                        data_to_upload = f.read()
                    print(f"Read image data from file: {file}")
                except Exception as e:
                    print(f"Error reading file: {str(e)}")
            elif image_url:
                # Download from URL
                data_to_upload = await download_image(image_url)
                if not data_to_upload:
                    print(f"Failed to download image from URL: {image_url}")

            # If we have data to upload, do it
            if data_to_upload:
                # Upload using direct method with fixed boundary
                try:
                    # Fixed boundary string
                    boundary = "----WebKitFormBoundarymkE1BAuPXiGrhrdB"

                    # Create the multipart form data manually
                    body = b""
                    body += f"--{boundary}\r\n".encode('utf-8')
                    body += b'Content-Disposition: form-data; name="image"; filename="image.jpg"\r\n'
                    body += b'Content-Type: image/jpeg\r\n\r\n'
                    body += data_to_upload
                    body += f"\r\n--{boundary}--\r\n".encode('utf-8')

                    headers = {
                        "accept": "application/json, text/plain, */*",
                        "accept-language": "en-US,en;q=0.9",
                        "content-type": f"multipart/form-data; boundary={boundary}",
                        "sec-fetch-dest": "empty",
                        "sec-fetch-mode": "cors",
                        "sec-fetch-site": "cross-site",
                        "referrer": "https://letsbonk.fun/",
                    }

                    async with aiohttp.ClientSession() as session:
                        async with session.post(
                            "https://gated.chat/upload/img",
                            data=body,
                            headers=headers
                        ) as response:
                            print(f"Image upload status: {response.status}")
                            response_text = await response.text()

                            if response.status == 200:
                                # The API returns the URL directly as plain text
                                if response_text.startswith("https://"):
                                    image_url = response_text.strip()
                                    print(
                                        f"Successfully uploaded image: {image_url}")
                                else:
                                    # Try to parse as JSON just in case
                                    try:
                                        result = json.loads(response_text)
                                        image_url = result.get("url")
                                        if image_url:
                                            print(
                                                f"Successfully uploaded image: {image_url}")
                                    except json.JSONDecodeError:
                                        pass

                            if not image_url:
                                print(f"Image upload error: {response_text}")
                                return None
                except Exception as e:
                    print(f"Error uploading image: {str(e)}")
                    return None

            # If we still don't have an image URL, use a default
            if not image_url:
                image_url = "https://sapphire-working-koi-276.mypinata.cloud/ipfs/bafybeihpy352xnqgn74nrjj6bgxndrss5nbqix4kfhwfanoyo766tgwzz4"
                print(f"Using default image URL: {image_url}")

        # Step 2: Create and upload metadata
        metadata = {
            "name": name,
            "symbol": symbol,
            "description": description,
            "createdOn": "https://bonk.fun",
            "image": image_url
        }

        # Add optional social links if provided
        if twitter:
            metadata["twitter"] = twitter
        if telegram:
            metadata["telegram"] = telegram
        if website:
            metadata["website"] = website

        # Upload metadata
        print(f"Uploading metadata for {name} ({symbol})...")

        headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "en-US,en;q=0.9",
            "content-type": "application/json",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "cross-site",
            "referrer": "https://letsbonk.fun/",
            "origin": "https://letsbonk.fun"
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://gated.chat/upload/meta",
                json=metadata,
                headers=headers
            ) as response:
                print(f"Metadata upload status: {response.status}")
                response_text = await response.text()

                if response.status == 200:
                    # The API might return the URL directly as plain text
                    if response_text.startswith("https://"):
                        metadata_uri = response_text.strip()
                        print(f"Metadata uploaded, direct URL: {metadata_uri}")
                        return metadata_uri

                    # Try to parse as JSON just in case
                    try:
                        result = json.loads(response_text)
                        metadata_uri = result.get("url")
                        if metadata_uri:
                            print(f"Metadata uploaded: {metadata_uri}")
                            return metadata_uri
                    except json.JSONDecodeError:
                        # Already handled above
                        pass

                print(f"Metadata upload error: {response_text}")
                return None

    except Exception as e:
        print(f"Error preparing IPFS metadata: {traceback.format_exc()}")
        return None


def calculate_tokens_receive(sol_amount, previous_sol=30, slippage=5):
    """
    Calculate tokens received for given SOL amount
    """
    LAMPORTS_PER_SOL = 10**9
    TOKEN_DECIMALS = 10**6

    INITIAL_TOKENS = 1073000191 * TOKEN_DECIMALS  # Convert to token units
    K = 32190005730 * TOKEN_DECIMALS  # Convert to token units

    # Convert SOL to lamports
    previous_lamports = int(previous_sol * LAMPORTS_PER_SOL)
    new_lamports = previous_lamports + int(sol_amount * LAMPORTS_PER_SOL)

    # Calculate tokens
    current_tokens = INITIAL_TOKENS - \
        (K / (previous_lamports / LAMPORTS_PER_SOL))
    new_tokens = INITIAL_TOKENS - (K / (new_lamports / LAMPORTS_PER_SOL))

    # Calculate difference in tokens
    tokens_received = (new_tokens - current_tokens) / TOKEN_DECIMALS
    max_sol_cost = sol_amount * (1 + slippage/100)

    return {
        "token_amount": tokens_received,
        "max_sol_cost": max_sol_cost
    }


async def create_temporary_wsol_account(
    payer_pubkey: Pubkey,
    amount: float
) -> tuple[Pubkey, list[Instruction]]:
    """
    Create a temporary WSOL token account with the specified amount of SOL.

    Args:
        payer_pubkey: The pubkey of the payer who will fund the account
        amount: Amount of SOL to fund the account with (in SOL)

    Returns:
        A tuple containing the token account pubkey and a list of instructions to add to a transaction
    """

    # Create a temporary keypair for the WSOL account
    wsol_keypair = Keypair()
    wsol_token_account = wsol_keypair.pubkey()

    # Get minimum rent
    try:
        min_rent = await client.get_minimum_balance_for_rent_exemption(165)
        min_rent = min_rent.value
    except RPCException:
        # Fallback if API call fails
        min_rent = 2039280  # Standard rent for token account

    # Amount to fund (rent + SOL for swap)
    lamports = min_rent + int(amount * 10**SOL_DECIMAL)

    # Create instructions
    instructions = []

    # Create account for WSOL
    create_wsol_account_ix = create_account(
        CreateAccountParams(
            from_pubkey=payer_pubkey,
            to_pubkey=wsol_token_account,
            lamports=lamports,
            space=165,
            owner=TOKEN_PROGRAM
        )
    )
    instructions.append(create_wsol_account_ix)

    # Initialize token account
    init_wsol_account_ix = initialize_account(
        InitializeAccountParams(
            program_id=TOKEN_PROGRAM,
            account=wsol_token_account,
            mint=WSOL_TOKEN,
            owner=payer_pubkey
        )
    )
    instructions.append(init_wsol_account_ix)

    return wsol_token_account, instructions, wsol_keypair


async def get_close_wsol_instruction(
    wsol_token_account: Pubkey,
    owner: Pubkey
) -> Instruction:
    """
    Get instruction to close a WSOL account and recover SOL

    Args:
        wsol_token_account: The WSOL token account to close
        owner: The owner of the token account who will receive the SOL

    Returns:
        Close account instruction
    """
    from spl.token.instructions import close_account, CloseAccountParams
    from bonk_mcp.settings import TOKEN_PROGRAM

    close_wsol_account_ix = close_account(
        CloseAccountParams(
            account=wsol_token_account,
            dest=owner,
            owner=owner,
            program_id=TOKEN_PROGRAM
        )
    )

    return close_wsol_account_ix


async def create_address_lookup_table(
    payer_pubkey: Pubkey,
    addresses: list[Pubkey]
) -> tuple[Pubkey, list[Instruction]]:
    """
    Create an address lookup table for the given addresses

    Args:
        payer_pubkey: The payer for the table creation
        addresses: List of addresses to include in the table

    Returns:
        Tuple of (lookup table address, instructions to create and extend the table)
    """
    from solders.address_lookup_table_account import AddressLookupTableAccount
    from solders.address_lookup_table import (
        create_lookup_table,
        extend_lookup_table,
        CreateLookupTableParams,
        ExtendLookupTableParams
    )

    # Get recent slot for table creation
    slot = (await client.get_slot()).value

    # Create the lookup table instruction
    create_lookup_params = CreateLookupTableParams(
        authority=payer_pubkey,
        payer=payer_pubkey,
        recent_slot=slot,
    )
    create_ix, lookup_table_address = create_lookup_table(create_lookup_params)

    # Extend the lookup table with our addresses
    extend_lookup_params = ExtendLookupTableParams(
        addresses=addresses,
        authority=payer_pubkey,
        lookup_table=lookup_table_address,
        payer=payer_pubkey
    )
    extend_ix = extend_lookup_table(extend_lookup_params)

    return lookup_table_address, [create_ix, extend_ix]


async def send_transaction_with_alt(
    txn: Transaction,
    address_lookup_tables: list[Pubkey],
    *signers,
    skip_preflight: bool = True
) -> bool:
    """
    Send and confirm a transaction using address lookup tables

    Args:
        txn: The transaction to send
        address_lookup_tables: List of ALT addresses to look up
        signers: Transaction signers
        skip_preflight: Whether to skip preflight checks

    Returns:
        True if transaction was successful, False otherwise
    """
    from solders.versioned_transaction import VersionedTransaction
    from solders.message import to_versioned_message
    from solders.address_lookup_table_account import AddressLookupTableAccount

    try:
        # Get address lookup tables
        alt_accounts = []
        for alt_pubkey in address_lookup_tables:
            alt_account = await client.get_account_info(alt_pubkey)
            if alt_account.value is not None:
                # Convert to AddressLookupTableAccount
                alt_accounts.append(
                    AddressLookupTableAccount(
                        key=alt_pubkey,
                        addresses=alt_account.value.data.addresses
                    )
                )

        # Convert to versioned transaction
        versioned_message = to_versioned_message(
            txn._solders.message,
            address_lookup_table_accounts=alt_accounts
        )

        # Sign the transaction
        signatures = []
        for signer in signers:
            signatures.append(signer.sign_message(
                versioned_message.serialize()))

        versioned_txn = VersionedTransaction(
            message=versioned_message,
            signatures=signatures
        )

        # Send transaction
        txn_sig = await client.send_transaction(
            versioned_txn.serialize(),
            opts=TxOpts(skip_preflight=skip_preflight, max_retries=3)
        )
        print("Transaction Signature:", txn_sig.value)

        # Wait for confirmation
        status = await client.confirm_transaction(txn_sig.value)
        return status.value.err is None

    except Exception as e:
        print(f"Transaction error: {traceback.format_exc()}")
        return False
