"""Status line styles: 24 renderers over the same data.

Every style takes (Data, Paint) and returns one or more lines. Pure functions,
stdlib only. `render(name, data, paint)` is the single entry point.
"""
import colorsys
import re
import unicodedata
from dataclasses import dataclass, field

DEFAULT = "plain"
SEV256 = {"g": 35, "y": 178, "r": 167}
SEVBG = {"g": 42, "y": 43, "r": 41}
TRACK = 238
SYMBOL = {"ctx": "◍", "ses": "◷", "wk": "▦"}
EMOJI = {"ctx": "🧠", "ses": "⏱", "wk": "📅"}
SHORT = {"ctx": "ctx", "ses": "5h", "wk": "7d"}
CIRCUIT = {"ctx": "CTX", "ses": "S", "wk": "W"}
GREEN_PHOSPHOR = "92"


def sev(pct):
    n = round(pct)
    return "g" if n < 60 else "y" if n <= 85 else "r"


@dataclass
class Metric:
    key: str                    # "ctx", "ses" or "wk"
    label: str                  # "CTX", "Session" or "Weekly"
    pct: float
    left: str = ""              # time to reset, "" for the context
    elapsed: float = None       # share of the window already passed, None for the context
    hist: list = field(default_factory=list)


@dataclass
class Data:
    branch: str = ""
    metrics: list = field(default_factory=list)


class Paint:
    """ANSI helper. With enabled False every method returns the bare text.

    With gray True no hue is used: severity is told by brightness (gray, white,
    bold white) and, on the number of a red value, by reverse video.
    """
    COLOR = {"g": "32", "y": "33", "r": "31", "c": "36", "dim": "90"}
    GRAY = {"g": "37", "y": "97", "r": "1;97", "c": "97", "dim": "90"}

    def __init__(self, enabled=True, truecolor=False, gray=False):
        self.enabled = enabled
        self.truecolor = truecolor
        self.gray = gray
        self.CODES = self.GRAY if gray else self.COLOR

    def sev256(self, s):
        return {"g": 245, "y": 250, "r": 255}[s] if self.gray else SEV256[s]

    def sevbg(self, s):
        return f"48;5;{self.sev256(s)}" if self.gray else str(SEVBG[s])

    @property
    def branch256(self):
        return 243 if self.gray else 74

    @property
    def edge256(self):
        return 240 if self.gray else 62

    @property
    def accent_bg(self):
        return "48;5;252" if self.gray else "46"

    @property
    def phosphor(self):
        return "97" if self.gray else GREEN_PHOSPHOR

    def wrap(self, codes, text):
        if not self.enabled or text == "":
            return text
        return f"\x1b[{codes}m{text}\x1b[0m"

    def col(self, name, text, bold=False):
        return self.wrap(("1;" if bold else "") + self.CODES[name], text)

    def dim(self, text):
        return self.col("dim", text)

    def val(self, pct):
        s = sev(pct)
        if self.gray and s == "r":
            return self.wrap("1;7;97", f"{round(pct)}%")
        return self.col(s, f"{round(pct)}%", True)


# ---------- width ----------

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def visible_width(text):
    """-> columns the widest line of text needs on screen (escapes ignored)."""
    best = 0
    for line in _ANSI.sub("", text).split("\n"):
        w = 0
        for ch in line:
            if unicodedata.combining(ch) or ch in "️‍":
                continue
            w += 2 if unicodedata.east_asian_width(ch) in "WF" else 1
        best = max(best, w)
    return best


# ---------- primitives ----------

def _tail(P, m):
    return " " + P.dim("⟳ " + m.left) if m.left else ""


def _plain_tail(m):
    return f" ⟳ {m.left}" if m.left else ""


def _cells(p, n):
    return max(0, min(n, round(p / 100 * n)))


def bar(P, p, n, full, empty):
    f = _cells(p, n)
    return P.col(sev(p), full * f) + P.dim(empty * (n - f))


