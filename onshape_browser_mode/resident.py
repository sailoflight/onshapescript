"""Keep one Onshape browser alive across MCP child processes, so the login survives.

Why this module exists
----------------------
Onshape Web has no "stay signed in": signing out is what closing the browser does.
Measured on the real host 2026-09-20, both halves of that statement, at zero Onshape
API quota:

* a graceful ``context.close()`` (the exact call this architecture already made on
  stdin EOF) followed by a read-only navigation without logging in ends on
  ``https://cad.onshape.com/signin``, and no ``onshape_profile`` Edge process remains;
* an abrupt ``Stop-Process -Force`` of every profile process ends on the same page;
* the profile's auth cookies (``.onshape.com on-session-id``, ``cad.onshape.com _u``)
  are session cookies -- ``persistent=0 has_expires=0`` -- so nothing written to disk
  can restore the session; only the ``_ga*``/``aws-waf-token`` cookies have an expiry.

The design note this repository already carried (commit ``e149bdf``,
``tools/windows/README.md``) says the same thing and prescribes the fix: the browser
must be held by a process that outlives the MCP child. Until now each bridge
connection got a fresh MCP child that launched the browser and closed it again on
stdin EOF (``mcp_main/win/mcp/server.py``, from ``9394ad0``), so every bridge restart
cost a human login.

What this module does
---------------------
:func:`start_resident_browser` probes ``http://127.0.0.1:<port>/json/version`` and, only
when nothing answers, spawns Microsoft Edge **detached** with
``--user-data-dir=<profile> --remote-debugging-port=<port>``. ``ResidentChromium`` then
ATTACHES with ``connect_over_cdp`` instead of launching, and hands back the browser's
real default context -- untouched by any proxy, because ``page.context is context`` is a
contract ``browser_common`` enforces when it reconciles pages.

Closing that context is safe, and this is the measurement the whole design rests on.
Live, on ``Edg/153.0.4234.32``, against a browser this module spawned (scratch profile,
port 9334, ``artifacts/cdp_close_probe.py``): ``context.close()`` returned, the DevTools
endpoint was still up, every target (the page and the extension background pages) was
still there, ``browser.is_connected()`` went ``False`` and ``browser.contexts`` went to
``0`` -- the call detached Playwright, it did not end the browser. A second
``connect_over_cdp`` then found 1 context with 1 page again, and ``playwright.stop()``
left the endpoint up as well. Chromium cannot dispose a browser's *default* context, so
on this connection ``close()`` is a detach.

That matters twice over: the login (held in the browser process's session cookies) and
the open document tabs both survive an MCP child's exit, and the adapter can return the
real context instead of a look-alike. What the child must never do is *launch*; only an
explicit ``taskkill`` -- or the human closing the window -- ends the session.

``--remote-allow-origins=*`` is added at spawn time because Chromium 111+ rejects
DevTools websocket connections that carry an ``Origin`` header. The endpoint is bound to
loopback and the profile is local, so this widens nothing beyond the MCP host.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable

from onshape_browser_mode.errors import BrowserLaunchError

DEFAULT_RESIDENT_PORT = 9333
# How long a freshly spawned browser may take to publish its DevTools endpoint.
ENDPOINT_WAIT_S = 30.0
ENDPOINT_POLL_S = 0.25
# One endpoint read is cheap; a hung browser must not hang the caller. Measured on the
# deployment host 2026-09-20: a loopback connect to a *closed* port raises
# ConnectionRefusedError only after ~2.0 s, so a 2 s budget turned a clean refusal into a
# timeout. Anything above that delay reports the real error.
PROBE_TIMEOUT_S = 3.0

_WINDOWS_BROWSER_RELATIVE_PATHS = {
    "msedge.exe": (
        r"Microsoft\Edge\Application\msedge.exe",
        r"Microsoft\Edge Beta\Application\msedge.exe",
        r"Microsoft\Edge Dev\Application\msedge.exe",
    ),
    "chrome.exe": (
        r"Google\Chrome\Application\chrome.exe",
        r"Google\Chrome Beta\Application\chrome.exe",
        r"Google\Chrome Dev\Application\chrome.exe",
    ),
}

_CHANNEL_BINARIES = {
    "msedge": "msedge.exe",
    "msedge-beta": "msedge.exe",
    "msedge-dev": "msedge.exe",
    "msedge-canary": "msedge.exe",
    "chrome": "chrome.exe",
    "chrome-beta": "chrome.exe",
    "chrome-dev": "chrome.exe",
    "chrome-canary": "chrome.exe",
    "chromium": "chrome.exe",
}


def endpoint_url(port: int) -> str:
    """The DevTools HTTP endpoint a resident browser publishes."""
    return f"http://127.0.0.1:{int(port)}/json/version"


_OPENER: urllib.request.OpenerDirector | None = None


def _direct_opener() -> urllib.request.OpenerDirector:
    """An opener that ignores every system/env proxy.

    The DevTools endpoint is loopback-only and must be probed directly. The deployment
    host has a system HTTP proxy configured (v2rayN on 127.0.0.1:10808), and `urlopen`
    honours it by default, so an absent browser shows up as a proxy timeout instead of
    the refusal it is. Cached because `wait_for_endpoint` polls.
    """
    global _OPENER
    if _OPENER is None:
        _OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return _OPENER


def probe_endpoint(port: int, *, timeout_s: float = PROBE_TIMEOUT_S) -> dict[str, Any]:
    """Read the CDP version document. Never raises: an absent browser is a normal state."""
    url = endpoint_url(port)
    try:
        with _direct_opener().open(url, timeout=timeout_s) as response:
            payload = json.loads(response.read().decode("utf-8", "replace"))
    except Exception as exc:  # URLError, timeout, JSON, a refused connect: all "not there"
        return {
            "reachable": False,
            "port": int(port),
            "url": url,
            "error": f"{type(exc).__name__}: {exc}",
        }
    return {
        "reachable": True,
        "port": int(port),
        "url": url,
        "browser": payload.get("Browser", ""),
        "protocolVersion": payload.get("Protocol-Version", ""),
        "webSocketDebuggerUrl": payload.get("webSocketDebuggerUrl", ""),
    }


def wait_for_endpoint(
    port: int,
    *,
    timeout_s: float = ENDPOINT_WAIT_S,
    interval_s: float = ENDPOINT_POLL_S,
    probe: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Poll until the endpoint answers or the budget expires; report which happened."""
    read = probe or probe_endpoint
    started = time.monotonic()
    deadline = started + timeout_s
    while True:
        status = dict(read(port))
        if status.get("reachable") or time.monotonic() >= deadline:
            status["waitedMs"] = int((time.monotonic() - started) * 1000)
            return status
        time.sleep(interval_s)


