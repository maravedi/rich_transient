"""Reusable Rich-based braille spinner, transient live panel, and CLI styling for output.

This package can be used by any project that needs:
- A braille-style status spinner (accessible, compact)
- A transient live panel that streams output and clears on exit
- Consistent section headers, separators, and key-value panels (Rule + Panel)

Dependencies: rich
"""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, fields, replace
from types import SimpleNamespace
from typing import Callable, Literal, Sequence, TypeVar

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text
from rich.theme import Theme

T = TypeVar("T")

# --- Semantic style names (raw colors; use with Rule/Panel when not using a theme) ---
STYLE_SECTION: str = "blue"
STYLE_SUCCESS: str = "green"
STYLE_WARNING: str = "yellow"
STYLE_DIM: str = "dim"

# --- Theme style keys: use these with Console(theme=get_theme(...)) then style="section" etc. ---
THEME_STYLE_SECTION: str = "section"
THEME_STYLE_SUCCESS: str = "success"
THEME_STYLE_WARNING: str = "warning"
THEME_STYLE_DIM: str = "dim"

# --- Built-in themes (same keys, different palettes); use with Console(theme=get_theme("name")) ---
THEMES: dict[str, Theme] = {
    "default": Theme({
        THEME_STYLE_SECTION: "blue",
        THEME_STYLE_SUCCESS: "green",
        THEME_STYLE_WARNING: "yellow",
        THEME_STYLE_DIM: "dim",
    }),
    "ngate": Theme({
        THEME_STYLE_SECTION: "blue",
        THEME_STYLE_SUCCESS: "green",
        THEME_STYLE_WARNING: "yellow",
        THEME_STYLE_DIM: "dim",
    }),
    "muted": Theme({
        THEME_STYLE_SECTION: "dim blue",
        THEME_STYLE_SUCCESS: "dim green",
        THEME_STYLE_WARNING: "dim yellow",
        THEME_STYLE_DIM: "dim",
    }),
    "high_contrast": Theme({
        THEME_STYLE_SECTION: "bold bright_blue",
        THEME_STYLE_SUCCESS: "bold bright_green",
        THEME_STYLE_WARNING: "bold bright_yellow",
        THEME_STYLE_DIM: "dim",
    }),
    "mono": Theme({
        THEME_STYLE_SECTION: "bold",
        THEME_STYLE_SUCCESS: "bold",
        THEME_STYLE_WARNING: "italic",
        THEME_STYLE_DIM: "dim",
    }),
    "nord": Theme({
        THEME_STYLE_SECTION: "#5e81ac",
        THEME_STYLE_SUCCESS: "#a3be8c",
        THEME_STYLE_WARNING: "#ebcb8b",
        THEME_STYLE_DIM: "dim",
    }),
    "dracula": Theme({
        THEME_STYLE_SECTION: "#bd93f9",
        THEME_STYLE_SUCCESS: "#50fa7b",
        THEME_STYLE_WARNING: "#f1fa8c",
        THEME_STYLE_DIM: "dim",
    }),
}


def get_theme(name: str) -> Theme:
    """Return a built-in theme by name. Use with Console(theme=get_theme(\"muted\")).

    Available names: default, ngate, muted, high_contrast, mono, nord, dracula.
    Falls back to \"default\" if name is unknown.
    """
    return THEMES.get(name, THEMES["default"])


def themed_console(theme_name: str = "default", **console_kwargs: object) -> Console:
    """Return a Console using a built-in theme. Use theme style names in helpers (e.g. style=\"section\").

    Example:
        console = themed_console(\"muted\")
        console.print(section_rule(\"Fetch complete\", style=\"section\"))
        console.print(key_value_panel([...], border_style=\"success\"))
    """
    return Console(theme=get_theme(theme_name), **console_kwargs)

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


# --- CLI styling helpers (section rules, key-value panels) ---


def section_rule(
    title: str,
    *,
    style: str = STYLE_SECTION,
) -> Rule:
    """Return a Rule with a bold section title (e.g. for command headers or stage labels).

    Example:
        console.print(section_rule("FETCH (THE FEED)"))
        console.print(section_rule("Finding top source categories", style=STYLE_SECTION))
    """
    return Rule(f"[bold {style}]{title}[/]", style=style)


def dim_rule() -> Rule:
    """Return a dim Rule for a subtle separator between sections."""
    return Rule(style=STYLE_DIM)


def key_value_panel(
    lines: Sequence[tuple[str, str | None]] | Sequence[str],
    *,
    title: str | None = None,
    border_style: str = STYLE_SECTION,
    padding: tuple[int, int] = (0, 1),
    label_markup: str = "[bold]",
    skip_none: bool = True,
) -> Panel:
    """Build a Panel from key-value pairs or preformatted lines.

    Args:
        lines: Either (label, value) pairs (values shown as plain; use markup in label)
               or a sequence of already-marked-up line strings.
        title: Optional panel title (e.g. "[bold blue]Top source[/]").
        border_style: Panel border color (STYLE_SECTION, STYLE_SUCCESS, etc.).
        padding: Panel padding (default (0, 1) for compact layout).
        label_markup: Markup for labels when lines are (label, value) pairs.
        skip_none: When True, omit pairs whose value is None.

    Example (key-value pairs):
        key_value_panel([
            ("Backend", "sumologic"),
            ("Hours Back", "24"),
            ("Limit", "10000"),
        ], title="[bold blue]Run settings[/]")

    Example (preformatted lines):
        key_value_panel([
            "  [bold]Size[/]  [white]1,234[/]",
            "  [bold]Rate[/]  [cyan]0.5 GB/hour[/]",
        ], border_style=STYLE_SUCCESS)
    """
    if not lines:
        content = ""
    elif isinstance(lines[0], str):
        content = "\n".join(lines)
    else:
        parts = []
        for item in lines:
            label, value = item[0], item[1]
            if skip_none and value is None:
                continue
            parts.append(f"  {label_markup}{label}:[/] {value}")
        content = "\n".join(parts)
    return Panel(
        content,
        title=title,
        border_style=border_style,
        padding=padding,
    )


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
    "STYLE_DIM",
    "STYLE_SECTION",
    "STYLE_SUCCESS",
    "STYLE_WARNING",
    "THEMES",
    "THEME_STYLE_DIM",
    "THEME_STYLE_SECTION",
    "THEME_STYLE_SUCCESS",
    "THEME_STYLE_WARNING",
    "TransientPanelConfig",
    "TRANSIENT_PANEL_PRESETS",
    "braille_spinner_for_status",
    "dim_rule",
    "get_braille_frame",
    "get_theme",
    "key_value_panel",
    "register_braille_spinner",
    "section_rule",
    "themed_console",
    "transient_live_panel",
]
