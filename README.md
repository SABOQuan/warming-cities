# Warming Cities

A static-data, interactive climate storytelling site. Python cleans, aggregates, and statistically
models 50+ years of temperature data — plus air quality, and sea level for coastal cities — across
ten major cities, exports the results to JSON, and a React/TypeScript frontend renders it as an
explorable, Y2K-styled experience.

**Cities:** Lahore, Beijing, São Paulo, Cairo, New York, Delhi, Manila, Jakarta, London, Sydney

**Status:** Phase 0 — repo and tooling scaffolded. Data acquisition (Phase 1) not started yet.

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
