.PHONY: test energy backtest worldstate sources snapshot

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
