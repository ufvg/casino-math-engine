from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import product
from typing import Mapping, Optional, Sequence

from game_config import setting, target_rtp
from prng import FairRng, generate_server_seed, server_seed_hash


Symbol = str
Reel = tuple[Symbol, ...]
Payline = tuple[int, ...]
Grid = tuple[tuple[Symbol, ...], ...]


@dataclass(frozen=True)
class SlotConfig:
    reels: tuple[Reel, ...]
    rows: int
    paylines: tuple[Payline, ...]
    paytable: Mapping[Symbol, Mapping[int, float]]
    wild_symbol: Optional[Symbol] = None
    scatter_symbol: Optional[Symbol] = None
    scatter_pays: Optional[Mapping[int, float]] = None


@dataclass(frozen=True)
class LineWin:
    payline_index: int
    symbol: Symbol
    count: int
    multiplier: float
    positions: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class ScatterWin:
    symbol: Symbol
    count: int
    multiplier: float


@dataclass(frozen=True)
class SpinResult:
    stops: tuple[int, ...]
    grid: Grid
    line_wins: tuple[LineWin, ...]
    scatter_win: Optional[ScatterWin]
    total_multiplier: float
    payout: float


def expand_weighted_reel(symbol_weights: Mapping[Symbol, int]) -> Reel:
    reel: list[Symbol] = []
    for symbol, weight in symbol_weights.items():
        if weight <= 0:
            raise ValueError("reel weights must be positive")
        reel.extend([symbol] * weight)
    return tuple(reel)


def validate_config(config: SlotConfig) -> None:
    if config.rows <= 0:
        raise ValueError("rows must be positive")
    if not config.reels:
        raise ValueError("at least one reel is required")
    if any(not reel for reel in config.reels):
        raise ValueError("reels cannot be empty")

    reel_count = len(config.reels)
    for payline in config.paylines:
        if len(payline) != reel_count:
            raise ValueError("each payline must contain one row index per reel")
        if any(row < 0 or row >= config.rows for row in payline):
            raise ValueError("payline row index is outside the visible grid")


def spin(config: SlotConfig, server_seed: str, client_seed: str, nonce: int, bet: float = 1.0) -> SpinResult:
    validate_config(config)
    rng = FairRng(server_seed, client_seed, nonce)
    stops = tuple(rng.random_int(len(reel)) for reel in config.reels)
    return evaluate_stops(config, stops, bet)


def evaluate_stops(config: SlotConfig, stops: Sequence[int], bet: float = 1.0) -> SpinResult:
    validate_config(config)
    if len(stops) != len(config.reels):
        raise ValueError("stops must contain one stop index per reel")
    if bet < 0:
        raise ValueError("bet cannot be negative")

    normalized_stops = tuple(stop % len(reel) for stop, reel in zip(stops, config.reels))
    grid = visible_grid(config.reels, normalized_stops, config.rows)
    line_wins = evaluate_lines(config, grid)
    scatter_win = evaluate_scatters(config, grid)
    total_multiplier = sum(win.multiplier for win in line_wins)

    if scatter_win is not None:
        total_multiplier += scatter_win.multiplier

    return SpinResult(
        stops=normalized_stops,
        grid=grid,
        line_wins=line_wins,
        scatter_win=scatter_win,
        total_multiplier=total_multiplier,
        payout=bet * total_multiplier,
    )


def scale_payouts(config: SlotConfig, payout_scale: float) -> SlotConfig:
    if payout_scale < 0:
        raise ValueError("payout_scale cannot be negative")

    paytable = {
        symbol: {count: multiplier * payout_scale for count, multiplier in payouts.items()}
        for symbol, payouts in config.paytable.items()
    }
    scatter_pays = None

    if config.scatter_pays is not None:
        scatter_pays = {count: multiplier * payout_scale for count, multiplier in config.scatter_pays.items()}

    return SlotConfig(
        reels=config.reels,
        rows=config.rows,
        paylines=config.paylines,
        paytable=paytable,
        wild_symbol=config.wild_symbol,
        scatter_symbol=config.scatter_symbol,
        scatter_pays=scatter_pays,
    )


