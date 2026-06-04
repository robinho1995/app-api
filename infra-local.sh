#!/bin/bash
# Subir infra local (Postgres + Redis) para rodar o app sem Docker
#
# Uso:
#   ./infra-local.sh up      -> sobe Postgres e Redis
#   ./infra-local.sh down    -> derruba e remove os containers
#   ./infra-local.sh status  -> verifica se estão rodando

set -e

PG_NAME="mba-postgres"
RD_NAME="mba-redis"

up() {
    echo ">>> Subindo PostgreSQL..."
    docker run -d \
        --name "$PG_NAME" \
        -e POSTGRES_USER=mbauser \
        -e POSTGRES_PASSWORD=mbapass \
        -e POSTGRES_DB=mbaapi \
        -p 5432:5432 \
        postgres:15-alpine

    echo ">>> Subindo Redis..."
    docker run -d \
        --name "$RD_NAME" \
        -p 6379:6379 \
        redis:7-alpine

    echo ""
    echo "Aguardando PostgreSQL ficar ready..."
    until docker exec "$PG_NAME" pg_isready -U mbauser -d mbaapi > /dev/null 2>&1; do
        printf "."
        sleep 1
    done
    echo " OK!"

    echo "Aguardando Redis ficar ready..."
    until docker exec "$RD_NAME" redis-cli ping > /dev/null 2>&1; do
        printf "."
        sleep 1
    done
    echo " OK!"

    echo ""
    echo ">>> Infra local pronta!"
    echo "    PostgreSQL: localhost:5432  (mbauser:mbapass / mbaapi)"
    echo "    Redis:      localhost:6379"
    echo ""
    echo "    Rodar o app:"
    echo "    cd app && .venv/bin/python3 -m app.main"
}

down() {
    echo ">>> Derrubando containers..."
    docker stop "$PG_NAME" "$RD_NAME" 2>/dev/null || true
    docker rm   "$PG_NAME" "$RD_NAME" 2>/dev/null || true
    echo ">>> Containers removidos."
}

status() {
    pg_running=$(docker inspect -f '{{.State.Running}}' "$PG_NAME" 2>/dev/null || echo "false")
    rd_running=$(docker inspect -f '{{.State.Running}}' "$RD_NAME" 2>/dev/null || echo "false")

    if [ "$pg_running" = "true" ]; then
        echo "PostgreSQL: localhost:5432  (rodando)"
    else
        echo "PostgreSQL: PARADO"
    fi

    if [ "$rd_running" = "true" ]; then
        echo "Redis:      localhost:6379  (rodando)"
    else
        echo "Redis:      PARADO"
    fi
}

case "${1:-}" in
    up)     up ;;
    down)   down ;;
    status) status ;;
    *)
        echo "Uso: $0 {up|down|status}"
        exit 1
        ;;
esac