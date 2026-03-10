import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { AgentPromptForm } from "@/components/agent/agent-prompt-form";
import { AgentRunView } from "@/components/agent/agent-run-view";
import { startAgentRun } from "@/hooks/use-agent";
import { useAgentRuns } from "@/hooks/use-agent";
import { StateBadge } from "@/components/state-badge";
import type { ToolHint } from "@/types";

export default function AgentPage() {
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [isStarting, setIsStarting] = useState(false);
  const { data: runs } = useAgentRuns();

  const handleStart = async (prompt: string, toolHints: ToolHint[]) => {
    setIsStarting(true);
    try {
      const run = await startAgentRun(prompt, toolHints);
      setActiveRunId(run.id);
    } finally {
      setIsStarting(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Agent Research</h1>
        <p className="text-muted-foreground text-sm mt-1">
          Start an AI-driven ML research session
        </p>
      </div>

      {/* Prompt form */}
      {!activeRunId && (
        <Card className="rounded-xl">
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">
              New Research Session
            </CardTitle>
          </CardHeader>
          <CardContent>
            <AgentPromptForm onSubmit={handleStart} isLoading={isStarting} />
          </CardContent>
        </Card>
      )}

      {/* Active run view */}
      {activeRunId && <AgentRunView runId={activeRunId} />}

      {/* Previous runs list */}
      {runs && runs.length > 0 && (
        <Card className="rounded-xl">
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Previous Runs
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {runs
                .filter((r) => r.id !== activeRunId)
                .map((run) => (
                  <button
                    key={run.id}
                    onClick={() => setActiveRunId(run.id)}
                    className="w-full flex items-center justify-between rounded-lg border px-3 py-2 text-left text-sm hover:bg-secondary/50 transition-colors"
                  >
                    <span className="truncate max-w-[60%]">{run.prompt}</span>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-muted-foreground">
                        {run.num_turns} turns
                      </span>
                      <StateBadge state={run.status} />
                    </div>
                  </button>
                ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
