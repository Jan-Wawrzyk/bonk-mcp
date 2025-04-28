import os
from solders.pubkey import Pubkey
from solana.rpc.async_api import AsyncClient
from dotenv import load_dotenv

# Load environment variables
load_dotenv(override=True)

KEYPAIR = os.getenv("KEYPAIR")

#############################
# COMPUTE BUDGET SETTINGS
#############################
UNIT_PRICE = 2_500_000
UNIT_BUDGET = 1_000_000

#############################
# TOKEN DECIMAL SETTINGS
#############################
TOKEN_DECIMAL = 6
SOL_DECIMAL = 9

#############################
# SYSTEM PROGRAM ADDRESSES
#############################
SYSTEM_PROGRAM = Pubkey.from_string("11111111111111111111111111111111")
TOKEN_PROGRAM = Pubkey.from_string(
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
ASSOC_TOKEN_ACC_PROG = Pubkey.from_string(
    "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL")
METAPLEX_PROGRAM = Pubkey.from_string(
    "metaqbxxUerdq28cj1RbAWkYQm3ybzjb6a8bt518x1s")
RENT = Pubkey.from_string("SysvarRent111111111111111111111111111111111")

#############################
# TOKEN ADDRESSES
#############################
WSOL_TOKEN = Pubkey.from_string("So11111111111111111111111111111111111111112")

#############################
# RAYDIUM LAUNCHPAD ADDRESSES
#############################
RAYDIUM_LAUNCHPAD_PROGRAM = Pubkey.from_string(
    "LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj")
RAYDIUM_AUTHORITY = Pubkey.from_string(
    "WLHv2UAZm6z4KyaaELi5pjdbJh6RESMva1Rnn8pJVVh")
GLOBAL_CONFIG = Pubkey.from_string(
    "6s1xP3hpbAfFoNtUNF8mfHsjr2Bd97JxFJRWLbL6aHuX")
PLATFORM_CONFIG = Pubkey.from_string(
    "FfYek5vEz23cMkWsdJwG2oa6EphsvXSHrGpdALN4g6W1")
EVENT_AUTHORITY = Pubkey.from_string(
    "2DPAtwB8L12vrMRExbLuyGnC7n2J5LNoZQSejeQGpwkr")

#############################
# PDA SEEDS
#############################
LAUNCHPAD_POOL_SEED = "pool".encode()
LAUNCHPAD_POOL_VAULT_SEED = "pool_vault".encode()

#############################
# RPC CONNECTION
#############################
# Get RPC URL from environment variable, fallback to Solana devnet
RPC_URL = os.getenv("RPC_URL", "https://api.devnet.solana.com")
client = AsyncClient(RPC_URL)
