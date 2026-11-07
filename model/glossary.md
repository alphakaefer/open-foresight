# Glossary: German keys and values in the world model

The world model exists in two files with the same structure:

- `world_model.de.json`: the original in German.
- `world_model.en.json`: the English translation.

Both use the **same German JSON keys** and the **same machine-readable values**, because the Python engine (`engine/`) reads them.
Only human-readable text is translated. This glossary explains every key and every coded value that appears in the files.

## Top level

| Key | English meaning |
|---|---|
| `schema` | Format version of the file (`weltmodell/v1` = world model, version 1) |
| `meta` | Metadata: title, version, date, horizons |
| `treiber` | Drivers: the 33 forces that shape the future |
| `szenarien` | Scenarios: the 12 active future worlds, with probabilities |
| `treiber_kopplung` | Driver coupling: how strongly each driver pushes each scenario (number from -1 to +1, per driver and scenario) |
| `bayes` | Settings for the Bayesian update of probabilities |
| `anzeichen` | Early-warning indicators: 23 measurable or reportable signs that move the scenarios |
| `beendet` | Retired scenarios: earlier scenarios that were merged into others, with their successor |
| `pruefung` | Structural check: a traffic-light check of the model's quality |
| `aussensicht` | Outside view: the model compared with history (base rates) and with external anchors such as prediction markets |
| `journal` | Forecast journal: the probabilities of every published version, kept for later scoring |
| `zufluss` | Evidence inflow: how incoming signals are de-duplicated and combined |
| `stufen` | Magnitude levels: several thresholds for one indicator, each with its own strength |
| `spanne_massstab` | Range scale: how far a revision like the last one could move a probability at most |

## `meta`

| Key | English meaning |
|---|---|
| `titel` | Title |
| `version` | Model version (e.g. `1.4.0`) |
| `stand` | Date of this model version (ISO date) |
| `horizonte` | Forecast horizons: `2028`, `2032`, `2040` |

## `treiber` (drivers)

| Key | English meaning |
|---|---|
| `id` | Driver id: `T` technology, `M` macro and finance, `G` geopolitics and governance, `N` society, `OE` ecology (e.g. `T1`, `M3`, `OE2`) |
| `cluster` | Cluster (topic group): Technology, Macro and finance, Geopolitics and governance, Society, Ecology |
| `name` | Short name of the driver |
| `typ` | Type of driver (e.g. critical uncertainty, strong trend, wildcard); a label, not read by the engine |
| `frage` | Key question the driver raises |
| `stand_2026` | Status 2026: what the evidence shows today |
| `unsicherheit` | Uncertainty, 1 (low) to 5 (high) |
| `wirkung` | Impact, 1 (low) to 5 (high). Note: under `anzeichen`, `wirkung` means something else (see below) |
| `tempo` | Speed of change (fast, medium, slow, slow to abrupt); a label |
| `richtung` | Direction of the driver (e.g. rising, worsening, open); a label. Not the same as `anzeichen/wirkung/richtung` |
| `indikatoren` | Indicators to watch for this driver |
| `indikatoren/name` | What is measured |
| `indikatoren/schwelle` | Threshold: the value at which the situation changes |
| `indikatoren/quelle` | Source of the data |
| `kreuzwirkung` | Cross-impact: ids of other drivers this driver affects |

## `szenarien` (scenarios)

