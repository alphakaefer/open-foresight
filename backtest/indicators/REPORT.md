# Backtest: would the early-warning indicators have warned before 2008, 2020 and 2022?

The numeric early-warning indicators of the world model have rules on public data series. For this backtest, the series were refilled back to 1947 where available. Each indicator rule was re-applied month by month, with the same code that computes the daily world state (the scenario probabilities the engine recomputes from the base model and the latest data; the base model is the published model version with its scenario probabilities). The daily world state was then recomputed backwards for each quarter end since 2000, and for each quarter the committor q0 was computed (the probability that the world reaches the build-up scenarios before the crisis scenarios, given that quarter's scenario mix and the transition matrix; a low q0 means crisis first). Model version v1.4.0 (base 2026-10-09), run on 2026-10-30. Reproduce with `python3 pruefung/anzeichen_geschichte.py rechnen`; all outputs are in `backtest/indicators/`, the series in `backtest/indicators/reihen/`. None of this changes a number in the model or in `model/`. It is a hint, not a proof: there are three events, and the model was built in 2026 with knowledge of them (section 5).

## Result

**No numeric indicator would have warned selectively and in time before 2008, 2020 and 2022.** (Selective: rare enough to separate the months before an event from other months.) Of 18 testable indicators, a rare sign (under 16% of all months) held in the twelve months before an event only as follows: before 2008, A12 (Brent above 115 $, May to July 2008, i.e. four months before Lehman) and A02 (no effect); before 2020, none; before 2022, A07 (four months) and A08 (eight months). The frequent signs A01, A03, A04 and A13 (38 to 69% of all months) do not separate the time before the events from other times. Two indicators (AS03, AS09) cannot be tested: no free historical download.

**Committor backwards** (pair krise_aufbau, horizon 2028, provisional): before Lehman, q0 tipped briefly and weakly towards crisis (2008-06: 0.521, among the lowest 6% of all quarters since 2000, triggered by A12 alone, Brent); before 2020 and before 2022 it did not (2019-12: 0.557 and 2021-12: 0.569, both in the upper half). q0 tipped only in the event quarter itself (2020-03: 0.516; 2022-03: 0.509). Today q0 is 0.527, lower than 93% of the quarters since 2000.

**One sentence per indicator** (numbers from the tables below; "before" means: in the twelve months before the event month 2008-09, 2020-03, 2022-02):

| Indicator | Would it have warned earlier? |
|---|---|
| A01 TFP (total factor productivity) below 1.2% (counter-indicator to S02 AI Surge) | No. Holds in 471 of 946 months and before all three events; it says nothing about a break. |
| A02 Brent between 85 and 110 $ (no effect) | Moves nothing. It held for five months before 2008, not before 2020 and not before 2022 (only in the event month). |
| A03 TFP above 1.5% for six quarters | Not a crisis sign, and the threshold barely separates: it holds in 396 of 940 months (42%), 23 episodes (an episode is a run of consecutive months in which the rule holds) since 1948. |
| A04 Core inflation falls while GDP rises | No. Holds in 117 of 306 months (38%), 29 episodes, and before all three events. |
| A05 Brent above 110 $ for seven months | Never: one month in 468 (2011-09). It did not hold in 2022 either, and it does not hold today. |
| A06 Core inflation above 3% with weak demand | Too late: only episode 2023-04 to 2024-02, after the event of 2022. |
| A07 German industry in decline for two years | Only at the same time: not before 2008, not before 2020 (holds only from 2020-03), before 2022 from 2021-02 (four months, in the wake of the slump of 2020). Holds in 62 of 395 months. |
| A08 Real yield below zero with inflation above 3% | Yes, once: before 2022, eight months of lead time (from 2021-06). It is the only episode since 2003 (2021-06 to 2022-04); no hit rate can be formed from it. |
| A10 US tariff rate above 15% | Never held. Highest value of the series since 1959: 11.3% (2025-10), latest 6.85% (2026-07). The threshold lies above anything the series ever showed. |
| A11 Real yield above 2.5% | Never held. Highest monthly value since 2003: 2.89% (2008-11), but never three months in a row above 2.5. |
| A12 Brent above 115 $ | Before 2008 yes (May to July 2008, four months before Lehman, but the break came from the credit market, not from oil); before 2020 no; before 2022 no (holds only in March 2022). 13 months in 474. |
| A13 Brent below 70 $ | No. Holds in 325 of 474 months (69%). |
| AS01 Geopolitical risk around Germany at war level (index above 1.0) | At the same time, not before: 13 of 500 months, five episodes (1991, 2001, 2003, 2022, 2026); before 2022 no, in the event month 2022-02 yes. |
| AS04 V-Dem liberal democracy DE below 0.75 | Not testable: never below since 1991, today 0.782. The threshold has no case in the history of the Federal Republic. |
| AS05 V-Dem freedom of expression DE below 0.9 | Not testable: never below since 1991, today 0.914. |
| AS06 V-Dem liberal democracy USA below 0.5 | Not yet triggered: since the Second World War below only in 1949. The series fell from 0.852 (2013) to 0.571 (2025). |
| AS07 Exploited vulnerabilities above 27 per month | Not testable before 2026: the series starts 2022-06 (counted as in the radar). Three months with a hit, all in 2026. |
| AS10 Wealth share of the richest 0.1% above 15% | Never held: the series reaches 15.0 (2026-04), the rule requires strictly more. |
| AS03 Politically motivated violence rises, AS09 power outage per customer (SAIDI) | Gap: no free, machine-readable series (radar: "by hand"). Not estimated. |

The statements A09, AS02 and AS08 have no number and are not part of this. The plan named 14 public series; the 20 indicators with rule and series lead to 16, of which 14 can be fetched freely (all 14 stored) and 2 cannot (AS03, AS09).

## 1. The series

The source of each file is in the CSV header (`# Quelle` source, `# Adresse` URL, `# Abruf: 2026-10-30` fetch date, processing, location in the radar; overview in `backtest/indicators/SERIES.md`). Processed as in `radar/collector/radar-sammeln.php`: monthly mean of daily values (Brent, real yield), annual rate from the index (inflation), customs revenue divided by goods imports, quarters stored under their first month, the same rounding. The radar fetches FRED and Eurostat only four years back; here without this limit. No key, no account: FRED as `fredgraph.csv`, Eurostat via the open API, Our World in Data as CSV, CISA as JSON, SF Fed as an Excel file, Iacoviello as a Stata file (the radar's reader is ported to Python).

Check against today's radar value: the live radar snapshot of 2026-10-15 (`wissensstand.json`) and the live world state of 2026-10-29 (`weltlage.json`, field `zuletzt`, the latest value per indicator).

| Series | Indicators | Values | From | To | Radar snapshot of 2026-10-15 (radar vs. refilled series) | World state of 2026-10-29 (world state vs. refilled series) |
|---|---|---|---|---|---|---|
| cisa-kev-monat | AS07 | 52 | 2022-06 | 2026-09 | 2026-09: 43 vs. 43; 52 of 52 common points equal | 2026-09: 43 vs. 43 |
| eurostat-bip-ea | A04, A06 | 122 | 1996-01 | 2026-04 | 2026-04: 1.2 vs. 1.2; 8 of 16 common points equal | not as "zuletzt" |
| eurostat-industrie-de | A07 | 428 | 1991-01 | 2026-08 | 2026-07: 90.3 vs. 90.3; 47 of 47 common points equal | 2026-08: 90.8 vs. 90.8 |
| eurostat-kerninflation-ea | A04, A06 | 310 | 2000-12 | 2026-09 | 2026-09: 2.5 vs. 2.5; 45 of 45 common points equal | 2026-09: 2.5 vs. 2.5 |
| fed-dfa-top01 | AS10 | 148 | 1989-07 | 2026-04 | 2026-04: 15 vs. 15; 148 of 148 common points equal | 2026-04: 15 vs. 15 |
| fred-brent | A02, A05, A12, A13 | 474 | 1987-05 | 2026-10 | 2026-10: 125.32 vs. 124.83; 57 of 58 common points equal | 2026-10: 124.96 vs. 124.83 |
| fred-inflation-usa | A08 | 944 | 1948-01 | 2026-09 | 2026-08: 3.35 vs. 3.35; 43 of 43 common points equal | not as "zuletzt" |
| fred-realrendite-10j | A08, A11 | 286 | 2003-01 | 2026-10 | 2026-10: 2.92 vs. 2.8; 57 of 58 common points equal | 2026-10: 2.84 vs. 2.8 |
| fred-zollsatz-usa | A10 | 271 | 1959-01 | 2026-07 | 2026-04: 8.22 vs. 8.22; 18 of 18 common points equal | 2026-04: 8.22 vs. 8.22 |
| gpr-deu | AS01 | 501 | 1985-01 | 2026-09 | 2026-09: 0.49 vs. 0.49; 501 of 501 common points equal | 2026-09: 0.49 vs. 0.49 |
| sffed-tfp-usa | A01, A03 | 317 | 1947-04 | 2026-04 | 2026-04: 0.09 vs. 0.62; 1 of 18 common points equal | 2026-04: 0.62 vs. 0.62 |
| vdem-libdem-de | AS04 | 191 | 1789-01 | 2025-01 | 2025-01: 0.782 vs. 0.782; 191 of 191 common points equal | 2025-01: 0.782 vs. 0.782 |
| vdem-libdem-usa | AS06 | 237 | 1789-01 | 2025-01 | 2025-01: 0.571 vs. 0.571; 237 of 237 common points equal | 2025-01: 0.571 vs. 0.571 |
| vdem-meinungsfreiheit-de | AS05 | 191 | 1789-01 | 2025-01 | 2025-01: 0.914 vs. 0.914; 191 of 191 common points equal | 2025-01: 0.914 vs. 0.914 |

Reading: eleven of the 14 series match the radar snapshot in the latest point; ten of the twelve series with "zuletzt" match the world state of 2026-10-29. Brent and the real yield differ (in both) only in the current month of October (partial month, different fetch time: 124.83 against 125.32 in the radar snapshot and 124.96 in the world state); in all 57 earlier common months they agree. TFP matches the world state of 2026-10-29 (0.62), not the radar snapshot of 2026-10-15 (0.09): the SF Fed file changed in between, the series is revised backwards (only 1 of 18 common quarters equal). For euro area GDP, 8 of 16 quarters differ by 0.1 (revisions). GPR (501 of 501), V-Dem (all three), CISA and the wealth series agree in every common point; this also tests the Stata reader, ported to Python, on real data. On core inflation: it comes from two datasets (old up to 12/2025, new under ECOICOP 2, the revised EU classification of consumer spending). The new one already has values from 2000-12 and replaces the old one where both have values (as in the radar): they differ by 0.1 in 20 of 289 common months.

**Check of an earlier source survey.** An earlier, unpublished research note on the sources was checked against the downloads. **Correct:** all 14 free URLs (each delivered without a key), the two gaps (BKA, the Federal Criminal Police Office, and BNetzA, the Federal Network Agency; not downloaded here; the radar comment says "by hand"), the locations of the series in the radar, the start years TFP 1947, inflation 1947 (index; the annual rate from 1948-01), real yield 2003, tariffs 1959 and imports 1947, wealth share 1989-07, GPR 1985, V-Dem from 1789, CISA from 2022-06. **Not correct:** (1) Brent: the URL (daily series `DCOILBRENTEU`) starts on 1987-05-20, monthly means from 1987-05; "first row 1987-06-01" belongs to the monthly series. (2) Core inflation: "the new series starts 01/2026" is wrong; it has values from 2000-12 (see above). **Open in the survey, now confirmed:** industry Germany from 1991-01, euro area GDP from 1996-01 (values up to 2026-04; the survey names 2026-Q3 without a value), core inflation from 2000-12; the Eurostat, V-Dem and CISA downloads were loaded in the run. Licences were not checked here; the CSV headers name only the source, as the radar names it.

## 2. Hits per indicator

For every month, the rule of each numeric indicator (field `anzeichen` in `model/world_model.de.json`) is applied with `tagesstand.pruefe` to the values up to that month, i.e. with the code of the daily world state (`gilt`, `pruefe` in `engine/tagesstand.py`). A12 counts here with level 1 (the indicator's own rule). "Data from" is the first month in which the rule has a status (for `jahresrueckgang 2`, 36 months of lead-in). Months after the last value of a series keep counting with the last value, as in the daily world state; for annual series (V-Dem) this means: the value of a year holds from January. In brackets: the length in months. Rules are written in the model's rule language (`model/glossary.md`, section "Rule language").

| Indicator | Series | Rule | Data from | Months with a hit | Episodes (start to end) |
|---|---|---|---|---|---|
| A01 | sffed-tfp-usa | mittel 4 < 1.2 | 1948-01 | 471 of 946 | 30, first 1949-01 to 1949-12; longest 2015-04 to 2019-09 (54); last 2024-10 to 2025-06 (9) |
| A02 | fred-brent | zwischen 3 85 110 | 1987-07 | 52 of 472 | 12, first 2007-12 to 2008-04; longest 2013-11 to 2014-11 (13); last 2026-04 to 2026-09 (6) |
| A03 | sffed-tfp-usa | mittel 6 > 1.5 | 1948-07 | 396 of 940 | 23, first 1948-07 to 1949-03; longest 1961-10 to 1967-03 (66); last 2025-07 to 2025-09 (3) |
| A04 | eurostat-kerninflation-ea + eurostat-bip-ea | faellt 3 and eurostat-bip-ea: alle 2 > 0 | 2001-05 | 117 of 306 | 29, first 2002-06 to 2003-05; longest 2023-06 to 2024-07 (14); last 2026-01 to 2026-03 (3) |
| A05 | fred-brent | alle 7 > 110 | 1987-11 | 1 of 468 | 2011-09 to 2011-09 (1) |
| A06 | eurostat-kerninflation-ea + eurostat-bip-ea | alle 3 > 3 and eurostat-bip-ea: mittel 2 < 1 | 2001-02 | 11 of 309 | 2023-04 to 2024-02 (11) |
| A07 | eurostat-industrie-de | jahresrueckgang 2 | 1993-12 | 62 of 395 | 9, first 1993-12 to 1994-08; longest 2024-10 to 2026-10 (25); last 2024-10 to 2026-10 (25) |
| A08 | fred-realrendite-10j + fred-inflation-usa | alle 3 < 0 and fred-inflation-usa: alle 3 > 3 | 2003-03 | 11 of 284 | 2021-06 to 2022-04 (11) |
| A10 | fred-zollsatz-usa | alle 2 > 15 | 1959-04 | 0 of 811 | none |
| A11 | fred-realrendite-10j | alle 3 > 2.5 | 2003-03 | 0 of 284 | none |
| A12 | fred-brent | mittel 1 > 115 | 1987-05 | 13 of 474 | 9, first 2008-05 to 2008-07; longest 2008-05 to 2008-07 (3); last 2026-10 to 2026-10 (1) |
| A13 | fred-brent | mittel 1 < 70 | 1987-05 | 325 of 474 | 10, first 1987-05 to 2006-03; longest 1987-05 to 2006-03 (227); last 2025-08 to 2026-01 (6) |
| AS01 | gpr-deu | mittel 3 > 1.0 | 1985-03 | 13 of 500 | 5, first 1991-02 to 1991-03; longest 2022-02 to 2022-07 (6); last 2026-05 to 2026-05 (1) |
| AS04 | vdem-libdem-de | mittel 1 < 0.75 | 1789-01 | 2424 of 2854 | 1789-01 to 1990-12 (2424) |
| AS05 | vdem-meinungsfreiheit-de | mittel 1 < 0.9 | 1789-01 | 2424 of 2854 | 1789-01 to 1990-12 (2424) |
| AS06 | vdem-libdem-usa | mittel 1 < 0.5 | 1789-01 | 1896 of 2854 | 1789-01 to 1945-12 (1884); 1949-01 to 1949-12 (12) |
| AS07 | cisa-kev-monat | mittel 3 > 27 | 2022-08 | 3 of 51 | 2026-04 to 2026-04 (1); 2026-09 to 2026-10 (2) |
| AS10 | fed-dfa-top01 | alle 2 > 15 | 1989-10 | 0 of 445 | none |

Whether the indicator held in the twelve months before an event (from when, how many months; "in event month" is shown separately, because a sign that only holds with the event did not warn). The events are a choice made for this backtest, not a judgement of the model: 2008-09 Lehman bankruptcy (the financial crisis began as early as August 2007), 2020-03 pandemic, 2022-02 Russia's attack on Ukraine.

| Indicator | before 2008-09 | before 2020-03 | before 2022-02 |
|---|---|---|---|
| A01 | yes, from 2007-09 (12 months; in event month: yes) | yes, from 2019-03 (9 months; in event month: yes) | yes, from 2022-01 (1 month; in event month: yes) |
| A02 | yes, from 2007-12 (5 months; in event month: no) | no; in event month: no | no; in event month: yes |
| A03 | no; in event month: no | no; in event month: no | yes, from 2021-02 (12 months; in event month: yes) |
| A04 | yes, from 2007-09 (10 months; in event month: no) | yes, from 2019-03 (4 months; in event month: no) | yes, from 2021-05 (3 months; in event month: no) |
| A05 | no; in event month: no | no; in event month: no | no; in event month: no |
| A06 | no; in event month: no | no; in event month: no | no; in event month: no |
| A07 | no; in event month: no | no; in event month: yes | yes, from 2021-02 (4 months; in event month: no) |
| A08 | no; in event month: no | no; in event month: no | yes, from 2021-06 (8 months; in event month: yes) |
| A10 | no; in event month: no | no; in event month: no | no; in event month: no |
| A11 | no; in event month: no | no; in event month: no | no; in event month: no |
| A12 | yes, from 2008-05 (3 months; in event month: no) | no; in event month: no | no; in event month: no |
| A13 | no; in event month: no | yes, from 2019-03 (10 months; in event month: yes) | yes, from 2021-02 (4 months; in event month: no) |
| AS01 | no; in event month: no | no; in event month: no | no; in event month: yes |
| AS04 | no; in event month: no | no; in event month: no | no; in event month: no |
| AS05 | no; in event month: no | no; in event month: no | no; in event month: no |
| AS06 | no; in event month: no | no; in event month: no | no; in event month: no |
| AS07 | no data | no data | no data |
| AS10 | no; in event month: no | no; in event month: no | no; in event month: no |

## 3. The daily world state backwards

For each quarter end from 2000-03 (to 2026-09; plus 2026-10 as a cross-check), computed with `tagesstand.aus_status` and `rechne_am`, like the daily world state: the status in the base model (series up to 2026-10) against the status on the reference date (series up to then). Where it changes, a signal to the drivers arises. It runs through the same Bayes update step with the switches set in `model/world_model.de.json` (de-duplication and unrounded on, magnitude levels for A12). The script rebuilds the signals itself once more to get the exact posterior; at each reference date it checks that the same rounded percentages come out as from `aus_status` (otherwise it stops). At the last reference date (2026-10) the result is today's daily world state, and nothing moves; the test `test_lage_am_juengstem_monat_ist_der_tagesstand` checks this against `tagesstand.tagesstand`.

**The limit first:** the prior is today's base model (v1.4.0). What holds today (A07, A12 and AS07) is priced in there; at every earlier reference date on which it did not hold, it appears as "dropped" (opposite direction) and shifts against the base. Therefore, read the differences between the reference dates, not the level against the base. The numbers are not a forecast from back then.

Step 3 over 107 quarter ends 2000-03 to 2026-09: the set of holding indicators changes in 74 of 106 quarter-to-quarter transitions; largest shift of one scenario for 2028 per quarter: median 2.9, at most 5.7 (reference date 2024-09) points, at least 0.9 (reference date 2012-03).

In 54 of the 74 transitions with a change, the change concerns only A01, A02, A03, A04 or A13, i.e. the frequent signs (A02 moves nothing). Here are the reference dates around the three events (the full table, 108 rows, is in `backtest/indicators/tabellen.md` and `backtest/indicators/tagesstand_rueckwaerts.csv`; there also the exact shift in points per scenario and horizon):

| Reference date | Holding | Appeared vs. base | Dropped vs. base | Largest move 2028 | Largest move 2032 | Largest move 2040 |
|---|---|---|---|---|---|---|
| 2007-06 | A01 | A01 | A07, A12 | S01 -2.5 | S15 +1.8 | S08 +1.9 |
| 2007-09 | A01, A04 | A01, A04 | A07, A12 | S01 -3.7 | S08 +4.8 | S08 +5.9 |
| 2007-12 | A01, A02 | A01 | A07, A12 | S01 -2.5 | S15 +1.8 | S08 +1.9 |
| 2008-03 | A01, A02, A04 | A01, A04 | A07, A12 | S01 -3.7 | S08 +4.8 | S08 +5.9 |
| 2008-06 | A01, A04, A12 | A01, A04 | A07 | S03 +1.2 | S08 +1.1 | S08 +1.4 |
| 2008-09 | A01 | A01 | A07, A12 | S01 -2.5 | S15 +1.8 | S08 +1.9 |
| 2008-12 | A01, A13 | A01, A13 | A07, A12 | S01 -2.5 | S15 +1.8 | S08 +1.9 |
| 2019-09 | A01, A04, A13 | A01, A04, A13 | A07, A12 | S01 -3.7 | S08 +4.8 | S08 +5.9 |
| 2019-12 | A13 | A13 | A07, A12 | S04 -2.5 | S08 +2.6 | S08 +3.0 |
| 2020-03 | A01, A07, A13 | A01, A13 | A12 | S01 -2.0 | S08 +1.3 | S08 +1.5 |
| 2020-06 | A01, A07, A13 | A01, A13 | A12 | S01 -2.0 | S08 +1.3 | S08 +1.5 |
| 2021-09 | A03, A08 | A03, A08 | A07, A12 | S13 +2.8 | S13 +3.9 | S13 +4.4 |
| 2021-12 | A03, A08 | A03, A08 | A07, A12 | S13 +2.8 | S13 +3.9 | S13 +4.4 |
| 2022-03 | A01, A02, A03, A08, A12, AS01 | A01, A03, A08, AS01 | A07 | S01 +3.5 | S08 -3.7 | S08 -5.0 |
| 2022-06 | A01, A12, AS01 | A01, AS01 | A07 | S04 +2.4 | S02 -1.8 | S02 -1.9 |
| 2022-09 | A01, A02 | A01 | A07, A12, AS07 | S15 +3.4 | S15 +4.0 | S15 +4.2 |
| 2026-09 | A02, A07, AS07 | none | A12 | S01 -1.7 | S08 +2.2 | S08 +2.7 |
| 2026-10 | A07, A12, AS07 | none | none | S01 +0.0 | S01 +0.0 | S01 +0.0 |

Scenarios in the tables: S01 Grinding Ascent, S02 AI Surge, S03 The Bust, S04 Energy-Driven Stagflation, S08 Green Boom on Cost, S13 Distribution Fight in the Welfare State, S15 European Restart, S17 Taiwan Rupture.

The same reference dates for the crisis and the build-up scenarios of the pair krise_aufbau (sum of the shift of scenarios S03, S04, S17 against S02, S08, S15, in points against the base, per horizon):

| Reference date | Crisis S03+S04+S17 2028 | Crisis S03+S04+S17 2032 | Crisis S03+S04+S17 2040 | Build-up S02+S08+S15 2028 | Build-up S02+S08+S15 2032 | Build-up S02+S08+S15 2040 |
|---|---|---|---|---|---|---|
| 2008-06 | +1.2 | +0.7 | +0.5 | +0.6 | +1.0 | +1.1 |
| 2008-09 | +0.6 | -0.1 | -0.3 | +2.1 | +2.5 | +2.2 |
| 2019-12 | -2.3 | -2.6 | -2.2 | +4.5 | +5.4 | +5.5 |
| 2020-03 | +1.9 | +1.1 | +0.7 | +0.7 | +0.9 | +0.7 |
| 2021-12 | -4.7 | -4.0 | -3.3 | +2.6 | +2.8 | +2.1 |
| 2022-03 | +0.9 | +1.9 | +1.6 | -4.4 | -5.8 | -6.9 |

## 4. The committor backwards

q0 per reference date with the distribution from step 3 (exact posterior of horizon 2028; 2032 and 2040 in the CSV), computed with `engine/committor.py`, the three pairs and the generator (transition matrix) from `model/uebergaenge.json`. The pairs: krise_aufbau (crisis S03, S04, S17 against build-up S02, S08, S15), klima (S09 Climate Shock Cascade against S08 Green Boom on Cost), gesellschaft (S14 Divided Society against S15 European Restart). The transitions and the pairs are proposals, and the switch is off; everything here is provisional, as in the transition check of the source model repository (not included here). The q values per scenario do not depend on the reference date (they depend only on the chain); q0 changes only through the distribution. The base is 0.527 (the transition check gives 0.53, with the rounded percentages of the nearest horizon; the same).

Question: would q0 have tipped towards crisis before 2008, 2020 and 2022? "Tipped" here means (a choice made for this backtest): q0 at the quarter end before the event lies among the lowest 10% of all quarter ends 2000-03 to 2026-09. A low q0 means: the world is more likely to tip into crisis scenarios (S03, S04, S17) first than into build-up scenarios (S02, S08, S15).

| Event | q0 at the quarter end before | four quarters earlier | Change | Rank of the change among all four-quarter changes | Rank of the level among all quarters | q0 in the event quarter | Tipped? |
|---|---|---|---|---|---|---|---|
| 2008-09 (2008) | 2008-06: 0.521 | 2007-06: 0.529 | -0.008 | 38 % ≤ | 6 % ≤ | 2008-09: 0.529 (+0.008, level 37 % ≤) | yes |
| 2020-03 (2020) | 2019-12: 0.557 | 2018-12: 0.548 | +0.009 | 62 % ≤ | 64 % ≤ | 2020-03: 0.516 (-0.041, level 5 % ≤) | no |
| 2022-02 (2022) | 2021-12: 0.569 | 2020-12: 0.585 | -0.016 | 33 % ≤ | 69 % ≤ | 2022-03: 0.509 (-0.060, level 2 % ≤) | no |

All 107 quarter ends 2000-03 to 2026-09: q0 (krise_aufbau, 2028) from 0.495 to 0.630, mean 0.556, median 0.548; base 2026-10: 0.527 (7% of the quarters lie at or below it).

- **2008:** yes, but briefly and for the wrong reason. The level of 2008-06 (0.521) is among the lowest 6%; the change against four quarters earlier (−0.008) is unremarkable (38% of all four-quarter changes lie below it). It was triggered by A12 alone (Brent above 115 $ in May to July 2008; it also holds today and so no longer counts as "dropped" against the base): the model reads an oil price shock; it has no sign for a credit and banking break. At the quarter end 2008-09, the quarter of Lehman, q0 is back at 0.529, the 37% level.
- **2020:** no. The quarter before (2019-12) is at 0.557, in the upper half; q0 tipped only in the event quarter (2020-03: 0.516, the lowest 5%), because A07 holds (the industry index falls from 105.4 in February to 94.2 in March 2020) and A01 appears: at the same time, not before.
- **2022:** no. 2021-12 is at 0.569 (69% of the quarters are lower or equal). q0 tipped in the event quarter (2022-03: 0.509; 2022-06: 0.495, the lowest value of the whole series), with A12 and AS01 in March 2022.
- All quarter ends together lie between 0.495 and 0.630; q0 jumps between a few states, depending on which signs hold (levers, i.e. the change in q0 when one indicator switches on, from the transition check for krise_aufbau: A03 +0.039, A01 −0.029, A04 +0.020).

Course over time (selection; full table in `backtest/indicators/tabellen.md` and `backtest/indicators/committor_rueckwaerts.csv`, there also the pairs klima and gesellschaft for 2032 and 2040):

| Reference date | q0 krise_aufbau 2028 | q0 klima 2028 | q0 gesellschaft 2028 | q0 krise_aufbau 2032 | q0 krise_aufbau 2040 |
|---|---|---|---|---|---|
| base 2026-10 | 0.527 | 0.586 | 0.374 | 0.589 | 0.637 |
| 2007-06 | 0.529 | 0.589 | 0.379 | 0.597 | 0.646 |
| 2007-09 | 0.548 | 0.600 | 0.378 | 0.623 | 0.673 |
| 2007-12 | 0.529 | 0.589 | 0.379 | 0.597 | 0.646 |
| 2008-03 | 0.548 | 0.600 | 0.378 | 0.623 | 0.673 |
| 2008-06 | 0.521 | 0.589 | 0.374 | 0.587 | 0.638 |
| 2008-09 | 0.529 | 0.589 | 0.379 | 0.597 | 0.646 |
| 2008-12 | 0.529 | 0.589 | 0.379 | 0.597 | 0.646 |
| 2019-09 | 0.548 | 0.600 | 0.378 | 0.623 | 0.673 |
| 2019-12 | 0.557 | 0.594 | 0.381 | 0.624 | 0.672 |
| 2020-03 | 0.516 | 0.588 | 0.374 | 0.583 | 0.634 |
| 2020-06 | 0.516 | 0.588 | 0.374 | 0.583 | 0.634 |
| 2021-09 | 0.569 | 0.586 | 0.381 | 0.626 | 0.668 |
| 2021-12 | 0.569 | 0.586 | 0.381 | 0.626 | 0.668 |
| 2022-03 | 0.509 | 0.577 | 0.372 | 0.558 | 0.604 |
| 2022-06 | 0.495 | 0.581 | 0.373 | 0.553 | 0.603 |
| 2022-09 | 0.544 | 0.594 | 0.392 | 0.615 | 0.663 |
| 2026-09 | 0.545 | 0.592 | 0.376 | 0.612 | 0.660 |
| 2026-10 | 0.527 | 0.586 | 0.374 | 0.589 | 0.637 |

**Second computation of the committor (independent implementation, not yet reviewed, not included here):** an independent second implementation of the committor was run once against `engine/committor.py`: its 4 of 4 tests pass, and on the real pairs the largest deviation of q is 1.1e-16 (krise_aufbau, klima) and 5.6e-17 (gesellschaft). The lever is not computed a second time there.

## 5. Limits and gaps

- **Hindsight bias.** The model was built in 2026 with knowledge of 2008, 2020 and 2022; indicators and thresholds (110 $, 115 $, 70 $, 3%, 15%) date from 2026. If a sign does not match history, that speaks against the threshold; if it does match, that is no evidence, because the threshold may have been built to fit history. Whether it was, has not been checked.
- **Three events.** With three cases there is no hit rate and no test. The choice of events, the twelve-month window and the tipping rule (lowest 10%) are choices made for this backtest; with other windows (2007-08 as the start of the crisis) the finding for 2008 can change. This is a hint, not a proof.
- **Today's prior.** See section 3: the base is v1.4.0, as of 2026-10-09; the horizons are fixed (2028, 2032, 2040) and the same for every reference date. q0 is "what today's model would have said about 2028 if this had held back then", not the state of the world on the reference date.
- **Today's values, without publication lag.** Revised series (TFP, GDP, Eurostat), no vintages (no data as first published). Quarterly values count from the first month of the quarter, annual values from January (according to the earlier source survey, V-Dem is published every March for the previous year). In reality each sign would have been noticed weeks to more than a year later; the warnings in the tables are therefore the most favourable reading.
- **Short series.** AS07 from 2022-06; A04 and A06 from 2001; A07 needs 36 months (data from 1993-12); A08 and A11 from 2003; V-Dem thresholds have no case since 1991. Where there are no data before an event, the table says "no data", and this does not count as a failure to warn.
- **Series that end earlier** stay at their last value (V-Dem 2025-01, TFP and wealth share 2026-04, industry 2026-08, core inflation 2026-09), as in the daily world state.
- **Core inflation:** the new series (ECOICOP 2) replaces the old one backwards where both have values; 20 of 289 months differ by 0.1 (as in the radar).
- **Gaps:** AS03 (bka-pmk-gewalt) and AS09 (bnetza-saidi): no free, machine-readable historical download (radar comment "by hand"; the earlier source survey names a PDF and a web page, not downloaded here). Not estimated.
- **Not computed:** the lever backwards, and steps 3 and 4 with magnitude levels for indicators other than A12 (only A12 has levels in the model file). q0 with a set pi0 (the starting distribution "where are we today?", to be set by the model owner; `filter.pi0` in `model/uebergaenge.json` is empty) and with fixed transitions (all still proposals).
- **File name:** the source model repository already has a script `pruefung/geschichte.py` (years 1973 to 2025, for the base rates of the outside view). This script is therefore called `pruefung/anzeichen_geschichte.py`, the test `tests/test_anzeichen_geschichte.py`.

## 6. Files and how to repeat

`pruefung/anzeichen_geschichte.py` (standard library only), `tests/test_anzeichen_geschichte.py` (24 tests in this repository), and in the folder `backtest/indicators/`: `reihen/*.csv` (14 series with source header), `radar_vergleich.csv` (comparison with the radar snapshot), `weltlage_vergleich.csv` (comparison with the world state), `treffer_monate.csv` (hits per month), `treffer_episoden.csv` (episodes), `treffer_vor_ereignissen.csv` (hits before the events), `tagesstand_rueckwaerts.csv` (daily world state backwards), `committor_rueckwaerts.csv` (committor backwards), `tabellen.md` (all tables, generated, German). Compute with the stored series (no network):

```bash
python3 pruefung/anzeichen_geschichte.py rechnen     # or: make backtest
```

The comparison in section 1 needs two optional inputs: `--radar` with the live radar snapshot of 2026-10-15 (`wissensstand.json`) and `--weltlage` with the live world state of 2026-10-29 (`weltlage.json`). Without them, the stored `radar_vergleich.csv` and `weltlage_vergleich.csv` are left as they are.

To fetch the series again: download the raw files into a folder (names: `brent.csv` `dfii10.csv` `cpi.csv` `zoll.csv` `einfuhr.csv` `dfa.csv` `tfp.xlsx` `industrie.json` `kern_alt.json` `kern_neu.json` `bip.json` `gpr.dta` `libdem.csv` `freiheit.csv` `kev.json`; the URLs are in the header of each CSV) and run `python3 pruefung/anzeichen_geschichte.py reihen --roh FOLDER`. On 2026-10-30, FRED rejected several simultaneous requests; one at a time with pauses, all of them worked.
