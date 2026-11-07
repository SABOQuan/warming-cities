import type { Domain } from '../lib/scale';

interface YearRangeProps {
  /** Full span the data covers. */
  bounds: Domain;
  value: Domain;
  onChange: (range: Domain) => void;
  /** Rounded start years offered as one-click presets. */
  presets?: number[];
}

/** "Show years between [from] and [to]" with a few presets. */
export function YearRange({
  bounds,
  value,
  onChange,
  presets = [1900, 1950, 1970, 2000],
}: YearRangeProps) {
  const [lo, hi] = bounds;
  const years: number[] = [];
  for (let y = lo; y <= hi; y++) years.push(y);
  const usable = presets.filter((p) => p > lo && p < hi);
  const isAll = value[0] === lo && value[1] === hi;

  return (
    <fieldset className="year-range">
      <legend>Years</legend>
      <label>
        between{' '}
        <select
          value={value[0]}
          onChange={(e) => onChange([Number(e.target.value), value[1]])}
          aria-label="First year"
        >
          {years
            .filter((y) => y < value[1])
            .map((y) => (
              <option key={y}>{y}</option>
            ))}
        </select>
      </label>{' '}
      <label>
        and{' '}
        <select
          value={value[1]}
          onChange={(e) => onChange([value[0], Number(e.target.value)])}
          aria-label="Last year"
        >
          {years
            .filter((y) => y > value[0])
            .map((y) => (
              <option key={y}>{y}</option>
            ))}
        </select>
      </label>
      <span className="year-presets">
        <button type="button" aria-pressed={isAll} onClick={() => onChange(bounds)}>
          all
        </button>
        {usable.map((p) => (
          <button
            key={p}
            type="button"
            aria-pressed={value[0] === p && value[1] === hi}
            onClick={() => onChange([p, hi])}
          >
            since {p}
          </button>
        ))}
      </span>
    </fieldset>
  );
}