| Key | English meaning |
|---|---|
| `id` | Scenario id (`S01` ... `S17`; gaps are retired scenarios) |
| `name` | Scenario name |
| `kurz` | Short label: one line |
| `these` | Thesis: what happens, in two or three sentences |
| `einfach` | Plain-language summary: one sentence for non-experts |
| `narrativ` | Narrative: the story of how this world comes about |
| `regime` | Regime: the scenario's position on 10 axes, each from -2 to +2 (keys already in English: `growth`, `inflation`, `real_rates`, `tech_concentration`, `energy_price`, `geopol_stress`, `labor_disruption`, `institutional_trust`, `climate_damage`, `capital_scarcity`) |
| `treiber_konstellation` | Driver constellation: the state each relevant driver has in this scenario (driver id → -2 ... +2) |
| `wahrscheinlichkeit` | Probability in percent per horizon (`2028`, `2032`, `2040`); per horizon all scenarios add up to 100 |
| `fruehindikatoren` | Early indicators: what you would see first if this scenario is coming |
| `was_es_widerlegt` | What refutes it: evidence that would rule the scenario out |
| `kernpreis` | Core price: a single market price to watch for this scenario |
| `kernpreis/text` | Name of that price |
| `kernpreis/quelle` | Who chose it and when |
| `fassung` | Text version of the scenario (1, 2, ...) |
| `quadrant` | Macro quadrant from growth and inflation: Stagflation, Overheating, Goldilocks, Deflation, Borderline (growth or inflation exactly 0) |
| `quadrant_achsen` | The two axis values used for the quadrant: `wachstum` (growth), `inflation` |
| `quadrant_hinweis` | Note on the quadrant (only for borderline cases) |
| `nachfolger_von` | Successor of: the retired scenario this one replaced |
| `abgespalten_von` | Split off from: the scenario this one was carved out of |
| `seit` | Since: model version in which the scenario first appeared |

## `bayes`

| Key | English meaning |
|---|---|
| `k_daempfung` | Damping factor k: how strongly one signal moves the probabilities (`0` switches updating off) |

## `anzeichen` (early-warning indicators)

