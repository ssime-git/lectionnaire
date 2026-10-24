.DEFAULT_GOAL := help

PYTHON := uv run python
DEMO_DAYS := 2026-07-08 2026-12-17 2026-02-21
# Moteur de rédaction : claude (abonnement Pro) ; MOTEUR=workers-ai pour Workers AI.
MOTEUR ?= claude

.PHONY: help setup test check validate render index catalogue generate serve

help:
	@echo "make setup | test | check | validate DATE=AAAA-MM-JJ | render DATE=AAAA-MM-JJ | index | catalogue | generate DATE=AAAA-MM-JJ | serve"

setup:
	uv sync

test:
	$(PYTHON) -m unittest discover -s tests -v
	node --test 'tests/js/*.test.mjs'

check: test
	@for day in $(DEMO_DAYS); do $(PYTHON) src/valider.py data/jours/$$day.json; done

validate:
	@test -n "$(DATE)" || (echo "DATE=AAAA-MM-JJ requis"; exit 2)
	$(PYTHON) src/valider.py data/jours/$(DATE).json

render:
	@test -n "$(DATE)" || (echo "DATE=AAAA-MM-JJ requis"; exit 2)
	$(PYTHON) src/render.py $(DATE)

index:
	$(PYTHON) -c "import sys; sys.path.insert(0, 'src'); import render; render.reconstruire_index()"

catalogue:
	$(PYTHON) src/videos.py

generate:
	@test -n "$(DATE)" || (echo "DATE=AAAA-MM-JJ requis"; exit 2)
	LECTIONNAIRE_MOTEUR=$(MOTEUR) $(PYTHON) src/generate.py $(DATE)

serve:
	$(PYTHON) -m http.server --directory docs 8000
