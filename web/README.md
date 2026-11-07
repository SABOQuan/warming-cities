# web/

The Warming Cities site: React 19 + TypeScript + Vite, with no runtime dependencies beyond
React. It reads the JSON that `etl/export.py` writes to `public/data/`.

```bash
npm install
npm run dev          # dev server
npm run build        # type-check + static build in dist/
npm run lint         # oxlint
npm run typecheck
npm run format       # prettier
```

## Structure

```
src/
  main.tsx, App.tsx       entry point; header, nav and page switch
  router.ts               hash routes: #/, #/city/<id>, #/compare?c=a,b, #/methods
  data.ts, types.ts       typed loader for cities.json and <city>.json
  pages/                  Home (catalogue), City, Methods
  components/
    Chart.tsx             generic SVG line/bar chart with axes and tooltips
    CityCharts.tsx        temperature anomaly + PM2.5 charts for one city
    Stripes.tsx           warming stripes
    Compare.tsx           up to three cities' anomalies on one chart
    YearRange.tsx         year-range filter
    Fuzzy.tsx             display type blurred by an SVG turbulence filter that sharpens on hover
  lib/                    scales, colours (RdBu diverging + categorical), formatting, catalogue helpers
  index.css               the whole theme
```

Charts are drawn by hand in SVG instead of using a chart library, which keeps the bundle small
and gives full control over the look.
