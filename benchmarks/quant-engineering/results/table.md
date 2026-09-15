# All measured configurations

Median milliseconds; spread is min–max across three fresh-process repetitions. RSS is the process high-water mark across warm-up and all measured stages.

| Paths × days | Case | Output | Backend/workers | Complete ms (min–max) | Three what-ifs ms | Peak MiB |
|---|---|---|---|---:|---:|---:|
| 2000 × 30 | normal | summary | old/1 | 3.52 (3.43–3.72) | 9.48 | 133.2 |
| 2000 × 30 | normal | summary | numpy/1 | 3.83 (3.44–4.23) | 9.53 | 131.0 |
| 2000 × 30 | normal | summary | native/1 | 3.42 (3.21–3.46) | 8.24 | 130.4 |
| 2000 × 30 | normal | summary | native/2 | 3.67 (3.61–3.81) | 8.71 | 131.0 |
| 2000 × 30 | normal | summary | native/4 | 3.60 (3.56–4.14) | 8.70 | 130.7 |
| 2000 × 30 | normal | full | old/1 | 28.15 (27.83–28.43) | 84.24 | 143.4 |
| 2000 × 30 | normal | full | numpy/1 | 32.69 (32.16–34.09) | 69.47 | 142.6 |
| 2000 × 30 | normal | full | native/1 | 31.83 (31.69–31.92) | 67.79 | 142.4 |
| 2000 × 30 | normal | full | native/2 | 32.06 (31.64–32.31) | 71.62 | 143.7 |
| 2000 × 30 | normal | full | native/4 | 31.95 (31.93–32.11) | 69.14 | 143.8 |
| 4000 × 30 | stressed | summary | old/1 | 4.95 (4.65–5.07) | 13.08 | 137.3 |
| 4000 × 30 | stressed | summary | numpy/1 | 4.79 (4.59–6.08) | 11.20 | 134.2 |
| 4000 × 30 | stressed | summary | native/1 | 4.17 (3.76–4.28) | 9.13 | 134.3 |
| 4000 × 30 | stressed | summary | native/2 | 4.13 (4.12–4.23) | 9.67 | 134.5 |
| 4000 × 30 | stressed | summary | native/4 | 4.40 (4.26–4.50) | 9.76 | 134.3 |
| 4000 × 30 | stressed | full | old/1 | 52.41 (52.01–54.08) | 157.91 | 141.3 |
| 4000 × 30 | stressed | full | numpy/1 | 45.34 (45.18–46.35) | 92.13 | 140.2 |
| 4000 × 30 | stressed | full | native/1 | 44.23 (42.17–47.45) | 92.85 | 140.3 |
| 4000 × 30 | stressed | full | native/2 | 48.62 (43.83–52.30) | 92.96 | 141.8 |
| 4000 × 30 | stressed | full | native/4 | 45.50 (43.83–47.57) | 95.03 | 143.0 |
| 4000 × 60 | weighted | summary | old/1 | 7.44 (6.78–9.46) | 17.46 | 146.3 |
| 4000 × 60 | weighted | summary | numpy/1 | 6.41 (6.32–6.78) | 13.68 | 140.1 |
| 4000 × 60 | weighted | summary | native/1 | 4.55 (4.37–4.98) | 9.75 | 140.4 |
| 4000 × 60 | weighted | summary | native/2 | 4.96 (4.80–5.78) | 10.53 | 140.0 |
| 4000 × 60 | weighted | summary | native/4 | 5.95 (5.44–6.81) | 11.64 | 140.4 |
| 4000 × 60 | weighted | full | old/1 | 85.09 (81.12–88.93) | 251.83 | 152.6 |
| 4000 × 60 | weighted | full | numpy/1 | 59.03 (58.08–61.60) | 108.50 | 149.9 |
| 4000 × 60 | weighted | full | native/1 | 53.21 (51.76–54.09) | 104.09 | 150.2 |
| 4000 × 60 | weighted | full | native/2 | 55.79 (54.63–56.25) | 105.42 | 151.8 |
| 4000 × 60 | weighted | full | native/4 | 56.17 (53.64–69.31) | 104.99 | 153.1 |
| 32768 × 30 | normal | summary | old/1 | 23.99 (22.78–24.73) | 65.24 | 203.0 |
| 32768 × 30 | normal | summary | numpy/1 | 22.07 (21.56–23.00) | 44.47 | 177.1 |
| 32768 × 30 | normal | summary | native/1 | 12.56 (11.62–13.02) | 24.32 | 176.5 |
| 32768 × 30 | normal | summary | native/2 | 13.80 (12.95–14.05) | 25.77 | 175.0 |
| 32768 × 30 | normal | summary | native/4 | 15.05 (13.42–20.68) | 25.63 | 175.8 |
| 32768 × 30 | normal | full | old/1 | 452.64 (444.13–460.82) | 1324.25 | 226.4 |
| 32768 × 30 | normal | full | numpy/1 | 243.55 (237.20–279.93) | 445.74 | 208.6 |
| 32768 × 30 | normal | full | native/1 | 230.78 (219.45–238.92) | 440.93 | 208.9 |
| 32768 × 30 | normal | full | native/2 | 229.95 (222.88–274.66) | 432.59 | 210.2 |
| 32768 × 30 | normal | full | native/4 | 231.93 (226.24–236.02) | 441.85 | 216.4 |
| 32768 × 60 | stressed | summary | old/1 | 43.16 (39.85–43.39) | 125.76 | 278.1 |
| 32768 × 60 | stressed | summary | numpy/1 | 34.04 (33.35–34.72) | 64.12 | 221.2 |
| 32768 × 60 | stressed | summary | native/1 | 18.19 (18.13–19.22) | 31.20 | 221.5 |
| 32768 × 60 | stressed | summary | native/2 | 19.31 (19.11–19.74) | 33.05 | 221.5 |
| 32768 × 60 | stressed | summary | native/4 | 18.40 (17.79–21.06) | 31.25 | 220.6 |
| 32768 × 60 | stressed | full | old/1 | 783.53 (764.64–816.46) | 2335.99 | 323.9 |
| 32768 × 60 | stressed | full | numpy/1 | 386.94 (381.02–392.92) | 630.40 | 297.1 |
| 32768 × 60 | stressed | full | native/1 | 364.44 (338.71–403.88) | 602.77 | 283.7 |
| 32768 × 60 | stressed | full | native/2 | 347.23 (339.16–410.33) | 571.16 | 286.9 |
| 32768 × 60 | stressed | full | native/4 | 341.97 (336.62–342.38) | 560.47 | 291.4 |
| 32768 × 60 | weighted | summary | old/1 | 45.09 (40.42–45.16) | 126.54 | 279.1 |
| 32768 × 60 | weighted | summary | numpy/1 | 34.00 (33.68–34.27) | 61.97 | 222.3 |
| 32768 × 60 | weighted | summary | native/1 | 18.99 (18.59–19.44) | 30.68 | 222.7 |
| 32768 × 60 | weighted | summary | native/2 | 21.04 (19.38–21.16) | 31.42 | 221.1 |
| 32768 × 60 | weighted | summary | native/4 | 18.65 (17.98–18.74) | 31.01 | 221.6 |
| 32768 × 60 | weighted | full | old/1 | 747.36 (731.76–761.99) | 2257.88 | 325.0 |
| 32768 × 60 | weighted | full | numpy/1 | 330.12 (327.73–350.74) | 553.32 | 285.6 |
| 32768 × 60 | weighted | full | native/1 | 306.05 (304.96–308.49) | 530.06 | 285.6 |
| 32768 × 60 | weighted | full | native/2 | 323.45 (322.96–329.50) | 534.21 | 287.2 |
| 32768 × 60 | weighted | full | native/4 | 326.87 (318.93–331.71) | 534.32 | 292.1 |
