"""Tests for scripts/notebook_style.py.

Plain-python assertions (no pytest dependency):

    python tests/test_notebook_style.py

Requires pandas, plotly, ipython, jinja2.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import numpy as np
import pandas as pd

import notebook_style as ns

# Capture everything the module display()s instead of rendering it.
CAPTURED = []
ns.display = lambda obj: CAPTURED.append(getattr(obj, "data", obj))


def last_css():
    return CAPTURED[-1]


def expect_error(fn, *args, fragment="", **kwargs):
    try:
        fn(*args, **kwargs)
    except ValueError as e:
        assert fragment.lower() in str(e).lower(), (
            f"error message {str(e)!r} missing {fragment!r}")
        return
    raise AssertionError(f"{fn.__name__}{args} should have raised ValueError")


# ---------------------------------------------------------------------------
# Public API: __all__ and the module help text stay in sync
# ---------------------------------------------------------------------------

def test_public_api_exists_and_is_documented():
    for name in ns.__all__:
        assert hasattr(ns, name), f"__all__ lists a missing attribute: {name}"
        assert name in ns.__doc__, f"{name} not shown in the module help text"
    for essential in ("setup", "show", "highlight_matches", "bar_chart",
                      "notebook_fonts", "table_style"):
        assert essential in ns.__all__


# ---------------------------------------------------------------------------
# CSS generation: toggles must emit explicit rules both ways
# ---------------------------------------------------------------------------

def test_css_defaults():
    CAPTURED.clear()
    ns.setup()
    fonts, table, progress = CAPTURED[-3], CAPTURED[-2], CAPTURED[-1]
    assert ':is(table.dataframe, table[id^="T_"])' in table  # pandas-only scope
    assert "position: sticky" in table
    assert "max-height: 480px" in table and "overflow: auto" in table
    assert "#2563eb" in table
    assert "transparent" not in table.split("nth-child(even) td")[1].split(";")[0]
    # table body is Overpass Mono; the header row is Google Sans
    assert f"font-family: {ns.MONO_FONT}" in table
    assert f"font-family: {ns.SANS_FONT}" in table
    assert table.index("Overpass Mono") < table.index("thead th")
    # notebook-wide fonts ride JupyterLab's CSS variables
    assert f"--jp-code-font-family: {ns.MONO_FONT}" in fonts
    assert f"--jp-content-font-family: {ns.SANS_FONT}" in fonts
    assert "@import" in fonts and "Overpass+Mono" in fonts
    assert "bar-stripes 0.8s" in progress and 'content: ""' in progress
    assert "prefers-reduced-motion" in progress


def test_css_disabling_features_emits_resets():
    CAPTURED.clear()
    ns.table_style(zebra=False, hover=False, sticky_header=False, max_height=None)
    css = last_css()
    assert "position: static" in css
    assert "max-height: none" in css and "overflow: visible" in css
    # zebra off -> transparent stripe; hover off -> transparent + stripe pair
    assert "nth-child(even) td { background-color: transparent" in css
    assert "tr:hover td { background-color: transparent" in css


def test_css_hover_off_keeps_zebra_on_hover():
    CAPTURED.clear()
    ns.table_style(zebra=True, hover=False)
    css = last_css()
    stripe = ns._tint(ns.PALETTES["blue"], 0.94)
    # even rows must keep their stripe while hovered
    assert f"nth-child(even):hover td {{ background-color: {stripe}" in css


def test_progress_toggles_and_reset():
    CAPTURED.clear()
    ns.progress_style(stripes=False, spinner=False, height=10)
    css = last_css()
    assert "animation: none" in css
    assert "background-size: 100% 100%" in css
    assert "content: none;" in css and 'content: ""' not in css
    assert "height: 10px" in css

    CAPTURED.clear()
    ns.setup(progress=False)
    reset = last_css()
    assert "revert" in reset and "content: none" in reset


def test_setup_passes_progress_args():
    CAPTURED.clear()
    ns.setup(progress_height=20, stripes=False, spinner=False)
    progress = CAPTURED[-1]
    assert "height: 20px" in progress and "animation: none" in progress


def test_notebook_fonts_options_and_reset():
    CAPTURED.clear()
    ns.notebook_fonts(code_font="Menlo, monospace",
                      text_font="Arial, sans-serif", web_fonts=False)
    css = last_css()
    assert "--jp-code-font-family: Menlo, monospace" in css
    assert "--jp-content-font-family: Arial, sans-serif" in css
    assert "@import" not in css                    # web_fonts=False

    CAPTURED.clear()
    ns.setup(fonts=False)                          # explicit reset rule
    fonts = CAPTURED[-3]
    assert "revert" in fonts and "@import" not in fonts

    expect_error(ns.notebook_fonts, code_font="", fragment="code_font")
    expect_error(ns.notebook_fonts, text_font=None, fragment="text_font")


def test_table_style_font_overrides():
    CAPTURED.clear()
    ns.table_style(body_font="Consolas, monospace",
                   header_font="Verdana, sans-serif")
    css = last_css()
    assert "font-family: Consolas, monospace" in css
    assert "font-family: Verdana, sans-serif" in css
    assert "Overpass Mono" not in css              # defaults fully replaced
    expect_error(ns.table_style, body_font=42, fragment="body_font")
    expect_error(ns.table_style, header_font=" ", fragment="header_font")


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

def test_accent_validation():
    assert ns._accent_hex("green") == "#16a34a"
    assert ns._accent_hex("#AaBbCc") == "#AaBbCc"
    for bad in ("#zzzzzz", "#12345", "#1234567", "blue2", 123, None, ["#112233"]):
        expect_error(ns._accent_hex, bad, fragment="accent")


def test_density_and_font_size_validation():
    expect_error(ns.table_style, density="cozy", fragment="density")
    expect_error(ns.table_style, font_size=0, fragment="font_size")
    expect_error(ns.table_style, font_size=-3, fragment="font_size")
    CAPTURED.clear()
    ns.table_style(density="compact")          # preset applies when None
    assert "font-size: 12px" in last_css()


def test_mix_boundaries():
    assert ns._tint("#2563eb", 0.0) == "#2563eb"
    assert ns._tint("#000000", 1.0) == "#ffffff"
    assert ns._shade("#ffffff", 1.0) == "#000000"


def test_chart_palette_validation():
    expect_error(ns.chart_palette, [], fragment="at least one")
    expect_error(ns.chart_palette, ["#12345z"], fragment="accent")
    expect_error(ns.chart_palette, "no_such_bird", fragment="unknown palette")
    assert ns.chart_palette(["green", "#112233"]) == ["#16a34a", "#112233"]
    ns.chart_palette("default")
    assert ns.CHART_COLORS == list(ns.DEFAULT_CHART_COLORS)


# ---------------------------------------------------------------------------
# Chart input validation
# ---------------------------------------------------------------------------

DF = pd.DataFrame({"cat": ["a", "b", "c"], "v1": [1, 2, 3],
                   "v2": [4.0, 5.0, 6.0], "txt": ["x", "y", "z"]})


def test_chart_empty_and_missing_columns():
    empty = pd.DataFrame({"a": [], "b": []})
    expect_error(ns.bar_chart, empty, fragment="no rows")
    expect_error(ns.line_chart, empty, fragment="no rows")
    expect_error(ns.line_chart, pd.Series([], dtype=float), fragment="empty")
    expect_error(ns.bar_chart, DF, x="nope", fragment="'nope' not found")
    expect_error(ns.bar_chart, DF, x="cat", y="nope", fragment="not found")
    expect_error(ns.bar_chart, DF, x="cat", y="txt", fragment="not numeric")
    expect_error(ns.bar_chart, DF, x="cat", y=["v1", "txt"], fragment="not numeric")


def test_line_endpoint_skips_trailing_nan():
    df = pd.DataFrame({"v": [1.0, 2.0, 3.0, np.nan, np.nan]})
    fig = ns.line_chart(df, y="v")
    endpoint = fig.data[1]                 # data[0] = line, data[1] = end dot
    assert list(endpoint.x) == [2]         # index of last finite value
    assert list(endpoint.y) == [3.0]
    assert endpoint.text == ("3",)         # single series labels the endpoint


def test_line_all_nan_series_has_no_endpoint():
    df = pd.DataFrame({"v": [np.nan, np.nan]})
    fig = ns.line_chart(df, y="v")
    assert len(fig.data) == 1              # just the (empty) line, no dot


def test_chart_colors_override():
    fig = ns.bar_chart(DF, x="cat", y="v1", colors=["#112233"])
    assert fig.data[0].marker.color == "#112233"
    fig = ns.line_chart(DF, x="cat", y=["v1", "v2"], colors=["#112233", "green"])
    assert fig.data[0].line.color == "#112233"
    assert fig.data[2].line.color == "#16a34a"   # preset name resolved
    # custom palette length caps the series count
    expect_error(ns.bar_chart, DF, x="cat", y=["v1", "v2"],
                 colors=["#112233"], fragment="too many")


def test_bar_chart_structure():
    fig = ns.bar_chart(DF, x="cat", y="v1", title="t")
    assert fig.data[0].type == "bar"
    assert list(fig.data[0].text) == ["1", "2", "3"]   # labels at bar ends
    assert fig.layout.yaxis.visible is False           # value axis dropped
    fig = ns.bar_chart(DF, x="cat", y=["v1", "v2"], horizontal=True)
    assert fig.data[0].orientation == "h"
    assert fig.layout.yaxis.autorange == "reversed"    # first row on top
    assert fig.layout.showlegend is True
    neg = ns.bar_chart(pd.Series({"a": 5, "b": -3}))
    assert neg.layout.yaxis.zeroline is True           # zero baseline shown


def test_area_chart_structure():
    df = pd.DataFrame({"day": [1, 2, 3],
                       "s3": [10.0, 12.0, 14.0], "api": [3.0, 4.0, 5.0]})
    # single series: wash fill to zero + endpoint dot with label
    fig = ns.area_chart(df, x="day", y="s3")
    assert fig.data[0].fill == "tozeroy"
    assert fig.data[0].fillcolor.startswith("rgba(")
    assert fig.data[1].text == ("14",)               # endpoint labeled
    # multi series stacked by default
    fig = ns.area_chart(df, x="day")
    assert all(t.stackgroup == "one" for t in fig.data)
    assert fig.layout.showlegend is True
    # stacked=False overlays washes instead
    fig = ns.area_chart(df, x="day", stacked=False)
    assert all(t.fill == "tozeroy" for t in fig.data)
    # colors override + shared validation
    fig = ns.area_chart(df, x="day", y="s3", colors=["#112233"])
    assert fig.data[0].line.color == "#112233"
    expect_error(ns.area_chart, df, x="nope", fragment="not found")
    expect_error(ns.area_chart, pd.DataFrame({"a": []}), fragment="no rows")


def test_donut_validation():
    expect_error(ns.donut_chart, pd.DataFrame({"k": [], "v": []}), fragment="no rows")
    expect_error(ns.donut_chart, pd.Series({"a": -1, "b": 5}), fragment="non-negative")
    expect_error(ns.donut_chart, pd.Series({"a": 0, "b": 0}), fragment="> 0")
    expect_error(ns.donut_chart, pd.Series({"a": np.nan, "b": 1}), fragment="numbers")
    expect_error(ns.donut_chart, pd.Series({"a": np.inf, "b": 1}), fragment="finite")
    expect_error(ns.donut_chart, DF, values="nope", fragment="not found")
    expect_error(ns.donut_chart, DF, labels="nope", fragment="not found")


def test_donut_drops_zero_slices_and_folds():
    fig = ns.donut_chart(pd.Series({"a": 5, "b": 3, "zero": 0}))
    assert len(fig.data[0].labels) == 2    # zero slice dropped
    assert fig.data[0].hole == 0.62
    big = pd.Series({c: 10 - i for i, c in enumerate("abcdefgh")})
    fig = ns.donut_chart(big)
    assert len(fig.data[0].labels) == 6    # folded into "Other" at the cap
    assert fig.data[0].labels[-1] == "Other"
    assert fig.data[0].marker.colors[-1] == ns.OTHER_COLOR


# ---------------------------------------------------------------------------
# show(): truncation and escaping
# ---------------------------------------------------------------------------

def test_show_truncates_and_reports():
    CAPTURED.clear()
    big = pd.DataFrame({"n": range(1000)})
    ns.show(big, max_rows=50)
    out = last_css()
    assert "Showing 50 of 1,000 rows" in out
    assert out.count("<tr>") <= 60         # 50 rows + header, not 1000

    CAPTURED.clear()
    ns.show(big.head(10), max_rows=500)    # under the cap: no note
    assert "Showing" not in last_css()

    CAPTURED.clear()
    ns.show(big, max_rows=None)            # explicit opt-out renders all
    assert last_css().count("<tr>") >= 1000


def test_show_escapes_title():
    CAPTURED.clear()
    ns.show(DF, title='<script>alert("x")</script> & more')
    out = last_css()
    assert "<script>" not in out
    assert "&lt;script&gt;" in out and "&amp; more" in out


# ---------------------------------------------------------------------------
# highlight_matches()
# ---------------------------------------------------------------------------

HDF = pd.DataFrame({"col1": ["val1", "other", "val3"],
                    "status": ["FAILED", "SUCCESS", None],
                    "amount": [1, 2, 3]})


def test_highlight_matches_cells_only():
    rules = {"col1": [{"value": "val1", "color": "#fffeee"},
                      {"value": "val3", "color": "#ffaaee"}]}
    out = ns.highlight_matches(HDF, rules).to_html()
    assert out.count("background-color: #fffeee") == 1
    assert out.count("background-color: #ffaaee") == 1
    # the 'other' row and the amount column carry no highlight
    assert out.count("background-color:") == 2
    # original untouched
    assert HDF.loc[0, "col1"] == "val1" and "style" not in HDF.columns


def test_highlight_matches_single_rule_and_multi_column():
    rules = {"status": {"value": "FAILED", "color": "#fee2e2"},
             "col1": {"value": "other", "color": "#dcfce7"}}
    out = ns.highlight_matches(HDF, rules).to_html()
    assert out.count("background-color: #fee2e2") == 1
    assert out.count("background-color: #dcfce7") == 1


def test_highlight_matches_null_and_type_sensitivity():
    out = ns.highlight_matches(
        HDF, {"status": {"value": None, "color": "#eeeeee"}}).to_html()
    assert out.count("background-color: #eeeeee") == 1   # the None cell
    out = ns.highlight_matches(
        HDF, {"amount": {"value": "1", "color": "#eeeeee"}}).to_html()
    assert "background-color" not in out                 # "1" != 1


def test_highlight_matches_text_color():
    out = ns.highlight_matches(
        HDF, {"col1": {"value": "val1", "color": "#fffeee"}},
        text_color="rose").to_html()
    assert "background-color: #fffeee" in out and "color: #e11d48" in out


def test_highlight_matches_validation():
    ok = {"col1": {"value": "x", "color": "#112233"}}
    try:
        ns.highlight_matches([[1]], ok)
        raise AssertionError("expected TypeError")
    except TypeError:
        pass
    expect_error(ns.highlight_matches, HDF, {}, fragment="non-empty")
    expect_error(ns.highlight_matches, HDF,
                 {"nope": {"value": 1, "color": "#112233"}}, fragment="not found")
    expect_error(ns.highlight_matches, HDF,
                 {"col1": {"value": 1}}, fragment="'value' and 'color'")
    expect_error(ns.highlight_matches, HDF,
                 {"col1": {"value": 1, "color": "red"}}, fragment="color")
    expect_error(ns.highlight_matches, HDF,
                 {"col1": [{"value": "a", "color": "#112233"},
                           {"value": "a", "color": "#445566"}]},
                 fragment="duplicate")
    expect_error(ns.highlight_matches, HDF, {"col1": []}, fragment="non-empty")


def test_show_with_highlights():
    CAPTURED.clear()
    ns.show(HDF, highlights={"col1": {"value": "val1", "color": "#fffeee"}})
    assert "background-color: #fffeee" in last_css()


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def test_fmt_num():
    f = ns._fmt_num
    assert f(1284) == "1.3K"
    assert f(4_200_000) == "4.2M"
    assert f(2_500_000_000) == "2.5B"
    assert f(-1500) == "-1.5K"
    assert f(0.5) == "0.5"
    assert f(7) == "7"
    assert f(float("nan")) == ""


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)} tests passed")
