.PHONY: help setup dev dev-raw dev-with-db dev-docker docker-down docker-logs backend backend-noreload frontend db-up db-down db-logs db-ps lint test-backend typecheck-frontend lint-frontend

help:
	@echo "Available targets:"
	@echo "  make setup              - install/check local prerequisites"
	@echo "  make dev                - start backend + frontend (managed launcher)"
	@echo "  make dev-raw            - start backend + frontend (concurrently)"
	@echo "  make dev-with-db        - start postgres, then backend + frontend"
	@echo "  make dev-docker         - start frontend + backend + postgres in Docker"
	@echo "  make docker-down        - stop the Docker dev stack"
	@echo "  make docker-logs        - tail Docker dev stack logs"
	@echo "  make backend            - start backend with reload"
	@echo "  make backend-noreload   - start backend without reload"
	@echo "  make frontend           - start frontend dev server"
	@echo "  make db-up              - start postgres container"
	@echo "  make db-down            - stop postgres container"
	@echo "  make db-logs            - tail postgres logs"
	@echo "  make db-ps              - show postgres container status"
	@echo "  make lint               - run all linters/type checks"
	@echo "  make test-backend       - run backend test suite"

setup:
	npm run setup

dev:
	npm run dev

dev-raw:
	npm run dev:raw

dev-with-db: db-up
	npm run dev

dev-docker:
	docker compose up --build

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f

backend:
	npm run dev:backend

backend-noreload:
	npm run dev:backend:noreload

frontend:
	npm run dev:frontend

db-up:
	docker compose up -d db

db-down:
	docker compose stop db

db-logs:
	docker compose logs -f db

db-ps:
	docker compose ps db

lint:
	npm run lint

test-backend:
	npm run test:backend

typecheck-frontend:
	npm run typecheck:frontend

lint-frontend:
	npm run lint:frontend