def shape_volatility(config: SlotConfig, exponent: float) -> SlotConfig:
    if exponent <= 0:
        raise ValueError("volatility exponent must be positive")

    paytable = {
        symbol: {count: multiplier**exponent for count, multiplier in payouts.items()}
        for symbol, payouts in config.paytable.items()
    }
    scatter_pays = None

    if config.scatter_pays is not None:
        scatter_pays = {count: multiplier**exponent for count, multiplier in config.scatter_pays.items()}

    return SlotConfig(
        reels=config.reels,
        rows=config.rows,
        paylines=config.paylines,
        paytable=paytable,
        wild_symbol=config.wild_symbol,
        scatter_symbol=config.scatter_symbol,
        scatter_pays=scatter_pays,
    )


def volatility_exponent(volatility: Optional[float] = None) -> float:
    exponent = float(volatility if volatility is not None else setting("slots", "volatility", 1.0))
    if exponent <= 0:
        raise ValueError("slot volatility must be positive")
    return exponent


def configure_rtp(
    config: SlotConfig,
    target: Optional[float] = None,
    volatility: Optional[float] = None,
    max_combinations: Optional[int] = None,
) -> SlotConfig:
    target = target if target is not None else target_rtp("slots", 0.96)
    shaped_config = shape_volatility(config, volatility_exponent(volatility))
    max_combinations = int(
        max_combinations
        if max_combinations is not None
        else setting("slots", "calibration_max_combinations", 1_000_000)
    )

    base_rtp = exact_rtp(shaped_config, max_combinations=max_combinations)
    if base_rtp <= 0:
        raise ValueError("base RTP must be positive to calibrate slot payouts")

    return scale_payouts(shaped_config, target / base_rtp)


def visible_grid(reels: Sequence[Reel], stops: Sequence[int], rows: int) -> Grid:
    columns = []
    for reel, stop in zip(reels, stops):
        columns.append(tuple(reel[(stop + row) % len(reel)] for row in range(rows)))

    return tuple(tuple(column[row] for column in columns) for row in range(rows))


def evaluate_lines(config: SlotConfig, grid: Grid) -> tuple[LineWin, ...]:
    wins = []
    for payline_index, payline in enumerate(config.paylines):
        symbols = tuple(grid[row][reel_index] for reel_index, row in enumerate(payline))
        win = best_line_win(config, payline_index, payline, symbols)
        if win is not None:
            wins.append(win)
    return tuple(wins)


def best_line_win(
    config: SlotConfig,
    payline_index: int,
    payline: Payline,
    symbols: Sequence[Symbol],
) -> Optional[LineWin]:
    best_win = None

    for pay_symbol, payouts in config.paytable.items():
        if pay_symbol == config.scatter_symbol:
            continue

        count = 0
        for symbol in symbols:
            if symbol == pay_symbol or symbol == config.wild_symbol:
                count += 1
            else:
                break

        multiplier = payouts.get(count)
        if multiplier is None:
            continue

        positions = tuple((payline[reel_index], reel_index) for reel_index in range(count))
        candidate = LineWin(payline_index, pay_symbol, count, multiplier, positions)

        if best_win is None or candidate.multiplier > best_win.multiplier:
            best_win = candidate

    return best_win


def evaluate_scatters(config: SlotConfig, grid: Grid) -> Optional[ScatterWin]:
    if config.scatter_symbol is None or not config.scatter_pays:
        return None

    count = sum(symbol == config.scatter_symbol for row in grid for symbol in row)
    multiplier = config.scatter_pays.get(count)
    if multiplier is None:
        return None

    return ScatterWin(config.scatter_symbol, count, multiplier)


def exact_rtp(config: SlotConfig, max_combinations: int = 1_000_000) -> float:
    """Calculate exact RTP by enumerating every reel-stop combination."""
    validate_config(config)
    combinations = math.prod(len(reel) for reel in config.reels)
    if combinations > max_combinations:
        raise ValueError(f"{combinations} combinations exceeds max_combinations={max_combinations}")

    total_multiplier = 0.0
    stop_ranges = [range(len(reel)) for reel in config.reels]
    for stops in product(*stop_ranges):
        total_multiplier += evaluate_stops(config, stops).total_multiplier

    return total_multiplier / combinations


def sample_rtp(config: SlotConfig, spins: int, server_seed: str, client_seed: str, starting_nonce: int = 0) -> float:
    """Estimate RTP from deterministic provably-fair spins."""
    if spins <= 0:
        raise ValueError("spins must be positive")

    total_multiplier = 0.0
    for offset in range(spins):
        total_multiplier += spin(config, server_seed, client_seed, starting_nonce + offset).total_multiplier

    return total_multiplier / spins
