#!/bin/bash
# Crea las bases de datos para cada microservicio.
# Cada servicio tiene su propia BD (Database per Service pattern).
set -e

for db in orders_db inventory_db notifications_db; do
    psql --username "$POSTGRES_USER" --dbname postgres \
         -tc "SELECT 1 FROM pg_database WHERE datname = '$db'" \
    | grep -q 1 \
    || psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
            -c "CREATE DATABASE $db;"
done
