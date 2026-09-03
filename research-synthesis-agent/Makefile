.PHONY: run serve test lint format docker-build docker-run docker-serve docker-test

QUERY ?= What is the current status of commercial nuclear fusion?

run:
	python -m src.main "$(QUERY)"

serve:
	python -m src.api

test:
	pytest -q

lint:
	ruff check .
	black --check .

format:
	ruff check --fix .
	black .

docker-build:
	docker compose build

docker-run:
	docker compose run --rm app python -m src.main "$(QUERY)"

docker-serve:
	docker compose run --rm -p 8000:8000 app python -m src.api

docker-test:
	docker compose run --rm \
		-e LLM_PROVIDER=fake \
		-e SEARCH_PROVIDER=fake \
		-e PAPERS_PROVIDER=fake \
		app pytest -q
