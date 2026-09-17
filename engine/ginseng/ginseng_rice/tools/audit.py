from palettes import PALETTES
from color import contrast, cvd, delta_ok
import itertools
TEXT_ROLES = ["ink","muted","focus","safe","thin","short","inflow","outflow","opt_credit","opt_liquidate","opt_hybrid","stamp"]
GRAPHIC_ROLES = ["rule","band_inner","ornament","accent","floor","median"]
def audit(name, p):
    worst = []
    for r in TEXT_ROLES:
        c1 = contrast(p[r], p["paper"]); c2 = contrast(p[r], p["panel"])
        worst.append((min(c1,c2), r))
    g = [(min(contrast(p[r], p["paper"]), contrast(p[r], p["panel"])), r) for r in GRAPHIC_ROLES]
    states = ["safe","thin","short"]
    de = {}
    for kind in ["none","deuteranomaly","protanomaly","tritanomaly"]:
        cols = [p[s] if kind=="none" else cvd(p[s], kind) for s in states]
        de[kind] = min(delta_ok(a,b) for a,b in itertools.combinations(cols,2))
    return sorted(worst)[:4], sorted(g)[:3], de
for name, p in PALETTES.items():
    w, g, de = audit(name, p)
    print(f"== {name}  paper {p['paper']} panel {p['panel']} ink {p['ink']}")
    print("   lowest text contrast:", ", ".join(f"{r}={c:.2f}" for c,r in w))
    print("   lowest graphic contrast:", ", ".join(f"{r}={c:.2f}" for c,r in g))
    print("   min dE_ok(safe,thin,short):", ", ".join(f"{k}={v:.3f}" for k,v in de.items()))
