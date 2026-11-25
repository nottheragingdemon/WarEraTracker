#!/bin/sh
# Collect fresh data and rebuild site/data.json. Safe to run repeatedly.
set -e
cd "$(dirname "$0")"
export WARTRACK_DB=wartrack.sqlite
python3 -m wartrack collect --since 2d --damage-limit 150 --bounty-top 200 --player-limit 5000
python3 -m wartrack export --out site/data.json
ls -l site/data.json
