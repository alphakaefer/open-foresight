# Regional values for the map comparisons

`regional.json` is written by `python3 radar/fetch_regional.py` (`make regional`). Every dataset records its source,
a URL and the period each value refers to. Values are as the source publishes them: nothing is estimated, and a region
without a value stays empty.

| Dataset | Regions | Source | Note |
|---|---|---|---|
| `wb_res`, `wb_energy_pc` | countries | World Bank WDI | latest year per country, mostly 2021 or 2022 |
| `es_res_elec`, `es_import_dep`, `es_price_hh`, `es_hicp_energy` | European countries | Eurostat | latest period per country |
| `mastr_wind`, `mastr_pv` | German states | Marktstammdatenregister, Bundesnetzagentur | unit counts in operation on the fetch date, not capacity |

The MaStR figures count registered units. They do not measure installed capacity, and they are not per head of
population. Check each source's terms of use before reusing the values; as for the radar series, they stay under the
licences of their publishers (see `LICENSE-DATA.md`).

The file depends on live sources, so it is not part of CI. `make test` and the UI read the committed copy.
