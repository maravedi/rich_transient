"""Reusable Rich-based braille spinner and transient live panel for CLI output.

This package can be used by any project that needs:
- A braille-style status spinner (accessible, compact)
- A transient live panel that streams output and clears on exit

Dependencies: rich
"""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, fields, replace
from types import SimpleNamespace
from typing import Callable, Literal, TypeVar

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

T = TypeVar("T")

# Braille spinner frames (one per refresh) so the status line visibly animates.
SPINNER_BRAILLE: tuple[str, ...] = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")

# Shared refresh rate for Live displays (transient panel and other live UIs).
LIVE_REFRESH_PER_SECOND: float = 8.0


def get_braille_frame() -> int:
    """Return the current animation frame index for the braille spinner (0 to len(SPINNER_BRAILLE)-1).

    Use with SPINNER_BRAILLE[get_braille_frame()] when building custom live UIs (e.g. tables, status lines).
    """
    return int(time.monotonic() * LIVE_REFRESH_PER_SECOND) % len(SPINNER_BRAILLE)


# Name under which we register the braille spinner in Rich's SPINNERS dict.
_BRAILLE_SPINNER_NAME = "braille"


def register_braille_spinner() -> None:
    """Register the braille spinner with Rich so console.status(..., spinner='braille') works.

    Idempotent; safe to call multiple times. Call once at startup or rely on braille_spinner_for_status().
    """
    try:
        from rich import _spinners

        _spinners.SPINNERS[_BRAILLE_SPINNER_NAME] = {
            "frames": list(SPINNER_BRAILLE),
            "interval": 1000.0 / LIVE_REFRESH_PER_SECOND,
        }
    except (ImportError, AttributeError):
        pass


def braille_spinner_for_status() -> str:
    """Return the Rich spinner name 'braille' for use with console.status(spinner=...).

    Registers the braille frames with Rich on first use, then returns the name so Status
    can look it up. Rich's Status expects a spinner name (str), not a Spinner instance.

    Example:
        with console.status("Loading...", spinner=braille_spinner_for_status()):
            do_work()
    """
    register_braille_spinner()
    return _BRAILLE_SPINNER_NAME


@dataclass(frozen=True)
class TransientPanelConfig:
    """Configuration for transient live panels. Use presets via transient_live_panel(..., preset='streaming')."""

    max_lines: int = 100
    display_lines: int = 24
    refresh_per_second: float = LIVE_REFRESH_PER_SECOND
    default_status: str = "Running"
    reserve_lines: int = 12  # Space for title, borders, padding, subtitle
    border_style: str = "dim"
    padding: tuple[int, int] = (0, 1)


# Presets for consistent behavior across commands.
TRANSIENT_PANEL_PRESETS: dict[str, TransientPanelConfig] = {
    "default": TransientPanelConfig(),
    "streaming": TransientPanelConfig(
        max_lines=200,
        display_lines=28,
        default_status="Running",
    ),
}


def _resolve_panel_config(
    preset: Literal["default", "streaming"] | None = None,
    config: TransientPanelConfig | None = None,
    **overrides: object,
) -> TransientPanelConfig:
    """Resolve config from preset, optional explicit config, and overrides."""
    base = config or TRANSIENT_PANEL_PRESETS.get(preset or "default") or TRANSIENT_PANEL_PRESETS["default"]
    valid_names = {f.name for f in fields(TransientPanelConfig)}
    clean = {k: v for k, v in overrides.items() if k in valid_names and v is not None}
    if not clean:
        return base
    return replace(base, **clean)


@contextmanager
def transient_live_panel(
    title: str,
    preset: Literal["default", "streaming"] = "default",
    config: TransientPanelConfig | None = None,
    *,
    max_lines: int | None = None,
    display_lines: int | None = None,
    border_style: str | None = None,
    console: Console | None = None,
):
    """Context manager that shows streaming output in a live panel; panel is cleared on exit.

    Use for verbose subprocess output: output streams into the panel while the task runs,
    then the panel is removed so only the high-level success/failure line remains.

    Presets:
      - "default": Short steps. max_lines=100, display_lines=24.
      - "streaming": Long tool output. max_lines=200, display_lines=28.

    Optional kwargs override the preset (e.g. display_lines=30).
    Pass console= to use a specific Rich Console (e.g. with custom theme).

    Yields an object with:
      - append(line: str) -> None
      - set_status(text: str) -> None   -- update the status line (e.g. "Downloading X...")
      - run_task(task_callable: Callable[[], T]) -> T
    """
    target_console = console if console is not None else Console()
    cfg = _resolve_panel_config(
        preset=preset,
        config=config,
        max_lines=max_lines,
        display_lines=display_lines,
        border_style=border_style,
    )
    lines_list: list[str] = []
    current_status: list[str] = [cfg.default_status]
    lock = threading.Lock()
    result_holder: list = []
    try:
        console_height = target_console.size.height
    except Exception:
        console_height = 30
    tail = min(cfg.display_lines, max(1, console_height - cfg.reserve_lines))

    def append(line: str) -> None:
        with lock:
            lines_list.append(line)

    def set_status(text: str) -> None:
        with lock:
            current_status[0] = text

    def render() -> Panel:
        with lock:
            recent = lines_list[-cfg.max_lines:] if len(lines_list) > cfg.max_lines else lines_list
            visible = recent[-tail:] if len(recent) > tail else recent
            content = "\n".join(visible)
            status_text = current_status[0]
        if content:
            try:
                streamed = Text.from_markup(content)
            except Exception:
                streamed = Text(content)
        else:
            streamed = Text("")
        frame_idx = get_braille_frame()
        status_line = Text(f" {SPINNER_BRAILLE[frame_idx]} {status_text}", style="dim")
        return Panel(
            streamed,
            title=title,
            subtitle=status_line,
            border_style=cfg.border_style,
            padding=cfg.padding,
            expand=True,
        )

    def run_task(task_callable: Callable[[], T]) -> T:
        result_holder.clear()
        exc_holder: list[BaseException | None] = [None]

        def run() -> None:
            try:
                result_holder.append(task_callable())
            except BaseException as e:
                exc_holder[0] = e

        th = threading.Thread(target=run)
        th.start()
        with Live(
            render(),
            refresh_per_second=cfg.refresh_per_second,
            transient=True,
            console=target_console,
        ) as live:
            while th.is_alive():
                live.update(render())
                time.sleep(0.05)
            live.update(render())
        th.join()
        if exc_holder[0] is not None:
            raise exc_holder[0]
        return result_holder[0]

    yield SimpleNamespace(append=append, set_status=set_status, run_task=run_task)


__all__ = [
    "SPINNER_BRAILLE",
    "LIVE_REFRESH_PER_SECOND",
    "TransientPanelConfig",
    "TRANSIENT_PANEL_PRESETS",
    "braille_spinner_for_status",
    "get_braille_frame",
    "register_braille_spinner",
    "transient_live_panel",
]
