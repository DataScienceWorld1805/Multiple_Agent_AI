.PHONY: run test lint format docker-build docker-run docker-test

QUERY ?= What is the current status of commercial nuclear fusion?

run:
	python -m src.main "$(QUERY)"

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

docker-test:
	docker compose run --rm \
		-e LLM_PROVIDER=fake \
		-e SEARCH_PROVIDER=fake \
		-e PAPERS_PROVIDER=fake \
		app pytest -q
