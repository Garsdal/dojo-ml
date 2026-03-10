import { StateBadge } from "@/components/state-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EventFeed } from "@/components/agent/event-feed";
import { RunSummary } from "@/components/agent/run-summary";
import { useAgentRun } from "@/hooks/use-agent";
import { useAgentEvents } from "@/hooks/use-agent-events";
import { stopAgentRun } from "@/hooks/use-agent";
import { Square } from "lucide-react";

interface AgentRunViewProps {
  runId: string;
}

export function AgentRunView({ runId }: AgentRunViewProps) {
  const { data: run, mutate } = useAgentRun(runId);
  const { events } = useAgentEvents(runId);

  if (!run) {
    return (
      <Card className="rounded-xl">
        <CardContent className="py-8">
          <p className="text-sm text-muted-foreground text-center">
            Loading run...
          </p>
        </CardContent>
      </Card>
    );
  }

  const isRunning = run.status === "running";

  const handleStop = async () => {
    await stopAgentRun(runId);
    void mutate();
  };

  return (
    <div className="space-y-4">
      {/* Status header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <StateBadge state={run.status} />
          <span className="text-sm text-muted-foreground">
            {run.num_turns > 0 && `Turn ${run.num_turns}`}
            {run.total_cost_usd != null &&
              ` · $${run.total_cost_usd.toFixed(3)}`}
          </span>
        </div>
        {isRunning && (
          <Button variant="destructive" size="sm" onClick={handleStop}>
            <Square className="h-3 w-3 mr-1" />
            Stop Agent
          </Button>
        )}
      </div>

      {/* Prompt */}
      <Card className="rounded-xl">
        <CardHeader>
          <CardTitle className="text-sm font-medium text-muted-foreground">
            Prompt
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm">{run.prompt}</p>
        </CardContent>
      </Card>

      {/* Event feed */}
      <Card className="rounded-xl">
        <CardHeader>
          <CardTitle className="text-sm font-medium text-muted-foreground">
            Event Feed
          </CardTitle>
        </CardHeader>
        <CardContent>
          <EventFeed events={events.length > 0 ? events : run.events} />
        </CardContent>
      </Card>

      {/* Run summary (shown when done) */}
      <RunSummary run={run} />
    </div>
  );
}
