import struct
import traceback
import aiohttp
import json
from typing import Optional, Tuple

from solders.pubkey import Pubkey
from solders.instruction import Instruction, AccountMeta
from solders.keypair import Keypair
from solders.compute_budget import set_compute_unit_limit, set_compute_unit_price
from solders.transaction import Transaction
from solders.system_program import CreateAccountParams, create_account

from solana.rpc.types import TxOpts  # for the solana-py client wrapper used below
from solana.rpc.api import RPCException

from bonk_mcp.settings import (
    client,
    UNIT_PRICE,
    UNIT_BUDGET,
    TOKEN_PROGRAM,
    SOL_DECIMAL,
    WSOL_TOKEN,
    ASSOC_TOKEN_ACC_PROG,
    SYSTEM_PROGRAM,
    RENT,
)

# SPL token instruction discriminators
SPL_TOKEN_INITIALIZE_ACCOUNT = bytes([1])  # InitializeAccount
SPL_TOKEN_CLOSE_ACCOUNT = bytes([9])  # CloseAccount


def buffer_from_string(string_data: str) -> bytes:
    """Convert string to buffer with length prefix"""
    str_bytes = string_data.encode("utf-8")
    length = len(str_bytes)
    return struct.pack("<I", length) + str_bytes


async def setup_transaction(payer_pubkey: Pubkey) -> Transaction:
    """Create and setup a new transaction with compute budget"""
    txn = Transaction(
        recent_blockhash=(await client.get_latest_blockhash()).value.blockhash,
        fee_payer=payer_pubkey,
    )
    txn.add(set_compute_unit_price(UNIT_PRICE))
    txn.add(set_compute_unit_limit(UNIT_BUDGET))
    return txn


# ------------------ ATA derivation + creation ------------------ #


def get_associated_token_address(owner: Pubkey, mint: Pubkey) -> Pubkey:
    token_program_pubkey = Pubkey.from_string(str(TOKEN_PROGRAM))
    assoc_prog = Pubkey.from_string(str(ASSOC_TOKEN_ACC_PROG))
    seeds = [bytes(owner), bytes(token_program_pubkey), bytes(mint)]
    ata, _ = Pubkey.find_program_address(seeds, assoc_prog)
    return ata


def create_associated_token_account_instruction(
    payer: Pubkey, owner: Pubkey, mint: Pubkey
) -> Tuple[Pubkey, Instruction]:
    ata = get_associated_token_address(owner, mint)
    assoc_prog = Pubkey.from_string(str(ASSOC_TOKEN_ACC_PROG))
    token_prog = Pubkey.from_string(str(TOKEN_PROGRAM))
    system_prog = Pubkey.from_string(str(SYSTEM_PROGRAM))
    rent_sysvar = Pubkey.from_string(str(RENT))

    metas = [
        AccountMeta(pubkey=payer, is_signer=True, is_writable=True),  # payer
        AccountMeta(pubkey=ata, is_signer=False, is_writable=True),  # ATA
        AccountMeta(pubkey=owner, is_signer=False, is_writable=False),  # wallet owner
        AccountMeta(pubkey=mint, is_signer=False, is_writable=False),  # mint
        AccountMeta(pubkey=system_prog, is_signer=False, is_writable=False),  # system program
        AccountMeta(pubkey=token_prog, is_signer=False, is_writable=False),  # token program
        AccountMeta(pubkey=rent_sysvar, is_signer=False, is_writable=False),  # rent
    ]

    # Debug
    print("Building ATA create instruction, metas:")
    for i, m in enumerate(metas):
        print(f"  {i}: {m.pubkey} signer={m.is_signer} writable={m.is_writable}")

    ix = Instruction(assoc_prog, b"", metas)
    return ata, ix


async def create_or_get_token_account(
    payer: Pubkey, owner: Pubkey, mint: Pubkey
) -> Tuple[Pubkey, Optional[Instruction]]:
    ata = get_associated_token_address(owner, mint)
    print(
        ">>> ATA debug:",
        {
            "payer": str(payer),
            "owner": str(owner),
            "mint": str(mint),
            "ata": str(ata),
        },
    )
    try:
        info = await client.get_account_info(ata)
        if info.value is not None:
            return ata, None
    except Exception as e:
        print("Warning fetching ATA info:", e)

    ata, ix = create_associated_token_account_instruction(payer, owner, mint)
    return ata, ix


