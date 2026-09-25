"""Typed loader for the browser-automation configuration.

Reads the module-owned `config/browser.toml` defaults and merges the optional
gitignored `config/browser.local.toml` on top. The MCP server core does not
import this module at startup; only browser_* handlers load it lazily.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parent
CONFIG_DIR = MODULE_ROOT / "config"
DEFAULT_CONFIG_PATH = CONFIG_DIR / "browser.toml"
LOCAL_CONFIG_PATH = CONFIG_DIR / "browser.local.toml"


@dataclass(frozen=True)
class BrowserCfg:
    channel: str = "chrome"
    executable_path: str = ""
    user_data_dir: str = "user_data/onshape_profile"
    locale: str = "en-US"
    timezone: str = "America/New_York"
    headless: bool = False
    proxy_server: str = ""  # e.g. "http://127.0.0.1:10808"; empty = no explicit proxy
    # Resident mode: keep ONE browser alive across MCP child processes so the Onshape
    # login survives a bridge restart. Onshape auth cookies are session cookies, so a
    # browser death costs a human login; see onshape_browser_mode/resident.py.
    resident: bool = False
    resident_port: int = 9333  # loopback DevTools endpoint of the resident browser
    # Isolation: optional SEPARATE profile directory, used instead of `user_data_dir`
    # when non-empty. Trade-off, stated plainly: the shared persistent profile keeps
    # the Onshape login across MCP restarts (that is why `user_data_dir` exists at
    # all), while a separate or throwaway directory starts anonymous and costs one
    # human sign-in per fresh directory. Empty (the default) leaves every existing
    # deployment on exactly the profile it used before.
    #
    # This is only a directory choice. `--guest` semantics are NOT implemented and
    # must not be inferred from this flag: the recon marked Edge's guest behaviour
    # UNKNOWN, so guest mode is deliberately not invented here.
    isolated_user_data_dir: str = ""


@dataclass(frozen=True)
class PacingCfg:
    min_delay_s: float = 0.8
    max_delay_s: float = 2.0
    max_actions_per_minute: int = 8


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
        listener=ListenerCfg(**_filter(ListenerCfg, _section_data(data, "listener"))),
    )
