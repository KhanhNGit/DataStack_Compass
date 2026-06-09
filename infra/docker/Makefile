###############################################################################
# DataStack Compass — Makefile (Local Development)
###############################################################################

COMPOSE = docker compose -f docker-compose.yml -p datastack

.PHONY: up down logs ps clean

## Start all services in detached mode
up:
	$(COMPOSE) up -d

## Stop and remove containers (keep volumes)
down:
	$(COMPOSE) down

## Tail logs for all services (Ctrl+C to exit)
logs:
	$(COMPOSE) logs -f

## Show running containers
ps:
	$(COMPOSE) ps -a

## Stop containers AND remove volumes + data directory
clean:
	$(COMPOSE) down -v
	rm -rf ./data

## ---- Convenience targets ----

## Start only storage layer (MinIO + StarRocks)
up-storage:
	$(COMPOSE) up -d minio minio-init starrocks

## Start only Airflow stack
up-airflow:
	$(COMPOSE) up -d postgres airflow-init airflow-webserver airflow-scheduler

## Follow logs for a specific service (usage: make log-service SVC=minio)
log-service:
	$(COMPOSE) logs -f $(SVC)

## Restart a specific service (usage: make restart SVC=airflow-webserver)
restart:
	$(COMPOSE) restart $(SVC)