# ------------------ Transaction utils ------------------ #


async def send_and_confirm_transaction(
    txn: Transaction, *signers, skip_preflight: bool = True, confirm: bool = False
) -> bool:
    """Send and confirm a transaction with simple rate-limit backoff."""
    backoff = 1
    for attempt in range(1, 4):
        try:
            txn_sig = await client.send_transaction(
                txn, *signers, opts=TxOpts(skip_preflight=skip_preflight, max_retries=1)
            )
            print("Transaction Signature:", txn_sig.value)
            if confirm:
                status = await client.confirm_transaction(txn_sig.value)
                return status
            return txn_sig.value
        except Exception as e:
            err_str = str(e)
            print(f"Transaction error (attempt {attempt}): {err_str}")
            if "429" in err_str or "Too Many Requests" in err_str:
                if attempt == 3:
                    break
                await asyncio.sleep(backoff)
                backoff *= 2
                continue
            break
    return False


# ------------------ WSOL & IPFS logic ------------------ #


async def download_image(image_url: str) -> Optional[bytes]:
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
    file: Optional[str] = None,
) -> Optional[str]:
    try:
        if image_url and image_url.startswith(
            "https://sapphire-working-koi-276.mypinata.cloud/ipfs/"
        ):
            print(f"Using provided Pinata image URL: {image_url}")
        else:
            data_to_upload = None
            if image_data:
                data_to_upload = image_data
            elif file:
                try:
                    with open(file, "rb") as f:
                        data_to_upload = f.read()
                except Exception as e:
                    print(f"Error reading file: {e}")
            elif image_url:
                data_to_upload = await download_image(image_url)
                if not data_to_upload:
                    print(f"Failed to download image from URL: {image_url}")

            if data_to_upload:
                boundary = "----WebKitFormBoundarymkE1BAuPXiGrhrdB"
                body = b""
                body += f"--{boundary}\r\n".encode("utf-8")
                body += b'Content-Disposition: form-data; name="image"; filename="image.jpg"\r\n'
                body += b"Content-Type: image/jpeg\r\n\r\n"
                body += data_to_upload
                body += f"\r\n--{boundary}--\r\n".encode("utf-8")
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
                        "https://gated.chat/upload/img", data=body, headers=headers
                    ) as response:
                        response_text = await response.text()
                        if response.status == 200:
                            if response_text.startswith("https://"):
                                image_url = response_text.strip()
                                print(f"Successfully uploaded image: {image_url}")
                            else:
                                try:
                                    result = json.loads(response_text)
                                    image_url = result.get("url")
                                except json.JSONDecodeError:
                                    pass
                        if not image_url:
                            print(f"Image upload error: {response_text}")
                            return None
            if not image_url:
                image_url = "https://sapphire-working-koi-276.mypinata.cloud/ipfs/bafybeihpy352xnqgn74nrjj6bgxndrss5nbqix4kfhwfanoyo766tgwzz4"
                print(f"Using default image URL: {image_url}")

        metadata = {
            "name": name,
            "symbol": symbol,
            "description": description,
            "createdOn": "https://bonk.fun",
            "image": image_url,
        }
        if twitter:
            metadata["twitter"] = twitter
        if telegram:
            metadata["telegram"] = telegram
        if website:
            metadata["website"] = website

        print(f"Uploading metadata for {name} ({symbol})...")
        headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "en-US,en;q=0.9",
            "content-type": "application/json",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "cross-site",
            "referrer": "https://letsbonk.fun/",
            "origin": "https://letsbonk.fun",
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://gated.chat/upload/meta", json=metadata, headers=headers
            ) as response:
                response_text = await response.text()
                if response.status == 200:
                    if response_text.startswith("https://"):
                        metadata_uri = response_text.strip()
                        print(f"Metadata uploaded, direct URL: {metadata_uri}")
                        return metadata_uri
                    try:
                        result = json.loads(response_text)
                        metadata_uri = result.get("url")
                        if metadata_uri:
                            print(f"Metadata uploaded: {metadata_uri}")
                            return metadata_uri
                    except json.JSONDecodeError:
                        pass
                print(f"Metadata upload error: {response_text}")
                return None
    except Exception:
        print(f"Error preparing IPFS metadata: {traceback.format_exc()}")
        return None


