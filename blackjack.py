from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional, Sequence

from cards import Card, Deck, shuffle_deck
from game_config import setting


BlackjackResult = str


@dataclass(frozen=True)
class BlackjackRules:
    decks: int = 6
    dealer_hits_soft_17: bool = False
    blackjack_payout: float = 1.5


@dataclass(frozen=True)
class BlackjackHand:
    cards: tuple[Card, ...]
    bet: float = 1.0
    stood: bool = False
    doubled: bool = False
    from_split: bool = False


@dataclass(frozen=True)
class BlackjackRound:
    deck: Deck
    next_card_index: int
    dealer_hand: BlackjackHand
    player_hands: tuple[BlackjackHand, ...]


@dataclass(frozen=True)
class BlackjackSettlement:
    hand: BlackjackHand
    result: BlackjackResult
    profit: float
    payout: float


def blackjack_card_value(card: Card) -> int:
    if card.rank == "A":
        return 11
    if card.rank in {"J", "Q", "K"}:
        return 10
    return int(card.rank)


def hand_value(cards: Sequence[Card]) -> tuple[int, bool]:
    total = sum(blackjack_card_value(card) for card in cards)
    aces = sum(card.rank == "A" for card in cards)

    while total > 21 and aces:
        total -= 10
        aces -= 1

    return total, aces > 0


def is_bust(hand: BlackjackHand) -> bool:
    total, _ = hand_value(hand.cards)
    return total > 21


def is_natural_blackjack(hand: BlackjackHand) -> bool:
    total, _ = hand_value(hand.cards)
    return len(hand.cards) == 2 and total == 21 and not hand.from_split


def configured_blackjack_rules() -> BlackjackRules:
    return BlackjackRules(
        decks=int(setting("blackjack", "decks", 6)),
        dealer_hits_soft_17=bool(setting("blackjack", "dealer_hits_soft_17", False)),
        blackjack_payout=float(setting("blackjack", "blackjack_payout", 1.5)),
    )


def deal_blackjack(
    server_seed: str,
    client_seed: str,
    nonce: int,
    rules: Optional[BlackjackRules] = None,
) -> BlackjackRound:
    rules = rules or configured_blackjack_rules()
    deck = shuffle_deck(server_seed, client_seed, nonce, rules.decks)
    player_hand = BlackjackHand(cards=(deck[0], deck[2]))
    dealer_hand = BlackjackHand(cards=(deck[1], deck[3]))

    if is_natural_blackjack(player_hand) or is_natural_blackjack(dealer_hand):
        player_hand = replace(player_hand, stood=True)
        dealer_hand = replace(dealer_hand, stood=True)

    return BlackjackRound(
        deck=deck,
        next_card_index=4,
        dealer_hand=dealer_hand,
        player_hands=(player_hand,),
    )


def hit(round_state: BlackjackRound, hand_index: int = 0) -> BlackjackRound:
    hand = round_state.player_hands[hand_index]
    if hand.stood or is_bust(hand) or is_natural_blackjack(hand):
        raise ValueError("cannot hit a completed hand")

    card = round_state.deck[round_state.next_card_index]
    updated_hand = replace(hand, cards=hand.cards + (card,))
    if is_bust(updated_hand):
        updated_hand = replace(updated_hand, stood=True)

    return replace_player_hand(round_state, hand_index, updated_hand, round_state.next_card_index + 1)


def stand(round_state: BlackjackRound, hand_index: int = 0) -> BlackjackRound:
    hand = round_state.player_hands[hand_index]
    return replace_player_hand(round_state, hand_index, replace(hand, stood=True), round_state.next_card_index)


def double_down(round_state: BlackjackRound, hand_index: int = 0) -> BlackjackRound:
    hand = round_state.player_hands[hand_index]
    if len(hand.cards) != 2 or hand.stood or is_natural_blackjack(hand):
        raise ValueError("double down is only allowed on an active two-card hand")

    card = round_state.deck[round_state.next_card_index]
    updated_hand = replace(
        hand,
        cards=hand.cards + (card,),
        bet=hand.bet * 2,
        stood=True,
        doubled=True,
    )
    return replace_player_hand(round_state, hand_index, updated_hand, round_state.next_card_index + 1)


def can_split(hand: BlackjackHand) -> bool:
    return len(hand.cards) == 2 and blackjack_card_value(hand.cards[0]) == blackjack_card_value(hand.cards[1])


