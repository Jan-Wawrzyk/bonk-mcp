import asyncio
import os
import sys
import base58
import ssl
import aiohttp
import json
from typing import Optional

from solders.keypair import Keypair
from solders.pubkey import Pubkey

# RPC client for balance checking
from solana.rpc.async_api import AsyncClient

# Commitment level
from solana.rpc.commitment import Confirmed

try:
    import certifi

    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    print("Warning: certifi not installed. Run: pip install certifi")
    SSL_CONTEXT = None

# bonk_mcp imports
from bonk_mcp.core.letsbonk import launch_token_with_buy, create_buy_tx
from bonk_mcp.utils import send_and_confirm_transaction, prepare_ipfs

# Configuration
NAME = "CHLADIK"
SYMBOL = "DICK"
DESCRIPTION = "GIANT COCK"
IMAGE_URL = "https://ipfs.io/ipfs/bafkreib2irepj4xxku6eovlbbmnb5wbkktyt6pecexdjfxhxvmuwpnirae"

RPC_URL = os.getenv("RPC_URL", "https://api.mainnet-beta.solana.com")
KEYPAIR_B58 = os.getenv("KEYPAIR")
INITIAL_BUY_SOL = 0.05 # in SOL



def validate_environment():
    if not KEYPAIR_B58:
        print("ERROR: KEYPAIR environment variable not set!")
        sys.exit(1)
    print(f"✓ RPC URL: {RPC_URL}")
    print(f"✓ Keypair provided (len {len(KEYPAIR_B58)})")


def make_keypair_from_base58(b58: str) -> Keypair:
    try:
        private_key_bytes = base58.b58decode(b58)
        if len(private_key_bytes) != 64:
            raise ValueError(f"Expected 64 bytes keypair, got {len(private_key_bytes)}")
        return Keypair.from_bytes(private_key_bytes)
    except Exception as e:
        print(f"ERROR decoding keypair: {e}")
        sys.exit(1)


async def test_ssl_connection():
    print("\n🔍 Testing SSL connections...")
    test_urls = ["https://ipfs.io", "https://api.mainnet-beta.solana.com"]
    connector = aiohttp.TCPConnector(ssl=SSL_CONTEXT) if SSL_CONTEXT else None
    async with aiohttp.ClientSession(connector=connector) as session:
        for url in test_urls:
            try:
                async with session.get(url, timeout=5) as resp:
                    print(f"  {url} -> {resp.status}")
            except Exception as e:
                print(f"  {url} failed: {e}")


async def prepare_ipfs_with_ssl_fix(name: str, symbol: str, description: str, image_url: str) -> Optional[str]:
    original = aiohttp.ClientSession

    class SSLFixedClientSession(original):
        def __init__(self, *args, **kwargs):
            if SSL_CONTEXT and "connector" not in kwargs:
                kwargs["connector"] = aiohttp.TCPConnector(ssl=SSL_CONTEXT)
            super().__init__(*args, **kwargs)

    aiohttp.ClientSession = SSLFixedClientSession
    try:
        return await prepare_ipfs(name=name, symbol=symbol, description=description, image_url=image_url)
    finally:
        aiohttp.ClientSession = original


async def get_wallet_balance(pubkey: Pubkey) -> float:
    try:
        async with aiohttp.ClientSession() as session:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getBalance",
                "params": [str(pubkey)],
            }
            async with session.post(RPC_URL, json=payload) as r:
                data = await r.json()
                if "result" in data:
                    lamports = data["result"]["value"]
                    return lamports / 1e9
    except Exception as e:
        print("Balance fetch error:", e)
    return 0.0


async def get_token_balance(owner_pubkey: str, mint_address: str) -> Optional[float]:
    """
    Fetch the token balance of the associated token account for owner+mint via getTokenAccountsByOwner
    """
    try:
        async with aiohttp.ClientSession() as session:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getTokenAccountsByOwner",
                "params": [
                    owner_pubkey,
                    {"mint": mint_address},
                    {"encoding": "jsonParsed"},
                ],
            }
            async with session.post(RPC_URL, json=payload) as r:
                res = await r.json()
                if "result" in res and res["result"]["value"]:
                    accounts = res["result"]["value"]
                    total = 0
                    for acc in accounts:
                        amt_str = acc["account"]["data"]["parsed"]["info"]["tokenAmount"]["uiAmount"]
                        total += amt_str if amt_str is not None else 0
                    return total
                return 0.0
    except Exception as e:
        print("Error fetching token balance:", e)
        return None


