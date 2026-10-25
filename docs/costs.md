# Costs

Precomputed with `scripts/precompute.py` on `gpt-4.1-mini` (list price $0.40 per million input tokens, $1.60 per million output). Tokens are the totals of every agent run stored for the match (`agent_runs`), retries and regenerations included; re-runs only add what was missing.

| Match | Insights | Agent / template | Fan texts | Agent runs | Fallbacks | Tokens in | Tokens out | Cost (USD) | Run time |
|---|---|---|---|---|---|---|---|---|---|
| `r01-chapinero-v-laureles` | 33 | 28 / 5 | 690 | 500 | 64 | 2,691,955 | 204,492 | 1.40 | 23.4 min |
| `r11-el-poblado-v-san-fernando` | 23 | 15 / 8 | 485 | 287 | 33 | 1,753,181 | 118,864 | 0.89 | 15.8 min |
| `r11-laureles-v-san-antonio` | 22 | 18 / 4 | 440 | 336 | 32 | 1,913,095 | 136,111 | 0.98 | 10.6 min |
| `r13-getsemani-v-el-prado` | 37 | 33 / 4 | 775 | 546 | 75 | 2,643,028 | 213,140 | 1.40 | 22.1 min |
| `r24-san-antonio-v-manrique` | 19 | 13 / 6 | 390 | 247 | 30 | 1,526,654 | 108,946 | 0.79 | 8.3 min |
| `r26-barrio-abajo-v-usaquen` | 34 | 25 / 9 | 725 | 462 | 65 | 2,658,964 | 201,598 | 1.39 | 15.3 min |
| `r36-chapinero-v-usaquen` | 40 | 33 / 7 | 865 | 573 | 88 | 2,712,984 | 229,396 | 1.45 | 16.3 min |
| `r37-siloe-v-el-poblado` | 30 | 24 / 6 | 625 | 422 | 32 | 2,354,341 | 180,141 | 1.23 | 14.1 min |
| **Total (8 matches)** | 238 | | 4995 | 3373 | 419 | 18,254,202 | 1,392,688 | **9.53** | |