def split_hand(round_state: BlackjackRound, hand_index: int = 0) -> BlackjackRound:
    hand = round_state.player_hands[hand_index]
    if not can_split(hand):
        raise ValueError("hand cannot be split")

    first_card = round_state.deck[round_state.next_card_index]
    second_card = round_state.deck[round_state.next_card_index + 1]
    first_hand = BlackjackHand(cards=(hand.cards[0], first_card), bet=hand.bet, from_split=True)
    second_hand = BlackjackHand(cards=(hand.cards[1], second_card), bet=hand.bet, from_split=True)

    hands = list(round_state.player_hands)
    hands[hand_index : hand_index + 1] = [first_hand, second_hand]

    return BlackjackRound(
        deck=round_state.deck,
        next_card_index=round_state.next_card_index + 2,
        dealer_hand=round_state.dealer_hand,
        player_hands=tuple(hands),
    )


def play_dealer(round_state: BlackjackRound, rules: Optional[BlackjackRules] = None) -> BlackjackRound:
    rules = rules or configured_blackjack_rules()
    dealer = round_state.dealer_hand
    next_card_index = round_state.next_card_index

    if dealer.stood or is_natural_blackjack(dealer) or any(is_natural_blackjack(hand) for hand in round_state.player_hands):
        return replace(round_state, dealer_hand=replace(dealer, stood=True))

    if all(is_bust(hand) for hand in round_state.player_hands):
        return replace(round_state, dealer_hand=replace(dealer, stood=True))

    while should_dealer_draw(dealer, rules):
        card = round_state.deck[next_card_index]
        dealer = replace(dealer, cards=dealer.cards + (card,))
        next_card_index += 1

    return BlackjackRound(
        deck=round_state.deck,
        next_card_index=next_card_index,
        dealer_hand=replace(dealer, stood=True),
        player_hands=round_state.player_hands,
    )


def should_dealer_draw(dealer: BlackjackHand, rules: BlackjackRules) -> bool:
    total, soft = hand_value(dealer.cards)
    if total < 17:
        return True
    return total == 17 and soft and rules.dealer_hits_soft_17


def settle_blackjack(
    round_state: BlackjackRound,
    rules: Optional[BlackjackRules] = None,
) -> tuple[BlackjackSettlement, ...]:
    rules = rules or configured_blackjack_rules()
    dealer = round_state.dealer_hand
    dealer_total, _ = hand_value(dealer.cards)
    dealer_blackjack = is_natural_blackjack(dealer)
    dealer_bust = dealer_total > 21

    settlements = []
    for hand in round_state.player_hands:
        player_total, _ = hand_value(hand.cards)
        player_blackjack = is_natural_blackjack(hand)

        if player_total > 21:
            result = "lose"
            profit = -hand.bet
        elif player_blackjack and dealer_blackjack:
            result = "push"
            profit = 0.0
        elif player_blackjack:
            result = "blackjack"
            profit = hand.bet * rules.blackjack_payout
        elif dealer_blackjack:
            result = "lose"
            profit = -hand.bet
        elif dealer_bust:
            result = "win"
            profit = hand.bet
        elif player_total > dealer_total:
            result = "win"
            profit = hand.bet
        elif player_total < dealer_total:
            result = "lose"
            profit = -hand.bet
        else:
            result = "push"
            profit = 0.0

        settlements.append(BlackjackSettlement(hand=hand, result=result, profit=profit, payout=hand.bet + profit))

    return tuple(settlements)


def play_actions(
    round_state: BlackjackRound,
    actions: Sequence[str],
    rules: Optional[BlackjackRules] = None,
    hand_index: int = 0,
) -> BlackjackRound:
    rules = rules or configured_blackjack_rules()
    for action in actions:
        if action == "hit":
            round_state = hit(round_state, hand_index)
        elif action == "stand":
            round_state = stand(round_state, hand_index)
        elif action == "double":
            round_state = double_down(round_state, hand_index)
        else:
            raise ValueError("actions must be hit, stand, or double")

        if round_state.player_hands[hand_index].stood:
            break

    if not round_state.player_hands[hand_index].stood:
        round_state = stand(round_state, hand_index)

    return play_dealer(round_state, rules)


def replace_player_hand(
    round_state: BlackjackRound,
    hand_index: int,
    hand: BlackjackHand,
    next_card_index: int,
) -> BlackjackRound:
    hands = list(round_state.player_hands)
    hands[hand_index] = hand
    return BlackjackRound(
        deck=round_state.deck,
        next_card_index=next_card_index,
        dealer_hand=round_state.dealer_hand,
        player_hands=tuple(hands),
    )
