import { useState, useMemo } from "react";
import type { MetricPoint } from "@/types";

interface MetricEvolutionChartProps {
  data: MetricPoint[] | undefined;
  isLoading: boolean;
}

export function MetricEvolutionChart({
  data,
  isLoading,
}: MetricEvolutionChartProps) {
  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }

  if (!data || data.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No metrics yet. Metrics appear after experiments complete.
      </p>
    );
  }

  // Collect all metric keys
  const metricKeys = useMemo(() => {
    const keys = new Set<string>();
    data.forEach((p) => Object.keys(p.metrics).forEach((k) => keys.add(k)));
    return Array.from(keys).sort();
  }, [data]);

  const [selectedMetric, setSelectedMetric] = useState<string>(
    metricKeys[0] ?? "",
  );

  // Get values for the selected metric across experiments
  const points = useMemo(() => {
    return data
      .filter((p) => selectedMetric in p.metrics)
      .map((p, i) => ({
        index: i,
        value: p.metrics[selectedMetric],
        experimentId: p.experiment_id,
        state: p.state,
      }));
  }, [data, selectedMetric]);

  if (metricKeys.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No numeric metrics recorded.
      </p>
    );
  }

  const maxVal = Math.max(...points.map((p) => p.value), 0.001);
  const minVal = Math.min(...points.map((p) => p.value), 0);

  return (
    <div className="space-y-3">
      {/* Metric selector */}
      <div className="flex items-center gap-2 flex-wrap">
        {metricKeys.map((key) => (
          <button
            key={key}
            onClick={() => setSelectedMetric(key)}
            className={`px-2 py-0.5 rounded text-xs border transition-colors ${
              key === selectedMetric
                ? "bg-foreground text-background border-foreground"
                : "bg-secondary/50 text-muted-foreground border-border hover:bg-secondary"
            }`}
          >
            {key}
          </button>
        ))}
      </div>

      {/* Simple bar chart */}
      <div className="flex items-end gap-1 h-32">
        {points.map((p) => {
          const height =
            maxVal === minVal
              ? 50
              : ((p.value - minVal) / (maxVal - minVal)) * 100;
          return (
            <div
              key={p.index}
              className="flex-1 min-w-[12px] rounded-t bg-foreground/40 hover:bg-foreground/60 transition-colors relative group"
              style={{ height: `${Math.max(height, 4)}%` }}
            >
              {/* Tooltip */}
              <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 hidden group-hover:block whitespace-nowrap rounded bg-popover border px-2 py-1 text-[10px] shadow-md z-10">
                <div className="font-mono">{p.value.toFixed(4)}</div>
                <div className="text-muted-foreground">
                  {p.experimentId.slice(0, 10)}…
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Axis labels */}
      <div className="flex justify-between text-[10px] text-muted-foreground">
        <span>{minVal.toFixed(3)}</span>
        <span className="font-medium">{selectedMetric}</span>
        <span>{maxVal.toFixed(3)}</span>
      </div>
    </div>
  );
}
