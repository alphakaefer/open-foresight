# The foresight process, from world to domain

Foresight here works on two levels. The **world model** answers "what kind of world will we be in?" for everyone.
A **domain** answers one concrete question inside that world ("how fast can the energy transition turn capacity
into usable electricity?"). The domain never re-estimates the world; it takes the world's scenarios and
probabilities as given and adds only what is specific to the domain.

| Step | Question | World level (shared) | Domain level (per question) | Where |
|---|---|---|---|---|
| 0. Frame | What do we want to know, by when, for whom? | Fixed horizons 2028 / 2032 / 2040 | `question`, `horizons` in `domain.json` | `domains/<name>/domain.json` |
| 1. Evidence & signals | What is happening already? | Radar: open data series + news + research, daily | Domain series selected from the radar (`radar_series`) | `radar/`, briefing §4 |
| 2. Drivers / key factors | What moves the outcome? | 33 drivers with type (trend, critical uncertainty, wildcard) and coupling to scenarios | Linked world drivers (judgment, with reason) + domain factors (bottleneck axes) | briefing §2 and §5 |
| 3. Scenarios | Which futures are plausible, how likely? | 12 mutually exclusive scenarios per horizon, each with a regime vector (energy price, climate damage, growth …) and probabilities | Scenarios seen through the domain's regime keys; probability mass per regime | briefing §1 |
| 4. Monitoring | How do we notice which future arrives? | 23 early-warning indicators as testable rules on data series; status change → Bayes update | Indicators that touch the linked drivers or domain series | briefing §3, `engine/tagesstand.py` |
| 5. Options | What should we do? | – (the world model does not recommend) | Options scored across scenarios: expected value, worst case, minimax regret | applications on top (e.g. Foresight Studio, separate repo) |

## Rules that keep it transparent

1. **Numbers come from files, not from memory.** Every probability, threshold and data point in a briefing is read
   from `model/`, `radar/` or computed by a formula in `engine/` or `domains/lens.py`.
2. **A link is a judgment and says so.** "Driver T8 matters for the energy transition" is not model output. It
   stands in `domain.json` with `"judgment": true` and a reason, so a reviewer can disagree with one line.
3. **Rules beat hand-picking.** Scenarios enter the domain by their regime values, indicators by the drivers and
   series they touch. Change the rule, not the list.
4. **Gaps stay visible.** Missing sources are marked `GAP`, missing data `no data in snapshot`.
5. **Recompute, never carry forward.** The world state is rebuilt from base model + data on every run;
   `make test` proves that the published state follows from the public inputs.

## Adding a new domain

```bash
cp -r domains/energy-transition domains/my-domain
$EDITOR domains/my-domain/domain.json     # question, linked drivers (with why), radar series, factors
python3 domains/lens.py my-domain         # writes briefing.md and briefing.json
```

The bottleneck model is optional; drop `bottleneck_model` if the domain has no complementary components, or
replace it with your own factor model and add a test like `tests/test_domain_energy.py`.
