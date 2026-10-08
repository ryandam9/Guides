#!/usr/bin/env python3
"""Generate the inline SVG diagrams in docs/spark-hbase-visual-guide.html.

Every diagram is static SVG: no JavaScript and no CDN. Each one sits in the
page between an opening ``<div class="dg..." data-dg="NAME">`` and a closing
``</div><!--/dg-->``. Running this script rewrites what is between them:

    python3 scripts/spark_hbase_diagrams.py

Most figures have two drawings: a wide one (800 units across) for desktop and
a narrow one (360 units) for phones. CSS chooses which one to show.

One colour means one thing on every diagram:
    blue   Spark compute (driver, executors, partitions, tasks)
    amber  data that moves over the network (shuffle, broadcast)
    teal   HBase (regions, RegionServers, MemStore)
    slate  external storage and services (files, HDFS, Kafka, YARN)
    violet results and written output
    rose   the costly step or a rejected row
"""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

PAGE = Path(__file__).resolve().parent.parent / "docs" / "spark-hbase-visual-guide.html"

TONES = {
    # stroke, deep text, soft fill top, soft fill bottom, solid top, solid bottom
    "blue": ("#3469ee", "#1a3f9c", "#f4f7ff", "#e4ecff", "#3d6ff0", "#2650c8"),
    "navy": ("#1d3375", "#ffffff", "#2a4597", "#1b2f6b", "#2a4597", "#1b2f6b"),
    "teal": ("#0b8a6f", "#075a48", "#f1fbf7", "#dcf3ea", "#14a383", "#0a7a62"),
    "amber": ("#d07f12", "#8a4f05", "#fff9ec", "#ffedc9", "#e39a2d", "#c27410"),
    "violet": ("#6946ba", "#46288f", "#f8f5ff", "#ebe3fb", "#7a58cc", "#5a3aa8"),
    "slate": ("#64748b", "#334155", "#f8fafc", "#e9eef5", "#64748b", "#475569"),
    "rose": ("#d1435b", "#9b1c32", "#fff6f7", "#fde2e7", "#df5a70", "#bf3049"),
}
INK = "#17233b"
MUTED = "#5b6b85"
# Drawings can render at about 0.9x on mid-size screens; this keeps every label near 10px or more.
MIN_FONT = 11.2
FONT_MONO = "ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"


# --------------------------------------------------------------------------
# Text measurement: a width estimate used for wrapping labels inside cards
# --------------------------------------------------------------------------
NARROW = set("iljtfr.,:;'|!() []")
WIDE = set("mwMW@%")


def text_width(s: str, size: float, bold: bool = False, mono: bool = False) -> float:
    size = max(size, MIN_FONT)
    if mono:
        return len(s) * size * 0.62
    w = 0.0
    for ch in s:
        if ch in NARROW:
            w += 0.32
        elif ch in WIDE:
            w += 0.86
        elif ch.isupper():
            w += 0.68
        elif ch.isdigit():
            w += 0.58
        elif ch in "#$&+=<>→←↔×…–—·":
            w += 0.62
        else:
            w += 0.55
    return w * size * (1.07 if bold else 1.0)


def wrap(s: str, max_w: float, size: float, bold=False, mono=False) -> list[str]:
    words = s.split(" ")
    lines, cur = [], ""
    for word in words:
        trial = (cur + " " + word).strip()
        if cur and text_width(trial, size, bold, mono) > max_w:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines


def esc(s) -> str:
    return html.escape(str(s), quote=True)


def f(n: float) -> str:
    return f"{n:.1f}".rstrip("0").rstrip(".")


# --------------------------------------------------------------------------
# Small icon set, drawn on a 16 x 16 grid
# --------------------------------------------------------------------------
ICONS = {
    "cpu": '<rect x="4" y="4" width="8" height="8" rx="1.5"/><path d="M6 1.5v2.5M10 1.5v2.5M6 12v2.5M10 12v2.5M1.5 6h2.5M1.5 10h2.5M12 6h2.5M12 10h2.5"/>',
    "db": '<ellipse cx="8" cy="3.6" rx="5.5" ry="2"/><path d="M2.5 3.6v8.8c0 1.1 2.5 2 5.5 2s5.5-.9 5.5-2V3.6M2.5 8c0 1.1 2.5 2 5.5 2s5.5-.9 5.5-2"/>',
    "file": '<path d="M4 1.5h5.5L13 5v9.5H4z"/><path d="M9.5 1.5V5H13"/>',
    "server": '<rect x="2" y="2" width="12" height="5" rx="1.2"/><rect x="2" y="9" width="12" height="5" rx="1.2"/><path d="M4.5 4.5h1M4.5 11.5h1"/>',
    "layers": '<path d="M8 2 14 5 8 8 2 5z"/><path d="M2 8l6 3 6-3M2 11l6 3 6-3"/>',
    "gear": '<circle cx="8" cy="8" r="2.4"/><path d="M8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2M3.4 3.4l1.4 1.4M11.2 11.2l1.4 1.4M3.4 12.6l1.4-1.4M11.2 4.8l1.4-1.4"/>',
    "grid": '<rect x="2" y="2" width="12" height="12" rx="1.5"/><path d="M2 6.5h12M2 10.5h12M6.5 2v12"/>',
    "clock": '<circle cx="8" cy="8" r="6"/><path d="M8 4.5V8l2.5 1.5"/>',
    "code": '<path d="M5.5 4 2 8l3.5 4M10.5 4 14 8l-3.5 4"/>',
    "stream": '<path d="M1.5 5h9M1.5 8h13M1.5 11h9"/><circle cx="13" cy="5" r="1"/><circle cx="13" cy="11" r="1"/>',
    "search": '<circle cx="7" cy="7" r="4.5"/><path d="m10.5 10.5 4 4"/>',
    "key": '<circle cx="5" cy="8" r="3"/><path d="M8 8h6.5M12 8v2.5M14.5 8v2"/>',
    "table": '<rect x="1.5" y="2.5" width="13" height="11" rx="1.5"/><path d="M1.5 6h13M1.5 9.5h13M6 6v7.5"/>',
    "chart": '<path d="M2 14h12"/><rect x="3" y="8" width="2.5" height="6"/><rect x="7" y="4" width="2.5" height="10"/><rect x="11" y="10" width="2.5" height="4"/>',
    "check": '<path d="m3 8.5 3 3 7-7"/>',
    "cross": '<path d="m4 4 8 8M12 4l-8 8"/>',
    "send": '<path d="M2 8h11M9 4l4 4-4 4"/>',
    "app": '<rect x="2" y="2.5" width="12" height="11" rx="1.5"/><path d="M2 5.5h12M4 4h.5M5.8 4h.5"/>',
}


