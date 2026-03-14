import { StateBadge } from "@/components/state-badge";
import type { Experiment } from "@/types";

interface ExperimentDetailPanelProps {
  experiment: Experiment;
}

export function ExperimentDetailPanel({ experiment }: ExperimentDetailPanelProps) {
  const hasMetrics = experiment.metrics && Object.keys(experiment.metrics).length > 0;
  const hasConfig = Object.keys(experiment.config).length > 0;

  return (
    <div className="bg-wheat/5 border-t border-soft-fawn/20 px-4 py-4 space-y-4">
      {/* Summary row */}
      <div className="flex items-center gap-3 flex-wrap">
        <StateBadge state={experiment.state} />
        <span className="font-mono text-xs text-grey">{experiment.id}</span>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {/* Config */}
        {hasConfig && (
          <div>
            <p className="text-xs text-grey font-medium mb-2">Config</p>
            <div className="space-y-1">
              {Object.entries(experiment.config).map(([k, v]) => (
                <div key={k} className="flex items-center gap-2">
                  <span className="text-xs text-grey shrink-0">{k}:</span>
                  <span className="text-xs text-blackberry font-mono truncate">
                    {String(v).slice(0, 60)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Metrics */}
        {hasMetrics && (
          <div>
            <p className="text-xs text-grey font-medium mb-2">Metrics</p>
            <div className="space-y-1">
              {Object.entries(experiment.metrics!).map(([k, v]) => (
                <div key={k} className="flex items-center justify-between">
                  <span className="text-xs text-grey">{k}</span>
                  <span className="text-xs font-semibold text-blackberry font-mono">
                    {typeof v === "number" ? v.toFixed(4) : String(v)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Error */}
      {experiment.error && (
        <div>
          <p className="text-xs text-grey font-medium mb-1">Error</p>
          <pre className="text-xs font-mono bg-danger/10 text-danger rounded-lg p-3 overflow-auto max-h-32 whitespace-pre-wrap">
            {experiment.error}
          </pre>
        </div>
      )}

      {!hasConfig && !hasMetrics && !experiment.error && (
        <p className="text-xs text-grey">No additional details available.</p>
      )}
    </div>
  );
}