def resolve_executable(*, channel: str = "", executable_path: str = "") -> str:
    """Locate the browser binary to spawn. ``executable_path`` wins over ``channel``."""
    if executable_path:
        path = Path(executable_path)
        if not path.exists():
            raise BrowserLaunchError(
                f"browser executable_path is set but does not exist: {executable_path}"
            )
        return str(path)

    name = _CHANNEL_BINARIES.get((channel or "").strip().lower(), "")
    if not name:
        candidate = (channel or "").strip()
        if candidate.lower().endswith(".exe"):
            name = candidate
    if not name:
        raise BrowserLaunchError(
            "resident browser mode needs an executable: set browser.channel "
            f"(one of {sorted(_CHANNEL_BINARIES)}) or browser.executable_path. "
            f"Got channel={channel!r}, executable_path={executable_path!r}."
        )

    relative_paths = _WINDOWS_BROWSER_RELATIVE_PATHS.get(name.lower(), ())
    roots = [
        os.environ.get("PROGRAMFILES", r"C:\Program Files"),
        os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
        os.environ.get("LOCALAPPDATA", ""),
    ]
    for root in roots:
        if not root:
            continue
        for relative in relative_paths:
            candidate = Path(root) / relative
            if candidate.exists():
                return str(candidate)
    found = shutil.which(name)
    if found:
        return found
    raise BrowserLaunchError(
        f"could not find {name} for channel={channel!r}. Set browser.executable_path "
        "in onshape_browser_mode/config/browser.local.toml to the exact binary."
    )


