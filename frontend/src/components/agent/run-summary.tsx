import type { AgentRun } from "@/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function RunSummary({ run }: { run: AgentRun }) {
  if (
    run.status !== "completed" &&
    run.status !== "failed" &&
    run.status !== "stopped"
  ) {
    return null;
  }

  const durationEvent = run.events.find((e) => e.event_type === "result");
  const durationMs = (durationEvent?.data?.duration_ms as number) ?? null;
  const durationStr = durationMs ? `${(durationMs / 1000).toFixed(1)}s` : "—";

  return (
    <Card className="rounded-xl">
      <CardHeader>
        <CardTitle className="text-sm font-medium text-muted-foreground">
          Run Summary
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <div className="text-muted-foreground text-xs">Status</div>
            <div className="font-medium capitalize">{run.status}</div>
          </div>
          <div>
            <div className="text-muted-foreground text-xs">Turns</div>
            <div className="font-medium">{run.num_turns}</div>
          </div>
          <div>
            <div className="text-muted-foreground text-xs">Cost</div>
            <div className="font-medium">
              {run.total_cost_usd != null
                ? `$${run.total_cost_usd.toFixed(3)}`
                : "—"}
            </div>
          </div>
          <div>
            <div className="text-muted-foreground text-xs">Duration</div>
            <div className="font-medium">{durationStr}</div>
          </div>
          {run.error && (
            <div className="col-span-2">
              <div className="text-muted-foreground text-xs">Error</div>
              <div className="text-red-400 text-xs font-mono mt-0.5">
                {run.error}
              </div>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
