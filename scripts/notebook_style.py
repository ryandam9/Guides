"""Shared notebook styling for JupyterLab / SageMaker Studio.

Keep this file next to your notebooks. Everyday use needs two names:

    from notebook_style import setup, show
    setup()

Everything importable, grouped by job:

    from notebook_style import (
        # one call does it all: fonts + pandas options + tables + progress
        setup,

        # tables
        show,               # styled scrollable preview (title, max_rows,
                            # highlights)
        highlight_matches,  # color matching cells per column/value rules
        as_strings,         # cast a pandas frame to strings for display

        # charts (interactive plotly figures)
        bar_chart, line_chart, area_chart, donut_chart,
        chart_palette,      # switch multi-series colors notebook-wide
        show_palettes,      # preview the default + all feathers palettes

        # pieces of setup(), applicable individually
        notebook_fonts,     # code + markdown fonts via CSS variables
        table_style,        # card table theme + scroll box + sticky header
        progress_style,     # deluxe progress bars
        pandas_options,     # all columns, max_rows / max_colwidth
    )

(`from notebook_style import *` imports exactly the names above, plus
the customization constants PALETTES / DENSITIES / MONO_FONT /
SANS_FONT / CHART_COLORS / DEFAULT_CHART_COLORS / FEATHERS /
OTHER_COLOR — see __all__.)

`setup()` applies everything at once: notebook-wide fonts (Overpass
Mono for code and table bodies, Google Sans for notebook text and
table headers), pandas display options, the card table theme, the
fixed-height scroll box with sticky headers, and the deluxe progress
bar styling. Everything is configurable through keyword arguments:

    setup()                                  # blue defaults
    setup(accent="green", density="compact") # green theme, tighter rows
    setup(accent="#e11d48", zebra=False)     # any hex color works
    setup(progress=False)                    # reset progress bars to default
    setup(fonts=False)                       # keep the frontend's own fonts

Each piece can also be applied individually — see the functions below.
Rerunning setup()/table_style() with different options replaces the
previous styling: enabling AND disabling features both take effect,
because every toggle emits an explicit rule.

Matching chart helpers draw straight from DataFrames as interactive
plotly figures (hover for values, zoom, legend-click to isolate):

    bar_chart(df, x="region", y="revenue")
    line_chart(df, x="day", y=["loaded", "failed"])
    area_chart(df, x="day", y=["s3", "kinesis", "api"])   # stacked
    donut_chart(df, labels="source", values="rows")

Multi-series colors come from a switchable palette — the validated
default, or any of the 12 Australian-bird palettes from the feathers
R package by Shandiya Balasubramaniam
(https://github.com/shandiya/feathers):

    chart_palette("eastern_rosella")   # see show_palettes() for all
    chart_palette("default")           # back to the built-in colors

Every chart also takes a one-off `colors=[...]` override.

Spark data: on a sparkmagic kernel (SageMaker Studio SparkMagic /
SparkAnalytics kernels, EMR notebooks), plain cells run ON THE CLUSTER
via Livy and %%local cells run in the notebook's own Python — the only
place this module exists. Run setup() and every helper in %%local
cells, and bridge bounded results down with sparkmagic's -o option:

    %%sql -o recent -n 500
    SELECT CAST(id AS STRING) AS id, status, created_at
    FROM events ORDER BY created_at DESC

    %%local
    show(recent, title="Latest events")

(Cast ids/decimals to string in the query — the -o transfer can mangle
them just like toPandas() would.)

Matched cells in a pandas preview can be highlighted per column/value:

    show(pdf, highlights={"status": {"value": "FAILED", "color": "#fee2e2"}})

Supported frontends: JupyterLab-based UIs (SageMaker Studio, JupyterLab
3/4). Classic Notebook, VS Code, and Colab use different output DOM and
are not targeted; the scroll box relies on the CSS :has() selector,
which needs a current browser.

Note: the injected CSS lives in the output of the cell that called
setup(). It survives kernel restarts but disappears if outputs are
cleared — just rerun the setup cell.
"""

import html
import re
from string import Template

import pandas as pd
from IPython.display import HTML, display

#: The public API — what `from notebook_style import *` brings in, and the
#: checklist for explicit imports (see the module docstring for a grouped,
#: commented version).
__all__ = [
    # one-call setup
    "setup",
    # tables
    "show", "highlight_matches", "as_strings",
    # charts
    "bar_chart", "line_chart", "area_chart", "donut_chart",
    "chart_palette", "show_palettes",
    # pieces of setup(), applicable individually
    "notebook_fonts", "table_style", "progress_style", "pandas_options",
    # customization constants
    "PALETTES", "DENSITIES", "MONO_FONT", "SANS_FONT",
    "CHART_COLORS", "DEFAULT_CHART_COLORS", "FEATHERS", "OTHER_COLOR",
]

# ---------------------------------------------------------------------------
# Customization knobs
# ---------------------------------------------------------------------------

#: Named accent presets — pass the name (or any "#rrggbb" hex) as `accent=`.
PALETTES = {
    "blue":   "#2563eb",
    "green":  "#16a34a",
    "purple": "#7c3aed",
    "slate":  "#334155",
    "amber":  "#d97706",
    "rose":   "#e11d48",
}

#: Density presets — font size and cell padding, pass the name as `density=`.
DENSITIES = {
    "compact":     {"font_size": 12, "cell_padding": "4px 8px",  "header_padding": "6px 8px"},
    "normal":      {"font_size": 13, "cell_padding": "6px 12px", "header_padding": "9px 12px"},
    "comfortable": {"font_size": 14, "cell_padding": "9px 14px", "header_padding": "12px 14px"},
}

