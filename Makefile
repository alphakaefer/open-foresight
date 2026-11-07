.PHONY: test energy backtest worldstate sources snapshot ui regional

test:            ## reproduce the published world state, run all model tests
	python3 -m pytest tests explain/test_check_numbers.py -q

energy:          ## break the world model down to the energy-transition question
	python3 domains/lens.py energy-transition

backtest:        ## rerun the indicator backtest (2008, 2020, 2022) from the committed series
	python3 pruefung/anzeichen_geschichte.py rechnen
	python3 backtest/list_series.py > backtest/indicators/SERIES.md

worldstate:      ## recompute today's world state from model + radar snapshot
	python3 -m engine.tagesstand --modell model/world_model.de.json \
	  --wissensstand radar/snapshot/wissensstand.json --ziel radar/snapshot/weltlage.recomputed.json

sources:         ## regenerate the radar source list
	python3 radar/list_sources.py > radar/SOURCES.md

snapshot:        ## fetch the latest public radar snapshot (then: make worldstate energy sources)
	bash radar/fetch_snapshot.sh

ui:              ## serve the UI prototype at http://localhost:8000/ui/ (serves the repo root)
	python3 -m http.server 8000

regional:        ## fetch per-country and per-state values for the map comparisons (needs internet)
	python3 radar/fetch_regional.py