# Core ------------------------------------------------------


async def do_initial_buy(payer_keypair: Keypair, mint_pubkey: Pubkey, amount_sol: float, pdas: dict):
    print(f"\n💸 Starting initial buy of {amount_sol} SOL...")

    minimum_amount_out = 0.0  # placeholder; should be slippage-protected in production

    buy_txn, extra_signers = await create_buy_tx(
        payer_keypair=payer_keypair,
        mint_pubkey=mint_pubkey,
        amount_in=amount_sol,
        minimum_amount_out=minimum_amount_out,
    )

    # Retry logic
    for attempt in range(1, 4):
        try:
            print(f"→ Sending buy transaction (attempt {attempt})...")
            success = await send_and_confirm_transaction(buy_txn, payer_keypair, *extra_signers)
            if success:
                print("✅ Initial buy succeeded.")
                return True
            else:
                print(f"❌ Buy failed on attempt {attempt}.")
        except Exception as e:
            print(f"✗ Attempt {attempt} error: {e}")
        await asyncio.sleep(1 + attempt)
    print("⚠️ Initial buy ultimately failed after retries.")
    return False


async def main():
    print("=" * 60)
    print("🚀 Launch + Initial Buy Script")
    print("=" * 60)

    validate_environment()
    await test_ssl_connection()

    payer = make_keypair_from_base58(KEYPAIR_B58)
    mint = Keypair()

    print(f"Payer: {payer.pubkey()}")
    print(f"New Mint: {mint.pubkey()}")

    balance = await get_wallet_balance(payer.pubkey())
    print(f"\n💰 Wallet SOL balance: {balance:.4f} SOL")
    if balance < INITIAL_BUY_SOL + 0.1:
        print(f"⚠️ Low balance: need at least {INITIAL_BUY_SOL + 0.1:.2f} SOL for buy + buffer. Aborting.")
        return

    # IPFS metadata
    print("\n📦 Preparing metadata...")
    uri = await prepare_ipfs_with_ssl_fix(NAME, SYMBOL, DESCRIPTION, IMAGE_URL)
    if not uri:
        print("❌ Failed to prepare IPFS metadata")
        return
    print(f"✓ Metadata URI: {uri}")

    # Launch token
    print("\n🎯 Launching token...")
    launch_result = await launch_token_with_buy(
        payer_keypair=payer,
        mint_keypair=mint,
        name=NAME,
        symbol=SYMBOL,
        uri=uri,
        decimals=6,
        supply="1000000000000000",
        base_sell="793100000000000",
        quote_raising="85000000000",
    )

    if launch_result.get("error"):
        print("❌ Launch failed:", launch_result["error"])
        return

    print("✅ Launch succeeded.")
    pdas = launch_result.get("pdas", {})
    base_token_account = launch_result.get("base_token_account")
    print(f"PDAs: {pdas}")
    print(f"Base token account (should receive buy output): {base_token_account}")

    # Initial buy
    bought = await do_initial_buy(payer, mint.pubkey(), INITIAL_BUY_SOL, pdas)
    if not bought:
        print("Buy failed. You can manually purchase at https://letsbonk.fun")
        return

    # Check token balance (DICK) in wallet
    print("\n🔎 Verifying token balance after buy...")
    token_balance = await get_token_balance(str(payer.pubkey()), str(mint.pubkey()))
    if token_balance is None:
        print("Could not fetch token balance.")
    else:
        print(f"🪙 DICK token balance in wallet: {token_balance}")

    print("\nDone.")
    

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Cancelled by user")
    except Exception as e:
        print("Fatal error:", e)
        import traceback
        traceback.print_exc()
