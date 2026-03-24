# Docker

## Bajar las imagenes (solo las baja y cachea localmente, no levanta el contenedor)

```bash
docker pull mysql:8.4
docker pull postgres:16
```

## Iniciar contenedor

Levanta MySQL en el puerto 3306 local, con password de root `patito`

```bash
docker run -e MYSQL_ROOT_PASSWORD=patito -p 3306:3306 -d mysql:8.4
```

Levanta MySQL en el puerto 1234 local, con password de root `patito`

```bash
docker run -e MYSQL_ROOT_PASSWORD=patito -p 1234:3306 -d mysql:8.4
```

## Lo mismo pero con Postgres

```bash
docker run -d -e POSTGRES_PASSWORD=patote -p 5678:5432 postgres:16
```

## Apagar y destruir contenedores

```bash
docker stop <nombre o ID del contenedor>
docker rm -f <nombre o ID del contenedor>
```

## Levantar docker compose

```bash
docker compose up -d

docker compose -f <nombre archivo personalizado> up -d

```

## Apagar docker compose

```bash
docker compose down

docker compose -f <nombre archivo personalizado> down
```