#: Font stacks. Overpass Mono is web-loaded from Google Fonts (see
#: notebook_fonts); Google Sans is proprietary and NOT on the public
#: Google Fonts CDN — it renders where the machine/browser has it
#: installed, otherwise the stack falls back to the system sans.
MONO_FONT = ('"Overpass Mono", ui-monospace, SFMono-Regular, Menlo, '
             'Consolas, monospace')
SANS_FONT = ('"Google Sans", "Product Sans", system-ui, -apple-system, '
             '"Segoe UI", sans-serif')

_HEX_RE = re.compile(r"#[0-9a-fA-F]{6}\Z")


def _accent_hex(accent):
    """Resolve a palette name ('green') or pass a '#rrggbb' hex through."""
    try:
        return PALETTES[accent]
    except (KeyError, TypeError):
        pass
    if isinstance(accent, str) and _HEX_RE.match(accent):
        return accent
    raise ValueError(
        f"accent must be one of {sorted(PALETTES)} or a '#rrggbb' hex, "
        f"got {accent!r}"
    )


def _font_stack(value, name):
    """Validate a CSS font-family string (any non-empty string passes)."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"{name} must be a non-empty CSS font-family string, got {value!r}")
    return value


def _mix(hex_color, other, weight):
    """Blend hex_color toward `other` by weight in [0, 1]."""
    a = [int(hex_color[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(other[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * weight):02x}" for x, y in zip(a, b))


def _tint(hex_color, weight):
    return _mix(hex_color, "#ffffff", weight)


def _shade(hex_color, weight):
    return _mix(hex_color, "#000000", weight)


# ---------------------------------------------------------------------------
# Notebook fonts: code cells, code output, and rendered markdown
# ---------------------------------------------------------------------------

# JupyterLab resolves all code and content typography through two CSS
# variables; overriding them on <body> beats the theme's :root defaults,
# so one rule covers code cells (CodeMirror 5 and 6), code output, and
# rendered markdown without fighting individual selectors.
_FONTS_TMPL = Template("""\
<style>
${web_import}/* --- Notebook fonts (notebook_style) ----------------------------------- */
body {
    --jp-code-font-family: ${code_font};      /* code cells + code output */
    --jp-content-font-family: ${text_font};   /* rendered markdown text */
}
</style>
""")

_OVERPASS_IMPORT = ("@import url('https://fonts.googleapis.com/css2"
                    "?family=Overpass+Mono:wght@400;600&display=swap');\n")

#: Returns both font variables to the frontend theme's defaults (used by
#: setup(fonts=False) so styling from an earlier call is removed).
FONT_RESET_CSS = """\
<style>
body { --jp-code-font-family: revert; --jp-content-font-family: revert; }
</style>
"""


def notebook_fonts(code_font=MONO_FONT, text_font=SANS_FONT, web_fonts=True):
    """Apply notebook-wide fonts via JupyterLab's CSS variables.

    code_font -- font-family for code cells and code output
                 (default Overpass Mono)
    text_font -- font-family for rendered markdown / notebook text
                 (default Google Sans)
    web_fonts -- also @import Overpass Mono from Google Fonts, so the
                 default renders without a local install (the fetch
                 happens in the BROWSER; offline it fails silently and
                 the stack's fallbacks apply). Google Sans cannot be
                 imported — it is proprietary and not on the public
                 Google Fonts CDN — so it renders only where installed,
                 falling back to the system sans otherwise.

    Rerunning with different fonts replaces the earlier choice;
    setup(fonts=False) resets both variables to the theme default.
    """
    _font_stack(code_font, "code_font")
    _font_stack(text_font, "text_font")
    display(HTML(_FONTS_TMPL.substitute(
        web_import=_OVERPASS_IMPORT if web_fonts else "",
        code_font=code_font,
        text_font=text_font,
    )))


# ---------------------------------------------------------------------------
# Table theme: card look (DataTables style) + scroll box + sticky header
# ---------------------------------------------------------------------------

# Scoped to pandas tables only: plain DataFrame output (table.dataframe)
# and Styler output (table id="T_..."), so tables from statsmodels or
# hand-written HTML are left alone.
_T = '.jp-OutputArea-output :is(table.dataframe, table[id^="T_"])'

# Every toggle emits an explicit rule (sticky/static, tint/transparent,
# px/none) so a later table_style() call fully replaces an earlier one —
# disabling a feature works, not just changing its value.
_TABLE_TMPL = Template("""\
<style>
/* --- Card table theme (notebook_style) --------------------------------- */
${t} {
    border-collapse: separate;   /* 'collapse' kills rounded corners */
    border-spacing: 0;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.15);
    font-size: ${font_size}px;
    font-family: ${body_font};   /* td and index cells inherit this */
    overflow: visible !important; /* required for sticky headers */
}
${t} thead th {
    background-color: ${accent} !important;   /* solid header bar */
    color: white !important;
    font-family: ${header_font};
    font-weight: 600; text-align: left;
    padding: ${header_padding};
    border: none; border-bottom: 2px solid ${accent_dark};
    position: ${sticky}; top: 0; z-index: 2;
}
${t} tbody th {      /* index column, kept quiet */
    background-color: #f8fafc !important;
    color: #64748b; font-weight: normal;
    padding: ${cell_padding};
    border: none; border-bottom: 1px solid #e2e8f0;
}
${t} td {
    padding: ${cell_padding};
    border: none; border-bottom: 1px solid #e2e8f0;
    white-space: nowrap;
}
${t} tbody tr:nth-child(even) td { background-color: ${stripe}; }
${t} tbody tr:hover td { background-color: ${hover_odd}; }
${t} tbody tr:nth-child(even):hover td { background-color: ${hover_even}; }
${t} tbody tr:last-child td,
${t} tbody tr:last-child th { border-bottom: none; }
/* --- Fixed-height scroll box for long tables ('none' disables) --------- */
.jp-OutputArea-output:has(table.dataframe) {
    max-height: ${max_height};
    overflow: ${overflow};
}
</style>
""")


def table_style(accent="blue", density="normal", font_size=None,
                zebra=True, hover=True, sticky_header=True, max_height=480,
                body_font=MONO_FONT, header_font=SANS_FONT):
    """Apply the card table theme.

    accent        -- palette name (see PALETTES) or any '#rrggbb' hex
    density       -- 'compact' | 'normal' | 'comfortable' (see DENSITIES)
    font_size     -- override the density preset's font size (px)
    zebra         -- stripe even rows with a light tint of the accent
    hover         -- highlight the row under the mouse
    sticky_header -- keep the header visible while scrolling
    max_height    -- scroll-box height in px for long tables; None disables
    body_font     -- font-family for table cells (default Overpass Mono —
                     monospace keeps ids/amounts column-aligned)
    header_font   -- font-family for the header row (default Google Sans)

    Rerunning with different options fully replaces the earlier styling,
    including turning features off.
    """
    accent = _accent_hex(accent)
    _font_stack(body_font, "body_font")
    _font_stack(header_font, "header_font")
    try:
        dens = DENSITIES[density]
    except (KeyError, TypeError):
        raise ValueError(
            f"density must be one of {sorted(DENSITIES)}, got {density!r}"
        ) from None
    size = dens["font_size"] if font_size is None else font_size
    if not isinstance(size, (int, float)) or size <= 0:
        raise ValueError(f"font_size must be a positive number, got {font_size!r}")

    stripe = _tint(accent, 0.94) if zebra else "transparent"
    hover_tint = _tint(accent, 0.82)
    css = _TABLE_TMPL.substitute(
        t=_T,
        accent=accent,
        accent_dark=_shade(accent, 0.30),
        font_size=size,
        cell_padding=dens["cell_padding"],
        header_padding=dens["header_padding"],
        body_font=body_font,
        header_font=header_font,
        sticky="sticky" if sticky_header else "static",
        stripe=stripe,
        hover_odd=hover_tint if hover else "transparent",
        hover_even=hover_tint if hover else stripe,
        max_height=f"{max_height}px" if max_height else "none",
        overflow="auto" if max_height else "visible",
    )
    display(HTML(css))


# ---------------------------------------------------------------------------
# Progress bars: wide bar, animated stripes, spinner
# ---------------------------------------------------------------------------

_PROGRESS_TMPL = Template("""\
<style>
.widget-hprogress { width: 95% !important; }
.widget-hprogress .widget-label {
    color: ${label}; font-weight: 600; min-width: 80px;
}
.widget-hprogress .progress {
    flex-grow: 1;
    height: ${height}px !important;
    border-radius: ${radius}px;
    background-color: #e2e8f0;
    box-shadow: inset 0 1px 2px rgba(0,0,0,0.12);
    overflow: hidden;
}
.widget-hprogress .progress-bar {
    border-radius: ${radius}px;
    background-image: ${fill} !important;
    background-size: ${bg_size};
    animation: ${bar_anim};
    transition: width 0.3s ease;
}
@keyframes bar-stripes {
    from { background-position: 24px 0, 0 0; }
    to   { background-position: 0 0, 0 0; }
}
.widget-hprogress::after { ${spinner} }
@keyframes spin { to { transform: rotate(360deg); } }
.jp-OutputArea-output progress {
    width: 95%; height: ${height}px; accent-color: ${accent};
}
/* Respect reduced-motion preferences: no crawling stripes, no spinning */
@media (prefers-reduced-motion: reduce) {
    .widget-hprogress .progress-bar { animation: none; transition: none; }
    .widget-hprogress::after { animation: none; }
}
</style>
""")

_STRIPE_OVERLAY = """linear-gradient(45deg,
            rgba(255,255,255,0.25) 25%, transparent 25%,
            transparent 50%, rgba(255,255,255,0.25) 50%,
            rgba(255,255,255,0.25) 75%, transparent 75%),
        """

#: Returns progress bars to the frontend's default look (used by
#: setup(progress=False) so styling from an earlier call is removed).
PROGRESS_RESET_CSS = """\
<style>
.widget-hprogress { width: revert !important; }
.widget-hprogress .widget-label { color: revert; font-weight: revert; min-width: revert; }
.widget-hprogress .progress {
    flex-grow: revert; height: revert !important; border-radius: revert;
    background-color: revert; box-shadow: revert; overflow: revert;
}
.widget-hprogress .progress-bar {
    border-radius: revert; background-image: revert !important;
    background-size: revert; animation: none; transition: revert;
}
.widget-hprogress::after { content: none; animation: none; }
.jp-OutputArea-output progress { width: revert; height: revert; accent-color: revert; }
</style>
"""


def progress_style(accent="blue", height=14, stripes=True, spinner=True):
    """Apply the deluxe progress bar styling.

    accent  -- palette name or '#rrggbb' hex, matched to the table theme
    height  -- bar height in px
    stripes -- animate diagonal candy stripes on the fill
    spinner -- append a rotating spinner after the bar (pure CSS cannot
               detect completion, so it spins while the bar is on screen;
               sparkmagic clears the widget when the job ends)

    Rerunning with different options fully replaces the earlier styling.
    Animations are disabled automatically for users with the
    prefers-reduced-motion accessibility preference set.
    """
    accent = _accent_hex(accent)
    gradient = f"linear-gradient(90deg, {_tint(accent, 0.12)}, {_shade(accent, 0.18)})"
    spinner_rules = (
        f'content: ""; flex: none;\n'
        f"    width: {height}px; height: {height}px; margin-left: 10px;\n"
        f"    border: 3px solid {_tint(accent, 0.72)}; border-top-color: {accent};\n"
        f"    border-radius: 50%; animation: spin 0.8s linear infinite;"
        if spinner else "content: none;"
    )
    css = _PROGRESS_TMPL.substitute(
        accent=accent,
        label=_shade(accent, 0.30),
        height=height,
        radius=height // 2,
        fill=(_STRIPE_OVERLAY + gradient) if stripes else gradient,
        bg_size="24px 24px, 100% 100%" if stripes else "100% 100%",
        bar_anim="bar-stripes 0.8s linear infinite" if stripes else "none",
        spinner=spinner_rules,
    )
    display(HTML(css))


# ---------------------------------------------------------------------------
# Pandas display options and the one-call setup
# ---------------------------------------------------------------------------

def pandas_options(max_rows=100, max_colwidth=80):
    """Show all columns; sensible row/width truncation."""
    pd.set_option("display.max_columns", None)
    pd.set_option("display.max_rows", max_rows)
    pd.set_option("display.max_colwidth", max_colwidth)


def setup(accent="blue", density="normal", font_size=None,
          zebra=True, hover=True, sticky_header=True, max_height=480,
          body_font=MONO_FONT, header_font=SANS_FONT,
          max_rows=100, max_colwidth=80,
          fonts=True, code_font=MONO_FONT, text_font=SANS_FONT,
          web_fonts=True,
          progress=True, progress_height=14, stripes=True, spinner=True):
    """Apply everything: fonts, pandas options, table theme, progress bars.

    Table options : accent, density, font_size, zebra, hover,
                    sticky_header, max_height, body_font, header_font
                    (see table_style)
    Pandas options: max_rows, max_colwidth (see pandas_options)
    Notebook fonts: code_font, text_font, web_fonts (see notebook_fonts);
                    fonts=False RESETS code/markdown fonts to the theme
                    default (table fonts are part of the table theme and
                    follow body_font/header_font regardless)
    Progress bars : progress_height, stripes, spinner (see progress_style);
                    progress=False RESETS progress bars to the frontend
                    default, removing styling from an earlier setup()

    Rerunning setup() with different options replaces the earlier styling —
    disabling a feature works, not just changing its value.
    """
    if fonts:
        notebook_fonts(code_font=code_font, text_font=text_font,
                       web_fonts=web_fonts)
    else:
        display(HTML(FONT_RESET_CSS))
    pandas_options(max_rows=max_rows, max_colwidth=max_colwidth)
    table_style(accent=accent, density=density, font_size=font_size,
                zebra=zebra, hover=hover, sticky_header=sticky_header,
                max_height=max_height, body_font=body_font,
                header_font=header_font)
    if progress:
        progress_style(accent=accent, height=progress_height,
                       stripes=stripes, spinner=spinner)
    else:
        display(HTML(PROGRESS_RESET_CSS))


# ---------------------------------------------------------------------------
# Charts: bar, line, donut from pandas DataFrames (requires plotly)
# ---------------------------------------------------------------------------

#: Default series colors, in FIXED order (colorblind-validated as a set —
#: worst adjacent-pair CVD ΔE 24.2 on a white surface). Never reorder or cycle
#: past the end: extra series must be folded into "Other" or split into charts.
DEFAULT_CHART_COLORS = (
    "#2a78d6",  # blue
    "#1baf7a",  # aqua
    "#eda100",  # yellow
    "#008300",  # green
    "#4a3aa7",  # violet
    "#e34948",  # red
    "#e87ba4",  # magenta
    "#eb6834",  # orange
)

#: Bird-plumage palettes from the feathers R package by Shandiya
#: Balasubramaniam — https://github.com/shandiya/feathers — selectable
#: with chart_palette("eastern_rosella"). Kept verbatim, in plumage order.
FEATHERS = {
    "spotted_pardalote": ["#feca00", "#d36328", "#cb0300", "#b4b9b3",
                          "#424847", "#000100"],
    "plains_wanderer": ["#edd8c5", "#d09a5e", "#e7aa01", "#ac570f",
                        "#73481b", "#442c0e", "#0d0403"],
    "bee_eater": ["#00346e", "#007cbf", "#06abdf", "#edd03e",
                  "#f5a200", "#6d8600", "#424d0c"],
    "rose_crowned_fruit_dove": ["#bd338f", "#eb8252", "#f5dc83", "#cdd4dc",
                                "#8098a2", "#8fa33f", "#5f7929", "#014820"],
    "eastern_rosella": ["#cd3122", "#f4c623", "#bee183", "#6c905e",
                        "#2f533c", "#b8c9dc", "#2f7ab9"],
    "oriole": ["#8a3223", "#bb5645", "#d97878", "#e2aba0", "#d0cfe9",
               "#a29eb8", "#6c6b75", "#b8a53f", "#93862a", "#4d4019"],
    "princess_parrot": ["#7090c9", "#8cb3de", "#afbe9f", "#616020",
                        "#6eb245", "#214917", "#cf2236", "#d683ad"],
    "superb_fairy_wren": ["#4f3321", "#aa7853", "#d9c4a7", "#b03f05",
                          "#020503"],
    "cassowary": ["#bda14d", "#3ebcb6", "#0169c4", "#153460",
                  "#d5114e", "#a56eb6", "#4b1c57", "#09090c"],
    "yellow_robin": ["#e19e00", "#fbeb5b", "#85773a", "#979eb9",
                     "#727b98", "#454b56", "#201b1e"],
    "galah": ["#ffd2cf", "#e9a7bb", "#d05478", "#aab9cc",
              "#8390a2", "#4c5766"],
    "blue_winged_kookaburra": ["#b5effb", "#0b7595", "#02407c", "#06213a",
                               "#c45829", "#9c4620", "#622c14", "#d4d8e3",
                               "#b8bcd8", "#ad8d9f", "#725f77"],
}

#: The ACTIVE palette that multi-series charts draw from — change it with
#: chart_palette(). Series colors are assigned in list order, never cycled.
CHART_COLORS = list(DEFAULT_CHART_COLORS)

OTHER_COLOR = "#94a3b8"   # the folded "Other" slice/bar — deliberately quiet


def _colors_list(colors):
    """Validate a user-supplied color list: non-empty, presets or hex."""
    colors = list(colors)
    if not colors:
        raise ValueError("colors must contain at least one color")
    return [_accent_hex(c) for c in colors]


def chart_palette(palette="default", preview=False):
    """Choose the colors multi-series charts use, notebook-wide.

    palette -- 'default' (the colorblind-validated 8), a feathers palette
               name (see FEATHERS / show_palettes()), or your own list of
               '#rrggbb' hex colors / preset names
    preview -- also display a swatch strip of the chosen colors

    The default palette's ordering is validated to stay distinguishable
    under color blindness; the feathers palettes follow each bird's
    plumage and make no such promise — when series look close, the legend
    and direct labels carry identity. The palette length also caps how
    many series one chart may hold. Returns the color list.

    For a one-off palette on a single chart, pass `colors=[...]` to the
    chart function instead of changing the notebook-wide palette.
    """
    if isinstance(palette, str):
        if palette == "default":
            colors = list(DEFAULT_CHART_COLORS)
        elif palette in FEATHERS:
            colors = list(FEATHERS[palette])
        else:
            raise ValueError(
                f"unknown palette {palette!r} — use 'default', a feathers "
                f"name ({', '.join(sorted(FEATHERS))}), or a list of hex colors"
            )
    else:
        colors = _colors_list(palette)
    CHART_COLORS[:] = colors
    if preview:
        _palette_strip(colors)
    return colors


def _palette_strip(colors, name=None):
    """Render one palette as a labeled swatch strip."""
    caption = (f'<span style="font-size:12px; color:#334155; font-weight:600; '
               f'display:inline-block; min-width:190px;">{html.escape(str(name))}</span>'
               if name else "")
    swatches = "".join(
        f'<div style="flex:1; background:{c};" title="{c}"></div>'
        for c in colors)
    display(HTML(
        f'<div style="display:flex; align-items:center; gap:10px; margin:3px 0;">'
        f'{caption}<div style="display:flex; height:26px; width:300px; '
        f'border-radius:5px; overflow:hidden; '
        f'box-shadow:0 1px 2px rgba(0,0,0,0.2);">{swatches}</div>'
        f'<span style="font-size:10px; color:#64748b;">{len(colors)} colors'
        f'</span></div>'
    ))


def show_palettes():
    """Preview every chart palette: the default and all feathers palettes."""
    _palette_strip(DEFAULT_CHART_COLORS, "default")
    for name, colors in FEATHERS.items():
        _palette_strip(colors, name)


# Chart chrome (slate ink family, matching the table theme)
_INK = "#0f172a"        # titles
_INK_2 = "#334155"      # value labels
_MUTED = "#64748b"      # axis tick labels
_GRID = "#e2e8f0"       # hairline gridlines
_BASELINE = "#cbd5e1"   # axis baseline


def _fmt_num(v):
    """Compact number for labels/ticks: 1284 -> 1.3K, 4200000 -> 4.2M."""
    if pd.isna(v):
        return ""
    for div, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(v) >= div:
            s = f"{v / div:.1f}".rstrip("0").rstrip(".")
            return s + suffix
    if isinstance(v, float) and not float(v).is_integer():
        return f"{v:,.2f}".rstrip("0").rstrip(".")
    return f"{v:,.0f}"


def _resolve_series(df, x, y, palette):
    """Return (category labels, {series name: values}) from df/x/y,
    with friendly validation errors."""
    if isinstance(df, pd.Series):
        if len(df) == 0:
            raise ValueError("nothing to plot: the Series is empty")
        return df.index, {df.name or "value": df.to_numpy()}
    if len(df) == 0:
        raise ValueError("nothing to plot: the DataFrame has no rows")
    if x is not None and x not in df.columns:
        raise ValueError(f"x column {x!r} not found — available: {list(df.columns)}")
    labels = df[x].to_numpy() if x is not None else df.index
    if y is None:
        cols = [c for c in df.columns
                if c != x and pd.api.types.is_numeric_dtype(df[c])]
    else:
        cols = [y] if isinstance(y, str) else list(y)
        missing = [c for c in cols if c not in df.columns]
        if missing:
            raise ValueError(
                f"y column(s) {missing} not found — available: {list(df.columns)}")
        non_numeric = [c for c in cols
                       if not pd.api.types.is_numeric_dtype(df[c])]
        if non_numeric:
            raise ValueError(f"y column(s) {non_numeric} are not numeric")
    if not cols:
        raise ValueError("no numeric columns to plot — pass y='column'")
    if len(cols) > len(palette):
        raise ValueError(
            f"{len(cols)} series is too many to tell apart by color "
            f"(max {len(palette)}) — fold the tail into 'Other' "
            "or split into several charts"
        )
    return labels, {c: df[c].to_numpy() for c in cols}


def _series_colors(n_series, accent, colors):
    """Colors for this chart: explicit override > accent (single) > palette."""
    if colors is not None:
        return _colors_list(colors)[:n_series]
    if n_series == 1:
        return [_accent_hex(accent)]
    return CHART_COLORS[:n_series]


def _plotly():
    try:
        import plotly.graph_objects as go
    except ImportError:
        raise ImportError("charts need plotly — pip install plotly") from None
    return go


def _chart_size(figsize, default_height):
    """Map an (inches, inches) figsize to pixels; None stays responsive."""
    if figsize is None:
        return None, default_height
    return int(figsize[0] * 96), int(figsize[1] * 96)


def _chart_layout(fig, title, n_series, height, width=None):
    """Recessive chrome: white surface, muted ticks, frameless legend."""
    fig.update_layout(
        paper_bgcolor="white", plot_bgcolor="white",
        font=dict(family=SANS_FONT, size=12, color=_INK_2),
        title=(dict(text=f"<b>{html.escape(str(title))}</b>", x=0,
                    xanchor="left", font=dict(size=15, color=_INK))
               if title else None),
        margin=dict(l=50, r=30, t=60 if title else 30, b=45),
        height=height, width=width,
        showlegend=n_series >= 2,
        legend=dict(bgcolor="rgba(0,0,0,0)", x=1.02, y=1,
                    font=dict(color=_INK_2, size=11)),
        hoverlabel=dict(bgcolor="white", bordercolor=_BASELINE,
                        font=dict(color=_INK, size=12)),
    )
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor=_BASELINE,
                     tickfont=dict(color=_MUTED, size=11))
    fig.update_yaxes(showgrid=False, zeroline=False,
                     linecolor="rgba(0,0,0,0)",
                     tickfont=dict(color=_MUTED, size=11))
    return fig


def bar_chart(df, x=None, y=None, title=None, horizontal=False,
              accent="blue", colors=None, figsize=None):
    """Bar chart from a DataFrame (or Series).

    x          -- category column; defaults to the index
    y          -- value column, or list of columns for grouped bars;
                  defaults to every numeric column
    horizontal -- sideways bars; use for long category names
    accent     -- single-series bar color (palette name or hex)
    colors     -- one-off color list for this chart; overrides both the
                  accent and the notebook-wide palette

    A single series is drawn in one color with the value at each bar end
    (coloring bars by their own height just repeats what length shows).
    Returns an interactive plotly Figure — hover for exact values,
    fig.write_html("chart.html") to export (write_image needs kaleido).
    """
    go = _plotly()
    palette = _colors_list(colors) if colors is not None else CHART_COLORS
    labels, series = _resolve_series(df, x, y, palette)
    labels = list(labels)
    n_cats, n_series = len(labels), len(series)
    bar_colors = _series_colors(n_series, accent, colors)
    label_all = n_series == 1 and n_cats <= 30
    has_negative = any(v < 0 for vals in series.values()
                       for v in vals if not pd.isna(v))

    fig = go.Figure()
    for j, (name, vals) in enumerate(series.items()):
        vals = list(vals)
        text = [_fmt_num(v) for v in vals] if label_all else None
        common = dict(name=name, marker_color=bar_colors[j], text=text,
                      textposition="outside", cliponaxis=False,
                      textfont=dict(color=_INK_2, size=11))
        if horizontal:
            fig.add_bar(y=labels, x=vals, orientation="h", **common)
        else:
            fig.add_bar(x=labels, y=vals, **common)

    default_height = (max(260, 34 * n_cats * n_series + 130) if horizontal
                      else 400)
    width, height = _chart_size(figsize, default_height)
    _chart_layout(fig, title, n_series, height, width)
    fig.update_layout(barmode="group",
                      bargap=0.45 if n_series == 1 else 0.25,
                      bargroupgap=0.12)
    val_axis = "xaxis" if horizontal else "yaxis"
    if horizontal:
        fig.update_yaxes(autorange="reversed")     # first row on top
        fig.update_xaxes(linecolor="rgba(0,0,0,0)")
        fig.update_yaxes(linecolor=_BASELINE)
    if label_all:                       # every value is labeled — drop the
        fig.update_layout(**{val_axis: dict(visible=False)})
    else:
        fig.update_layout(**{val_axis: dict(showgrid=True, gridcolor=_GRID,
                                            gridwidth=1)})
    if has_negative:                    # bars straddle zero — mark the baseline
        fig.update_layout(**{val_axis: dict(zeroline=True,
                                            zerolinecolor=_BASELINE,
                                            zerolinewidth=1)})
    return fig


def line_chart(df, x=None, y=None, title=None, accent="blue", colors=None,
               figsize=(7.5, 4)):
    """Line chart from a DataFrame (or Series), typically over time.

    x      -- x-axis column (dates work); defaults to the index
    y      -- value column or list of columns; defaults to every numeric column
    accent -- single-series line color
    colors -- one-off color list for this chart

    Each line ends in a dot with a white ring at its last FINITE value
    (trailing gaps are skipped); a single series also gets that value
    labeled at the line end. Hover shows all series at the cursor's x.
    Returns an interactive plotly Figure.
    """
    import numpy as np
    go = _plotly()
    palette = _colors_list(colors) if colors is not None else CHART_COLORS
    xvals, series = _resolve_series(df, x, y, palette)
    xvals = list(xvals)
    n_series = len(series)
    line_colors = _series_colors(n_series, accent, colors)

    fig = go.Figure()
    for j, (name, vals) in enumerate(series.items()):
        vals = list(vals)
        fig.add_scatter(x=xvals, y=vals, mode="lines", name=name,
                        line=dict(color=line_colors[j], width=2,
                                  shape="linear"))
        finite = np.flatnonzero(np.isfinite(
            pd.to_numeric(pd.Series(vals), errors="coerce")
            .astype(float).to_numpy()))
        if finite.size == 0:
            continue                       # nothing plottable in this series
        last = int(finite[-1])
        single = n_series == 1
        fig.add_scatter(x=[xvals[last]], y=[vals[last]],
                        mode="markers+text" if single else "markers",
                        marker=dict(color=line_colors[j], size=9,
                                    line=dict(color="white", width=2)),
                        text=[_fmt_num(vals[last])] if single else None,
                        textposition="middle right",
                        textfont=dict(color=_INK_2, size=12),
                        cliponaxis=False, showlegend=False,
                        hoverinfo="skip")

    width, height = _chart_size(figsize if figsize != (7.5, 4) else None, 400)
    _chart_layout(fig, title, n_series, height, width)
    fig.update_yaxes(showgrid=True, gridcolor=_GRID, gridwidth=1)
    fig.update_layout(hovermode="x unified")
    return fig


def _rgba(hex_color, alpha):
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r},{g},{b},{alpha})"


def area_chart(df, x=None, y=None, title=None, accent="blue", colors=None,
               stacked=True, figsize=None):
    """Area chart from a DataFrame (or Series), typically over time.

    x       -- x-axis column (dates work); defaults to the index
    y       -- value column or list of columns; defaults to every
               numeric column
    accent  -- single-series color
    colors  -- one-off color list for this chart
    stacked -- multiple series stack to show composition over time
               (the default); stacked=False overlays translucent
               washes instead — fine for 2 series, muddy beyond that

    A single series is a 2px line over a soft wash of the same hue,
    with a white-ringed dot and label at its last finite value. Stacked
    hover shows every series at the cursor's x. Returns an interactive
    plotly Figure.
    """
    import numpy as np
    go = _plotly()
    palette = _colors_list(colors) if colors is not None else CHART_COLORS
    xvals, series = _resolve_series(df, x, y, palette)
    xvals = list(xvals)
    n_series = len(series)
    area_colors = _series_colors(n_series, accent, colors)

    fig = go.Figure()
    for j, (name, vals) in enumerate(series.items()):
        vals = list(vals)
        c = area_colors[j]
        kw = dict(x=xvals, y=vals, mode="lines", name=name,
                  line=dict(color=c, width=2))
        if n_series > 1 and stacked:
            # stacked segments don't overlap, so they carry more opacity
            kw.update(stackgroup="one", fillcolor=_rgba(c, 0.45))
        else:
            # a wash, never a saturated block
            kw.update(fill="tozeroy", fillcolor=_rgba(c, 0.12))
        fig.add_scatter(**kw)

    if n_series == 1:                      # end dot + label, like line_chart
        vals = list(next(iter(series.values())))
        finite = np.flatnonzero(np.isfinite(
            pd.to_numeric(pd.Series(vals), errors="coerce")
            .astype(float).to_numpy()))
        if finite.size:
            last = int(finite[-1])
            fig.add_scatter(x=[xvals[last]], y=[vals[last]],
                            mode="markers+text",
                            marker=dict(color=area_colors[0], size=9,
                                        line=dict(color="white", width=2)),
                            text=[_fmt_num(vals[last])],
                            textposition="middle right",
                            textfont=dict(color=_INK_2, size=12),
                            cliponaxis=False, showlegend=False,
                            hoverinfo="skip")

    width, height = _chart_size(figsize, 400)
    _chart_layout(fig, title, n_series, height, width)
    fig.update_yaxes(showgrid=True, gridcolor=_GRID, gridwidth=1,
                     rangemode="tozero")
    fig.update_layout(hovermode="x unified")
    return fig


def donut_chart(df, labels=None, values=None, title=None, max_slices=6,
                colors=None, figsize=(6.4, 4.2)):
    """Donut chart for a part-to-whole breakdown, with the total in the hole.

    labels     -- label column; defaults to the first non-numeric column
                  (or the index). A Series works too: index = labels.
    values     -- value column; defaults to the first numeric column
    max_slices -- slices are sorted largest-first and everything past this
                  is folded into a gray "Other" (capped at 6 — more slices
                  than that stop being readable at a glance)
    colors     -- one-off color list for this chart

    Values must be non-negative and finite, and the total must be > 0;
    zero-valued slices are dropped. Donuts are for at-a-glance
    proportions only; to compare close values, use bar_chart.
    Returns an interactive plotly Figure.
    """
    import numpy as np
    go = _plotly()
    if isinstance(df, pd.Series):
        s = df.copy()
    else:
        if len(df) == 0:
            raise ValueError("nothing to plot: the DataFrame has no rows")
        if values is None:
            numeric = [c for c in df.columns
                       if pd.api.types.is_numeric_dtype(df[c])]
            if not numeric:
                raise ValueError(
                    f"no numeric column found — available: {list(df.columns)}")
            values = numeric[0]
        elif values not in df.columns:
            raise ValueError(
                f"values column {values!r} not found — available: {list(df.columns)}")
        if labels is not None and labels not in df.columns:
            raise ValueError(
                f"labels column {labels!r} not found — available: {list(df.columns)}")
        if labels is None:
            non_num = [c for c in df.columns
                       if not pd.api.types.is_numeric_dtype(df[c])]
            s = pd.Series(df[values].to_numpy(),
                          index=df[non_num[0]] if non_num else df.index)
        else:
            s = pd.Series(df[values].to_numpy(), index=df[labels])

    if len(s) == 0:
        raise ValueError("nothing to plot: the data is empty")
    numeric_vals = pd.to_numeric(s, errors="coerce")
    if numeric_vals.isna().any():
        bad = list(s.index[numeric_vals.isna()][:5])
        raise ValueError(
            f"donut values must be numbers (no missing values) — bad: {bad}")
    if not np.isfinite(numeric_vals.astype(float).to_numpy()).all():
        raise ValueError("donut values must be finite (no inf)")
    if (numeric_vals < 0).any():
        neg = list(s.index[(numeric_vals < 0).to_numpy()][:5])
        raise ValueError(f"donut values must be non-negative — negative: {neg}")
    s = s[(numeric_vals > 0).to_numpy()]  # zero slices are invisible clutter
    if len(s) == 0:
        raise ValueError("donut total must be > 0 — all values are zero")

    s = s.sort_values(ascending=False)
    palette = _colors_list(colors) if colors is not None else CHART_COLORS
    max_slices = min(max_slices, 6, len(palette))
    if max_slices < 1:
        raise ValueError("max_slices must be at least 1")
    if len(s) > max_slices:
        s = pd.concat([s.iloc[:max_slices - 1],
                       pd.Series({"Other": s.iloc[max_slices - 1:].sum()})])

    slice_colors = list(palette[:len(s)])
    if "Other" in s.index:
        slice_colors = slice_colors[:len(s) - 1] + [OTHER_COLOR]
    total = s.sum()

    fig = go.Figure(go.Pie(
        labels=[str(i) for i in s.index],
        values=[float(v) for v in s.to_numpy()],
        hole=0.62, sort=False, direction="clockwise",
        marker=dict(colors=slice_colors, line=dict(color="white", width=2)),
        textinfo="label+percent", textposition="outside",
        textfont=dict(color=_INK_2, size=11),
    ))
    fig.add_annotation(text=f"<b>{_fmt_num(total)}</b>", showarrow=False,
                       x=0.5, y=0.53, xref="paper", yref="paper",
                       font=dict(size=22, color=_INK))
    fig.add_annotation(text="total", showarrow=False,
                       x=0.5, y=0.44, xref="paper", yref="paper",
                       font=dict(size=11, color=_MUTED))
    width, height = _chart_size(figsize if figsize != (6.4, 4.2) else None, 420)
    _chart_layout(fig, title, 1, height, width)
    fig.update_layout(showlegend=False)
    return fig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def show(df, height=420, title=None, max_rows=500, highlights=None):
    """Display a DataFrame in its own fixed-height scroll box.

    title      -- optional caption rendered above the table (HTML-escaped)
    max_rows   -- rows rendered into the page; the rest are truncated with a
                  visible "Showing X of Y rows" note. None renders everything
                  (beware: a 100k-row table will hurt the browser tab).
    highlights -- optional highlight_matches() rules applied to the
                  rendered rows
    """
    total = len(df)
    visible = df if max_rows is None else df.head(max_rows)
    caption = (f'<div style="font-weight:600; color:#334155; '
               f'margin-bottom:6px;">{html.escape(str(title))}</div>'
               if title else "")
    note = ("" if len(visible) == total else
            f'<div style="font-size:11px; color:#64748b; margin-top:4px;">'
            f'Showing {len(visible):,} of {total:,} rows</div>')
    body = (highlight_matches(visible, highlights).to_html()
            if highlights else visible.to_html())
    display(HTML(
        f'{caption}<div style="max-height:{height}px; overflow:auto; '
        f'display:inline-block;">{body}</div>{note}'
    ))


def highlight_matches(df, rules, *, text_color=None):
    """Return a pandas Styler with configured matching cells highlighted.

    rules maps a column name to one rule or a list of rules, each rule
    being {"value": <cell value>, "color": "#rrggbb"}:

        highlight_matches(pdf, {
            "status": [
                {"value": "FAILED",  "color": "#fee2e2"},
                {"value": "SUCCESS", "color": "#dcfce7"},
            ],
            "priority": {"value": "HIGH", "color": "#fef3c7"},
        })

    Only the matching cells are colored — never the whole row. Matching
    is exact and type-sensitive (the string "1" does not match the
    integer 1); a rule value of None / NaN matches null cells. Duplicate
    rules for the same column and value are rejected. The original
    DataFrame is not modified. text_color optionally sets the text color
    of matched cells (accent preset name or hex).
    """
    if not isinstance(df, pd.DataFrame):
        raise TypeError("df must be a pandas DataFrame")
    if not isinstance(rules, dict) or not rules:
        raise ValueError("rules must be a non-empty mapping of column -> rule(s)")
    try:
        import jinja2  # noqa: F401 -- pandas Styler needs it at render time
    except ImportError:
        raise ImportError(
            "highlight_matches needs jinja2 (the pandas Styler dependency) — "
            "pip install jinja2"
        ) from None
    missing = [c for c in rules if c not in df.columns]
    if missing:
        raise ValueError(
            f"highlight columns not found: {missing} — available: {list(df.columns)}")

    text_css = f" color: {_accent_hex(text_color)};" if text_color is not None else ""
    styles = pd.DataFrame("", index=df.index, columns=df.columns)

    for column, column_rules in rules.items():
        if isinstance(column_rules, dict):
            column_rules = [column_rules]
        if not isinstance(column_rules, (list, tuple)) or not column_rules:
            raise ValueError(
                f"rules for {column!r} must be a rule dict or a non-empty list of them")
        seen = []
        for rule in column_rules:
            if not isinstance(rule, dict) or "value" not in rule or "color" not in rule:
                raise ValueError(
                    f"each rule for {column!r} needs 'value' and 'color', got {rule!r}")
            color = rule["color"]
            if not isinstance(color, str) or not _HEX_RE.match(color):
                raise ValueError(
                    f"invalid highlight color for {column!r}: {color!r} "
                    "(use '#rrggbb')")
            value = rule["value"]
            key = "<null>" if (not isinstance(value, (list, dict)) and pd.isna(value)) else repr(value)
            if key in seen:
                raise ValueError(
                    f"duplicate rule for {column!r} value {key} — "
                    "one color per value")
            seen.append(key)
            if key == "<null>":
                mask = df[column].isna()
            else:
                mask = df[column].eq(value)
            styles.loc[mask.fillna(False), column] = (
                f"background-color: {color};{text_css}")

    return df.style.apply(lambda _: styles, axis=None)


def as_strings(df, blank_nulls=True):
    """Return a copy with every column as string dtype.

    Prevents FURTHER display artifacts (ints turning into floats on
    display, scientific notation when formatting) — but it cannot restore
    information already lost at load time: leading zeros stripped or
    precision dropped by read_csv or the Spark handoff are gone before
    this runs. To preserve formatting, load as strings at the source:
    read_csv(dtype=str), or CAST(... AS STRING) in the query that
    produces the data."""
    out = df.astype("string")
    if blank_nulls:
        out = out.fillna("")
    return out