def smooth(P, p, n):
    te = max(0, min(n * 8, round(p / 100 * n * 8)))
    full, part = divmod(te, 8)
    s = "█" * full
    if full < n:
        s += (" ▏▎▍▌▋▊▉"[part] if part else " ") + " " * (n - full - 1)
    return P.wrap(f"48;5;{TRACK};{P.CODES[sev(p)]}", s)


def gradient(P, p, n):
    f = _cells(p, n)
    s = ""
    for i in range(f):
        if P.gray:
            s += P.wrap(f"38;5;{240 + round(15 * i / max(1, n - 1))}", "█")
        elif P.truecolor:
            r, g, b = colorsys.hls_to_rgb((140 - 140 * i / max(1, n - 1)) / 360, 0.55, 0.72)
            s += P.wrap(f"38;2;{round(r * 255)};{round(g * 255)};{round(b * 255)}", "█")
        else:
            s += P.col(sev((i + 1) / n * 100), "█")
    return s + P.dim("░" * (n - f))


def heat(P, p, n):
    f = _cells(p, n)
    return "".join(P.col(sev((i + 1) / n * 100), "▮") for i in range(f)) + P.dim("▯" * (n - f))


def pie(P, p):
    return P.col(sev(p), "○◔◑◕●"[min(4, round(p / 25))])


