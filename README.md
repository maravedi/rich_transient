# rich_transient

Reusable [Rich](https://github.com/Textualize/rich)-based **braille spinner** and **transient live panel** for CLI output. Use it to show streaming subprocess or task output in a live-updating panel that disappears when the task finishes, with an animated status line.

**Requires:** Python 3.11+, `rich>=13.7.1`

---

## Installation

**Standalone (from this repo):**
```bash
pip install -e /path/to/AutoIaC/rich_transient
```

**As part of AutoIaC:**
```bash
pip install -e /path/to/AutoIaC
# installs both auto_iac and rich_transient
```

---

## Quick start: transient live panel

Wrap a long-running task so its output streams into a live panel; when the task ends, the panel is cleared (transient) and only your final message remains.

```python
from rich_transient import transient_live_panel

with transient_live_panel("Installing dependencies") as panel:
    def do_work():
        # Simulate streaming output
        for i in range(20):
            print(f"Step {i + 1}/20...")
        return "done"

    result = panel.run_task(do_work)

print(f"Result: {result}")
```

The panel shows a scrolling tail of output and an animated braille spinner in the status line; when `run_task` returns, the panel is removed.

---

## Using the panel API

The context manager yields an object with three methods:

| Method | Description |
|--------|-------------|
| `panel.append(line: str)` | Add a line to the panel content (e.g. from a subprocess stdout). |
| `panel.set_status(text: str)` | Update the status line shown next to the spinner (e.g. "Downloading X..."). |
| `panel.run_task(callable)` | Run a callable in a background thread; the panel refreshes until it completes. Returns the callable's return value; re-raises any exception. |

**Streaming subprocess output into the panel:**

```python
import subprocess
from rich_transient import transient_live_panel

with transient_live_panel("Running tests") as panel:
    def run():
        proc = subprocess.Popen(
            ["pytest", "-v"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        for line in proc.stdout:
            panel.append(line.rstrip())
        proc.wait()
        return proc.returncode

    exit_code = panel.run_task(run)
print(f"Tests exited with code {exit_code}")
```

**Updating the status line:**

```python
with transient_live_panel("Building") as panel:
    def build():
        panel.set_status("Compiling...")
        # do compile
        panel.set_status("Linking...")
        # do link
        return 0

    panel.run_task(build)
```

---

## Braille spinner

Use the spinner frames for your own live UI (e.g. a custom table or status line).

**With Rich `console.status()`** — use the built-in braille spinner so the whole app shares one style:

```python
from rich.console import Console
from rich_transient import braille_spinner_for_status

console = Console()

with console.status("Loading state...", spinner=braille_spinner_for_status()) as status:
    do_work()
    status.update("Almost done...")
```

**Custom live UI** — use `get_braille_frame()` so you don't duplicate the frame math:

```python
import time
from rich.console import Console
from rich.live import Live
from rich_transient import SPINNER_BRAILLE, LIVE_REFRESH_PER_SECOND, get_braille_frame

console = Console()

def make_status():
    frame = get_braille_frame()
    return f"{SPINNER_BRAILLE[frame]} Working..."

with Live(make_status(), refresh_per_second=LIVE_REFRESH_PER_SECOND, console=console) as live:
    for _ in range(20):
        time.sleep(0.1)
        live.update(make_status())
```

**Exports:**

- `SPINNER_BRAILLE` — tuple of 10 braille characters for animation frames.
- `LIVE_REFRESH_PER_SECOND` — default refresh rate (8.0) for live displays.
- `get_braille_frame()` — current animation frame index (use with `SPINNER_BRAILLE[i]`).
- `braille_spinner_for_status()` — Registers the braille spinner with Rich and returns the name `"braille"` for `console.status(spinner=...)`.
- `register_braille_spinner()` — Idempotent registration of the braille spinner in Rich's SPINNERS dict (called automatically by `braille_spinner_for_status()`).

---

## Presets and options

**Presets** control buffer size and visible lines:

- `preset="default"` — max_lines=100, display_lines=24 (short steps).
- `preset="streaming"` — max_lines=200, display_lines=28 (long streaming output).

Override per call:

```python
with transient_live_panel(
    "Long log",
    preset="streaming",
    max_lines=500,
    display_lines=40,
) as panel:
    panel.run_task(my_task)
```

**Custom Rich theme:** pass a `Console` so the panel uses your theme:

```python
from rich.console import Console
from rich.theme import Theme
from rich_transient import transient_live_panel

my_theme = Theme({"info": "cyan", "success": "green"})
console = Console(theme=my_theme)

with transient_live_panel("Task", console=console) as panel:
    panel.run_task(my_task)
```

---

## Configuration

For full control, use `TransientPanelConfig` and `TRANSIENT_PANEL_PRESETS`:

```python
from rich_transient import (
    TransientPanelConfig,
    TRANSIENT_PANEL_PRESETS,
    transient_live_panel,
)

# Use a built-in preset
cfg = TRANSIENT_PANEL_PRESETS["streaming"]

# Or build your own
custom = TransientPanelConfig(
    max_lines=300,
    display_lines=30,
    default_status="Processing...",
    border_style="blue",
)

with transient_live_panel("Custom", config=custom) as panel:
    panel.run_task(my_task)
```

---

## CLI styling helpers (section rules and key-value panels)

For consistent command headers and summary blocks (e.g. run settings, completion messages), use semantic style constants and helpers so all commands share the same look.

**Semantic style constants** (use with `border_style=` or `style=`):

- `STYLE_SECTION` — `"blue"` (section headers, info panels)
- `STYLE_SUCCESS` — `"green"` (completion, success panels)
- `STYLE_WARNING` — `"yellow"` (warnings)
- `STYLE_DIM` — `"dim"` (separators)

**Section header (Rule):**

```python
from rich.console import Console
from rich_transient import section_rule, dim_rule, STYLE_SUCCESS

console = Console()

console.print(section_rule("FETCH (THE FEED)"))
# ... content ...
console.print(dim_rule())

console.print(section_rule("Fetch complete", style=STYLE_SUCCESS))
```

**Key-value panel** (static summary box with consistent padding and border):

```python
from rich_transient import key_value_panel, STYLE_SECTION, STYLE_SUCCESS

# From (label, value) pairs
console.print(key_value_panel([
    ("Backend", "sumologic"),
    ("Hours Back", "24"),
    ("Limit", "10000"),
], title="[bold blue]Run settings[/]", border_style=STYLE_SECTION))

# Preformatted lines (full markup control)
console.print(key_value_panel([
    "  [bold]Logs saved to:[/] [cyan]/path/to/logs[/]",
    "  [bold]Next steps:[/]",
    "    [dim]# Run analysis:[/]",
    "    [cyan]ngate analyze /path/to/logs/[/]",
], border_style=STYLE_SUCCESS))
```

Use these with `transient_live_panel` so that after the transient panel clears, your final summary uses the same `STYLE_SUCCESS` and `key_value_panel` for a consistent “done” block.

---

## Themes

The module provides **themes** so you can keep the same semantic roles (section, success, warning, dim) but switch palettes. Use a themed console and pass **theme style names** (`"section"`, `"success"`, `"warning"`, `"dim"`) to `section_rule`, `key_value_panel`, and `Panel`/`Rule`; the theme maps those names to colors.

**Built-in themes:**

| Theme name       | Description |
|------------------|-------------|
| `default` / `ngate` | Blue sections, green success, yellow warning (current nGate-style). |
| `muted`          | Softer dim blue/green/yellow; good for low-contrast terminals. |
| `high_contrast`  | Bold bright blue/green/yellow for accessibility. |
| `mono`           | No color: bold for section/success, italic for warning, dim for separator. |
| `nord`           | [Nord](https://www.nordtheme.com/) palette (blue, green, yellow). |
| `dracula`        | [Dracula](https://draculatheme.com/) palette (purple, green, yellow). |

**Using a theme:**

```python
from rich_transient import (
    themed_console,
    get_theme,
    section_rule,
    key_value_panel,
    THEME_STYLE_SECTION,
    THEME_STYLE_SUCCESS,
)

# Option 1: themed_console (one-liner)
console = themed_console("muted")
console.print(section_rule("Fetch complete", style=THEME_STYLE_SECTION))
console.print(key_value_panel([("Output", "/path/to/logs")], border_style=THEME_STYLE_SUCCESS))

# Option 2: get_theme with your own Console
from rich.console import Console
console = Console(theme=get_theme("nord"))
console.print(section_rule("Running", style="section"))
```

**Theme style name constants:** `THEME_STYLE_SECTION`, `THEME_STYLE_SUCCESS`, `THEME_STYLE_WARNING`, `THEME_STYLE_DIM` — use these (or the strings `"section"`, `"success"`, etc.) when printing with a themed console so the theme supplies the actual color.

**Without a theme:** you can still pass raw colors to the helpers, e.g. `section_rule("Title", style=STYLE_SECTION)` (or `style="blue"`). That works with any Console.

---

## API summary

| Export | Type | Description |
|--------|------|-------------|
| `SPINNER_BRAILLE` | `tuple[str, ...]` | Braille spinner frames. |
| `LIVE_REFRESH_PER_SECOND` | `float` | Default refresh rate for live displays. |
| `STYLE_SECTION` | `str` | `"blue"` for section headers and info panels. |
| `STYLE_SUCCESS` | `str` | `"green"` for completion/success. |
| `STYLE_WARNING` | `str` | `"yellow"` for warnings. |
| `STYLE_DIM` | `str` | `"dim"` for separators. |
| `THEMES` | `dict[str, Theme]` | Built-in themes: default, ngate, muted, high_contrast, mono, nord, dracula. |
| `THEME_STYLE_SECTION` | `str` | Theme key `"section"` for section headers/panels. |
| `THEME_STYLE_SUCCESS` | `str` | Theme key `"success"` for completion/success. |
| `THEME_STYLE_WARNING` | `str` | Theme key `"warning"` for warnings. |
| `THEME_STYLE_DIM` | `str` | Theme key `"dim"` for separators. |
| `get_theme(name)` | `(str) -> Theme` | Return a built-in theme by name. |
| `themed_console(theme_name, **kwargs)` | `() -> Console` | Console using a built-in theme. |
| `get_braille_frame()` | `() -> int` | Current animation frame index for use with `SPINNER_BRAILLE`. |
| `braille_spinner_for_status()` | `() -> str` | Registers braille spinner with Rich and returns `"braille"` for `console.status(spinner=...)`. |
| `register_braille_spinner()` | `() -> None` | Idempotent registration of braille spinner in Rich's SPINNERS. |
| `section_rule(title, style=...)` | `() -> Rule` | Rule with bold section title. |
| `dim_rule()` | `() -> Rule` | Dim Rule separator. |
| `key_value_panel(lines, ...)` | `() -> Panel` | Panel from (label, value) pairs or preformatted lines; optional title, border_style, padding. |
| `TransientPanelConfig` | dataclass | Panel configuration (max_lines, display_lines, border_style, etc.). |
| `TRANSIENT_PANEL_PRESETS` | `dict[str, TransientPanelConfig]` | `"default"` and `"streaming"` presets. |
| `transient_live_panel(...)` | context manager | Yields an object with `append`, `set_status`, `run_task`. |
