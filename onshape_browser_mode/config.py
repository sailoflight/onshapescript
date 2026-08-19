"""Typed loader for the browser-automation configuration.

Reads `config/browser.toml` (committed defaults) and merges the optional
gitignored `config/browser.local.toml` on top. The MCP server core does not
import this module at startup; only browser_* handlers load it lazily.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = ROOT / "config" / "browser.toml"
LOCAL_CONFIG_PATH = ROOT / "config" / "browser.local.toml"


@dataclass(frozen=True)
class BrowserCfg:
    channel: str = "chrome"
    executable_path: str = ""
    user_data_dir: str = "./user_data/onshape_profile"
    locale: str = "en-US"
    timezone: str = "America/New_York"
    headless: bool = False


@dataclass(frozen=True)
class PacingCfg:
    min_delay_s: float = 0.8
    max_delay_s: float = 2.0
    scroll_steps: int = 3
    max_actions_per_minute: int = 8


@dataclass(frozen=True)
class ClickCfg:
    enabled: bool = True
    path_steps_min: int = 2
    path_steps_max: int = 5
    move_pause_min: float = 0.01
    move_pause_max: float = 0.04
    hover_pause_min: float = 0.03
    hover_pause_max: float = 0.08
    hold_min: float = 0.03
    hold_max: float = 0.08
    jitter_px: float = 2.0
    off_center: float = 0.12


@dataclass(frozen=True)
class ListenerCfg:
    enabled: bool = True
    record_dom_snippets: bool = True
    record_network: bool = True
    snippet_max_chars: int = 240
    default_watch_seconds: int = 180
    output_dir: str = "./dev/watch-sessions"


@dataclass(frozen=True)
class BrowserConfig:
    browser: BrowserCfg
    pacing: PacingCfg
    click: ClickCfg
    listener: ListenerCfg



def _section_data(data: dict, name: str) -> dict:
    value = data.get(name, {})
    return value if isinstance(value, dict) else {}


def _filter(cls, data: dict) -> dict:
    allowed = cls.__dataclass_fields__.keys()
    return {k: v for k, v in data.items() if k in allowed}


def load_browser_config(path: str | Path | None = None) -> BrowserConfig:
    """Load the merged browser config; local overrides win over defaults.

    Re-reads the files when their mtimes change so a long-running MCP server can
    pick up config edits without restarting. Missing files simply fall back to
    the dataclass defaults.
    """
    main_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    local_path = LOCAL_CONFIG_PATH

    data: dict = {}
    for config_path in (main_path, local_path):
        if config_path.is_file():
            with config_path.open("rb") as stream:
                parsed = tomllib.load(stream)
            for section, values in parsed.items():
                if isinstance(values, dict):
                    data.setdefault(section, {}).update(values)

    return BrowserConfig(
        browser=BrowserCfg(**_filter(BrowserCfg, _section_data(data, "browser"))),
        pacing=PacingCfg(**_filter(PacingCfg, _section_data(data, "pacing"))),
        click=ClickCfg(**_filter(ClickCfg, _section_data(data, "click"))),
        listener=ListenerCfg(**_filter(ListenerCfg, _section_data(data, "listener"))),
    )
