#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
docker compose -f compose.json config --quiet
docker compose -f compose.json run --rm --use-aliases tests
