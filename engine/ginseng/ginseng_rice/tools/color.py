"""Color math for the Ginseng kisekae guide: OKLCH <-> sRGB, contrast, xterm-256, CVD."""
import math

def srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

def linear_to_srgb(c):
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055

def oklab_to_linear_rgb(L, a, b):
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_ ** 3, m_ ** 3, s_ ** 3
    return (
        +4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
        -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
        -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s,
    )

def linear_rgb_to_oklab(r, g, b):
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l_, m_, s_ = (math.copysign(abs(v) ** (1 / 3), v) for v in (l, m, s))
    return (
        0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
        1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
        0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_,
    )

def in_gamut(rgb, eps=1e-6):
    return all(-eps <= c <= 1 + eps for c in rgb)

def oklch_to_hex(L, C, h):
    """Convert OKLCH to #rrggbb, reducing chroma (keeping L and h) until in sRGB gamut."""
    lo, hi = 0.0, C
    def lin(Cc):
        hr = math.radians(h)
        return oklab_to_linear_rgb(L, Cc * math.cos(hr), Cc * math.sin(hr))
    if not in_gamut(lin(C)):
        for _ in range(40):
            mid = (lo + hi) / 2
            if in_gamut(lin(mid)):
                lo = mid
            else:
                hi = mid
        C = lo
    r, g, b = (min(1, max(0, linear_to_srgb(max(0.0, c)))) for c in lin(C))
    return "#%02X%02X%02X" % (round(r * 255), round(g * 255), round(b * 255))

def hex_to_rgb01(hx):
    hx = hx.lstrip("#")
    return tuple(int(hx[i:i + 2], 16) / 255 for i in (0, 2, 4))

def hex_to_oklch(hx):
    r, g, b = (srgb_to_linear(c) for c in hex_to_rgb01(hx))
    L, a, bb = linear_rgb_to_oklab(r, g, b)
    C = math.hypot(a, bb)
    h = math.degrees(math.atan2(bb, a)) % 360
    return L, C, h

def hex_to_oklab(hx):
    r, g, b = (srgb_to_linear(c) for c in hex_to_rgb01(hx))
    return linear_rgb_to_oklab(r, g, b)

def oklab_to_hex(L, a, b):
    r, g, bl = (min(1, max(0, linear_to_srgb(max(0.0, c)))) for c in oklab_to_linear_rgb(L, a, b))
    return "#%02X%02X%02X" % (round(r * 255), round(g * 255), round(bl * 255))

def rel_luminance(hx):
    r, g, b = (srgb_to_linear(c) for c in hex_to_rgb01(hx))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b

def contrast(fg, bg):
    a, b = rel_luminance(fg), rel_luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)

def mix_oklab(h1, h2, t):
    a = hex_to_oklab(h1); b = hex_to_oklab(h2)
    return oklab_to_hex(*(a[i] + (b[i] - a[i]) * t for i in range(3)))

def mix_srgb(h1, h2, t):
    a = hex_to_rgb01(h1); b = hex_to_rgb01(h2)
    c = [a[i] + (b[i] - a[i]) * t for i in range(3)]
    return "#%02X%02X%02X" % tuple(round(v * 255) for v in c)

_CUBE = [0, 95, 135, 175, 215, 255]
def xterm256(hx):
    """Nearest xterm-256 index, comparing cube and grey ramp in OKLab distance."""
    target = hex_to_oklab(hx)
    best = None
    def consider(idx, rgb):
        nonlocal best
        h = "#%02X%02X%02X" % rgb
        d = sum((x - y) ** 2 for x, y in zip(hex_to_oklab(h), target))
        if best is None or d < best[0]:
            best = (d, idx, h)
    for r in range(6):
        for g in range(6):
            for b in range(6):
                consider(16 + 36 * r + 6 * g + b, (_CUBE[r], _CUBE[g], _CUBE[b]))
    for i in range(24):
        v = 8 + 10 * i
        consider(232 + i, (v, v, v))
    return best[1], best[2], math.sqrt(best[0])

def delta_ok(h1, h2):
    a = hex_to_oklab(h1); b = hex_to_oklab(h2)
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))

def cvd(hx, kind="deuteranomaly", severity=100):
    from colorspacious import cspace_convert
    import numpy as np
    rgb = np.array(hex_to_rgb01(hx))
    out = cspace_convert(rgb, {"name": "sRGB1+CVD", "cvd_type": kind, "severity": severity}, "sRGB1")
    out = np.clip(out, 0, 1)
    return "#%02X%02X%02X" % tuple(int(round(v * 255)) for v in out)
