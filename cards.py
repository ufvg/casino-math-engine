from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from prng import FairRng


RANKS = ("A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K")
SUITS = ("spades", "hearts", "diamonds", "clubs")


@dataclass(frozen=True)
class Card:
    rank: str
    suit: str

    def __str__(self) -> str:
        return f"{self.rank} of {self.suit}"


Deck = tuple[Card, ...]


def build_deck(decks: int = 1) -> Deck:
    if decks <= 0:
        raise ValueError("decks must be positive")

    return tuple(Card(rank, suit) for _ in range(decks) for suit in SUITS for rank in RANKS)


def fisher_yates_shuffle(cards: Sequence[Card], rng: FairRng) -> Deck:
    shuffled = list(cards)

    for index in range(len(shuffled) - 1, 0, -1):
        swap_index = rng.random_int(index + 1)
        shuffled[index], shuffled[swap_index] = shuffled[swap_index], shuffled[index]

    return tuple(shuffled)


def shuffle_deck(server_seed: str, client_seed: str, nonce: int, decks: int = 1) -> Deck:
    rng = FairRng(server_seed, client_seed, nonce)
    return fisher_yates_shuffle(build_deck(decks), rng)
