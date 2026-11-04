// Shapes of the JSON written by pipeline/export.py (schema_version 1).

export type YearRange = [number, number];

export interface Methodology {
  baseline_period: YearRange;
  trend_start_year: number;
  rolling_window_years: number;
  extreme_heat_month: string;
  who_pm25_guideline: number;
  sources: { temperature: string; air_quality: string };
  caveat: string;
}

export interface CitySummary {
  id: string;
  name: string;
  lat: number;
  lon: number;
  warming_per_decade_c: number | null;
  recent_anomaly_c: number | null;
  temperature_years: YearRange;
  mean_pm25: number | null;
  pm25_pct_per_year: number | null;
  pm25_years: YearRange | null;
}

export interface CitiesIndex {
  generated: string;
  methodology: Methodology;
  cities: CitySummary[];
}

export interface TemperatureYear {
  year: number;
  temp_c: number;
  anomaly_c: number;
  n_months: number;
  /** Centred rolling mean of anomaly_c (not of temp_c). */
  rolling_c: number | null;
}

export interface ExtremeHeatYear {
  year: number;
  hot_months: number;
  months_observed: number;
}

export interface DecadeAnomaly {
  decade: number;
  anomaly_c: number;
  n_years: number;
}

export interface WarmYear {
  year: number;
  anomaly_c: number;
  rank: number;
}

export interface AirQualityYear {
  year: number;
  pm25: number;
  n_months: number;
  n_locations: number;
  who_multiple: number;
}

export interface TemperatureTrend {
  per_decade_c: number;
  ci95_low_c: number;
  ci95_high_c: number;
  p_value: number;
  r2: number;
  n_years: number;
  first_year: number;
  last_year: number;
}

export interface Pm25Trend {
  n_years: number;
  first_year: number;
  last_year: number;
  mean_pm25: number;
  sufficient: boolean;
  per_year?: number;
  ci95_low?: number;
  ci95_high?: number;
  pct_per_year?: number;
  p_value?: number;
}

export interface TempPm25Correlation {
  n_years: number;
  r: number | null;
  p_value: number | null;
  r_detrended: number | null;
  p_detrended: number | null;
}

export interface CityData {
  schema_version: number;
  id: string;
  name: string;
  lat: number;
  lon: number;
  station: { station_id: string; station_name: string; distance_km: number };
  baseline: { period: YearRange; baseline_c: number; baseline_years: number };
  temperature: TemperatureYear[];
  extreme_heat: ExtremeHeatYear[];
  decades: DecadeAnomaly[];
  warmest_years: WarmYear[];
  air_quality: AirQualityYear[];
  stats: {
    baseline_years: number;
    baseline_ok: boolean;
    recent_anomaly_c: number | null;
    temperature_trend: TemperatureTrend | null;
    pm25_trend: Pm25Trend | null;
    temp_pm25_correlation: TempPm25Correlation | null;
  };
  notes: string[];
}
