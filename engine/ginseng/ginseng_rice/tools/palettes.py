"""Palette specs for the eight coords, written in OKLCH (L, C, h) or hex, resolved to sRGB hex."""
from color import oklch_to_hex

O = lambda L, C, h: ("oklch", L, C, h)

SPECS = {
 "seifuku": dict(dark=False,
    paper=O(0.985,0.006,265), panel=O(0.955,0.018,265), ink="#0100F4", muted=O(0.50,0.14,265),
    rule=O(0.78,0.08,265), focus="#0100F4", accent=O(0.52,0.20,25),
    band_outer=O(0.915,0.045,265), band_inner=O(0.82,0.10,265), median="#0100F4", floor=O(0.52,0.20,25),
    safe="#0100F4", thin=O(0.47,0.16,305), short=O(0.52,0.20,25),
    inflow="#0100F4", outflow=O(0.36,0.14,265),
    opt_credit=O(0.44,0.30,264), opt_liquidate=O(0.53,0.15,264), opt_hybrid=O(0.30,0.16,264), opt_protective=O(0.36,0.20,264),
    stamp=O(0.52,0.20,25), ornament=O(0.70,0.10,265)),
 "gothpunk": dict(dark=True,
    paper=O(0.155,0.012,300), panel=O(0.195,0.016,300), ink=O(0.93,0.012,300), muted=O(0.72,0.02,300),
    rule=O(0.42,0.02,300), focus=O(0.68,0.19,268), accent=O(0.66,0.22,20),
    band_outer=O(0.30,0.04,300), band_inner=O(0.42,0.07,290), median=O(0.93,0.012,300), floor=O(0.66,0.22,20),
    safe=O(0.80,0.09,300), thin=O(0.83,0.12,85), short=O(0.66,0.22,20),
    inflow=O(0.80,0.09,300), outflow=O(0.72,0.02,300),
    opt_credit=O(0.70,0.17,268), opt_liquidate=O(0.80,0.10,330), opt_hybrid=O(0.90,0.02,300), opt_protective=O(0.78,0.12,95),
    stamp=O(0.66,0.22,20), ornament=O(0.62,0.02,300)),
 "dojima": dict(dark=True,
    paper=O(0.235,0.055,262), panel=O(0.28,0.06,262), ink=O(0.94,0.018,85), muted=O(0.76,0.03,250),
    rule=O(0.47,0.06,258), focus=O(0.85,0.14,85), accent=O(0.70,0.19,38),
    band_outer=O(0.345,0.06,258), band_inner=O(0.46,0.08,250), median=O(0.94,0.018,85), floor=O(0.70,0.19,38),
    safe=O(0.81,0.10,160), thin=O(0.85,0.14,85), short=O(0.70,0.19,38),
    inflow=O(0.81,0.10,160), outflow=O(0.76,0.03,250),
    opt_credit=O(0.77,0.11,230), opt_liquidate=O(0.81,0.11,60), opt_hybrid=O(0.87,0.08,160), opt_protective=O(0.83,0.10,320),
    stamp=O(0.70,0.19,36), ornament=O(0.64,0.07,80)),
 "techwear": dict(dark=True,
    paper=O(0.145,0.004,250), panel=O(0.185,0.005,250), ink=O(0.85,0.005,250), muted=O(0.64,0.006,250),
    rule=O(0.36,0.006,250), focus=O(0.99,0.0,0), accent=O(0.73,0.19,48),
    band_outer=O(0.265,0.004,250), band_inner=O(0.37,0.005,250), median=O(0.97,0.0,0), floor=O(0.73,0.19,48),
    safe=O(0.72,0.01,250), thin=O(0.99,0.0,0), short=O(0.73,0.19,48),
    inflow=O(0.85,0.005,250), outflow=O(0.64,0.006,250),
    opt_credit=O(0.80,0.0,0), opt_liquidate=O(0.62,0.0,0), opt_hybrid=O(0.97,0.0,0), opt_protective=O(0.70,0.0,0),
    stamp=O(0.73,0.19,48), ornament=O(0.36,0.006,250)),
 "mori": dict(dark=True,
    paper=O(0.225,0.022,150), panel=O(0.265,0.025,148), ink=O(0.91,0.022,95), muted=O(0.74,0.03,110),
    rule=O(0.45,0.03,140), focus=O(0.83,0.09,140), accent=O(0.71,0.13,30),
    band_outer=O(0.325,0.03,145), band_inner=O(0.44,0.05,140), median=O(0.91,0.022,95), floor=O(0.68,0.15,32),
    safe=O(0.80,0.08,175), thin=O(0.89,0.13,92), short=O(0.68,0.15,32),
    inflow=O(0.80,0.08,175), outflow=O(0.74,0.03,110),
    opt_credit=O(0.79,0.07,200), opt_liquidate=O(0.81,0.08,60), opt_hybrid=O(0.87,0.07,120), opt_protective=O(0.84,0.09,20),
    stamp=O(0.68,0.15,32), ornament=O(0.63,0.05,130)),
 "decora": dict(dark=False,
    paper=O(0.975,0.018,340), panel=O(0.945,0.035,320), ink=O(0.30,0.09,300), muted=O(0.46,0.07,310),
    rule=O(0.78,0.10,330), focus=O(0.52,0.18,340), accent=O(0.52,0.14,250),
    band_outer=O(0.91,0.05,200), band_inner=O(0.83,0.09,175), median=O(0.30,0.09,300), floor=O(0.415,0.18,18),
    safe=O(0.47,0.10,228), thin=O(0.515,0.11,78), short=O(0.415,0.18,18),
    inflow=O(0.46,0.10,225), outflow=O(0.46,0.07,310),
    opt_credit=O(0.50,0.14,250), opt_liquidate=O(0.50,0.17,340), opt_hybrid=O(0.46,0.10,175), opt_protective=O(0.48,0.14,60),
    stamp=O(0.415,0.18,18), ornament=O(0.72,0.14,330)),
 "stage": dict(dark=True,
    paper="#000000", panel=O(0.14,0.0,0), ink="#FFFFFF", muted=O(0.80,0.0,0),
    rule=O(0.52,0.0,0), focus="#56B4E9", accent="#D55E00",
    band_outer=O(0.26,0.0,0), band_inner=O(0.40,0.05,240), median="#FFFFFF", floor="#D55E00",
    safe="#56B4E9", thin="#F0E442", short="#D55E00",
    inflow="#56B4E9", outflow=O(0.80,0.0,0),
    opt_credit="#56B4E9", opt_liquidate="#CC79A7", opt_hybrid="#009E73", opt_protective="#E69F00",
    stamp="#D55E00", ornament="#CC79A7"),
 "gosurori": dict(dark=True,
    paper=O(0.115,0.028,258), panel=O(0.155,0.032,258), ink=O(0.93,0.015,245), muted=O(0.68,0.045,250),
    rule=O(0.36,0.035,252), focus=O(0.72,0.16,250), accent=O(0.68,0.09,285),
    band_outer=O(0.235,0.045,258), band_inner=O(0.36,0.075,255), median=O(0.93,0.015,245), floor=O(0.615,0.22,25),
    safe=O(0.80,0.09,220), thin=O(0.62,0.15,300), short=O(0.615,0.22,25),
    inflow=O(0.80,0.09,220), outflow=O(0.68,0.045,250),
    opt_credit=O(0.72,0.15,245), opt_liquidate=O(0.80,0.09,270), opt_hybrid=O(0.62,0.08,255), opt_protective=O(0.90,0.03,235),
    stamp=O(0.615,0.22,25), ornament=O(0.68,0.05,235)),
 "rococo": dict(dark=False,
    paper=O(0.965,0.022,85), panel=O(0.935,0.03,70), ink=O(0.32,0.055,45), muted=O(0.47,0.05,40),
    rule=O(0.73,0.06,20), focus=O(0.51,0.13,5), accent=O(0.50,0.08,150),
    band_outer=O(0.895,0.04,20), band_inner=O(0.81,0.07,15), median=O(0.32,0.055,45), floor=O(0.405,0.15,15),
    safe=O(0.47,0.075,235), thin=O(0.515,0.10,68), short=O(0.405,0.15,15),
    inflow=O(0.46,0.07,235), outflow=O(0.47,0.05,40),
    opt_credit=O(0.48,0.09,260), opt_liquidate=O(0.50,0.12,5), opt_hybrid=O(0.46,0.07,150), opt_protective=O(0.47,0.10,85),
    stamp=O(0.405,0.15,15), ornament=O(0.73,0.06,20)),
}

def resolve(spec):
    out = {}
    for k, v in spec.items():
        if k == "dark":
            out[k] = v
        elif isinstance(v, tuple):
            out[k] = oklch_to_hex(*v[1:])
        else:
            out[k] = v
    return out

PALETTES = {name: resolve(s) for name, s in SPECS.items()}