class Svg:
    """A tiny builder for one SVG drawing."""

    def __init__(self, uid: str, w: int, h: int, label: str):
        self.uid, self.w, self.h, self.label = uid, w, h, label
        self.body: list[str] = []
        self.tones_used: set[str] = set()

    # ---- primitives -------------------------------------------------------
    def add(self, s: str):
        self.body.append(s)

    def text(self, x, y, s, size=12.5, weight=600, fill=INK, anchor="middle", mono=False, cls="", spacing=None, italic=False):
        size = max(size, MIN_FONT)
        fam = f' font-family="{FONT_MONO}"' if mono else ""
        ls = f' letter-spacing="{spacing}"' if spacing else ""
        st = ' font-style="italic"' if italic else ""
        c = f' class="{cls}"' if cls else ""
        self.add(
            f'<text x="{f(x)}" y="{f(y)}" font-size="{size}" font-weight="{weight}" fill="{fill}" '
            f'text-anchor="{anchor}" dominant-baseline="central"{fam}{ls}{st}{c}>{esc(s)}</text>'
        )

    def lines(self, x, y, rows, size=12.5, weight=600, fill=INK, anchor="middle", mono=False, gap=1.3):
        """Draw several lines centred vertically on y."""
        n = len(rows)
        top = y - (n - 1) * size * gap / 2
        for i, r in enumerate(rows):
            self.text(x, top + i * size * gap, r, size, weight, fill, anchor, mono)

    def icon(self, name, x, y, size=16, color=INK, stroke_w=1.6):
        k = size / 16
        self.add(
            f'<g transform="translate({f(x)},{f(y)}) scale({k:.3f})" fill="none" stroke="{color}" '
            f'stroke-width="{stroke_w / k:.2f}" stroke-linecap="round" stroke-linejoin="round">{ICONS[name]}</g>'
        )

    def grad(self, tone, solid=False):
        self.tones_used.add(tone)
        return f"url(#{self.uid}-{'s' if solid else 'g'}-{tone})"

    # ---- composite shapes ---------------------------------------------------
    def lane(self, x, y, w, h, tone, title=None, sub=None, dashed=False, icon=None):
        stroke, deep, top, _, _, _ = TONES[tone]
        self.tones_used.add(tone)
        da = ' stroke-dasharray="5 5"' if dashed else ""
        self.add(
            f'<rect x="{f(x)}" y="{f(y)}" width="{f(w)}" height="{f(h)}" rx="16" fill="{top}" '
            f'stroke="{stroke}" stroke-opacity=".35" stroke-width="1.2"{da}/>'
        )
        if title:
            tx = x + 14
            if icon:
                self.icon(icon, x + 13, y + 11, 14, deep)
                tx = x + 33
            self.text(tx, y + 18, title.upper(), 10.5, 800, deep, "start", spacing="1.1")
            if sub:
                tw = text_width(title.upper(), 10.5, True) + 1.1 * len(title)
                self.text(tx + tw + 8, y + 18, sub, 11, 600, MUTED, "start")

    def card(self, x, y, w, h, tone, title, sub=None, style="soft", icon=None, mono=False,
             size=13.5, sub_size=11.5, dashed=False, shadow=True, pad=12):
        stroke, deep, top, bottom, s_top, s_bot = TONES[tone]
        self.tones_used.add(tone)
        if style == "solid":
            fill, tcol, scol, bstroke = self.grad(tone, True), "#ffffff", "#ffffffd9", s_bot
        elif style == "ghost":
            fill, tcol, scol, bstroke = "#ffffff", deep, MUTED, stroke
        else:
            fill, tcol, scol, bstroke = self.grad(tone), deep, MUTED, stroke
        da = ' stroke-dasharray="5 4"' if dashed else ""
        flt = f' filter="url(#{self.uid}-sh)"' if shadow else ""
        self.add('<g class="dg-card">')
        self.add(
            f'<rect x="{f(x)}" y="{f(y)}" width="{f(w)}" height="{f(h)}" rx="11" fill="{fill}" '
            f'stroke="{bstroke}" stroke-width="1.4"{da}{flt}/>'
        )
        cx = x + w / 2
        if icon:
            # icon in a small round plate on the left
            px, py = x + pad + 13, y + h / 2
            plate = "#ffffff33" if style == "solid" else "#ffffff"
            self.add(f'<circle cx="{f(px)}" cy="{f(py)}" r="13" fill="{plate}" stroke="{stroke if style != "solid" else "#ffffff66"}" stroke-width="1"/>')
            self.icon(icon, px - 8, py - 8, 16, tcol if style == "solid" else stroke)
            text_left = px + 13 + 8
            cx = text_left + (x + w - pad - text_left) / 2
            avail = x + w - pad - text_left
        else:
            avail = w - 2 * pad
        anchor = "middle"
        t_lines = wrap(title, avail, size, True, mono)
        s_lines = wrap(sub, avail, sub_size) if sub else []
        th = len(t_lines) * size * 1.22
        sh = len(s_lines) * sub_size * 1.3
        block = th + (4 + sh if s_lines else 0)
        ty = y + h / 2 - block / 2 + size * 0.61
        for i, ln in enumerate(t_lines):
            self.text(cx, ty + i * size * 1.22, ln, size, 750, tcol, anchor, mono)
        sy = ty + (len(t_lines) - 1) * size * 1.22 + size * 0.61 + 4 + sub_size * 0.65
        for i, ln in enumerate(s_lines):
            self.text(cx, sy + i * sub_size * 1.3, ln, sub_size, 600, scol, anchor)
        self.add("</g>")

    def pill(self, x, y, s, tone, solid=False, anchor="middle", size=11, mono=False):
        stroke, deep, *_ = TONES[tone]
        self.tones_used.add(tone)
        tw = text_width(s, size, True, mono)
        w, h = tw + 14, size + 9
        x0 = x - w / 2 if anchor == "middle" else (x - w if anchor == "end" else x)
        fill = self.grad(tone, True) if solid else "#ffffff"
        col = "#ffffff" if solid else deep
        self.add(
            f'<g class="dg-pill"><rect x="{f(x0)}" y="{f(y - h / 2)}" width="{f(w)}" height="{f(h)}" rx="{f(h / 2)}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="1"/>'
        )
        self.text(x0 + w / 2, y, s, size, 750, col, "middle", mono)
        self.add("</g>")
        return w

    def step(self, x, y, n, tone="blue", r=10.5):
        self.add(f'<circle cx="{f(x)}" cy="{f(y)}" r="{r}" fill="{self.grad(tone, True)}" stroke="#ffffff" stroke-width="2"/>')
        self.text(x, y + 0.5, str(n), 11.5, 800, "#ffffff")

    def path(self, d, tone, width=1.8, dashed=False, flow=False, arrow=True, opacity=1.0, start_arrow=False):
        stroke = TONES[tone][0]
        self.tones_used.add(tone)
        cls = ' class="dg-flow"' if flow else ""
        da = ' stroke-dasharray="5 5"' if dashed and not flow else ""
        me = f' marker-end="url(#{self.uid}-a-{tone})"' if arrow else ""
        ms = f' marker-start="url(#{self.uid}-a-{tone})"' if start_arrow else ""
        op = f' stroke-opacity="{opacity}"' if opacity != 1 else ""
        self.add(f'<path d="{d}" fill="none" stroke="{stroke}" stroke-width="{f(width)}" stroke-linecap="round" stroke-linejoin="round"{da}{op}{cls}{me}{ms}/>')

    def line(self, x1, y1, x2, y2, tone, **kw):
        self.path(f"M{f(x1)},{f(y1)} L{f(x2)},{f(y2)}", tone, **kw)

    def curve(self, x1, y1, x2, y2, tone, vertical=False, **kw):
        if vertical:
            my = (y1 + y2) / 2
            d = f"M{f(x1)},{f(y1)} C{f(x1)},{f(my)} {f(x2)},{f(my)} {f(x2)},{f(y2)}"
        else:
            mx = (x1 + x2) / 2
            d = f"M{f(x1)},{f(y1)} C{f(mx)},{f(y1)} {f(x2)},{f(y2)} {f(x2)},{f(y2)}"
        self.path(d, tone, **kw)

    def elbow(self, pts, tone, r=10, **kw):
        """Polyline with rounded corners through the given points."""
        d = f"M{f(pts[0][0])},{f(pts[0][1])}"
        for i in range(1, len(pts) - 1):
            (x0, y0), (x1, y1), (x2, y2) = pts[i - 1], pts[i], pts[i + 1]
            def toward(ax, ay, bx, by, dist):
                L = max(((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5, 1e-6)
                k = min(dist, L / 2) / L
                return ax + (bx - ax) * k, ay + (by - ay) * k
            ax, ay = toward(x1, y1, x0, y0, r)
            bx, by = toward(x1, y1, x2, y2, r)
            d += f" L{f(ax)},{f(ay)} Q{f(x1)},{f(y1)} {f(bx)},{f(by)}"
        d += f" L{f(pts[-1][0])},{f(pts[-1][1])}"
        self.path(d, tone, **kw)

    # ---- output -------------------------------------------------------------
    def render(self, cls: str) -> str:
        defs = [
            f'<filter id="{self.uid}-sh" x="-10%" y="-10%" width="120%" height="140%">'
            f'<feDropShadow dx="0" dy="2" stdDeviation="2.4" flood-color="#1b2f6b" flood-opacity=".10"/></filter>'
        ]
        for t in sorted(self.tones_used | {"slate"}):
            stroke, deep, top, bottom, s_top, s_bot = TONES[t]
            defs.append(
                f'<linearGradient id="{self.uid}-g-{t}" x1="0" y1="0" x2="0" y2="1">'
                f'<stop offset="0" stop-color="{top}"/><stop offset="1" stop-color="{bottom}"/></linearGradient>'
                f'<linearGradient id="{self.uid}-s-{t}" x1="0" y1="0" x2="0" y2="1">'
                f'<stop offset="0" stop-color="{s_top}"/><stop offset="1" stop-color="{s_bot}"/></linearGradient>'
                f'<marker id="{self.uid}-a-{t}" viewBox="0 0 10 10" refX="8.6" refY="5" markerWidth="7" '
                f'markerHeight="7" orient="auto-start-reverse" markerUnits="userSpaceOnUse">'
                f'<path d="M0,0.8 L10,5 L0,9.2 L2.6,5 z" fill="{stroke}"/></marker>'
            )
        return (
            f'<svg class="{cls}" viewBox="0 0 {self.w} {self.h}" role="img" aria-label="{esc(self.label)}" '
            f'xmlns="http://www.w3.org/2000/svg" font-family="inherit">'
            f'<defs>{"".join(defs)}</defs>{"".join(self.body)}</svg>'
        )


def pair(name, label, wide, narrow=None, keys=None, steps=None):
    """Assemble one figure block: wide + narrow drawing and optional key notes."""
    out = []
    if narrow is None:
        out.append(wide.render("dg-one"))
    else:
        out.append(wide.render("dg-w"))
        out.append(narrow.render("dg-n"))
    if steps:
        out.append('<ol class="dg-steps">' + "".join(f"<li>{s}</li>" for s in steps) + "</ol>")
    if keys:
        out.append('<dl class="dg-keys">' + "".join(f"<div><dt>{esc(k)}</dt><dd>{v}</dd></div>" for k, v in keys) + "</dl>")
    return "".join(out)


# ==========================================================================
# Figures
# ==========================================================================

def fig_architecture():
    label = ("Spark application: the driver asks the cluster manager for executors, the manager launches one executor on "
             "each worker node, and the driver sends tasks to the executors' cores.")

    def executor(s, x, y, w, name, tasks):
        s.card(x, y, w, 44, "blue", f"Executor {name}", "JVM process · 2 cores", icon="server", shadow=False)
        cw = (w - 10) / 2
        for i, t in enumerate(tasks):
            s.card(x + i * (cw + 10), y + 54, cw, 40, "blue", t, f"core {i + 1}", style="solid", size=12.5, sub_size=10.5, shadow=False)

    w = Svg("dg-arch-w", 800, 372, label)
    w.card(16, 136, 200, 116, "navy", "Driver", "SparkSession · plans jobs · schedules tasks", style="solid", icon="gear")
    w.card(584, 136, 200, 116, "slate", "Cluster manager", "YARN · Kubernetes · Standalone", icon="grid")
    for i, (yy, name, tasks) in enumerate([(52, "A", ("Task 1", "Task 2")), (212, "B", ("Task 3", "Task 4"))]):
        w.lane(280, yy, 240, 148, "slate", f"Worker node {name}", icon="server")
        executor(w, 296, yy + 38, 208, name, tasks)
    # 1 request
    w.elbow([(116, 136), (116, 24), (684, 24), (684, 136)], "slate", r=14, dashed=True)
    w.step(258, 24, 1, "slate")
    w.pill(400, 24, "request executors", "slate")
    # 2 launch
    w.curve(584, 172, 520, 112, "slate", dashed=True)
    w.curve(584, 216, 520, 272, "slate", dashed=True)
    w.pill(552, 194, "launch", "slate")
    w.step(552, 168, 2, "slate")
    # 3 tasks
    w.curve(216, 172, 296, 112, "blue", width=2, flow=True)
    w.curve(216, 216, 296, 272, "blue", width=2, flow=True)
    w.pill(248, 194, "tasks ⇄ status", "blue")
    w.step(248, 168, 3, "blue")

    n = Svg("dg-arch-n", 360, 522, label)
    n.card(12, 44, 158, 96, "navy", "Driver", "plans · schedules", style="solid", icon="gear", size=13, sub_size=11)
    n.card(190, 44, 158, 96, "slate", "Cluster manager", "YARN · K8s", icon="grid", size=13, sub_size=11)
    n.elbow([(91, 44), (91, 20), (269, 20), (269, 44)], "slate", r=10, dashed=True)
    n.step(180, 20, 1, "slate")
    for yy, name, tasks in [(178, "A", ("Task 1", "Task 2")), (356, "B", ("Task 3", "Task 4"))]:
        n.lane(40, yy, 280, 158, "slate", f"Worker node {name}", icon="server")
        executor(n, 54, yy + 40, 252, name, tasks)
    n.elbow([(26, 140), (26, 240), (54, 240)], "blue", r=10, width=2, flow=True)
    n.elbow([(26, 140), (26, 418), (54, 418)], "blue", r=10, width=2, flow=True)
    n.step(26, 160, 3, "blue")
    n.elbow([(334, 140), (334, 210), (320, 210)], "slate", r=8, dashed=True)
    n.elbow([(334, 140), (334, 388), (320, 388)], "slate", r=8, dashed=True)
    n.step(334, 160, 2, "slate")
    steps = [
        "<b>Request.</b> The driver asks the cluster manager for executors.",
        "<b>Launch.</b> The cluster manager starts an executor on each worker node.",
        "<b>Run.</b> The driver sends tasks to the executor cores and receives status and results.",
    ]
    return pair("architecture", label, w, n, steps=steps)


def fig_yarn_submit():
    label = ("spark-submit in cluster mode on YARN: spark-submit sends the application to the ResourceManager, the "
             "ResourceManager starts the ApplicationMaster with the driver in a container on node A, the ApplicationMaster "
             "asks the ResourceManager for executor containers, the NodeManagers on nodes B and C start the executors, and "
             "the executors register with the driver and run its tasks.")

    def node(s, x, y, w, h, name, cont, card, compact=False):
        s.lane(x, y, w, h, "slate", name, icon="server")
        nm_h = 40 if compact else 44
        s.card(x + 12, y + 32, w - 24, nm_h, "slate", "NodeManager", None if compact else "starts containers",
               style="ghost", size=12.5, sub_size=11, shadow=False)
        cy = y + 32 + nm_h + 10
        ch = h - (cy - y) - 12
        s.lane(x + 12, cy, w - 24, ch, "blue", cont, dashed=True)
        title, sub, tone = card
        s.card(x + 24, cy + 28, w - 48, ch - 40, tone, title, sub, style="solid", size=12.5 if compact else 13,
               sub_size=11, shadow=False)

    w = Svg("dg-yarn-w", 800, 456, label)
    w.card(16, 24, 190, 96, "slate", "spark-submit", "shell or EMR step", style="ghost", icon="code")
    w.card(290, 24, 190, 96, "slate", "ResourceManager", "primary node · scheduler", icon="grid")
    node(w, 16, 170, 240, 250, "Core node A", "Container 1",
         ("ApplicationMaster", "runs the driver in cluster mode", "navy"))
    node(w, 560, 24, 216, 190, "Core node B", "Container 2", ("Executor 1", "runs tasks", "blue"))
    node(w, 560, 236, 216, 190, "Task node C", "Container 3", ("Executor 2", "runs tasks", "blue"))
    # 1 submit
    w.line(206, 72, 290, 72, "slate", dashed=True)
    w.step(248, 72, 1, "slate")
    w.pill(248, 48, "submit", "slate")
    # 2 start the AM container
    w.elbow([(330, 120), (330, 224), (244, 224)], "slate", r=10, dashed=True)
    w.step(330, 160, 2, "slate")
    w.pill(287, 224, "start AM", "slate")
    # 3 AM asks for executor containers
    w.elbow([(244, 330), (420, 330), (420, 120)], "slate", r=10, dashed=True, start_arrow=True)
    w.step(420, 200, 3, "slate")
    w.pill(340, 330, "ask for executors", "slate")
    # 4 AM tells the NodeManagers to start executors
    w.elbow([(244, 380), (510, 380), (510, 78), (572, 78)], "slate", r=10, dashed=True)
    w.elbow([(510, 300), (510, 290), (572, 290)], "slate", r=10, dashed=True)
    w.step(510, 200, 4, "slate")
    w.pill(380, 380, "start executors", "slate")
    # 5 executors register with the driver; tasks and results
    w.elbow([(764, 156), (788, 156), (788, 440), (136, 440), (136, 408)], "blue", r=10, width=2, flow=True)
    w.elbow([(764, 368), (788, 368), (788, 390)], "blue", r=10, width=2, flow=True, arrow=False)
    w.step(470, 440, 5, "blue")
    w.pill(300, 440, "register · tasks ⇄ results", "blue")

    n = Svg("dg-yarn-n", 360, 562, label)
    n.card(18, 12, 150, 72, "slate", "spark-submit", "shell or EMR step", style="ghost", size=13, sub_size=11)
    n.card(198, 12, 150, 72, "slate", "ResourceManager", "primary node", size=13, sub_size=11)
    node(n, 18, 112, 330, 192, "Core node A", "Container 1",
         ("ApplicationMaster", "runs the driver", "navy"), compact=True)
    node(n, 18, 330, 160, 200, "Core node B", "Container 2", ("Executor 1", "runs tasks", "blue"), compact=True)
    node(n, 188, 330, 160, 200, "Task node C", "Container 3", ("Executor 2", "runs tasks", "blue"), compact=True)
    n.line(168, 48, 198, 48, "slate", dashed=True)
    n.step(183, 48, 1, "slate")
    n.line(300, 84, 300, 144, "slate", dashed=True)
    n.step(300, 106, 2, "slate")
    n.elbow([(336, 250), (354, 250), (354, 98), (330, 98), (330, 86)], "slate", r=6, dashed=True, start_arrow=True)
    n.step(342, 98, 3, "slate")
    n.elbow([(183, 292), (183, 318), (158, 318), (158, 360)], "slate", r=8, dashed=True)
    n.elbow([(183, 318), (326, 318), (326, 360)], "slate", r=8, dashed=True)
    n.step(183, 310, 4, "slate")
    n.elbow([(98, 518), (98, 548), (8, 548), (8, 250), (30, 250)], "blue", r=8, width=2, flow=True)
    n.elbow([(268, 518), (268, 548), (98, 548)], "blue", r=8, width=2, flow=True, arrow=False)
    n.step(183, 548, 5, "blue")
    steps = [
        "<b>Submit.</b> <code>spark-submit</code> sends the application to the ResourceManager. "
        "It also copies the application files to a staging folder in HDFS.",
        "<b>Start the AM.</b> The scheduler finds free space in the queue. "
        "The ResourceManager tells one NodeManager to start the ApplicationMaster in container 1.",
        "<b>Ask for executors.</b> The ApplicationMaster registers with the ResourceManager. "
        "It asks for one container for each executor.",
        "<b>Start executors.</b> The ResourceManager gives containers on nodes that have free space. "
        "The ApplicationMaster tells the NodeManager on each node to start an executor in its container.",
        "<b>Run.</b> Each executor registers with the driver. The driver sends tasks and receives the results. "
        "At the end, the ApplicationMaster unregisters and YARN releases all the containers.",
    ]
    return pair("yarn-submit", label, w, n, steps=steps)


def fig_planning():
    label = ("Transformations only record a plan. The show() action starts a job: Spark turns the logical plan into a "
             "physical plan, runs stage 1, shuffles, runs stage 2 and returns rows to show().")
    w = Svg("dg-plan-w", 800, 322, label)
    w.lane(16, 14, 768, 96, "slate", "Your PySpark code", "transformations are recorded, not run", icon="code")
    code = [(32, 168, "spark.read…", "source"), (212, 196, '.filter(status = …)', "recorded"),
            (420, 220, '.groupBy("merchant").sum()', "recorded")]
    for x, cw, t, sub in code:
        w.card(x, 44, cw, 52, "slate", t, sub, style="ghost", mono=True, size=12, dashed=True, shadow=False)
    for (x1, w1, *_), (x2, *_) in zip(code, code[1:]):
        w.line(x1 + w1 + 4, 70, x2 - 4, 70, "slate", width=1.4)
    w.card(668, 44, 104, 52, "violet", "show()", "action", style="solid", mono=True, size=13)
    # bracket under transformations, then stem to logical plan
    w.path("M36,116 v8 H636 v-8", "slate", width=1.4, arrow=False)
    w.line(96, 124, 96, 196, "slate", width=1.6, dashed=True)
    w.pill(96, 142, "builds the plan", "slate")
    # show() triggers the job
    w.elbow([(690, 96), (690, 152), (238, 152), (238, 196)], "violet", r=12, width=2)
    w.pill(470, 152, "starts a job", "violet", solid=True)
    w.lane(16, 168, 768, 140, "blue", "Spark engine", icon="gear")
    nodes = [(32, 128, "Logical plan", "what to compute", "blue", "soft"),
             (174, 128, "Physical plan", "how to run it", "blue", "soft"),
             (316, 150, "Stage 1", "scan · filter · partial sum", "blue", "solid"),
             (480, 84, "Shuffle", "by merchant", "amber", "soft"),
             (578, 82, "Stage 2", "merge", "blue", "solid"),
             (674, 98, "3 rows", "back to show()", "violet", "soft")]
    for x, nw, t, sub, tone, st in nodes:
        w.card(x, 206, nw, 76, tone, t, sub, style=st, size=13)
    for (x1, w1, *_), (x2, *r) in zip(nodes, nodes[1:]):
        tone = "amber" if r[3] == "amber" or x1 == 480 else "blue"
        w.line(x1 + w1 + 3, 244, x2 - 3, 244, tone, width=1.8, flow=tone == "amber")
    w.line(746, 206, 746, 98, "violet", width=2)

    n = Svg("dg-plan-n", 360, 640, label)
    n.lane(12, 10, 336, 248, "slate", "Your PySpark code", icon="code")
    rows = [("spark.read…", 44), ('.filter(status = …)', 96), ('.groupBy("merchant").sum()', 148)]
    for t, y in rows:
        n.card(28, y, 230, 42, "slate", t, None, style="ghost", mono=True, size=11.5, dashed=True, shadow=False)
    n.path("M264,48 h8 V186 h-8", "slate", width=1.4, arrow=False)
    n.text(300, 104, "recorded", 11, 700, MUTED)
    n.text(300, 120, "only", 11, 700, MUTED)
    n.card(28, 200, 230, 44, "violet", "show()  · action", None, style="solid", mono=True, size=12.5)
    n.line(143, 244, 143, 296, "violet", width=2)
    n.pill(240, 272, "starts a job", "violet", solid=True)
    n.lane(12, 298, 336, 332, "blue", "Spark engine", icon="gear")
    vn = [("Logical plan", "what to compute", "blue", "soft"), ("Physical plan", "how to run it", "blue", "soft"),
          ("Stage 1", "scan · filter · partial sum", "blue", "solid"), ("Shuffle", "by merchant", "amber", "soft"),
          ("Stage 2", "merge → 3 rows to show()", "blue", "solid")]
    for i, (t, sub, tone, st) in enumerate(vn):
        y = 332 + i * 58
        n.card(40, y, 280, 44, tone, t, sub, style=st, size=12.5, sub_size=11)
        if i:
            tn = "amber" if tone == "amber" or vn[i - 1][2] == "amber" else "blue"
            n.line(180, y - 13, 180, y - 2, tn, width=1.8)
    keys = [("Transformation", "Adds a step to the plan. Nothing runs yet."),
            ("Action", "Asks for a result, so Spark plans and runs a job."),
            ("Shuffle", "Moves rows between tasks. It usually separates two stages.")]
    return pair("planning", label, w, n, keys=keys)


def fig_job():
    label = ("One job with two stages: four stage-1 tasks each write shuffle data for both stage-2 tasks; the two "
             "stage-2 tasks merge the partial sums into three merchant totals.")
    w = Svg("dg-job-w", 800, 338, label)
    w.lane(16, 14, 290, 310, "blue", "Stage 1", "4 tasks · one per partition")
    ys = [52, 118, 184, 250]
    for i, y in enumerate(ys):
        w.card(30, y, 262, 58, "blue", f"Task {i + 1} · reads P{i + 1}", "scan → filter → partial sum", size=13)
    w.lane(490, 14, 168, 310, "blue", "Stage 2", "2 tasks")
    ry = [86, 206]
    for j, y in enumerate(ry):
        w.card(504, y, 140, 76, "blue", f"Task {j + 5}", f"partition {j + 1} · merge", style="solid", size=13)
    for y in ys:
        for y2 in ry:
            w.curve(292, y + 29, 504, y2 + 38, "amber", width=1.6, flow=True, opacity=.85)
    w.pill(398, 30, "shuffle: write by key → fetch", "amber")
    w.card(682, 128, 102, 92, "violet", "3 totals", "one per merchant", size=13.5)
    for y in ry:
        w.curve(644, y + 38, 682, 174, "violet", width=1.8)

    n = Svg("dg-job-n", 360, 560, label)
    n.lane(12, 10, 336, 196, "blue", "Stage 1", "4 tasks")
    pos = [(26, 44), (186, 44), (26, 124), (186, 124)]
    for i, (x, y) in enumerate(pos):
        n.card(x, y, 148, 66, "blue", f"Task {i + 1} · P{i + 1}", "scan → filter → partial sum", size=12.5, sub_size=10.5)
    n.lane(12, 330, 336, 120, "blue", "Stage 2", "2 tasks")
    r2 = [(26, 364), (186, 364)]
    for j, (x, y) in enumerate(r2):
        n.card(x, y, 148, 70, "blue", f"Task {j + 5}", f"partition {j + 1} · merge", style="solid", size=12.5, sub_size=10.5)
    for x in (100, 260):
        n.curve(x, 206, 180, 266, "amber", vertical=True, width=1.8, flow=True, arrow=False)
        n.curve(180, 266, x, 330, "amber", vertical=True, width=1.8, flow=True)
    n.pill(180, 266, "shuffle: write by key → fetch", "amber")
    n.card(100, 478, 160, 64, "violet", "3 totals", "one per merchant", size=13)
    for x, y in r2:
        n.curve(x + 74, y + 70, 180, 478, "violet", vertical=True, width=1.8)
    keys = [("Task count", "A stage runs one task for each partition it reads. Stage 1 has 4; stage 2 has 2."),
            ("Every-to-every", "Each stage-1 task writes a piece for each stage-2 task. That is why a shuffle is costly.")]
    return pair("job", label, w, n, keys=keys)


def fig_dependencies():
    label = ("Narrow: each output partition reads one input partition, so Spark keeps the work in one stage. "
             "Wide: rows with key A and key B are spread over all inputs, so a shuffle regroups them into new partitions.")

    def panel(s, x, y, pw):
        s.lane(x, y, pw, 250, "blue", "Narrow · filter, select")
        bw = (pw - 28 - 2 * 12) / 3
        for i in range(3):
            bx = x + 14 + i * (bw + 12)
            s.card(bx, y + 44, bw, 52, "blue", f"P{i + 1}", "input", size=13)
            s.line(bx + bw / 2, y + 100, bx + bw / 2, y + 150, "blue", width=2)
            s.card(bx, y + 154, bw, 52, "blue", f"P{i + 1}′", "output", style="solid", size=13)
        s.text(x + pw / 2, y + 228, "one parent each → same stage", 11.5, 700, TONES["blue"][1])

    def wide_panel(s, x, y, pw):
        s.lane(x, y, pw, 250, "amber", "Wide · groupBy, join")
        bw = (pw - 28 - 2 * 12) / 3
        keys = [("A", "B", "A"), ("B", "A", "B"), ("A", "B", "B")]
        cx_out = [x + 14 + (pw - 28) * 0.25, x + 14 + (pw - 28) * 0.75]
        ow = (pw - 28 - 16) / 2
        for i in range(3):
            bx = x + 14 + i * (bw + 12)
            s.card(bx, y + 44, bw, 52, "blue", "", None)
            s.text(bx + bw / 2, y + 60, f"P{i + 1}", 13, 750, TONES["blue"][1])
            for k, key in enumerate(keys[i]):
                dx = bx + bw / 2 + (k - 1) * 22
                s.add(f'<circle cx="{f(dx)}" cy="{f(y + 81)}" r="8" fill="#fff" stroke="{TONES["slate"][0]}" stroke-width="1"/>')
                s.text(dx, y + 81.5, key, 10.5, 800, TONES["slate"][1])
            s.curve(bx + bw / 2 - 10, y + 96, cx_out[0], y + 154, "amber", vertical=True, width=1.6, flow=True)
            s.curve(bx + bw / 2 + 10, y + 96, cx_out[1], y + 154, "amber", vertical=True, width=1.6, flow=True)
        for j, key in enumerate("AB"):
            ox = x + 14 + j * (ow + 16)
            s.card(ox, y + 154, ow, 52, "blue", f"key {key} rows", "new partition", style="solid", size=13)
        s.text(x + pw / 2, y + 228, "rows regroup by key → shuffle, new stage", 11.5, 700, TONES["amber"][1])

    w = Svg("dg-dep-w", 800, 266, label)
    panel(w, 16, 8, 376)
    wide_panel(w, 408, 8, 376)
    n = Svg("dg-dep-n", 360, 524, label)
    panel(n, 12, 8, 336)
    wide_panel(n, 12, 270, 336)
    keys = [("Narrow", "Spark chains narrow steps inside one task, with no data movement."),
            ("Wide", "A child partition needs rows from many parents, so Spark shuffles and starts a new stage.")]
    return pair("dependencies", label, w, n, keys=keys)


def fig_executors():
    label = "Three executors with two cores each give six task slots. Four partitions make four tasks, so two slots stay idle."
    w = Svg("dg-slots-w", 800, 236, label)
    tasks = [("Task 1", "P1"), ("Task 2", "P2"), ("Task 3", "P3"), ("Task 4", "P4"), None, None]
    for e in range(3):
        x = 16 + e * 260
        w.lane(x, 10, 248, 136, "blue", f"Executor {'ABC'[e]}", "2 cores")
        for c in range(2):
            t = tasks[e * 2 + c]
            cx = x + 14 + c * 114
            if t:
                w.card(cx, 46, 106, 84, "blue", t[0], f"{t[1]} · core {c + 1}", style="solid", size=13, sub_size=11)
            else:
                w.card(cx, 46, 106, 84, "slate", "idle", f"core {c + 1}", style="ghost", dashed=True, size=12.5, shadow=False)
    # utilisation meter
    w.text(16, 178, "TASK SLOTS IN USE", 10.5, 800, TONES["blue"][1], "start", spacing="1.1")
    for i in range(6):
        x = 170 + i * 74
        if i < 4:
            w.add(f'<rect x="{x}" y="166" width="68" height="24" rx="6" fill="{w.grad("blue", True)}"/>')
        else:
            w.add(f'<rect x="{x}" y="166" width="68" height="24" rx="6" fill="#fff" stroke="{TONES["slate"][0]}" stroke-dasharray="4 3"/>')
    w.text(624, 178, "4 of 6", 13, 800, INK, "start")
    w.text(16, 212, "4 partitions → 4 tasks. More executors would not add tasks; more partitions would.", 12, 600, MUTED, "start")

    n = Svg("dg-slots-n", 360, 470, label)
    for e in range(3):
        y = 8 + e * 124
        n.lane(12, y, 336, 112, "blue", f"Executor {'ABC'[e]}", "2 cores")
        for c in range(2):
            t = tasks[e * 2 + c]
            cx = 26 + c * 158
            if t:
                n.card(cx, y + 38, 150, 60, "blue", t[0], f"{t[1]} · core {c + 1}", style="solid", icon="cpu", size=12.5, sub_size=11)
            else:
                n.card(cx, y + 38, 150, 60, "slate", "idle", f"core {c + 1}", style="ghost", dashed=True, size=12.5, shadow=False)
    for i in range(6):
        x = 12 + i * 46
        if i < 4:
            n.add(f'<rect x="{x}" y="392" width="42" height="22" rx="6" fill="{n.grad("blue", True)}"/>')
        else:
            n.add(f'<rect x="{x}" y="392" width="42" height="22" rx="6" fill="#fff" stroke="{TONES["slate"][0]}" stroke-dasharray="4 3"/>')
    n.text(292, 403, "4 of 6", 13, 800, INK, "start")
    n.text(12, 440, "4 partitions → 4 tasks · 2 slots idle", 12, 650, MUTED, "start")
    keys = [("Parallelism", "Tasks that run at the same time ≤ executors × cores. Here 3 × 2 = 6 slots."),
            ("Idle slots", "No ready task, too few partitions, or another bottleneck.")]
    return pair("executors", label, w, n, keys=keys)


def fig_skew():
    label = ("Task timeline: tasks 1, 2 and 4 read about 55 MB each and finish early; task 3 reads 410 MB, "
             "so the stage waits for it while the other cores sit idle.")
    data = [("Task 1", "P1", 60), ("Task 2", "P2", 55), ("Task 3", "P3", 410), ("Task 4", "P4", 52)]

    def draw(s, x0, x1, top, row, compact):
        scale = (x1 - x0) / 410
        end = x0 + 410 * scale
        # grid
        for mb in range(0, 401, 200 if compact else 100):
            gx = x0 + mb * scale
            s.add(f'<line x1="{f(gx)}" y1="{top - 8}" x2="{f(gx)}" y2="{top + 4 * row}" stroke="#e5eaf3" stroke-width="1"/>')
            s.text(gx, top + 4 * row + 14, f"{mb} MB" if mb else "0", 11, 600, MUTED)
        for i, (t, p, mb) in enumerate(data):
            y = top + i * row
            s.text(x0 - 10, y + row / 2 - 4, f"{t} · {p}", 12, 700, INK, "end")
            bw = mb * scale
            hot = mb > 100
            tone = "rose" if hot else "blue"
            if not hot:
                s.add(f'<rect x="{f(x0 + bw)}" y="{f(y + 4)}" width="{f(end - x0 - bw)}" height="{row - 16}" rx="6" '
                      f'fill="url(#{s.uid}-hatch)" stroke="#d6dde9" stroke-width="1"/>')
            s.add(f'<rect x="{f(x0)}" y="{f(y + 4)}" width="{f(bw)}" height="{row - 16}" rx="6" fill="{s.grad(tone, True)}"/>')
            if hot:
                s.text(x0 + bw - 10, y + row / 2 - 4, f"{mb} MB · the straggler", 12, 800, "#fff", "end")
            else:
                s.text(x0 + bw + 8, y + row / 2 - 4, f"{mb} MB", 12, 750, TONES["blue"][1], "start")
                if not compact:
                    s.text(x0 + bw + 60, y + row / 2 - 4, "done · core idle", 11, 600, MUTED, "start", italic=True)
        med = x0 + 57.5 * scale
        s.add(f'<line x1="{f(med)}" y1="{top - 14}" x2="{f(med)}" y2="{top + 4 * row - 4}" stroke="{TONES["slate"][1]}" stroke-width="1.4" stroke-dasharray="3 3"/>')
        s.pill(med, top - 22, "median 57.5 MB", "slate", size=10.5)
        s.add(f'<line x1="{f(end)}" y1="{top - 14}" x2="{f(end)}" y2="{top + 4 * row - 4}" stroke="{TONES["rose"][0]}" stroke-width="2"/>')
        s.pill(end, top - 22, "stage ends", "rose", solid=True, anchor="end", size=10.5)

    hatch = lambda uid: (f'<pattern id="{uid}-hatch" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
                         f'<rect width="7" height="7" fill="#f6f8fb"/><line x1="0" y1="0" x2="0" y2="7" stroke="#dfe5ee" stroke-width="3"/></pattern>')
    w = Svg("dg-skew-w", 800, 280, label)
    w.add(f"<defs>{hatch(w.uid)}</defs>")
    draw(w, 128, 772, 46, 46, False)
    w.text(450, 268, "shuffle read per task · task time grows with it", 11.5, 650, MUTED)
    n = Svg("dg-skew-n", 360, 272, label)
    n.add(f"<defs>{hatch(n.uid)}</defs>")
    draw(n, 102, 346, 46, 44, True)
    n.text(224, 260, "shuffle read per task", 11.5, 650, MUTED)
    keys = [("Read it", "Three tasks finish early. Their cores wait (hatched) until task 3 ends."),
            ("Effect", "The slowest task sets the stage time, not the average task.")]
    return pair("skew", label, w, n, keys=keys)


def fig_joins():
    label = ("Broadcast join: the driver sends one copy of the 50-row lookup to every executor. Each executor joins its own "
             "payment partitions locally, so the 2 million payment rows never move.")
    parts = [("P1", "P2"), ("P3",), ("P4",)]

    def executor(s, x, y, ew, e, compact):
        s.lane(x, y, ew, 176 if not compact else 132, "blue", f"Executor {e + 1}", icon="server")
        py = y + 40
        s.card(x + 14, py, ew - 28, 36, "amber", "lookup copy · 50 rows", None, size=12, shadow=False)
        pw = (ew - 28 - 8 * (len(parts[e]) - 1)) / len(parts[e])
        for k, p in enumerate(parts[e]):
            s.card(x + 14 + k * (pw + 8), py + 46, pw, 38, "blue", f"{p} · 500k rows" if len(parts[e]) == 1 or compact else f"{p} · 500k", None, size=12, shadow=False)
        if not compact:
            s.card(x + 14, py + 94, ew - 28, 34, "violet", "local hash join", None, style="solid", size=12, shadow=False)

    w = Svg("dg-bcast-w", 800, 342, label)
    w.card(280, 12, 240, 64, "navy", "Driver", "collects the 50-row lookup", style="solid", icon="gear")
    xs = [16, 282, 548]
    for e, x in enumerate(xs):
        executor(w, x, 142, 236, e, False)
        w.curve(400, 76, x + 186, 182, "amber", vertical=True, width=2, flow=True)
    w.pill(400, 110, "broadcast: one copy per executor", "amber")
    w.text(400, 332, "Payment partitions stay where they are · no shuffle of the large table", 12, 700, TONES["blue"][1])

    n = Svg("dg-bcast-n", 360, 552, label)
    n.card(80, 10, 200, 62, "navy", "Driver", "collects the lookup", style="solid", icon="gear", size=13)
    for e in range(3):
        y = 110 + e * 142
        executor(n, 40, y, 308, e, True)
        n.elbow([(100, 72), (100, 92), (20, 92), (20, y + 58), (54, y + 58)], "amber", r=8, width=1.8, flow=True)
    n.text(180, 538, "No shuffle of the 2M payment rows", 12, 700, TONES["blue"][1])
    keys = [("Use it when", "One side is small enough to copy to every executor."),
            ("Benefit", "Spark reads the large side in place. Only the small side crosses the network.")]
    return pair("joins", label, w, n, keys=keys)


def fig_memory():
    label = ("Without a cache, the second action reads and filters the source again. With persist(), the first action "
             "fills the cache and the second action reads it, which saves the repeated read.")
    RD, FL, RP, FC, RC = 116, 96, 86, 74, 76
    segs_no = [[("Read source", RD, "slate"), ("Filter", FL, "blue"), ("Report 1", RP, "violet")],
               [("Read again", RD, "rose"), ("Filter again", FL, "rose"), ("Report 2", RP, "violet")]]
    segs_yes = [[("Read source", RD, "slate"), ("Filter", FL, "blue"), ("Fill cache", FC, "blue"), ("Report 1", RP, "violet")],
                [("Read cache", RC, "blue"), ("Report 2", RP, "violet")]]

    def bar(s, x, y, segs, k=1.0, size=11.5):
        for t, sw, tone in segs:
            st = "solid" if t in ("Fill cache", "Read cache") else "soft"
            s.card(x, y, sw * k - 4, 34, tone, t, None, style=st, size=size, shadow=False, pad=4)
            x += sw * k
        return x

    w = Svg("dg-cache-w", 800, 300, label)
    w.lane(16, 10, 768, 124, "slate", "Without cache")
    w.lane(16, 150, 768, 136, "blue", "With persist()")
    x0 = 150
    for y, t in [(62, "Action 1"), (104, "Action 2"), (204, "Action 1"), (246, "Action 2")]:
        w.text(140, y, t, 12, 750, INK, "end")
    a1 = bar(w, x0, 45, segs_no[0])
    e1 = bar(w, a1 + 10, 87, segs_no[1])
    w.pill(x0 + 6, 172, "persist() only marks the plan", "blue", anchor="start", size=10.5)
    a1 = bar(w, x0, 187, segs_yes[0])
    e2 = bar(w, a1 + 10, 229, segs_yes[1])
    w.add(f'<rect x="{f(e2)}" y="229" width="{f(e1 - e2 - 4)}" height="34" rx="8" fill="#fff" stroke="{TONES["blue"][0]}" stroke-dasharray="4 3"/>')
    w.text((e1 + e2 - 4) / 2, 246, "time saved", 11, 800, TONES["blue"][1])

    n = Svg("dg-cache-n", 360, 384, label)
    n.lane(12, 8, 336, 152, "slate", "Without cache")
    n.lane(12, 176, 336, 200, "blue", "With persist()")
    k = 1.0
    n.text(26, 50, "Action 1", 11.5, 750, INK, "start")
    bar(n, 26, 60, segs_no[0], k, 11)
    n.text(26, 112, "Action 2 · repeats the work", 11.5, 750, TONES["rose"][1], "start")
    bar(n, 26, 122, segs_no[1], k, 11)
    n.pill(26, 214, "persist() only marks the plan", "blue", anchor="start", size=10.5)
    n.text(26, 238, "Action 1 · fills the cache", 11.5, 750, INK, "start")
    bar(n, 26, 248, segs_yes[0][:3], k, 11)
    n.text(26, 300, "… then Report 1 · Action 2 reads the cache", 11.5, 750, INK, "start")
    bar(n, 26, 310, segs_yes[1], k, 11)
    keys = [("Do not cache by default", "A cache uses executor memory and can evict other data or spill."),
            ("Good case", "Several actions reuse one costly DataFrame. Call unpersist() when they finish.")]
    return pair("memory", label, w, n, keys=keys)


def fig_storage():
    label = ("A 256 MB file is split into two Spark partitions at the 128 MB limit, and four small files are packed into "
             "one partition. Each of the three write tasks then writes its own output file.")

    def draw(s, W, compact):
        if compact:
            gx, cx0 = 10, 30          # rotated row labels in a left gutter
        else:
            gx, cx0 = 124, 140        # right-aligned row labels
        rows = [(8, 108, "Input files", "slate"), (156, 80, "Spark partitions", "blue"), (276, 80, "Output files", "violet")]
        for y, h, t, tone in rows:
            s.add(f'<rect x="{cx0}" y="{y}" width="{W - cx0 - 12}" height="{h}" rx="14" fill="{TONES[tone][2]}" stroke="{TONES[tone][0]}" stroke-opacity=".3"/>')
            if compact:
                s.add(f'<text transform="translate({gx + 6},{y + h / 2}) rotate(-90)" font-size="10.5" font-weight="800" fill="{TONES[tone][1]}" '
                      f'text-anchor="middle" dominant-baseline="central" letter-spacing="1">{esc(t.upper())}</text>')
            else:
                s.lines(gx, y + h / 2, wrap(t, 100, 12.5, True), 12.5, 800, TONES[tone][1], "end")
        inner = W - cx0 - 12 - 24
        gap = 12
        pw = (inner - 2 * gap) / 3
        px = [cx0 + 12 + i * (pw + gap) for i in range(3)]
        fw = 2 * pw + gap
        # file-1 as one card with two halves
        s.card(px[0], 22, fw, 66, "slate", "", None)
        half = fw / 2
        s.add(f'<line x1="{f(px[0] + half)}" y1="18" x2="{f(px[0] + half)}" y2="94" stroke="{TONES["slate"][1]}" stroke-width="1.5" stroke-dasharray="4 3"/>')
        for k in range(2):
            hx = px[0] + half * k + half / 2
            s.text(hx, 44, "file-1.parquet", 12 if not compact else 11, 750, TONES["slate"][1])
            s.text(hx, 64, f"bytes {k * 128}–{(k + 1) * 128} MB" if not compact else f"{k * 128}–{(k + 1) * 128} MB", 11, 600, MUTED)
        s.pill(px[0] + half, 98, "split at 128 MB", "slate", size=10.5)
        sw = (pw - 6) / 2
        for k, nm in enumerate(["file-2", "file-3", "file-4", "file-5"]):
            sx = px[2] + (k % 2) * (sw + 6)
            sy = 22 + (k // 2) * 34
            s.card(sx, sy, sw, 30, "slate", nm if compact else f"{nm} · 20 MB", None, size=10.5 if compact else 11, shadow=False, pad=3)
        s.line(px[0] + half / 2, 90, px[0] + half / 2, 184, "blue", width=2)
        s.line(px[0] + half * 1.5, 90, px[1] + pw / 2, 184, "blue", width=2)
        for k in range(4):
            sx = px[2] + (k % 2) * (sw + 6) + sw / 2
            s.curve(sx, 86, px[2] + pw / 2, 184, "blue", vertical=True, width=1.4)
        s.pill(px[2] + pw / 2, 130, "packed together", "blue", size=10.5)
        names = ["P1 · 128 MB", "P2 · 128 MB", "P3 · 80 MB"]
        for i in range(3):
            s.card(px[i], 186, pw, 46, "blue", names[i] if not compact else f"P{i + 1}", f"task {i + 1}" if not compact else names[i].split(" · ")[1], style="solid", size=12.5, sub_size=10.5)
            s.line(px[i] + pw / 2, 232, px[i] + pw / 2, 304, "violet", width=2, flow=True)
            s.card(px[i], 306, pw, 40, "violet", f"part-0000{i}", None, mono=True, size=11 if compact else 12.5)

    w = Svg("dg-files-w", 800, 360, label)
    draw(w, 800, False)
    n = Svg("dg-files-n", 360, 360, label)
    draw(n, 360, True)
    keys = [("Read side", "Spark splits large files and packs small ones (spark.sql.files.maxPartitionBytes)."),
            ("Write side", "Each write task that has rows writes at least one file. Here, 3 tasks give 3 or more files.")]
    return pair("storage", label, w, n, keys=keys)


def fig_streaming():
    label = ("Micro-batches: at each trigger Spark takes the events that arrived since the last batch, writes the planned "
             "offsets to the checkpoint, processes the batch, then writes a commit.")

    def draw(s, x0, step, nb, compact):
        trig = [x0 + i * step for i in range(nb + 1)]
        top = 44
        s.text(x0 - 10, top + 8, "Kafka", 11.5, 750, TONES["slate"][1], "end")
        s.text(x0 - 10, top + 74, "Spark", 11.5, 750, TONES["blue"][1], "end")
        s.text(x0 - 10, top + 136, "Checkpoint" if not compact else "Check-", 11.5, 750, TONES["slate"][1], "end")
        if compact:
            s.text(x0 - 10, top + 150, "point", 11.5, 750, TONES["slate"][1], "end")
        for yy in (top + 8, top + 136):
            s.add(f'<line x1="{x0}" y1="{yy}" x2="{trig[-1] + 10}" y2="{yy}" stroke="#d5dce8" stroke-width="1.5"/>')
        ev = [0.15, 0.36, 0.7, 1.12, 1.3, 1.62, 1.86, 2.2, 2.45, 2.7, 2.9, 3.3, 3.55, 3.8]
        for e in ev:
            if e > nb - 0.05:
                continue
            ex = x0 + e * step
            s.add(f'<circle cx="{f(ex)}" cy="{top + 8}" r="{4.5 if compact else 5.5}" fill="{TONES["slate"][0]}" stroke="#fff" stroke-width="1.5"/>')
        for i, tx in enumerate(trig):
            s.add(f'<line x1="{f(tx)}" y1="{top - 10}" x2="{f(tx)}" y2="{top + 158}" stroke="#c4cddc" stroke-width="1" stroke-dasharray="3 3"/>')
            s.text(tx, top + 172, f"t{i}", 11.5, 700, MUTED)
        bw = step * 0.7
        for b in range(1, nb):
            bx = trig[b]
            s.path(f"M{f(trig[b - 1] + 4)},{top + 20} Q{f((trig[b - 1] + bx) / 2)},{top + 32} {f(bx + 2)},{top + 54}",
                   "slate", width=1.2, opacity=.7)
            s.add(f'<rect x="{f(bx + 4)}" y="{top + 56}" width="{f(bw)}" height="36" rx="9" fill="{s.grad("blue", True)}"/>')
            s.text(bx + 4 + bw / 2, top + 74, f"Batch {b}", 12 if not compact else 11.5, 750, "#fff")
            s.add(f'<rect x="{f(bx - 1)}" y="{top + 131}" width="10" height="10" transform="rotate(45 {f(bx + 4)} {top + 136})" fill="{TONES["slate"][1]}"/>')
            s.add(f'<circle cx="{f(bx + 4 + bw)}" cy="{top + 136}" r="5.5" fill="#fff" stroke="{TONES["slate"][1]}" stroke-width="2"/>')
            s.line(bx + 4, top + 92, bx + 4, top + 128, "slate", width=1.2, arrow=False, dashed=True)
            s.line(bx + 4 + bw, top + 92, bx + 4 + bw, top + 130, "slate", width=1.2, arrow=False, dashed=True)
        if not compact:
            lx = trig[1] + 4
            s.text(lx + 10, top + 112, "offsets", 11, 700, TONES["slate"][1], "start")
            s.text(lx + bw - 8, top + 112, "commit", 11, 700, TONES["slate"][1], "end")
        if not compact:
            s.text(trig[-1] - 4, top + 74, "next…", 11.5, 650, MUTED, "end", italic=True)

    w = Svg("dg-stream-w", 800, 236, label)
    draw(w, 110, 168, 4, False)
    n = Svg("dg-stream-n", 360, 236, label)
    draw(n, 82, 90, 3, True)
    keys = [("Micro-batch", "Each trigger processes the events that arrived since the previous batch."),
            ("Checkpoint", "◆ Spark writes the offsets before a batch runs and ○ a commit after it. A restart resumes from them.")]
    return pair("streaming", label, w, n, keys=keys)


def fig_monitoring():
    label = ("Investigation loop: find the slow job, find its longest stage, compare its tasks, read the evidence, "
             "change one thing, then measure the same input again.")
    steps = [("Find the slow job", "Jobs tab", "search"), ("Longest stage", "Stages tab", "chart"),
             ("Compare tasks", "max vs median time", "cpu"), ("Read the evidence", "shuffle · spill · GC · input", "table"),
             ("Change one thing", "code or one setting", "gear")]
    w = Svg("dg-mon-w", 800, 214, label)
    cw = 140
    for i, (t, sub, ic) in enumerate(steps):
        x = 16 + i * (cw + 17)
        last = i == 4
        w.card(x, 30, cw, 96, "blue", t, sub, style="solid" if last else "soft", size=13, sub_size=11)
        w.step(x + 14, 30, i + 1, "blue")
        if i:
            w.line(x - 15, 78, x - 3, 78, "blue", width=1.8)
    w.elbow([(16 + 4 * 157 + 70, 126), (16 + 4 * 157 + 70, 170), (16 + 157 + 70, 170), (16 + 157 + 70, 130)], "blue", r=14, width=2, flow=True)
    w.pill(400, 170, "measure the same input again → repeat", "blue", solid=True)

    n = Svg("dg-mon-n", 360, 380, label)
    for i, (t, sub, ic) in enumerate(steps):
        y = 10 + i * 72
        last = i == 4
        n.card(36, y, 264, 56, "blue", t, sub, style="solid" if last else "soft", size=13, sub_size=11, icon=ic)
        n.step(36, y, i + 1, "blue")
        if i:
            n.line(168, y - 14, 168, y - 3, "blue", width=1.8)
    n.elbow([(300, 10 + 4 * 72 + 28), (334, 10 + 4 * 72 + 28), (334, 10 + 72 + 28), (302, 10 + 72 + 28)], "blue", r=12, width=2, flow=True)
    n.text(340, 210, "repeat", 11, 750, TONES["blue"][1], "end")
    keys = [("Rule", "Run the same input before and after one change, and compare the same metrics."),
            ("Spark UI", "Stage and task metrics show where time goes before you tune a setting.")]
    return pair("monitoring", label, w, n, keys=keys)


def fig_hbase_write():
    label = ("HBase write path: the client finds the region in hbase:meta, sends the Put to RegionServer A, which appends "
             "it to the WAL on HDFS, then writes it to the MemStore of region R2 and acknowledges. Later the MemStore "
             "flushes to an HFile.")
    w = Svg("dg-write-w", 800, 290, label)
    w.card(16, 20, 176, 66, "teal", "hbase:meta", "which region holds 01#…?", icon="search", size=13, sub_size=11)
    w.card(16, 136, 176, 84, "slate", "Client", "Put 01#TXN1003", icon="app", size=13.5)
    w.line(104, 136, 104, 90, "teal", width=1.8, dashed=True)
    w.step(104, 113, 1, "teal")
    w.lane(244, 12, 330, 266, "teal", "RegionServer A", icon="server")
    w.card(262, 48, 294, 212, "teal", "", None, shadow=False)
    w.text(278, 70, "Region R2 · keys 01# – 02#", 12.5, 800, TONES["teal"][1], "start")
    w.card(282, 100, 254, 136, "teal", "MemStore", "sorted cells in memory", style="solid", icon="layers", size=14)
    w.step(282, 100, 3, "teal")
    w.lane(616, 12, 168, 266, "slate", "HDFS", "durable", icon="db")
    w.card(630, 46, 140, 84, "slate", "WAL", "append-only log", icon="file", size=13.5)
    w.card(630, 168, 140, 84, "slate", "HFiles", "immutable, sorted", icon="file", size=13.5)
    w.curve(192, 160, 262, 128, "teal", width=2, flow=True)
    w.step(226, 142, 2, "teal")
    w.curve(262, 210, 192, 200, "slate", width=1.6, dashed=True)
    w.text(226, 224, "4 ack", 11.5, 750, TONES["slate"][1])
    w.curve(556, 84, 630, 86, "slate", width=2)
    w.text(593, 72, "append", 11.5, 750, TONES["slate"][1])
    w.curve(536, 200, 630, 210, "slate", width=2, dashed=True)
    w.step(586, 205, 5, "slate")

    n = Svg("dg-write-n", 360, 548, label)
    n.card(12, 10, 160, 64, "slate", "Client", "Put 01#TXN1003", icon="app", size=13)
    n.card(188, 10, 160, 64, "teal", "hbase:meta", "find the region", icon="search", size=13)
    n.line(172, 42, 188, 42, "teal", width=1.6, dashed=True)
    n.step(180, 82, 1, "teal")
    n.lane(12, 118, 336, 230, "teal", "RegionServer A", icon="server")
    n.card(26, 152, 308, 178, "teal", "", None, shadow=False)
    n.text(40, 172, "Region R2 · keys 01# – 02#", 12, 800, TONES["teal"][1], "start")
    n.card(44, 200, 272, 98, "teal", "MemStore", "sorted cells in memory", style="solid", icon="layers", size=14)
    n.step(44, 200, 3, "teal")
    n.line(70, 74, 70, 150, "teal", width=2, flow=True)
    n.step(70, 100, 2, "teal")
    n.line(110, 150, 110, 74, "slate", width=1.6, dashed=True)
    n.text(118, 100, "4 ack", 11.5, 750, TONES["slate"][1], "start")
    n.lane(12, 384, 336, 152, "slate", "HDFS", "durable", icon="db")
    n.card(26, 420, 146, 96, "slate", "WAL", "append-only log", icon="file", size=13)
    n.card(188, 420, 146, 96, "slate", "HFiles", "immutable, sorted", icon="file", size=13)
    n.line(99, 330, 99, 418, "slate", width=2)
    n.text(106, 364, "append", 11.5, 750, TONES["slate"][1], "start")
    n.line(261, 298, 261, 418, "slate", width=2, dashed=True)
    n.step(261, 362, 5, "slate")
    n.text(274, 362, "flush", 11.5, 750, TONES["slate"][1], "start")
    steps = [
        "<b>Locate.</b> The client finds the region for the row key in <code>hbase:meta</code> (and caches it).",
        "<b>Put.</b> The client sends the write to RegionServer A. The server appends it to the WAL on HDFS first.",
        "<b>MemStore.</b> The server adds the cell to region R2's MemStore, a sorted in-memory buffer.",
        "<b>Ack.</b> HBase acknowledges the write. The write is durable because the WAL holds it.",
        "<b>Flush.</b> Later, a full MemStore flushes to a new immutable HFile on HDFS.",
    ]
    return pair("hbase-write", label, w, n, steps=steps)


def fig_regions():
    label = ("The payments row-key space is cut into four regions at 01#, 02# and 03#. RegionServer A serves R1 and R2; "
             "RegionServer B serves R3 and R4.")
    regs = [("R1", "start", "01#", ["00#TXN1001", "00#TXN1002"]), ("R2", "01#", "02#", ["01#TXN1003", "01#TXN1004"]),
            ("R3", "02#", "03#", ["02#TXN1005", "02#TXN1006"]), ("R4", "03#", "end", ["03#TXN1007", "03#TXN1008"])]

    def draw(s, x0, segw, compact):
        y = 40
        h = 116 if not compact else 64
        s.text(x0, y - 18, "table start", 11, 650, MUTED, "start")
        s.text(x0 + 4 * segw, y - 18, "table end", 11, 650, MUTED, "end")
        for i, (r, a, b, rows) in enumerate(regs):
            x = x0 + i * segw
            s.card(x + 2, y, segw - 4, h, "teal", "", None, shadow=not compact)
            s.text(x + segw / 2, y + 20, r, 15, 850, TONES["teal"][1])
            if compact:
                rng = {"R1": "< 01#", "R4": "≥ 03#"}.get(r, f"{a}–{b}")
            else:
                rng = f"[{a}, {b})"
            s.text(x + segw / 2, y + 42, rng, 11, 650, MUTED, mono=True)
            if not compact:
                for k, row in enumerate(rows):
                    s.card(x + 12, y + 56 + k * 28, segw - 24, 24, "teal", row, None, style="ghost", mono=True, size=11, shadow=False)
        for k, b in enumerate(["01#", "02#", "03#"]):
            bx = x0 + (k + 1) * segw
            s.add(f'<line x1="{f(bx)}" y1="{y - 10}" x2="{f(bx)}" y2="{y + h + 6}" stroke="{TONES["teal"][1]}" stroke-width="1.5" stroke-dasharray="3 3"/>')
            s.pill(bx, y - 18, b, "teal", solid=True, mono=True, size=10.5)
        ry = y + h + 46
        rw = 2 * segw - 20
        for j, nm in enumerate("AB"):
            rx = x0 + j * 2 * segw + 10
            if compact:
                s.card(rx, ry, rw, 52, "teal", f"RegionServer {nm}", f"R{2 * j + 1} + R{2 * j + 2}", style="solid", size=12.5, sub_size=11)
            else:
                s.card(rx, ry, rw, 54, "teal", f"RegionServer {nm}", f"serves R{2 * j + 1} and R{2 * j + 2}", style="solid", icon="server", size=13, sub_size=11)
            for k in range(2):
                cx = x0 + (2 * j + k) * segw + segw / 2
                s.curve(cx, y + h, rx + rw / 2 + (k - 0.5) * 40, ry, "teal", vertical=True, width=1.6, arrow=False)

    w = Svg("dg-regions-w", 800, 290, label)
    draw(w, 24, 188, False)
    n = Svg("dg-regions-n", 360, 212, label)
    draw(n, 12, 84, True)
    keys = [("Region", "A contiguous, sorted row-key range. The range includes the start key but not the end key."),
            ("RegionServer", "One server serves many regions. HBase can move a region to another server.")]
    return pair("regions", label, w, n, keys=keys)


def fig_split():
    label = ("Region R2 (12 GB, keys 01# to 02#) splits at 01#TXN5000 into daughters R2a and R2b of about 6 GB each. "
             "The daughters first point at the parent's HFiles through reference files; compaction rewrites them later.")

    def draw(s, x0, W, compact):
        mid = x0 + W / 2
        s.text(x0, 22, "BEFORE", 10.5, 800, MUTED, "start", spacing="1.1")
        s.card(x0, 34, W, 60, "teal", "", None)
        s.text(x0 + 16, 56, "R2 · 12 GB", 14, 800, TONES["teal"][1], "start")
        s.text(x0 + 16, 76, "[01#, 02#)", 11.5, 600, MUTED, "start", mono=True)
        s.add(f'<line x1="{f(mid)}" y1="30" x2="{f(mid)}" y2="150" stroke="{TONES["teal"][1]}" stroke-width="1.6" stroke-dasharray="4 3"/>')
        s.add(f'<path d="M{f(mid - 6)},30 h12 l-6,8 z" fill="{TONES["teal"][1]}"/>')
        s.pill(mid, 120, "split key 01#TXN5000", "teal", solid=True, mono=True, size=10.5)
        s.text(x0, 140, "AFTER", 10.5, 800, MUTED, "start", spacing="1.1")
        for edge in (x0, x0 + W):
            s.add(f'<line x1="{f(edge)}" y1="96" x2="{f(edge)}" y2="150" stroke="#c4cddc" stroke-width="1.2" stroke-dasharray="3 3"/>')
        dw = W / 2 - 4
        for k, (nm, rng) in enumerate([("R2a · ~6 GB", "[01#, 01#TXN5000)"), ("R2b · ~6 GB", "[01#TXN5000, 02#)")]):
            dx = x0 if k == 0 else mid + 4
            s.card(dx, 152, dw, 64, "teal", "", None, style="solid")
            s.text(dx + dw / 2, 174, nm, 13.5, 800, "#fff")
            s.text(dx + dw / 2, 196, rng, 10.5 if compact else 11.5, 650, "#ffffffd9", mono=True)
            if not compact:
                s.pill(dx + dw - 10, 152, "new", "teal", anchor="end", size=10)
        hw = W * 0.46 if not compact else W * 0.6
        hx = mid - hw / 2
        s.card(hx, 278, hw, 50, "slate", "Parent HFiles", "unchanged on HDFS", icon="file", size=13, sub_size=11)
        s.elbow([(x0 + dw / 2, 216), (x0 + dw / 2, 303), (hx - 2, 303)], "slate", r=12, width=1.5, dashed=True)
        s.elbow([(mid + 4 + dw / 2, 216), (mid + 4 + dw / 2, 303), (hx + hw + 2, 303)], "slate", r=12, width=1.5, dashed=True)
        s.text(mid, 248, "reference files until compaction", 11, 700, TONES["slate"][1])

    w = Svg("dg-split-w", 800, 336, label)
    draw(w, 40, 720, False)
    n = Svg("dg-split-n", 360, 336, label)
    draw(n, 12, 336, True)
    keys = [("Range", "The two daughters cover exactly the parent's key range."),
            ("Storage", "A split does not copy data. Compaction rewrites the daughters' files later.")]
    return pair("split", label, w, n, keys=keys)


def fig_mapping():
    label = ("Default rule for a new scan with TableInputFormat: each of the four regions becomes one InputSplit, "
             "each split becomes one Spark partition, and each partition is read by one scan task.")
    cols = [("HBase region", "teal", "soft"), ("InputSplit", "slate", "soft"), ("Spark partition", "blue", "soft"), ("Scan task", "blue", "solid")]
    owners = [("HBASE", 0, 0, "teal"), ("CONNECTOR", 1, 1, "slate"), ("SPARK", 2, 3, "blue")]

    def draw(s, x0, cw, gap, row, compact):
        xs = [x0 + i * (cw + gap) for i in range(4)]
        for name, a, b, tone in owners:
            xa, xb = xs[a], xs[b] + cw
            s.add(f'<path d="M{f(xa)},28 v-8 H{f(xb)} v8" fill="none" stroke="{TONES[tone][0]}" stroke-width="1.4"/>')
            s.text((xa + xb) / 2, 10, name, 10.5, 800, TONES[tone][1], spacing="1.1")
        for i, (t, tone, _) in enumerate(cols):
            s.lines(xs[i] + cw / 2, 48, wrap(t, cw, 11.5, True), 11.5, 750, TONES[tone][1])
        rngs = ["00#–01#", "01#–02#", "02#–03#", "03# →"]
        for r in range(4):
            y = 72 + r * row
            vals = [(f"R{r + 1}", None if compact else rngs[r]), (f"Split {r + 1}", None), (f"P{r + 1}", None),
                    (f"T{r + 1}" if compact else f"Task {r + 1}", None)]
            for i, (t, sub) in enumerate(vals):
                _, tone, st = cols[i]
                s.card(xs[i], y, cw, row - 12, tone, t, sub, style=st, size=12.5, sub_size=10.5, shadow=not compact)
                if i:
                    s.line(xs[i - 1] + cw + 3, y + (row - 12) / 2, xs[i] - 3, y + (row - 12) / 2, cols[i][1] if i < 3 else "blue", width=1.6)
        return xs

    w = Svg("dg-map-w", 800, 286, label)
    xs = draw(w, 27, 140, 62, 52, False)
    w.pill((xs[0] + 140 + xs[1]) / 2, 48, "getSplits()", "slate", mono=True, size=10)
    n = Svg("dg-map-n", 360, 268, label)
    draw(n, 15, 66, 22, 48, True)
    keys = [("Connector assumption", "TableInputFormat makes one InputSplit per region by default. Other connectors and settings can make more or fewer."),
            ("Spark", "One task in the scan stage reads each initial partition, preferably on the region's host.")]
    return pair("mapping", label, w, n, keys=keys)


def fig_payment():
    label = ("Follow the 8 sample rows: each scan task drops FAILED rows and sums by merchant; the shuffle sends each "
             "merchant's partial sums to one of 2 merge tasks; the totals are Grocery $195, Travel $550, Energy $150.")
    tasks = [
        ("Task 1 · R1", [("Grocery", 120, True), ("Travel", 80, False)], [("Grocery", 120)]),
        ("Task 2 · R2", [("Travel", 250, True), ("Grocery", 75, True)], [("Travel", 250), ("Grocery", 75)]),
        ("Task 3 · R3", [("Energy", 110, True), ("Grocery", 60, False)], [("Energy", 110)]),
        ("Task 4 · R4", [("Travel", 300, True), ("Energy", 40, True)], [("Travel", 300), ("Energy", 40)]),
    ]
    totals = {"Grocery": 195, "Travel": 550, "Energy": 150}
    sources = {m: " + ".join(str(a) for _, _, ps in tasks for mm, a in ps if mm == m) for m in totals}

    def row_line(s, x, y, m, amt, ok, size=12):
        col = INK if ok else TONES["rose"][1]
        s.icon("check" if ok else "cross", x, y - 7, 13, TONES["teal"][0] if ok else TONES["rose"][0], 2)
        s.text(x + 18, y, f"{m} {amt}", size, 650, col, "start")
        if not ok:
            tw = text_width(f"{m} {amt}", size)
            s.add(f'<path d="M{f(x + 16)},{f(y)} h{f(tw + 4)}" stroke="{TONES["rose"][0]}" stroke-width="1.4"/>')

    w = Svg("dg-pay-w", 800, 436, label)
    w.text(16, 16, "STAGE 1 · SCAN, FILTER, PARTIAL SUM", 10.5, 800, TONES["blue"][1], "start", spacing="1")
    w.pill(392, 16, "shuffle by merchant", "amber")
    w.text(482, 16, "STAGE 2 · MERGE", 10.5, 800, TONES["blue"][1], "start", spacing="1")
    w.text(784, 16, "REPORT", 10.5, 800, TONES["violet"][1], "end", spacing="1")
    chip_pos = []
    for i, (t, rows, parts) in enumerate(tasks):
        y = 32 + i * 100
        w.card(16, y, 286, 88, "blue", "", None)
        w.text(30, y + 18, t, 12.5, 800, TONES["blue"][1], "start")
        for k, (m, a, ok) in enumerate(rows):
            row_line(w, 30, y + 44 + k * 24, m, a, ok)
        for k, (m, a) in enumerate(parts):
            cy = y + 44 + k * 24
            w.card(186, cy - 11, 104, 22, "blue", f"{m} {a}", None, style="solid", size=11, shadow=False)
            chip_pos.append((m, a, 290, cy))
    red = [(482, 52, 180, "Task 5 · partition 1", ["Grocery", "Energy"]), (482, 262, 116, "Task 6 · partition 2", ["Travel"])]
    slot_y = {}
    for x, y, h, t, ms in red:
        w.card(x, y, 170, h, "blue", "", None)
        w.text(x + 14, y + 20, t, 12.5, 800, TONES["blue"][1], "start")
        for k, m in enumerate(ms):
            sy = y + 62 + k * 64
            slot_y[m] = sy
            w.card(x + 12, sy - 22, 146, 44, "blue", m, sources[m], style="solid", size=12, sub_size=10.5, shadow=False)
    for m, a, x, y in chip_pos:
        w.curve(x, y, 494, slot_y[m], "amber", width=1 + a / 300 * 6, flow=True, opacity=.8)
    for m, sy in slot_y.items():
        w.card(682, sy - 22, 102, 44, "violet", m, f"${totals[m]}", style="solid", size=12.5, sub_size=12)
        w.line(652, sy, 680, sy, "violet", width=1.8)
    w.card(682, 362, 102, 44, "violet", "Total", "$895", size=12.5, sub_size=12)

    n = Svg("dg-pay-n", 360, 640, label)
    n.text(12, 14, "STAGE 1 · SCAN, FILTER, PARTIAL SUM", 10.5, 800, TONES["blue"][1], "start", spacing="1")
    for i, (t, rows, parts) in enumerate(tasks):
        y = 26 + i * 76
        n.card(12, y, 336, 68, "blue", "", None)
        n.text(24, y + 16, t, 12, 800, TONES["blue"][1], "start")
        for k, (m, a, ok) in enumerate(rows):
            row_line(n, 24, y + 36 + k * 20, m, a, ok, 11.5)
        for k, (m, a) in enumerate(parts):
            n.card(208, y + 10 + k * 26, 128, 22, "blue", f"{m} {a}", None, style="solid", size=11, shadow=False)
    # one shuffle band instead of crossing lines
    n.path("M180,334 L180,374", "amber", width=10, arrow=False, opacity=.25)
    n.line(180, 330, 180, 384, "amber", width=2.2, flow=True)
    n.pill(180, 356, "shuffle by merchant", "amber")
    n.text(12, 400, "STAGE 2 · MERGE", 10.5, 800, TONES["blue"][1], "start", spacing="1")
    n.card(12, 412, 168, 126, "blue", "", None)
    n.text(24, 430, "Task 5 · partition 1", 11.5, 800, TONES["blue"][1], "start")
    n.card(188, 412, 160, 126, "blue", "", None)
    n.text(200, 430, "Task 6 · partition 2", 11.5, 800, TONES["blue"][1], "start")
    for m, (x, y, ww) in {"Grocery": (22, 444, 148), "Energy": (22, 490, 148), "Travel": (198, 444, 140)}.items():
        n.card(x, y, ww, 40, "blue", m, sources[m], style="solid", size=11.5, sub_size=10.5, shadow=False)
    n.text(12, 556, "REPORT", 10.5, 800, TONES["violet"][1], "start", spacing="1")
    for k, m in enumerate(["Grocery", "Energy", "Travel"]):
        n.card(12 + k * 86, 568, 80, 50, "violet", m, f"${totals[m]}", style="solid", size=12, sub_size=12)
    n.card(270, 568, 78, 50, "violet", "Total", "$895", size=12, sub_size=12)
    keys = [("Why shuffle", "All partial sums for one merchant must meet in one merge task."),
            ("Which task", "Spark hashes the merchant to pick the partition. The split shown here is one possible result."),
            ("Rows", "✓ kept by the SUCCESS filter · ✗ FAILED row, dropped before the shuffle.")]
    return pair("payment", label, w, n, keys=keys)


def fig_split_impact():
    label = ("Job A is planned before R2 splits and keeps its 4 scan tasks. Job B is planned after the split and sees "
             "5 regions, so it gets 5 scan tasks. Both jobs still merge in 2 shuffle tasks.")

    def row(s, x0, y, W, regs, title, sub):
        s.text(x0, y - 12, title, 12.5, 800, INK, "start")
        s.text(x0 + text_width(title, 12.5, True) + 10, y - 12, sub, 11.5, 600, MUTED, "start")
        sw = W / len(regs)
        for i, r in enumerate(regs):
            x = x0 + i * sw
            new = r.startswith("R2") and len(r) == 3
            s.card(x + 2, y, sw - 4, 38, "teal", r, None, style="solid" if new else "soft", size=12.5, shadow=False)
            s.line(x + sw / 2, y + 38, x + sw / 2, y + 52, "blue", width=1.6)
            s.card(x + 2, y + 54, sw - 4, 34, "blue", f"T{i + 1}", None, style="solid", size=12, shadow=False)

    w = Svg("dg-impact-w", 800, 332, label)
    w.line(40, 24, 40, 292, "slate", width=1.6)
    w.text(40, 308, "time", 11, 700, MUTED)
    for y, t, tone in [(72, "Job A planned", "blue"), (158, "R2 splits", "teal"), (226, "Job B planned", "blue")]:
        w.add(f'<circle cx="40" cy="{y}" r="6" fill="{TONES[tone][0]}" stroke="#fff" stroke-width="2"/>')
        w.text(54, y, t, 11.5, 750, TONES[tone][1], "start")
    row(w, 180, 50, 600, ["R1", "R2", "R3", "R4"], "Job A", "4 scan tasks, even if a split happens mid-job")
    row(w, 180, 210, 600, ["R1", "R2a", "R2b", "R3", "R4"], "Job B", "5 scan tasks*")
    w.text(180, 166, "Both jobs merge in 2 shuffle tasks (spark.sql.shuffle.partitions = 2)", 11.5, 650, TONES["slate"][1], "start")
    w.text(780, 318, "* with the default one split per region", 11, 600, MUTED, "end")

    n = Svg("dg-impact-n", 360, 300, label)
    row(n, 12, 28, 336, ["R1", "R2", "R3", "R4"], "Job A", "before the split · 4 tasks")
    row(n, 12, 160, 336, ["R1", "R2a", "R2b", "R3", "R4"], "Job B", "after the split · 5 tasks*")
    n.text(12, 272, "Both jobs merge in 2 shuffle tasks", 11.5, 700, TONES["slate"][1], "start")
    n.text(12, 290, "* with the default one split per region", 11, 600, MUTED, "start")
    keys = [("Time", "A job that is already planned keeps its tasks. Only a later scan sees the new regions."),
            ("Two controls", "HBase sets the scan partitions. spark.sql.shuffle.partitions sets the merge partitions.")]
    return pair("split-impact", label, w, n, keys=keys)


def fig_end_to_end():
    label = ("End to end: four HBase regions feed four stage-1 tasks that scan, filter and sum; the shuffle regroups by "
             "merchant into two stage-2 tasks; the report has three totals that add up to $895.")
    w = Svg("dg-e2e-w", 800, 300, label)
    for x, t, tone in [(76, "HBASE", "teal"), (293, "STAGE 1", "blue"), (459, "SHUFFLE", "amber"), (590, "STAGE 2", "blue"), (737, "REPORT", "violet")]:
        w.text(x, 14, t, 10.5, 800, TONES[tone][1], spacing="1.1")
    ys = [32, 92, 152, 212]
    for i, y in enumerate(ys):
        w.card(16, y, 120, 48, "teal", f"R{i + 1}", "RegionServer " + ("A" if i < 2 else "B"), size=13, sub_size=10.5)
        w.line(138, y + 24, 186, y + 24, "teal", width=1.8)
        w.card(188, y, 210, 48, "blue", f"Task {i + 1}", "scan → keep SUCCESS → partial sum", size=12.5, sub_size=10.5)
    r2 = [(520, 66), (520, 166)]
    for x, y in r2:
        for yy in ys:
            w.curve(398, yy + 24, x, y + 34, "amber", width=1.4, flow=True, opacity=.8)
    w.card(520, 66, 140, 68, "blue", "Task 5", "merge Grocery, Energy", style="solid", size=12.5, sub_size=10.5)
    w.card(520, 166, 140, 68, "blue", "Task 6", "merge Travel", style="solid", size=12.5, sub_size=10.5)
    w.card(690, 96, 94, 108, "violet", "3 totals", "$895", style="solid", size=13, sub_size=13)
    for x, y in r2:
        w.curve(660, y + 34, 690, 150, "violet", width=1.8)
    w.text(400, 286, "One split per region → 4 scan tasks · spark.sql.shuffle.partitions = 2 → 2 merge tasks", 11.5, 650, MUTED)

    n = Svg("dg-e2e-n", 360, 420, label)

    def gutter(y, h, t, tone):
        n.add(f'<text transform="translate(14,{f(y + h / 2)}) rotate(-90)" font-size="10.5" font-weight="800" fill="{TONES[tone][1]}" '
              f'text-anchor="middle" dominant-baseline="central" letter-spacing="1">{esc(t)}</text>')
    gutter(20, 46, "HBASE", "teal")
    gutter(92, 56, "STAGE 1", "blue")
    gutter(242, 56, "STAGE 2", "blue")
    gutter(334, 60, "REPORT", "violet")
    xs = [32 + i * 81 for i in range(4)]
    for i, x in enumerate(xs):
        n.card(x, 22, 75, 42, "teal", f"R{i + 1}", None, size=13, shadow=False)
        n.line(x + 37.5, 64, x + 37.5, 90, "teal", width=1.8)
        n.card(x, 92, 75, 56, "blue", f"Task {i + 1}", "filter, sum", size=12, sub_size=10.5)
    r2 = [(40, 242), (196, 242)]
    for x, y in r2:
        for xx in xs:
            n.curve(xx + 37.5, 148, x + 66, y, "amber", vertical=True, width=1.3, flow=True, opacity=.8)
    n.pill(190, 196, "shuffle by merchant", "amber")
    n.card(40, 242, 132, 56, "blue", "Task 5", "Grocery, Energy", style="solid", size=12.5, sub_size=10.5)
    n.card(196, 242, 132, 56, "blue", "Task 6", "Travel", style="solid", size=12.5, sub_size=10.5)
    n.card(110, 334, 150, 60, "violet", "3 totals", "$895", style="solid", size=13, sub_size=13)
    for x, y in r2:
        n.curve(x + 66, y + 56, 185, 334, "violet", vertical=True, width=1.8)
    keys = [("HBase", "Regions decide how Spark splits the scan: here 4 scan tasks."),
            ("Spark", "The shuffle setting decides the merge stage: here 2 tasks.")]
    return pair("end-to-end", label, w, n, keys=keys)


FIGURES = {
    "architecture": fig_architecture, "yarn-submit": fig_yarn_submit, "planning": fig_planning, "job": fig_job, "dependencies": fig_dependencies,
    "executors": fig_executors, "skew": fig_skew, "joins": fig_joins, "memory": fig_memory, "storage": fig_storage,
    "streaming": fig_streaming, "monitoring": fig_monitoring, "hbase-write": fig_hbase_write, "regions": fig_regions,
    "split": fig_split, "mapping": fig_mapping, "payment": fig_payment, "split-impact": fig_split_impact,
    "end-to-end": fig_end_to_end,
}

# --------------------------------------------------------------------------
# Scenario diagrams: three steps, labelled arrows, the costly step in rose
# --------------------------------------------------------------------------
PERF = {
    "01": (
        [("Executors", "hold 2M rows", "blue"), ("Driver memory", "every row", "rose"), ("Python loop", "one thread", "slate")],
        ["collect()", "iterate"],
        [("Executors", "filter + partial sums", "blue"), ("Executors", "merge by merchant", "blue"), ("Driver", "3 rows", "slate")],
        ["shuffle partials", "show()"]),
    "02": (
        [("JVM rows", "in the executor", "blue"), ("Python UDF", "row by row", "rose"), ("JVM rows", "results back", "blue")],
        ["serialize", "deserialize"],
        [("JVM rows", "in the executor", "blue"), ("trim + upper", "built-in functions", "blue"), ("JVM rows", "no Python hop", "blue")],
        ["stays in JVM", None]),
    "03": (
        [("Raw values", "every row", "blue"), ("Group per key", "held in memory", "rose"), ("Sum", "per merchant", "blue")],
        ["shuffle all rows", None],
        [("Partial sums", "inside each task", "blue"), ("Merge", "per merchant", "blue"), ("Totals", "3 rows", "violet")],
        ["shuffle partials", None]),
    "04": (
        [("Payments", "2M rows", "blue"), ("Shuffle + sort", "both sides", "rose"), ("Merge join", "sorted inputs", "blue")],
        ["exchange", None],
        [("Lookup", "3 rows", "slate"), ("Every executor", "gets one copy", "amber"), ("Hash join", "payments stay put", "blue")],
        ["broadcast", None]),
    "05": (
        [("repartition", "48 · shuffle 1", "rose"), ("repartition", "96 · shuffle 2", "rose"), ("groupBy", "shuffle 3", "blue")],
        ["filter", None],
        [("filter", "no shuffle", "blue"), ("groupBy", "one shuffle", "amber"), ("Totals", "3 rows", "violet")],
        [None, None]),
    "06": (
        [("All dt folders", "listed", "slate"), ("Every file", "read in full", "rose"), ("payment_date", "filtered in Spark", "blue")],
        [None, None],
        [("dt = 2026-10-03", "partition filter", "blue"), ("One dt folder", "pruned scan", "slate"), ("3 columns", "column pruning", "blue")],
        ["prunes", None]),
    "07": (
        [("Source", "read 3 times", "slate"), ("Filter × 3", "once per action", "rose"), ("3 results", "3 jobs", "violet")],
        [None, None],
        [("Source", "read once", "slate"), ("persist()", "filled by count()", "blue"), ("3 results", "from the cache", "violet")],
        [None, "reuse"]),
    "08": (
        [("Partitions", "many, in parallel", "blue"), ("coalesce(1)", "one task writes", "rose"), ("One file", "slow write", "violet")],
        [None, None],
        [("Partitions", "many, in parallel", "blue"), ("Write tasks", "one per partition", "blue"), ("Several files", "check the sizes", "violet")],
        [None, None]),
    "09": (
        [("8 partitions", "status mixed", "blue"), ("8 write tasks", "a file per status", "rose"), ("Small files", "up to 8 × 2", "violet")],
        ["partitionBy", None],
        [("repartition", "by status", "amber"), ("1 task / status", "all its rows", "blue"), ("1 file / folder", "2 files", "violet")],
        ["shuffle", None]),
    "10": (
        [("Hot merchant", "most rows", "rose"), ("One join task", "all hot rows", "rose"), ("Slow stage", "waits on 1 task", "blue")],
        ["shuffle by key", None],
        [("key + salt", "salt 0 … 7", "blue"), ("8 join tasks", "lookup × 8", "blue"), ("Even stage", "no straggler", "violet")],
        ["shuffle", None]),
    "11": (
        [("1 partition", "AQE off", "rose"), ("1 reduce task", "other cores idle", "rose"), ("Long stage", "", "blue")],
        [None, None],
        [("200 partitions", "start target", "blue"), ("AQE coalesces", "by real size", "blue"), ("Even tasks", "", "violet")],
        [None, None]),
    "12": (
        [("count Grocery", "job 1", "rose"), ("count Travel", "job 2", "rose"), ("count Energy", "job 3", "rose")],
        ["scan again", "scan again"],
        [("One scan", "isin filter", "blue"), ("groupBy", "merchant", "blue"), ("3 counts", "one job", "violet")],
        [None, None]),
    "13": (
        [("All regions", "full table scan", "teal"), ("Every row", "sent over RPC", "rose"), ("Spark filter", "drops most rows", "blue")],
        [None, None],
        [("4 key ranges", "start/stop rows", "teal"), ("Rows in range", "needed columns", "teal"), ("Spark tasks", "small input", "blue")],
        [None, None]),
    "14": (
        [("orderBy", "all rows", "blue"), ("Range shuffle", "+ sample job", "rose"), ("Write", "sorted files", "violet")],
        [None, None],
        [("Write", "no global sort", "violet"), ("Aggregate", "3 rows", "blue"), ("Sort 3 rows", "for the report", "violet")],
        [None, None]),
}


def perf_svg(num, kind, steps, edges):
    good = kind == "good"
    label = ("Better: " if good else "Less efficient: ") + " → ".join(t for t, *_ in steps)
    uid = f"dg-s{num}{kind[0]}"
    w = Svg(uid + "w", 400, 96, label)
    cw, gap = 112, 32
    for i, (t, sub, tone) in enumerate(steps):
        x = 4 + i * (cw + gap)
        mono = "(" in t
        w.card(x, 30, cw, 58, tone, t, sub or None, style="soft", size=12, sub_size=10.5, mono=mono, shadow=False)
        if tone == "rose":
            w.add(f'<circle cx="{f(x + cw - 8)}" cy="38" r="7" fill="{TONES["rose"][0]}"/>')
            w.text(x + cw - 8, 38.5, "!", 10.5, 900, "#fff")
        if i:
            tn = "amber" if steps[i][2] == "amber" or (edges[i - 1] or "").startswith(("shuffle", "broadcast", "exchange", "collect")) else "slate"
            w.line(x - gap + 4, 59, x - 4, 59, tn, width=1.8, flow=tn == "amber")
            if edges[i - 1]:
                w.text(x - gap / 2, 14, edges[i - 1], 10.5, 750, TONES[tn][1], mono="(" in edges[i - 1])
    n = Svg(uid + "n", 300, 196, label)
    for i, (t, sub, tone) in enumerate(steps):
        y = 4 + i * 66
        mono = "(" in t
        n.card(50, y, 200, 48, tone, t, sub or None, size=12, sub_size=10.5, mono=mono, shadow=False)
        if tone == "rose":
            n.add(f'<circle cx="{f(242)}" cy="{f(y + 8)}" r="7" fill="{TONES["rose"][0]}"/>')
            n.text(242, y + 8.5, "!", 10.5, 900, "#fff")
        if i:
            tn = "amber" if steps[i][2] == "amber" or (edges[i - 1] or "").startswith(("shuffle", "broadcast", "exchange", "collect")) else "slate"
            n.line(150, y - 15, 150, y - 3, tn, width=1.8, flow=tn == "amber")
            if edges[i - 1]:
                n.text(162, y - 9, edges[i - 1], 10.5, 750, TONES[tn][1], "start", mono="(" in edges[i - 1])
    return w.render("dg-w") + n.render("dg-n")


# --------------------------------------------------------------------------
# Page update
# --------------------------------------------------------------------------
BLOCK = re.compile(r'(<div class="(?:dg|perf-diagram dg)[^"]*" data-dg="([^"]+)">)(.*?)(</div><!--/dg-->)', re.S)


def build(page: str) -> str:
    def repl(m):
        name = m.group(2)
        if name.startswith("perf-"):
            _, num, kind = name.split("-")
            bad_steps, bad_edges, good_steps, good_edges = PERF[num]
            inner = perf_svg(num, kind, *((bad_steps, bad_edges) if kind == "bad" else (good_steps, good_edges)))
        else:
            inner = FIGURES[name]()
        return m.group(1) + inner + m.group(4)

    out, n = BLOCK.subn(repl, page)
    expected = len(FIGURES) + 2 * len(PERF)
    if n != expected:
        sys.exit(f"expected {expected} diagram blocks, found {n}")
    return out


if __name__ == "__main__":
    text = PAGE.read_text(encoding="utf-8")
    PAGE.write_text(build(text), encoding="utf-8")
    print(f"updated {PAGE.relative_to(Path.cwd()) if PAGE.is_relative_to(Path.cwd()) else PAGE}")
