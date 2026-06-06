from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from cards import Card, Deck, shuffle_deck
from game_config import setting


BaccaratBet = str
BaccaratOutcome = str


@dataclass(frozen=True)
class BaccaratRound:
    deck: Deck
    player_hand: tuple[Card, ...]
    banker_hand: tuple[Card, ...]
    player_total: int
    banker_total: int
    outcome: BaccaratOutcome
    natural: bool
    player_third_card: Optional[Card]
    banker_third_card: Optional[Card]


@dataclass(frozen=True)
class BaccaratSettlement:
    bet_on: BaccaratBet
    stake: float
    profit: float
    payout: float


def baccarat_card_value(card: Card) -> int:
    if card.rank == "A":
        return 1
    if card.rank in {"10", "J", "Q", "K"}:
        return 0
    return int(card.rank)


def hand_total(cards: tuple[Card, ...]) -> int:
    return sum(baccarat_card_value(card) for card in cards) % 10


def deal_baccarat(server_seed: str, client_seed: str, nonce: int, decks: Optional[int] = None) -> BaccaratRound:
    decks = int(decks if decks is not None else setting("baccarat", "decks", 8))
    deck = shuffle_deck(server_seed, client_seed, nonce, decks)

    player_hand = [deck[0], deck[2]]
    banker_hand = [deck[1], deck[3]]
    next_card_index = 4

    player_total = hand_total(tuple(player_hand))
    banker_total = hand_total(tuple(banker_hand))
    natural = player_total in {8, 9} or banker_total in {8, 9}
    player_third_card = None
    banker_third_card = None

    if not natural:
        if player_total <= 5:
            player_third_card = deck[next_card_index]
            player_hand.append(player_third_card)
            next_card_index += 1

        player_total = hand_total(tuple(player_hand))
        banker_total = hand_total(tuple(banker_hand))

        if should_banker_draw(banker_total, player_third_card):
            banker_third_card = deck[next_card_index]
            banker_hand.append(banker_third_card)

    player_total = hand_total(tuple(player_hand))
    banker_total = hand_total(tuple(banker_hand))
    outcome = baccarat_outcome(player_total, banker_total)

    return BaccaratRound(
        deck=deck,
        player_hand=tuple(player_hand),
        banker_hand=tuple(banker_hand),
        player_total=player_total,
        banker_total=banker_total,
        outcome=outcome,
        natural=natural,
        player_third_card=player_third_card,
        banker_third_card=banker_third_card,
    )


def should_banker_draw(banker_total: int, player_third_card: Optional[Card]) -> bool:
    if player_third_card is None:
        return banker_total <= 5

    player_third_value = baccarat_card_value(player_third_card)

    if banker_total <= 2:
        return True
    if banker_total == 3:
        return player_third_value != 8
    if banker_total == 4:
        return 2 <= player_third_value <= 7
    if banker_total == 5:
        return 4 <= player_third_value <= 7
    if banker_total == 6:
        return 6 <= player_third_value <= 7
    return False


def baccarat_outcome(player_total: int, banker_total: int) -> BaccaratOutcome:
    if player_total > banker_total:
        return "player"
    if banker_total > player_total:
        return "banker"
    return "tie"


def settle_baccarat_bet(
    round_result: BaccaratRound,
    bet_on: BaccaratBet,
    stake: float = 1.0,
    banker_commission: Optional[float] = None,
    tie_payout: Optional[float] = None,
) -> BaccaratSettlement:
    banker_commission = float(
        banker_commission if banker_commission is not None else setting("baccarat", "banker_commission", 0.05)
    )
    tie_payout = float(tie_payout if tie_payout is not None else setting("baccarat", "tie_payout", 8.0))

    if stake < 0:
        raise ValueError("stake cannot be negative")
    if bet_on not in {"player", "banker", "tie"}:
        raise ValueError("bet_on must be player, banker, or tie")

    if bet_on == "tie":
        profit = stake * tie_payout if round_result.outcome == "tie" else -stake
    elif round_result.outcome == "tie":
        profit = 0.0
    elif bet_on == round_result.outcome:
        multiplier = 1.0 - banker_commission if bet_on == "banker" else 1.0
        profit = stake * multiplier
    else:
        profit = -stake

    return BaccaratSettlement(
        bet_on=bet_on,
        stake=stake,
        profit=profit,
        payout=stake + profit,
    )
