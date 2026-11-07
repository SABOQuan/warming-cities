"""Phase 2.5 — the statistics behind the site: trends, anomalies, rolling means, correlation.

Works on clean.py's annual CSVs. Kept as a tested module (rather than living only in the
notebook) because Phase 3's export draws its numbers from here — the notebook is the narrative
and the charts, this is the arithmetic.

Methodology decisions:

1. Warming trend = OLS slope of annual mean temperature on year, reported in °C/decade with a
   95% confidence interval. Fitted from TREND_START (1970) for every city: station records begin
   anywhere from 1841 to 1954, so full-record slopes aren't comparable across cities, and 1970 is
   roughly where the modern, greenhouse-driven warming signal begins.
2. Anomaly = annual temperature minus the city's own 1961-1990 mean (the WMO-standard baseline).
   Cities with fewer than 20 baseline years are flagged (Jakarta has 14).
3. PM2.5 trend = OLS slope in µg/m³ per year, also expressed as % of the city's mean per year.
   With 4-11 years of data these are short records: trends from fewer than MIN_PM25_YEARS years
   are reported as insufficient rather than given a slope.
4. Temperature vs PM2.5: Pearson r between annual temperature anomaly and annual PM2.5 over the
   years both exist, both raw and after removing each series' linear trend. The detrended r is
   the one to read: two series that merely both drift over the same years correlate raw without
   any year-to-year link. Correlation is NOT causation — warming is driven by global greenhouse
   gas concentrations, PM2.5 by local emissions and weather (hot, stagnant years trap
   pollution); with at most ~11 overlapping years and nine cities tested, any single r is weak
   evidence. Reported with p-values and n so it can't be over-read.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from cities import CITIES

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

PROCESSED_DIR = Path(__file__).parent / "data" / "processed"

BASELINE = (1961, 1990)
MIN_BASELINE_YEARS = 20
TREND_START = 1970
RECENT_PERIOD = (2016, 2025)  # "the last decade" for the headline anomaly
ROLLING_WINDOW = 10
MIN_PM25_YEARS = 5
MIN_OVERLAP_YEARS = 5


def load_processed(processed_dir: Path = PROCESSED_DIR) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(temperature_annual, air_quality_annual) as written by clean.py."""
    temp = pd.read_csv(processed_dir / "temperature_annual.csv")
    aq = pd.read_csv(processed_dir / "air_quality_annual.csv")
    return temp, aq


def linear_trend(years: pd.Series, values: pd.Series) -> dict | None:
    """OLS fit of values on years. Returns slope per year, its 95% CI, p-value, R², and n —
    or None with fewer than 3 points (no degrees of freedom left for a CI)."""
    x = np.asarray(years, dtype=float)
    y = np.asarray(values, dtype=float)
    if len(x) < 3:
        return None
    fit = stats.linregress(x, y)
    half_width = stats.t.ppf(0.975, len(x) - 2) * fit.stderr
    return {
        "slope": float(fit.slope),
        "ci95_low": float(fit.slope - half_width),
        "ci95_high": float(fit.slope + half_width),
        "p_value": float(fit.pvalue),
        "r2": float(fit.rvalue**2),
        "n": int(len(x)),
        "first_year": int(x.min()),
        "last_year": int(x.max()),
    }


def add_anomalies(temp_annual: pd.DataFrame) -> pd.DataFrame:
    """Add anomaly_c = temp_c minus the city's 1961-1990 mean, and baseline_years per city."""
    in_baseline = temp_annual["year"].between(*BASELINE)
    baseline = temp_annual[in_baseline].groupby("city")["temp_c"].agg(["mean", "size"])
    out = temp_annual.copy()
    out["anomaly_c"] = out["temp_c"] - out["city"].map(baseline["mean"])
    out["baseline_years"] = out["city"].map(baseline["size"]).fillna(0).astype(int)
    return out


def add_rolling_mean(
    annual: pd.DataFrame, value_col: str, window: int = ROLLING_WINDOW
) -> pd.DataFrame:
    """Add <value_col>_rolling: centred rolling mean over `window` calendar years per city.

    Rolls over calendar years, not rows, so a gap year isn't silently treated as adjacent; needs
    at least 70% of the window present.
    """
    frames = []
    for _city, group in annual.groupby("city", sort=False):
        series = group.set_index("year")[value_col]
        full = series.reindex(range(series.index.min(), series.index.max() + 1))
        rolled = full.rolling(window, center=True, min_periods=int(window * 0.7)).mean()
        frames.append(group.assign(**{f"{value_col}_rolling": group["year"].map(rolled).values}))
    return pd.concat(frames, ignore_index=True)


def temperature_trends(temp_annual: pd.DataFrame, since: int = TREND_START) -> pd.DataFrame:
    """Per city: warming trend since `since` in °C/decade, with 95% CI and p-value."""
    rows = []
    for city, group in temp_annual.groupby("city", sort=False):
        recent = group[group["year"] >= since]
        fit = linear_trend(recent["year"], recent["temp_c"])
        if fit is None:
            continue
        rows.append(
            {
                "city": city,
                "per_decade_c": fit["slope"] * 10,
                "ci95_low_c": fit["ci95_low"] * 10,
                "ci95_high_c": fit["ci95_high"] * 10,
                "p_value": fit["p_value"],
                "r2": fit["r2"],
                "n_years": fit["n"],
                "first_year": fit["first_year"],
                "last_year": fit["last_year"],
            }
        )
    return pd.DataFrame(rows)


