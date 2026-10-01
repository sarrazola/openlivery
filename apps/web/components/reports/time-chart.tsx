"use client";

// A bar chart over time with a value axis: gridlines at four even steps up
// to a rounded ceiling, one group of bars per point, labels under every nth
// point, and a tooltip naming each series. Used by every time series in the
// reports so they all read the same way.

export type ChartPoint = { key: string; label: string; values: number[] };
export type ChartSeries = { name: string; color: string };

const STEPS = 4;

// The smallest "round" step (1, 2, 2.5, 5 times a power of ten) whose four
// multiples cover the largest value, so the axis reads 0, 5, 10, 15 rather
// than 0, 3.25, 6.5, 9.75.
export function niceStep(max: number): number {
  if (!(max > 0)) return 1;
  const raw = max / STEPS;
  const power = Math.pow(10, Math.floor(Math.log10(raw)));
  return [1, 2, 2.5, 5, 10].map((m) => m * power).find((s) => s >= raw) ?? raw;
}

// How many decimals the step needs, so every tick shows the same number of
// them: a step of 0.005 reads 0.000, 0.005, 0.010, not 0, 0.005, 0.01.
export function stepDecimals(step: number): number {
  for (let d = 0; d <= 8; d += 1) {
    if (Math.abs(step * Math.pow(10, d) - Math.round(step * Math.pow(10, d))) < 1e-9) return d;
  }
  return 8;
}

export function TimeChart({ points, series, format, axisFormat, ariaLabel }: {
  points: ChartPoint[];
  series: ChartSeries[];
  // The tooltip's number format, and the axis one: the axis gets the
  // decimals the step needs so its ticks line up.
  format?: (value: number) => string;
  axisFormat?: (value: number, decimals: number) => string;
  ariaLabel: string;
}) {
  const fmt = format ?? ((v: number) => v.toLocaleString());
  const step = niceStep(Math.max(0, ...points.flatMap((p) => p.values)));
  const decimals = stepDecimals(step);
  const axis = axisFormat ?? ((v: number, d: number) => v.toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d }));
  const ceiling = step * STEPS;
  const ticks = Array.from({ length: STEPS + 1 }, (_, i) => step * i);
  const every = Math.max(1, Math.ceil(points.length / 8));
  return <div className="tchart" role="img" aria-label={ariaLabel}>
    <div className="tchart-y">
      {ticks.map((tick, i) => <span key={i} style={{ bottom: `${(i / STEPS) * 100}%` }}>{axis(tick, decimals)}</span>)}
    </div>
    <div className="tchart-plot">
      <div className="tchart-grid">{ticks.map((_, i) => <i key={i} style={{ bottom: `${(i / STEPS) * 100}%` }} />)}</div>
      <div className="tchart-bars">
        {points.map((point) => <div className="tchart-group" key={point.key}>
          <div className="report-chart-tip">
            <strong>{point.label}</strong>
            {series.map((s, i) => <span key={s.name}>{s.name}: {fmt(point.values[i] ?? 0)}</span>)}
          </div>
          {series.map((s, i) => <i key={s.name} style={{ height: `${Math.min(100, ((point.values[i] ?? 0) / ceiling) * 100)}%`, background: s.color }} />)}
        </div>)}
      </div>
    </div>
    <div className="tchart-x">
      {points.map((point, i) => <small key={point.key}>{i % every === 0 ? point.label : " "}</small>)}
    </div>
  </div>;
}
