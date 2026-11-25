# WarEra Tracker

Dashboard for WarEra battle damage, orders, bounty, contracts and citizens' company locations/taxes,
filterable by alliance, country, MU and player. Data comes from `api2.warera.io`.

- `streamlit_app.py` serves `site/index.html` with `site/data.json` inlined (deploy on Streamlit Community Cloud).
- `.github/workflows/refresh.yml` runs hourly: restores the history database from the `state` branch, collects new data,
  rebuilds `site/data.json`, saves the database back to `state` (one force-pushed commit) and commits `data.json`.
- `wartrack/` is the collector/exporter (standard library only). `scope.json` limits collection to The Emerald Accord's battles since 2026-11-10.

## Set up
1. Repo **Settings → Secrets and variables → Actions → New repository secret**: `WARERA_API_KEY` = your API key.
2. Repo **Settings → Actions → General → Workflow permissions: Read and write**.
3. **Actions → Refresh data → Run workflow** once.
4. On https://share.streamlit.io choose **Create app**, pick this repo, branch `main`, file `streamlit_app.py`.

The API key is never stored in the repo. This repo is public, so the `state` branch (the collected game data) is public too.

Run locally: `WARERA_API_KEY=... sh refresh.sh` then `uv run streamlit run streamlit_app.py`.