def pm25_trends(aq_annual: pd.DataFrame, min_years: int = MIN_PM25_YEARS) -> pd.DataFrame:
    """Per city: PM2.5 trend in µg/m³/year and %/year of the city's mean. Cities with fewer than
    min_years years get sufficient=False and no slope."""
    rows = []
    for city, group in aq_annual.groupby("city", sort=False):
        row = {
            "city": city,
            "n_years": int(len(group)),
            "first_year": int(group["year"].min()),
            "last_year": int(group["year"].max()),
            "mean_pm25": float(group["pm25"].mean()),
            "sufficient": len(group) >= min_years,
        }
        fit = linear_trend(group["year"], group["pm25"]) if row["sufficient"] else None
        if fit:
            row.update(
                per_year=fit["slope"],
                ci95_low=fit["ci95_low"],
                ci95_high=fit["ci95_high"],
                pct_per_year=100 * fit["slope"] / row["mean_pm25"],
                p_value=fit["p_value"],
            )
        rows.append(row)
    return pd.DataFrame(rows)


def temp_pm25_correlation(
    temp_with_anomalies: pd.DataFrame,
    aq_annual: pd.DataFrame,
    min_overlap: int = MIN_OVERLAP_YEARS,
) -> pd.DataFrame:
    """Per city: Pearson r (raw and detrended) between temperature anomaly and PM2.5 over
    overlapping years. See module docstring, point 4, for why this isn't read causally."""
    merged = temp_with_anomalies.merge(aq_annual, on=["city", "year"])
    rows = []
    for city, group in merged.groupby("city", sort=False):
        row = {"city": city, "n_years": int(len(group))}
        if len(group) >= min_overlap:
            r, p = stats.pearsonr(group["anomaly_c"], group["pm25"])
            r_d, p_d = stats.pearsonr(
                _detrend(group["year"], group["anomaly_c"]), _detrend(group["year"], group["pm25"])
            )
            row.update(r=float(r), p_value=float(p), r_detrended=float(r_d), p_detrended=float(p_d))
        rows.append(row)
    return pd.DataFrame(rows)


def _detrend(years: pd.Series, values: pd.Series) -> np.ndarray:
    """Residuals of values after removing their OLS line on years."""
    x = np.asarray(years, dtype=float)
    y = np.asarray(values, dtype=float)
    return y - np.polyval(np.polyfit(x, y, 1), x)


def summarize(temp_annual: pd.DataFrame, aq_annual: pd.DataFrame) -> dict[str, dict]:
    """Every derived number per city, in one JSON-ready dict (consumed by Phase 3's export)."""
    temp = add_anomalies(temp_annual)
    t_trend = temperature_trends(temp).set_index("city")
    a_trend = pm25_trends(aq_annual).set_index("city")
    corr = temp_pm25_correlation(temp, aq_annual).set_index("city")

    def clean_row(frame: pd.DataFrame, city: str) -> dict | None:
        if city not in frame.index:
            return None
        # records keep each column's own dtype; .loc[city] would upcast years/counts to float
        row = frame.loc[[city]].to_dict("records")[0]
        def tidy(key: str, value):
            if not isinstance(value, float):
                return value
            # p-values span many orders of magnitude; 4 decimals would turn 1e-9 into 0.0
            return float(f"{value:.3g}") if key.startswith("p_") else round(value, 4)

        return {
            k: tidy(k, v) for k, v in row.items() if not (isinstance(v, float) and np.isnan(v))
        }

    summary = {}
    for city in CITIES:
        city_temp = temp[temp["city"] == city]
        recent = city_temp[city_temp["year"].between(*RECENT_PERIOD)]
        baseline_years = int(city_temp["baseline_years"].iloc[0]) if len(city_temp) else 0
        summary[city] = {
            "baseline_years": baseline_years,
            "baseline_ok": baseline_years >= MIN_BASELINE_YEARS,
            "recent_anomaly_c": round(float(recent["anomaly_c"].mean()), 3)
            if len(recent)
            else None,
            "temperature_trend": clean_row(t_trend, city),
            "pm25_trend": clean_row(a_trend, city),
            "temp_pm25_correlation": clean_row(corr, city),
        }
    return summary


def main() -> None:
    temp, aq = load_processed()
    summary = summarize(temp, aq)
    (PROCESSED_DIR / "analysis_summary.json").write_text(json.dumps(summary, indent=2))
    for city, s in summary.items():
        t = s["temperature_trend"] or {}
        a = s["pm25_trend"] or {}
        log.info(
            "%-17s %+.2f °C/decade since %s (95%% CI %+.2f..%+.2f)  last decade %+.2f °C  "
            "PM2.5 %s",
            city, t.get("per_decade_c", float("nan")), t.get("first_year"),
            t.get("ci95_low_c", float("nan")), t.get("ci95_high_c", float("nan")),
            s["recent_anomaly_c"] or float("nan"),
            f"{a['pct_per_year']:+.1f}%/yr" if a.get("sufficient") else "insufficient years",
        )


if __name__ == "__main__":
    main()
