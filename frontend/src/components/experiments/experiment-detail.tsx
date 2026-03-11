import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { StateBadge } from "@/components/state-badge";
import { Separator } from "@/components/ui/separator";
import type { Experiment } from "@/types";

interface ExperimentDetailProps {
  experiment: Experiment;
}

export function ExperimentDetail({ experiment }: ExperimentDetailProps) {
  return (
    <Card className="rounded-xl">
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium text-muted-foreground">
            Experiment Detail
          </CardTitle>
          <StateBadge state={experiment.state} />
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <p className="text-xs text-muted-foreground mb-1">Experiment ID</p>
            <p className="font-mono text-sm">{experiment.id}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground mb-1">Domain ID</p>
            <p className="font-mono text-sm">{experiment.domain_id}</p>
          </div>
        </div>

        <Separator />

        <div>
          <p className="text-xs text-muted-foreground mb-1">Config</p>
          <pre className="text-xs font-mono bg-muted/50 rounded-lg p-3 overflow-auto max-h-[200px]">
            {JSON.stringify(experiment.config, null, 2)}
          </pre>
        </div>

        {experiment.metrics && Object.keys(experiment.metrics).length > 0 && (
          <>
            <Separator />
            <div>
              <p className="text-xs text-muted-foreground mb-1">Metrics</p>
              <div className="grid grid-cols-2 gap-2">
                {Object.entries(experiment.metrics).map(([key, value]) => (
                  <div
                    key={key}
                    className="flex justify-between bg-muted/50 rounded-lg px-3 py-2"
                  >
                    <span className="text-xs text-muted-foreground">{key}</span>
                    <span className="font-mono text-xs">
                      {value.toFixed(4)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}

        {experiment.error && (
          <>
            <Separator />
            <div>
              <p className="text-xs text-muted-foreground mb-1">Error</p>
              <pre className="text-xs font-mono bg-red-950/50 text-red-300 rounded-lg p-3 overflow-auto">
                {experiment.error}
              </pre>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