def spawn_command(
    *,
    executable: str,
    profile_dir: Path,
    port: int,
    proxy_server: str = "",
    locale: str = "",
    window_size: str = "",
) -> list[str]:
    """The exact detached-browser argv. Documented and asserted, never assembled inline."""
    command = [
        str(executable),
        f"--user-data-dir={profile_dir}",
        f"--remote-debugging-port={int(port)}",
        # Chromium 111+ refuses DevTools websockets that carry an Origin header.
        "--remote-allow-origins=*",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    if proxy_server:
        command.append(f"--proxy-server={proxy_server}")
    if locale:
        command.append(f"--lang={locale}")
    if window_size:
        command.append(f"--window-size={window_size}")
    command.append("about:blank")
    return command


def _popen_detached(command: list[str]) -> dict[str, Any]:
    """Start the browser so that it outlives this process and this MCP connection."""
    kwargs: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
    else:
        kwargs["start_new_session"] = True
    process = subprocess.Popen(command, **kwargs)
    return {"pid": process.pid, "command": list(command)}


def start_resident_browser(
    *,
    profile_dir: Path,
    port: int = DEFAULT_RESIDENT_PORT,
    channel: str = "",
    executable_path: str = "",
    proxy_server: str = "",
    locale: str = "",
    window_size: str = "",
    probe: Callable[..., dict[str, Any]] | None = None,
    wait: Callable[..., dict[str, Any]] | None = None,
    spawn: Callable[[list[str]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Ensure a resident browser and return the provenance of how it came to exist.

    ``alreadyRunning`` means the endpoint answered and nothing was spawned: a previous
    MCP child's browser -- login included -- is still there.
    """
    read = probe or probe_endpoint
    poll = wait or wait_for_endpoint
    launch = spawn or _popen_detached

    status = dict(read(port))
    if status.get("reachable"):
        return {"action": "attached", "alreadyRunning": True, "endpoint": status}

    executable = resolve_executable(channel=channel, executable_path=executable_path)
    command = spawn_command(
        executable=executable,
        profile_dir=profile_dir,
        port=port,
        proxy_server=proxy_server,
        locale=locale,
        window_size=window_size,
    )
    spawned = launch(command)
    status = poll(port)
    if not status.get("reachable"):
        raise BrowserLaunchError(
            f"spawned the resident browser but its DevTools endpoint never answered: "
            f"{endpoint_url(port)} ({status.get('error', 'no error reported')}). "
            f"Profile: {profile_dir}. If another Edge/Chrome process already owns that "
            "profile without --remote-debugging-port, the spawn is handed to it and the "
            "endpoint never appears; close that browser (it costs one login) or point "
            "user_data_dir at a free profile."
        )
    return {
        "action": "spawned",
        "alreadyRunning": False,
        "endpoint": status,
        "executable": executable,
        "pid": spawned.get("pid"),
        "command": command,
    }


class ResidentChromium:
    """Drop-in for ``playwright.chromium`` that attaches instead of launching.

    The call signature matches ``BrowserType.launch_persistent_context``, but the
    persistent-context options are consumed here, at spawn time, rather than by
    Playwright: ``user_data_dir`` picks the profile the endpoint must belong to,
    ``channel``/``executable_path`` pick the binary to spawn, ``proxy_server``/``locale``
    become browser argv, and ``viewport`` becomes the spawn window size. ``headless`` and
    ``timezone_id`` have no attached-browser equivalent and are reported as
    ``notApplied`` instead of being silently ignored -- resident mode is for the headed,
    human-watched session.

    The returned context is the browser's own default context, not a wrapper: closing a
    context this adapter attached to detaches the connection and leaves the browser, its
    tabs and its login alone (measured; see the module docstring).
    """

    def __init__(
        self,
        chromium: Any,
        *,
        profile_dir: Path,
        port: int = DEFAULT_RESIDENT_PORT,
        channel: str = "",
        executable_path: str = "",
        proxy_server: str = "",
        locale: str = "",
        probe: Callable[..., dict[str, Any]] | None = None,
        wait: Callable[..., dict[str, Any]] | None = None,
        spawn: Callable[[list[str]], dict[str, Any]] | None = None,
    ) -> None:
        self._chromium = chromium
        self._profile_dir = Path(profile_dir)
        self._port = int(port)
        self._channel = channel
        self._executable_path = executable_path
        self._proxy_server = proxy_server
        self._locale = locale
        self._probe = probe or probe_endpoint
        self._wait = wait or wait_for_endpoint
        self._spawn = spawn or _popen_detached
        # Provenance of every attach, for status reporting and for tests.
        self.starts: list[dict[str, Any]] = []

    def launch_persistent_context(self, *args: Any, **kwargs: Any) -> Any:
        profile_dir = Path(kwargs.get("user_data_dir") or self._profile_dir)
        bootstrap = start_resident_browser(
            profile_dir=profile_dir,
            port=self._port,
            channel=self._channel or kwargs.get("channel", ""),
            executable_path=self._executable_path or kwargs.get("executable_path", ""),
            proxy_server=self._proxy_server,
            locale=self._locale,
            window_size=self._window_size(kwargs.get("viewport")),
            probe=self._probe,
            wait=self._wait,
            spawn=self._spawn,
        )
        browser = self._chromium.connect_over_cdp(endpoint_url(self._port))
        contexts = list(browser.contexts)
        if not contexts:
            raise BrowserLaunchError(
                f"the resident browser at {endpoint_url(self._port)} exposed no default "
                "context; refusing to create a second one, because a new context would "
                "not be the profile that holds the login. Close the browser and let this "
                "module spawn a fresh one."
            )
        context = contexts[0]
        record = dict(bootstrap)
        record.update(
            {
                "contexts": len(contexts),
                "pages": len(list(context.pages)),
                "notApplied": {
                    key: kwargs[key]
                    for key in ("headless", "timezone_id")
                    if key in kwargs
                },
            }
        )
        self.starts.append(record)
        return context

    @staticmethod
    def _window_size(viewport: Any) -> str:
        """Map the configured page viewport onto the spawn window size.

        An attached page's viewport is not Playwright's to set without reaching into
        pages this process does not own, so the configured size is applied to the window
        the browser is spawned with; the page viewport then differs by the browser
        chrome. Reported here rather than approximated silently.
        """
        if isinstance(viewport, dict) and viewport.get("width") and viewport.get("height"):
            return f"{int(viewport['width'])},{int(viewport['height'])}"
        return ""


class _ResidentManager:
    """What a Playwright factory returns: ``start()`` -> driver, ``__exit__`` -> stop."""

    def __init__(self, chromium_options: dict[str, Any]) -> None:
        self._options = dict(chromium_options)
        self._manager: Any = None
        self._driver: _ResidentDriver | None = None

    def start(self) -> "_ResidentDriver":
        from playwright.sync_api import sync_playwright

        self._manager = sync_playwright()
        playwright = self._manager.start()
        self._driver = _ResidentDriver(
            self, playwright, ResidentChromium(playwright.chromium, **self._options)
        )
        return self._driver

    def stop(self) -> None:
        """Release Playwright. Detaching never closes the resident browser."""
        manager, self._manager = self._manager, None
        self._driver = None
        if manager is not None:
            manager.__exit__(None, None, None)

    def __exit__(self, *exc: Any) -> bool:
        self.stop()
        return False


class _ResidentDriver:
    """The object ``browser_common`` treats as the Playwright driver."""

    def __init__(self, manager: _ResidentManager, playwright: Any, chromium: ResidentChromium) -> None:
        self._manager = manager
        self.playwright = playwright
        self.chromium = chromium

    def stop(self) -> None:
        self._manager.stop()


def resident_playwright_factory(**chromium_options: Any) -> Callable[[], _ResidentManager]:
    """Build the ``playwright_factory`` that ``browser_common.SyncSession`` accepts."""
    options = dict(chromium_options)

    def factory() -> _ResidentManager:
        return _ResidentManager(options)

    return factory