def gauge(P, p):
    return P.col(sev(p), "▁▂▃▄▅▆▇█"[max(0, min(7, int(p // 12.5)))])


def spark(P, values, p):
    values = values or [p]
    s = "".join("▁▂▃▄▅▆▇█"[max(0, min(7, int(v // 12.5)))] for v in values)
    return P.col(sev(values[-1]), s)


def pace(P, p, elapsed, n):
    f = _cells(p, n)
    mk = max(0, min(n - 1, round(elapsed * n)))
    out = ""
    for i in range(n):
        if i == mk:
            out += P.wrap("1;97", "┃")
        else:
            out += P.col(sev(p), "█") if i < f else P.dim("░")
    return out


def _join(parts, sep):
    return sep.join(x for x in parts if x)


def _branch(d, make):
    return make(d.branch) if d.branch else ""


# ---------- registry ----------

REG = {}


def style(name, desc, needs=(), color=False):
    def deco(fn):
        REG[name] = {"fn": fn, "desc": desc, "needs": tuple(needs), "color": color}
        return fn
    return deco


def _glyph_style(glyph, sep="  "):
    def fn(d, P):
        br = _branch(d, lambda b: "⎇ " + P.col("c", b))
        return _join([br] + [P.dim(m.label) + " " + glyph(P, m) + " " + P.val(m.pct) + _tail(P, m)
                             for m in d.metrics], sep)
    return fn


@style("plain", "Branch: main | CTX 4% | Session 12% ⟳ 4h | Weekly 14% ⟳ 4d")
def _plain(d, P):
    br = _branch(d, lambda b: "Branch: " + b)
    return _join([br] + [f"{m.label} {P.val(m.pct)}{_plain_tail(m)}" for m in d.metrics], " | ")


@style("dim", "Faded labels, bold values")
def _dim(d, P):
    br = _branch(d, lambda b: P.dim("branch ") + P.col("c", b, True))
    return _join([br] + [P.dim(m.label.lower() + " ") + P.val(m.pct) + _tail(P, m) for m in d.metrics],
                 P.dim(" │ "))


REG["segments"] = {"fn": _glyph_style(lambda P, m: bar(P, m.pct, 10, "▰", "▱")),
                   "desc": "Ten ▰▱ cells per metric", "needs": (), "color": False}
REG["solid"] = {"fn": _glyph_style(lambda P, m: bar(P, m.pct, 10, "█", "░")),
                "desc": "Full block over light shade", "needs": (), "color": False}
REG["smooth"] = {"fn": _glyph_style(lambda P, m: smooth(P, m.pct, 10)),
                 "desc": "Eighth-block edge on a tinted track (80 steps)", "needs": (), "color": True}
REG["gradient"] = {"fn": _glyph_style(lambda P, m: gradient(P, m.pct, 12)),
                   "desc": "Green to red hue along the bar", "needs": ("truecolor",), "color": False}
REG["heat"] = {"fn": _glyph_style(lambda P, m: heat(P, m.pct, 10)),
               "desc": "Cells turn yellow past 60, red past 85", "needs": (), "color": False}
REG["dots"] = {"fn": _glyph_style(lambda P, m: bar(P, m.pct, 10, "●", "○")),
               "desc": "Filled and hollow circles", "needs": (), "color": False}
REG["pie"] = {"fn": _glyph_style(lambda P, m: pie(P, m.pct)),
              "desc": "One ○◔◑◕● glyph per metric", "needs": (), "color": False}
REG["gauge"] = {"fn": _glyph_style(lambda P, m: gauge(P, m.pct)),
                "desc": "One rising block per metric", "needs": (), "color": False}
REG["spark"] = {"fn": _glyph_style(lambda P, m: spark(P, m.hist, m.pct)),
                "desc": "Last eight readings (history file)", "needs": (), "color": False}
REG["pace"] = {"fn": _glyph_style(lambda P, m: pace(P, m.pct, m.elapsed, 16) if m.elapsed is not None
                                  else bar(P, m.pct, 16, "█", "░")),
               "desc": "White ┃ marks how much of the window has passed", "needs": (), "color": False}


@style("lights", "Only a dot carries the color")
def _lights(d, P):
    br = _branch(d, lambda b: P.col("c", "⎇ ") + b)
    return _join([br] + [P.col(sev(m.pct), "●") + f" {m.label} {round(m.pct)}%" + _tail(P, m)
                         for m in d.metrics], "   ")


@style("chips", "Gray label tile, colored value tile", color=True)
def _chips(d, P):
    br = _branch(d, lambda b: P.wrap(f"48;5;{TRACK};97", " ⎇ ") + P.wrap(f"{P.accent_bg};30;1", f" {b} "))
    return _join([br] + [P.wrap(f"48;5;{TRACK};97", f" {m.label} ") +
                         P.wrap(f"{P.sevbg(sev(m.pct))};30;1", f" {round(m.pct)}% ") + _tail(P, m)
                         for m in d.metrics], "  ")


@style("brackets", "[main] [CTX 4%] [Session 12% ⟳ 4h]")
def _brackets(d, P):
    br = _branch(d, lambda b: P.dim("[") + P.col("c", b) + P.dim("]"))
    return _join([br] + [P.dim("[") + f"{m.label} " + P.val(m.pct) + _tail(P, m) + P.dim("]")
                         for m in d.metrics], " ")


@style("pills", "Rounded capsules", needs=("nerd",), color=True)
def _pills(d, P):
    def pill(c, text):
        return (P.wrap(f"38;5;{c}", "") + P.wrap(f"48;5;{c};38;5;16;1", text) +
                P.wrap(f"38;5;{c}", ""))
    br = _branch(d, lambda b: pill(P.branch256, f"⎇ {b}"))
    return _join([br] + [pill(P.sev256(sev(m.pct)), f"{m.label} {round(m.pct)}%{_plain_tail(m)}")
                         for m in d.metrics], " ")


@style("powerline", "Arrow-joined colored segments", needs=("nerd",), color=True)
def _powerline(d, P):
    segs = []
    if d.branch:
        segs.append((P.edge256, 15, f" {d.branch} "))
    for m in d.metrics:
        segs.append((P.sev256(sev(m.pct)), 16, f" {m.label} {round(m.pct)}%{_plain_tail(m)} "))
    out = ""
    for i, (bg, fg, text) in enumerate(segs):
        nxt = f"48;5;{segs[i + 1][0]}" if i + 1 < len(segs) else "49"
        out += P.wrap(f"48;5;{bg};38;5;{fg};1", text) + P.wrap(f"38;5;{bg};{nxt}", "")
    return out


@style("emoji", "🌿 main 🧠 4% ⏱ 12% 📅 14%", needs=("emoji",))
def _emoji(d, P):
    br = _branch(d, lambda b: "🌿 " + P.wrap("1", b))
    return _join([br] + [EMOJI[m.key] + " " + P.val(m.pct) + _tail(P, m) for m in d.metrics], "   ")


@style("symbols", "Monochrome symbols instead of emoji")
def _symbols(d, P):
    br = _branch(d, lambda b: "⎇ " + P.col("c", b, True))
    return _join([br] + [P.dim(SYMBOL[m.key]) + " " + P.val(m.pct) + _tail(P, m) for m in d.metrics], "  ")


@style("tree", "Four aligned lines with bars")
def _tree(d, P):
    rows = []
    if d.branch:
        rows.append("⎇ " + P.col("c", d.branch, True))
    for m in d.metrics:
        rows.append(f"{m.label:<8} " + bar(P, m.pct, 12, "█", "░") + f" {round(m.pct):>3}%" +
                    ("  " + P.dim("⟳ " + m.left) if m.left else ""))
    lines = []
    for i, row in enumerate(rows):
        pre = "╭─" if i == 0 and len(rows) > 1 else "╰─" if i == len(rows) - 1 else "├─"
        lines.append(P.dim(pre) + " " + row)
    return "\n".join(lines)


@style("dash", "Two lines: branch and context, then the two limits")
def _dash(d, P):
    sep = P.dim(" │ ")

    def piece(m):
        return P.dim(m.label + " ") + bar(P, m.pct, 10, "█", "░") + " " + P.val(m.pct) + _tail(P, m)
    ctx = [m for m in d.metrics if m.key == "ctx"]
    lim = [m for m in d.metrics if m.key != "ctx"]
    top = _join([_branch(d, lambda b: "⎇ " + P.col("c", b, True))] + [piece(m) for m in ctx], sep)
    return "\n".join(x for x in (top, _join([piece(m) for m in lim], sep)) if x)


@style("circuit", "Boxes joined by lines in phosphor green")
def _circuit(d, P):
    g = lambda t: P.wrap(P.phosphor, t)

    def seg(inner):
        return g("[ ") + inner + g(" ]")

    def num(m):
        return g(f"{round(m.pct)}%") if sev(m.pct) == "g" else P.val(m.pct)
    parts = [seg(g("⎇ " + d.branch))] if d.branch else []
    parts += [seg(g(CIRCUIT[m.key] + " ") + num(m) + (g(" ⟳ " + m.left) if m.left else "")) for m in d.metrics]
    return g("──").join(parts)


@style("whisper", "Everything dim except what needs attention")
def _whisper(d, P):
    def q(m):
        num = P.dim(f"{round(m.pct)}%") if sev(m.pct) == "g" else P.val(m.pct)
        return P.dim(SHORT[m.key] + " ") + num + (P.dim(" ⟳ " + m.left) if m.left else "")
    return _join([P.dim(d.branch)] + [q(m) for m in d.metrics], P.dim(" · "))


@style("inbar", "Label and value inside the bar", color=True)
def _inbar(d, P):
    def piece(m, w):
        txt = f"{m.label} {round(m.pct)}%"
        pad = (w - len(txt)) // 2
        s = " " * pad + txt + " " * (w - len(txt) - pad)
        f = _cells(m.pct, w)
        return (P.wrap(f"{P.sevbg(sev(m.pct))};30;1", s[:f]) + P.wrap(f"48;5;{TRACK}", s[f:]) + _tail(P, m))
    br = _branch(d, lambda b: "⎇ " + P.col("c", b, True))
    return _join([br] + [piece(m, 14 if m.key == "ctx" else 18) for m in d.metrics], "  ")


NAMES = list(REG)


def describe(name):
    s = REG[name]
    needs = {"nerd": "Nerd/Powerline font", "emoji": "emoji", "truecolor": "truecolor"}
    note = ", ".join(needs[n] for n in s["needs"])
    return s["desc"] + (f" (needs {note})" if note else "")


def render(name, data, paint):
    spec = REG.get(name) or REG[DEFAULT]
    if spec["color"] and not paint.enabled:
        spec = REG["brackets"]
    return spec["fn"](data, paint)
