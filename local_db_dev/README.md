# Commands for the local database

Launch these commands from the root directory of the project.

## Starting the server

```docker compose -f local_db_dev/compose.yaml up -d```

## Stopping the server while keeping the data

```docker compose down```

## Stopping the server and deleting the volume

```docker compose down -v```
