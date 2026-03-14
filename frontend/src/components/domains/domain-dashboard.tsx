import { FlaskConical, Brain, TrendingUp } from "lucide-react";
import { MetricEvolutionChart } from "@/components/charts/metric-evolution-chart";
import { KnowledgeEvolutionChart } from "@/components/charts/knowledge-evolution-chart";
import { ErrorBoundary } from "@/components/ui/error-boundary";
import { StateBadge } from "@/components/state-badge";
import { useKnowledgeEvolution } from "@/hooks/use-knowledge-evolution";
import type { Experiment, KnowledgeAtom, MetricPoint } from "@/types";

interface DomainDashboardProps {
  experiments: Experiment[] | undefined;
  knowledge: KnowledgeAtom[] | undefined;
  metrics: MetricPoint[] | undefined;
  metricsLoading: boolean;
  onExperimentClick: (experimentId: string) => void;
}

export function DomainDashboard({
  experiments,
  knowledge,
  metrics,
  metricsLoading,
  onExperimentClick,
}: DomainDashboardProps) {
  const knowledgeEvolution = useKnowledgeEvolution(knowledge);
  const runningCount = experiments?.filter((e) => e.state === "running").length ?? 0;
  const completedCount = experiments?.filter((e) => e.state === "completed").length ?? 0;
  const recentExperiments = experiments?.slice(-5).reverse() ?? [];
  const recentKnowledge = knowledge?.slice(-5).reverse() ?? [];

  // Latest metric values (last experiment's metrics)
  const latestMetrics =
    experiments
      ?.filter((e) => e.metrics && Object.keys(e.metrics).length > 0)
      .slice(-1)[0]?.metrics ?? null;

  return (
    <div className="space-y-6">
      {/* Quick stats */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="bg-white rounded-xl border border-soft-fawn/20 px-4 py-3">
          <div className="flex items-center gap-2 mb-1">
            <FlaskConical className="h-3.5 w-3.5 text-grey" />
            <span className="text-xs text-grey font-medium">Running</span>
          </div>
          <p className="text-2xl font-bold text-blackberry">{runningCount}</p>
        </div>
        <div className="bg-white rounded-xl border border-soft-fawn/20 px-4 py-3">
          <div className="flex items-center gap-2 mb-1">
            <FlaskConical className="h-3.5 w-3.5 text-grey" />
            <span className="text-xs text-grey font-medium">Completed</span>
          </div>
          <p className="text-2xl font-bold text-blackberry">{completedCount}</p>
        </div>
        <div className="bg-white rounded-xl border border-soft-fawn/20 px-4 py-3">
          <div className="flex items-center gap-2 mb-1">
            <Brain className="h-3.5 w-3.5 text-grey" />
            <span className="text-xs text-grey font-medium">Knowledge</span>
          </div>
          <p className="text-2xl font-bold text-blackberry">{knowledge?.length ?? "—"}</p>
        </div>
        {latestMetrics && Object.keys(latestMetrics).length > 0 && (
          <div className="bg-white rounded-xl border border-soft-fawn/20 px-4 py-3">
            <div className="flex items-center gap-2 mb-1">
              <TrendingUp className="h-3.5 w-3.5 text-grey" />
              <span className="text-xs text-grey font-medium truncate">
                {Object.keys(latestMetrics)[0]}
              </span>
            </div>
            <p className="text-2xl font-bold text-blackberry">
              {Object.values(latestMetrics)[0].toFixed(3)}
            </p>
          </div>
        )}
      </div>

      {/* Metrics progression chart */}
      <div className="bg-white rounded-2xl border border-soft-fawn/20 p-4">
        <h3 className="font-heading font-semibold text-blackberry text-sm mb-4">
          Metrics Progression
        </h3>
        <ErrorBoundary fallback={<p className="text-sm text-grey">Failed to load metrics chart.</p>}>
          <MetricEvolutionChart
            data={metrics}
            isLoading={metricsLoading}
            onPointClick={onExperimentClick}
          />
        </ErrorBoundary>
        {metrics && metrics.length > 0 && (
          <p className="text-xs text-grey mt-2 text-center">
            Click a data point to navigate to that experiment
          </p>
        )}
      </div>

      {/* Knowledge evolution chart */}
      <KnowledgeEvolutionChart data={knowledgeEvolution} />

      {/* Recent activity */}
      {(recentExperiments.length > 0 || recentKnowledge.length > 0) && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {/* Recent experiments */}
          {recentExperiments.length > 0 && (
            <div className="bg-white rounded-2xl border border-soft-fawn/20 p-4">
              <h3 className="font-heading font-semibold text-blackberry text-sm mb-3">
                Recent Experiments
              </h3>
              <div className="space-y-2">
                {recentExperiments.map((exp) => (
                  <button
                    key={exp.id}
                    onClick={() => onExperimentClick(exp.id)}
                    className="w-full flex items-center justify-between gap-3 hover:bg-wheat/10 rounded-lg px-2 py-1.5 transition-colors text-left"
                  >
                    <span className="font-mono text-xs text-grey truncate">
                      {exp.id.slice(0, 12)}…
                    </span>
                    <StateBadge state={exp.state} />
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Recent knowledge */}
          {recentKnowledge.length > 0 && (
            <div className="bg-white rounded-2xl border border-soft-fawn/20 p-4">
              <h3 className="font-heading font-semibold text-blackberry text-sm mb-3">
                Recent Knowledge
              </h3>
              <div className="space-y-2">
                {recentKnowledge.map((atom) => (
                  <div key={atom.id} className="flex items-start gap-2">
                    <div
                      className="mt-1.5 w-1.5 h-1.5 rounded-full shrink-0"
                      style={{
                        backgroundColor:
                          atom.confidence >= 0.7
                            ? "var(--color-muted-teal, #8BBF9F)"
                            : atom.confidence >= 0.4
                              ? "var(--color-wheat, #D6BA73)"
                              : "var(--color-danger, #E57373)",
                      }}
                    />
                    <p className="text-xs text-blackberry line-clamp-2">{atom.claim}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
