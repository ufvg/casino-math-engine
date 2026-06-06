from __future__ import annotations

import hashlib
import hmac
import math
import secrets


class FairRng:
    """Deterministic HMAC-SHA256 byte stream for a server seed, client seed, and nonce."""

    def __init__(self, server_seed: str, client_seed: str, nonce: int) -> None:
        self.server_seed = server_seed
        self.client_seed = client_seed
        self.nonce = nonce
        self.cursor = 0

    def random_bytes(self, length: int) -> bytes:
        if length <= 0:
            raise ValueError("length must be positive")

        output = b""
        while len(output) < length:
            message = f"{self.client_seed}:{self.nonce}:{self.cursor}".encode()
            output += hmac.new(self.server_seed.encode(), message, hashlib.sha256).digest()
            self.cursor += 1

        return output[:length]

    def random_int(self, upper_bound: int) -> int:
        """Return an unbiased integer in [0, upper_bound)."""
        if upper_bound <= 0:
            raise ValueError("upper_bound must be positive")

        byte_length = max(1, math.ceil(upper_bound.bit_length() / 8))
        sample_space = 1 << (8 * byte_length)
        unbiased_limit = sample_space - (sample_space % upper_bound)

        while True:
            value = int.from_bytes(self.random_bytes(byte_length), "big")
            if value < unbiased_limit:
                return value % upper_bound


def generate_server_seed() -> str:
    return secrets.token_hex(32)


def server_seed_hash(server_seed: str) -> str:
    return hashlib.sha256(server_seed.encode()).hexdigest()