| Key | English meaning |
|---|---|
| `id` | Indicator id (`A01` ... `A13`, `AS01` ... `AS10`) |
| `bezug` | Reference: the scenario (or driver) the indicator belongs to |
| `rolle` | Role. `widerlegt` = refuting / counter-indicator: when it is triggered, its scenario goes **down**. If the key is missing, the indicator supports its scenario |
| `art` | Kind. `zahl` = number: checked automatically against a data series. `aussage` = statement: matched in news, counts only after a human confirms it |
| `text` | What the indicator says |
| `reihe` | Series id: the data series in the radar snapshot (e.g. `fred-brent`, `sffed-tfp-usa`) |
| `regel` | Rule: a small expression the engine evaluates on the series (see "Rule language" below) |
| `reihe2`, `regel2` | Second series and rule; both must hold |
| `muster` | Pattern: a regular expression matched against news titles and teasers (the news feed is German, so the pattern stays German) |
| `hinweis` | Note: how the value is measured |
| `warum` | Why: what the indicator means for the model |
| `wirkung` | Effect on drivers when the indicator switches |
| `wirkung/treiber_ids` | The drivers it moves |
| `wirkung/richtung` | Direction: `bestaetigend` = confirming (pushes the drivers' scenarios up), `widersprechend` = contradicting (pushes them down). The engine also knows `neutral` and `neu` (new, not yet classified); both move nothing |
| `wirkung/staerke` | Strength of the signal (at most 5) |

### Rule language (`regel`, `regel2`, `stufen/.../regel`)

| Rule | Meaning |
|---|---|
| `mittel n > x` / `mittel n < x` | The mean of the last n values is above / below x |
| `alle n > x` / `alle n < x` | All of the last n values are above / below x |
| `zwischen n a b` | The mean of the last n values lies between a and b |
| `jahresrueckgang n` | Annual decline: the annual mean fell n years in a row |
| `faellt n` / `steigt n` | Falls / rises: the mean of the last n values is below / above the mean of the n values before |

## `beendet` (retired scenarios)

| Key | English meaning |
|---|---|
| `id` | Id of the retired scenario |
| `name` | Its last name |
| `bis` | Valid until (date) |
| `bis_version` | Valid until model version |
| `nachfolger` | Successor: the scenario that took it over |
| `begruendung` | Reason for retiring it |

## `pruefung` (structural check)

| Key | English meaning |
|---|---|
| `ampel` | Traffic light for the whole model: `gruen` = green. Other possible values: `gelb` = yellow, `rot` = red |
| `stand` | Date of the check |
| `faellig` | Due: whether a new check is due now |
| `naechste` | Date of the next check |
| `begruendung` | Reasons for a yellow or red light (empty when green) |
| `kennzahlen` | Check metrics |
| `kennzahlen/schluessel` | Metric key: `fehlender_treiber` (missing driver), `keine_trennung` (scenarios no longer separate), `unbalanciert` (unbalanced scenario set), `effektive_dimension` (effective dimension: are the scenarios different enough), `krisenlast` (crisis load: share of probability on crisis scenarios) |
| `kennzahlen/frage` | The question the metric answers |
| `kennzahlen/status` | Traffic light of this metric (`gruen`, `gelb`, `rot`) |
| `kennzahlen/befund` | Finding |
| `krisenlast_begruendung` | Why the crisis load is where it is |

## `aussensicht` (outside view)

| Key | English meaning |
|---|---|
| `schema` | Format version of this block |
| `stand` | Date |
| `geschichte` | History: the reference class used for base rates |
| `geschichte/zeitraum` | Period |
| `geschichte/region` | Region |
| `geschichte/quelle` | Source |
| `geschichte/hinweis` | Note |
| `vergleiche` | Comparisons: model share vs. historical share for one class of worlds |
| `vergleiche/id` | Comparison id: `wachstum_schwach` (below-normal growth), `schrumpft` (economy shrinks), `stagflation`, `inflation_hoch` (high inflation), `energie_teuer` (expensive energy) |
| `vergleiche/frage` | The question, as a short label |
| `vergleiche/erklaerung` | Explanation: which scenarios count and what they are compared with |
| `vergleiche/szenarien` | The scenario ids that count |
| `vergleiche/geschichte` | Historical share in percent of years |
| `vergleiche/begruendung` | Justification of the deviation from history |
| `anker` | Anchors: external forecasts (e.g. prediction markets) |
| `anker/id` | Anchor id: `taiwan`, `rezession` (recession), `iwf` (IMF) |
| `anker/frage` | The external question |
| `anker/szenarien` | Scenarios it is compared with |
| `anker/horizont` | Horizon it is compared at |
| `anker/extern` | External probability in percent (number; `null` if there is none) |
| `anker/extern_text` | The external value as display text |
| `anker/quelle`, `anker/url`, `anker/datum` | Source, link, date |
| `anker/hinweis` | Note on how far the comparison holds |

## `journal` (forecast journal)

| Key | English meaning |
|---|---|
| `version` | Model version |
| `datum` | Date of publication |
| `szenarien` | Scenario names at that version (id → name) |
| `wahrscheinlichkeiten` | Probabilities at that version (horizon → scenario id → percent) |

## `zufluss` (evidence inflow)

| Key | English meaning |
|---|---|
| `entdoppeln` | De-duplication: the same event from several sources counts once |
| `entdoppeln/an` | Switch on (`true`) or off |
| `entdoppeln/buendel_exponent` | Bundle exponent beta: n signals on the same drivers in the same month share weight n^-beta |
| `ungerundet` | Unrounded: compute with exact rather than whole-number probabilities |
| `ungerundet/an` | Switch on or off |
| `ungerundet/p_min_prozent` | Floor: no scenario drops below this percentage |
| `ungerundet/basis_version` | Model version whose exact probabilities are the starting point |
| `p_basis` | Exact base probabilities (horizon → scenario id → percent) |
| `signale` | Signals since that base version |

## `stufen` (magnitude levels)

| Key | English meaning |
|---|---|
| `<indicator id>` | List of levels for this indicator; level 1 is the indicator's own rule |
| `regel` | Rule for the level |
| `staerke` | Strength of the level |

## `spanne_massstab` (range scale)

| Key | English meaning |
|---|---|
| `je_horizont` | Scale eta per horizon: relative entropy (Kullback-Leibler divergence) between the last two published versions |
| `quelle` | How the scale was computed |

## Fields left in German on purpose

These values stay identical in both files because the engine reads or compares them, or because they are ids:

- all ids (`T1`, `S01`, `A01`, `OE2`, `wachstum_schwach`, `taiwan`, ...), `bezug`, `nachfolger`, `nachfolger_von`, `abgespalten_von`, `kreuzwirkung`, `treiber_ids`
- `art` (`zahl`, `aussage`), `rolle` (`widerlegt`), `wirkung/richtung` (`bestaetigend`, `widersprechend`)
- `regel`, `regel2`, `reihe`, `reihe2`, `muster`, all rules under `stufen`
- `pruefung/ampel`, `pruefung/kennzahlen/status` (`gruen`), `pruefung/kennzahlen/schluessel`
- `schema` values, versions, dates, URLs, `geschichte/zeitraum`
- `kernpreis/quelle` (attribution with a German-format date)
