.DEFAULT_GOAL := help

PYTHON := uv run python
DEMO_DAYS := 2026-07-08 2026-12-17 2026-02-21

.PHONY: help setup test check validate render generate serve

help:
	@echo "make setup | test | check | validate DATE=AAAA-MM-JJ | render DATE=AAAA-MM-JJ | generate DATE=AAAA-MM-JJ | serve"

setup:
	uv sync

test:
	$(PYTHON) -m unittest discover -s tests -v

check: test
	@for day in $(DEMO_DAYS); do $(PYTHON) src/valider.py data/jours/$$day.json; done

validate:
	@test -n "$(DATE)" || (echo "DATE=AAAA-MM-JJ requis"; exit 2)
	$(PYTHON) src/valider.py data/jours/$(DATE).json

render:
	@test -n "$(DATE)" || (echo "DATE=AAAA-MM-JJ requis"; exit 2)
	$(PYTHON) src/render.py $(DATE)

generate:
	@test -n "$(DATE)" || (echo "DATE=AAAA-MM-JJ requis"; exit 2)
	$(PYTHON) src/generate.py $(DATE)

serve:
	$(PYTHON) -m http.server --directory docs 8000
