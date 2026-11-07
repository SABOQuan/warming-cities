# Warming Cities

A static-data, interactive climate storytelling site. Python cleans, aggregates, and statistically
models 50+ years of temperature data, plus PM2.5 air quality, across eleven major cities, exports
the results to JSON, and a React/TypeScript frontend renders it as an explorable, Y2K-styled
experience.

**Cities:** Lahore, Beijing, São Paulo, Addis Ababa, New York, Delhi, Ho Chi Minh City, Jakarta,
London, Sydney, Santiago

**Status:** Phase 1 — temperature (NOAA GHCN) and air quality (OpenAQ) downloaded for all eleven
cities. Cleaning (Phase 2) is next.

See [`ROADMAP.md`](./ROADMAP.md) for the full build plan, data sources, git workflow, and CI/CD
strategy — including the pipeline diagram.

## Project layout

```
etl/    Python: data download, cleaning, SQL aggregation, statistical modeling, JSON export
web/    React + TypeScript frontend
```

## Getting started

```bash
# Python side
cd etl
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest

# Frontend side
cd web
npm install
npm run dev
```

Opening `warming-cities.code-workspace` in VS Code loads both `etl/` and `web/` as separate roots
with the right formatter/linter defaults for each.

## License

MIT — see [`LICENSE`](./LICENSE).
