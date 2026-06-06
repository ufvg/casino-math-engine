from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


CONFIG_PATH = Path(__file__).with_name("game_config.json")


@lru_cache(maxsize=1)
def load_game_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}

    with CONFIG_PATH.open("r", encoding="utf-8") as config_file:
        return json.load(config_file)


def reload_game_config() -> dict[str, Any]:
    load_game_config.cache_clear()
    return load_game_config()


def game_settings(game: str) -> dict[str, Any]:
    settings = load_game_config().get(game, {})
    if not isinstance(settings, dict):
        raise ValueError(f"{game} settings must be an object")
    return settings


def setting(game: str, key: str, default: Any) -> Any:
    return game_settings(game).get(key, default)


def target_rtp(game: str, default: float) -> float:
    value = float(setting(game, "target_rtp", default))
    if value <= 0 or value > 1:
        raise ValueError(f"{game} target_rtp must be between 0 and 1")
    return value
