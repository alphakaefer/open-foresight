.PHONY: test energy worldstate sources snapshot app

test:            ## reproduce the published world state, run all model tests
	python3 -m pytest tests -q

energy:          ## break the world model down to the energy-transition question
	python3 domains/lens.py energy-transition

worldstate:      ## recompute today's world state from model + radar snapshot
	python3 -m engine.tagesstand --modell model/world_model.de.json \
	  --wissensstand radar/snapshot/wissensstand.json --ziel radar/snapshot/weltlage.recomputed.json

sources:         ## regenerate the radar source list
	python3 radar/list_sources.py > radar/SOURCES.md

snapshot:        ## fetch the latest public radar snapshot (then: make worldstate energy sources)
	bash radar/fetch_snapshot.sh

app:             ## run the Foresight Studio web app
	cd app && npm install && npm run dev
