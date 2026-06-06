import hashlib
import hmac
import os
from pathlib import Path
import secrets
from functools import lru_cache
from typing import Optional
import requests

from game_config import setting, target_rtp


ETHERSCAN_API_URL = "https://api.etherscan.io/api"
DEFAULT_CRASH_RTP = 0.98
DEFAULT_INSTANT_CRASH_MODULUS = 25


def _load_env_api_key() -> Optional[str]:
    env_path = Path(__file__).with_name(".env")
    if not env_path.exists():
        return None

    for line in env_path.read_text().splitlines():
        key, separator, value = line.partition("=")
        if separator and key.strip() == "ETHERSCAN_API_KEY":
            return value.strip().strip("\"'")

    return None


def _etherscan_api_key(api_key: Optional[str] = None) -> str:
    key = api_key or os.getenv("ETHERSCAN_API_KEY") or _load_env_api_key()
    if not key:
        raise RuntimeError("Set ETHERSCAN_API_KEY before fetching Ethereum block hashes.")
    return key


@lru_cache(maxsize=1)
def get_latest_eth_block_hash(api_key: Optional[str] = None) -> str:
    """Fetch the latest Ethereum block hash from Etherscan."""
    params = {
        "module": "proxy",
        "action": "eth_blockNumber",
        "apikey": _etherscan_api_key(api_key),
    }

    with requests.Session() as session:
        response = session.get(ETHERSCAN_API_URL, params=params, timeout=10)
        response.raise_for_status()
        block_number = int(response.json()["result"], 16)

        block_params = {
            "module": "proxy",
            "action": "eth_getBlockByNumber",
            "tag": hex(block_number),
            "boolean": "true",
            "apikey": _etherscan_api_key(api_key),
        }

        block_response = session.get(ETHERSCAN_API_URL, params=block_params, timeout=10)
        block_response.raise_for_status()
        return block_response.json()["result"]["hash"]


def generate_initial_server_seed() -> str:
    """Generate a private random server seed."""
    return secrets.token_hex(32)


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def derive_server_seed(initial_seed: str, nonce: int) -> str:
    """Derive a per-game server seed from the initial server seed."""
    return sha256_hex(f"{initial_seed}:{nonce}")


def hmac_sha256(server_seed: str, client_seed: str, nonce: int, cursor: int = 0) -> bytes:
    message = f"{client_seed}:{nonce}:{cursor}".encode()
    return hmac.new(server_seed.encode(), message, hashlib.sha256).digest()


def is_divisible(hex_value: str, modulus: int) -> bool:
    return int(hex_value[:8], 16) % modulus == 0


def multiplier(server_seed: str, client_seed: str, nonce: int) -> float:
    """Turn a server seed, client seed, and nonce into a crash-game multiplier."""
    digest = hmac_sha256(server_seed, client_seed, nonce).hex()

    instant_crash_modulus = int(setting("crash", "instant_crash_modulus", DEFAULT_INSTANT_CRASH_MODULUS))
    if is_divisible(digest, instant_crash_modulus):
        return 1.0

    hash_int = int(digest[:13], 16)
    max_hash_int = 2**52
    payout_percent = target_rtp("crash", DEFAULT_CRASH_RTP) * 100

    return max(1.0, (payout_percent * max_hash_int - hash_int) / (max_hash_int - hash_int) / 100)


def fair_multiplier(game_number: int, initial_seed: str, client_seed: str) -> float:
    server_seed = derive_server_seed(initial_seed, game_number)
    return multiplier(server_seed, client_seed, game_number)
