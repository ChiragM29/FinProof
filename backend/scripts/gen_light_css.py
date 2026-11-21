"""Generate dashboard/light.css: light-theme overrides derived from the dark CSS, plus a hand-written section.

Every rule that sets a colour in style.css, cc.css or truce.css gets a twin under html[data-theme="light"] with the colour
mapped: light text becomes dark text, dark panels become white, dark borders become #e2e8f0, bright accents get their
darker, readable variant. Run from dashboard/: python gen_light.py
"""
import colorsys
import re
import sys
from pathlib import Path

DASH = Path(sys.argv[1])
SOURCES = ["style.css", "cc.css", "truce.css"]
P = 'html[data-theme="light"]'

HEX_RE = re.compile(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b")
RGBA_RE = re.compile(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+)\s*)?\)")
COLOR_RE = re.compile(HEX_RE.pattern + "|" + RGBA_RE.pattern)


def parse(tok):
    if tok.startswith("#"):
        h = tok[1:]
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 1.0
    m = RGBA_RE.fullmatch(tok)
    return int(m[1]), int(m[2]), int(m[3]), float(m[4]) if m[4] else 1.0


def lum(r, g, b):
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255


def hue_sat(r, g, b):
    h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    return h * 360, s, l


def accent_dark(r, g, b):
    h, s, l = hue_sat(r, g, b)
    if 180 <= h < 212: return "#0284c7"
    if 212 <= h < 262: return "#4f46e5"
    if 262 <= h < 300: return "#6d28d9"
    if 300 <= h < 340: return "#be185d"
    if h >= 340 or h < 16: return "#e11d48"
    if 16 <= h < 66: return "#b45309"
    return "#047857"


def map_text(tok):
    r, g, b, a = parse(tok)
    h, s, l = hue_sat(r, g, b)
    if lum(r, g, b) < 0.45:
        return None                        # already dark text (e.g. on a bright button)
    if s < 0.25:                           # grey / white text
        return "#0f172a" if lum(r, g, b) > 0.72 else "#475569"
    return accent_dark(r, g, b)


def map_bg(tok):
    r, g, b, a = parse(tok)
    h, s, l = hue_sat(r, g, b)
    if lum(r, g, b) < 0.22 and s < 0.6:    # dark panel
        return "#ffffff" if a >= 0.55 else "#f8fafc"
    if s < 0.3 and lum(r, g, b) <= 0.5:    # mid-grey inset box
        return "#f1f5f9"
    if s < 0.25 and lum(r, g, b) > 0.5:    # light grey wash used on dark (hover etc.)
        return f"rgba(15, 23, 42, {min(0.06, a):.2f})"
    return None                            # accent tints and bright fills stay


def map_border(tok):
    r, g, b, a = parse(tok)
    h, s, l = hue_sat(r, g, b)
    if s < 0.3:
        return "#e2e8f0" if lum(r, g, b) < 0.5 else "#cbd5e1"
    if lum(r, g, b) > 0.45 and a >= 0.9:
        return accent_dark(r, g, b)
    return None


def remap(value, fn):
    out, changed = [], False
    pos = 0
    for m in COLOR_RE.finditer(value):
        new = fn(m.group(0))
        out.append(value[pos:m.start()])
        out.append(new or m.group(0))
        changed |= bool(new)
        pos = m.end()
    out.append(value[pos:])
    return "".join(out), changed


LIGHT_SHADOW = "0 1px 3px rgba(15, 23, 42, 0.08)"


def map_decl(prop, value):
    prop = prop.strip().lower()
    v = value.strip()
    if prop in ("color", "fill", "stroke", "-webkit-text-fill-color", "caret-color", "stop-color", "outline-color",
                "text-decoration-color"):
        return remap(v, map_text)
    if prop in ("background", "background-color", "background-image"):
        if "gradient" in v:

            toks = [parse(m.group(0)) for m in COLOR_RE.finditer(v)]
            if toks and all(lum(r, g, b) < 0.25 for r, g, b, a in toks):
                return "#ffffff", True
            return v, False
        return remap(v, map_bg)
    if prop.startswith("border") or prop == "outline" or prop == "column-rule":
        return remap(v, map_border)
    if prop in ("box-shadow",):
        toks = [parse(m.group(0)) for m in COLOR_RE.finditer(v)]
        if toks and any(lum(r, g, b) < 0.1 for r, g, b, a in toks):
            return LIGHT_SHADOW, True
        return v, False
    return v, False


def strip_comments(css):
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def blocks(css):
    """Yield (prelude, body) at the top level, handling nested braces."""
    i, n = 0, len(css)
    while i < n:
        j = css.find("{", i)
        if j < 0:
            return
        prelude = css[i:j].strip()
        depth, k = 1, j + 1
        while k < n and depth:
            if css[k] == "{": depth += 1
            elif css[k] == "}": depth -= 1
            k += 1
        yield prelude, css[j + 1:k - 1]
        i = k


def prefix(selectors):
    out = []
    for sel in selectors.split(","):
        sel = sel.strip()
        if not sel:
            continue
        if sel in (":root", "html"):
            out.append(P)
        elif sel.startswith("html"):
            out.append(P + sel[4:])
        else:
            out.append(f"{P} {sel}")
    return ",\n".join(out)


def rules(css):
    res = []
    for pre, body in blocks(css):
        if pre.startswith("@media") or pre.startswith("@supports"):
            inner = rules(body)
            if inner:
                res.append(f"{pre} {{\n" + "\n".join(inner) + "\n}")
            continue
        if pre.startswith("@"):
            continue
        decls = []
        for d in body.split(";"):
            if ":" not in d:
                continue
            prop, val = d.split(":", 1)
            if prop.strip().startswith("--"):
                continue
            new, changed = map_decl(prop, val)
            if changed:
                decls.append(f"  {prop.strip()}: {new};")
        if decls:
            res.append(prefix(pre) + " {\n" + "\n".join(decls) + "\n}")
    return res


out = ["/* GENERATED by gen_light.py from style.css, cc.css and truce.css: the light theme's colour overrides.",
       "   The hand-written part (variables, label, logo, chart surroundings) is in light-extra.css. */"]
for name in SOURCES:
    out.append(f"\n/* ---- from {name} */")
    out.extend(rules(strip_comments((DASH / name).read_text(encoding="utf-8"))))
(DASH / "light.css").write_text("\n".join(out) + "\n", encoding="utf-8")
print("rules:", sum(1 for x in out if "{" in x))
