# Provably Fair Casino Math Modules

Python modules for deterministic, verifiable casino-style game math:

- Crash/Limbo-style multipliers
- Weighted reel slots
- Baccarat
- Blackjack
- Shared HMAC-SHA256 PRNG
- Shared card/deck shuffle utilities

The core idea is:

```text
server_seed + client_seed + nonce -> HMAC-SHA256 -> deterministic outcome
```

If the server seed hash is published before play and the server seed is revealed after play, the result can be independently recomputed.

## Files

```text
prng.py              Shared HMAC-SHA256 PRNG and seed helpers
cards.py             Card model, deck builder, Fisher-Yates shuffle
prng_crash_limbo.py  Crash multiplier engine
slots.py             Slot reels, paylines, RTP calibration, volatility shaping
baccarat.py          Baccarat dealing, draw rules, settlement
blackjack.py         Blackjack dealing, actions, dealer rules, settlement
game_config.py       JSON config loader
game_config.json     Editable RTP/rule config
math_engine.tex      Detailed LaTeX math documentation
math_engine.pdf      Compiled math documentation
```

## Requirements

The library uses the Python standard library for most modules. `prng_crash_limbo.py` also uses `requests` to fetch the latest Ethereum block hash from Etherscan.

```powershell
py -m pip install requests
```

For Etherscan support, create a local `.env` file:

```text
ETHERSCAN_API_KEY=your_etherscan_api_key_here
```

Use `.env.example` as the template. The real `.env` is ignored by git.

## Provably Fair Flow

1. Generate a private server seed.
2. Publish `SHA256(server_seed)` before the game.
3. Use a client seed chosen by the player or external source.
4. Increment the nonce per game.
5. Compute the outcome.
6. Reveal the server seed later.
7. Anyone can recompute the same outcome.

Example:

```python
from prng import generate_server_seed, server_seed_hash

server_seed = generate_server_seed()
commitment = server_seed_hash(server_seed)

print(commitment)
```

## Shared PRNG

`FairRng` creates deterministic bytes from a server seed, client seed, and nonce:

```python
from prng import FairRng

rng = FairRng("server-seed", "client-seed", nonce=0)
value = rng.random_int(52)
```

`random_int(upper_bound)` uses rejection sampling, so it avoids modulo bias.

## Crash / Limbo Multipliers

```python
from prng import generate_server_seed
from prng_crash_limbo import fair_multiplier

server_seed = generate_server_seed()
client_seed = "client-seed"

result = fair_multiplier(
    game_number=0,
    initial_seed=server_seed,
    client_seed=client_seed,
)

print(result)
```

Crash RTP is directly controlled by `game_config.json`:

```json
"crash": {
  "target_rtp": 0.98,
  "instant_crash_modulus": 25
}
```

`target_rtp = 0.98` means 98%.

## Slots

Build a slot config from reels, visible rows, paylines, and payouts:

```python
from prng import generate_server_seed
from slots import SlotConfig, configure_rtp, expand_weighted_reel, spin

reel = expand_weighted_reel({
    "A": 2,
    "K": 4,
    "Q": 8,
    "W": 1,
    "S": 1,
})

base_config = SlotConfig(
    reels=(reel, reel, reel, reel, reel),
    rows=3,
    paylines=(
        (0, 0, 0, 0, 0),
        (1, 1, 1, 1, 1),
        (2, 2, 2, 2, 2),
    ),
    paytable={
        "A": {3: 5.0, 4: 20.0, 5: 100.0},
        "K": {3: 3.0, 4: 10.0, 5: 50.0},
        "Q": {3: 1.0, 4: 5.0, 5: 25.0},
    },
    wild_symbol="W",
    scatter_symbol="S",
    scatter_pays={3: 5.0, 4: 20.0, 5: 100.0},
)

config = configure_rtp(base_config)

result = spin(
    config,
    server_seed=generate_server_seed(),
    client_seed="client-seed",
    nonce=0,
    bet=1.0,
)

print(result.total_multiplier, result.payout)
```

Slot RTP and volatility are configured here:

```json
"slots": {
  "target_rtp": 0.96,
  "volatility": 1.0,
  "calibration_max_combinations": 1000000
}
```

Volatility is numeric:

```text
0.75  lower volatility
1.00  neutral
1.35  higher volatility
1.75  very high volatility
```

`configure_rtp()` first reshapes payouts by volatility, then scales payouts so exact RTP matches `target_rtp`.

Important: exact RTP enumerates every reel-stop combination:

```text
combinations = len(reel_1) * len(reel_2) * ... * len(reel_n)
```

For large slots, use `sample_rtp()` instead of exact enumeration.

## Baccarat

```python
from prng import generate_server_seed
from baccarat import deal_baccarat, settle_baccarat_bet

server_seed = generate_server_seed()
round_result = deal_baccarat(server_seed, "client-seed", nonce=0)
settlement = settle_baccarat_bet(round_result, "banker", stake=1.0)

print(round_result.outcome)
print(settlement.payout)
```

Baccarat settings:

```json
"baccarat": {
  "target_rtp": 0.98,
  "decks": 8,
  "banker_commission": 0.05,
  "tie_payout": 8.0
}
```

`target_rtp` is informational for baccarat. Actual RTP comes from rules and payouts, especially banker commission and tie payout.

## Blackjack

```python
from prng import generate_server_seed
from blackjack import deal_blackjack, play_actions, settle_blackjack

server_seed = generate_server_seed()
round_state = deal_blackjack(server_seed, "client-seed", nonce=0)

if not round_state.player_hands[0].stood:
    round_state = play_actions(round_state, ["hit", "stand"])

settlements = settle_blackjack(round_state)
print(settlements[0].result, settlements[0].payout)
```

Blackjack settings:

```json
"blackjack": {
  "target_rtp": 0.99,
  "decks": 6,
  "dealer_hits_soft_17": false,
  "blackjack_payout": 1.5
}
```

`target_rtp` is informational for blackjack. Actual RTP depends on rules and player strategy.

## Game Config

Config values live in `game_config.json`.

RTP values are decimals:

```text
0.96 = 96%
0.98 = 98%
1.00 = 100%
```

If you edit config during a long-running Python process, clear the config cache:

```python
from game_config import reload_game_config

reload_game_config()
```

## Math Documentation

The detailed math is in:

- `math_engine.tex`
- `math_engine.pdf`

It covers HMAC generation, rejection sampling, Fisher-Yates shuffling, crash multiplier math, slot RTP/volatility, baccarat rules, blackjack settlement, and verification flow.

## Development Checks

Compile all modules:

```powershell
py -m py_compile game_config.py prng.py cards.py slots.py baccarat.py blackjack.py prng_crash_limbo.py
```

Compile the math document:

```powershell
pdflatex -interaction=nonstopmode -halt-on-error math_engine.tex
pdflatex -interaction=nonstopmode -halt-on-error math_engine.tex
```

## Notes

This library provides deterministic, auditable math primitives. It does not provide a complete casino backend, wallet logic, regulatory controls, anti-fraud systems, or production game server infrastructure.