def calculate_tokens_receive(sol_amount, previous_sol=30, slippage=5):
    LAMPORTS_PER_SOL = 10 ** 9
    TOKEN_DECIMALS = 10 ** 6
    INITIAL_TOKENS = 1073000191 * TOKEN_DECIMALS
    K = 32190005730 * TOKEN_DECIMALS

    previous_lamports = int(previous_sol * 10 ** LAMPORTS_PER_SOL)
    new_lamports = previous_lamports + int(sol_amount * 10 ** LAMPORTS_PER_SOL)

    current_tokens = INITIAL_TOKENS - (K / (previous_lamports / LAMPORTS_PER_SOL))
    new_tokens = INITIAL_TOKENS - (K / (new_lamports / LAMPORTS_PER_SOL))

    tokens_received = (new_tokens - current_tokens) / TOKEN_DECIMALS
    max_sol_cost = sol_amount * (1 + slippage / 100)

    return {"token_amount": tokens_received, "max_sol_cost": max_sol_cost}


async def create_temporary_wsol_account(
    payer_pubkey: Pubkey, amount: float
) -> tuple[Pubkey, list[Instruction], Keypair]:
    """
    Create a temporary WSOL token account and initialize it properly.
    """
    wsol_keypair = Keypair()
    wsol_token_account = wsol_keypair.pubkey()

    try:
        min_rent_resp = await client.get_minimum_balance_for_rent_exemption(165)
        min_rent = min_rent_resp.value
    except Exception:
        min_rent = 2039280  # fallback

    lamports = min_rent + int(amount * 10 ** SOL_DECIMAL)
    instructions: list[Instruction] = []

    # 1. Create account
    create_wsol_account_ix = create_account(
        CreateAccountParams(
            from_pubkey=payer_pubkey,
            to_pubkey=wsol_token_account,
            lamports=lamports,
            space=165,
            owner=Pubkey.from_string(str(TOKEN_PROGRAM)),
        )
    )
    instructions.append(create_wsol_account_ix)

    # 2. Initialize account for WSOL mint
    init_wsol_account_ix = Instruction(
        Pubkey.from_string(str(TOKEN_PROGRAM)),
        SPL_TOKEN_INITIALIZE_ACCOUNT,
        [
            AccountMeta(pubkey=wsol_token_account, is_signer=False, is_writable=True),  # account
            AccountMeta(pubkey=Pubkey.from_string(str(WSOL_TOKEN)), is_signer=False, is_writable=False),  # mint
            AccountMeta(pubkey=payer_pubkey, is_signer=False, is_writable=False),  # owner
            AccountMeta(pubkey=Pubkey.from_string(str(RENT)), is_signer=False, is_writable=False),  # rent
        ],
    )
    instructions.append(init_wsol_account_ix)

    return wsol_token_account, instructions, wsol_keypair


async def get_close_wsol_instruction(
    wsol_token_account: Pubkey, owner: Pubkey
) -> Instruction:
    """
    Close WSOL account to recover SOL.
    """
    close_wsol_account_ix = Instruction(
        Pubkey.from_string(str(TOKEN_PROGRAM)),
        SPL_TOKEN_CLOSE_ACCOUNT,
        [
            AccountMeta(pubkey=wsol_token_account, is_signer=False, is_writable=True),  # account to close
            AccountMeta(pubkey=owner, is_signer=False, is_writable=True),  # destination
            AccountMeta(pubkey=owner, is_signer=True, is_writable=False),  # authority
        ],
    )
    return close_wsol_account_ix


async def get_token_account_balance(token_account: Pubkey) -> int:
    balance = await client.get_token_account_balance(token_account)
    return balance.value.amount
