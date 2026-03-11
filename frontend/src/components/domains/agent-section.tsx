import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { AgentPromptForm } from "@/components/agent/agent-prompt-form";
import { AgentRunView } from "@/components/agent/agent-run-view";
import { startAgentRun, useAgentRuns } from "@/hooks/use-agent";
import { StateBadge } from "@/components/state-badge";
import type { ToolHint } from "@/types";

interface AgentSectionProps {
  domainId: string;
}

export function AgentSection({ domainId }: AgentSectionProps) {
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [isStarting, setIsStarting] = useState(false);
  const { data: runs } = useAgentRuns();

  // Filter runs for this domain
  const domainRuns = runs?.filter((r) => r.domain_id === domainId) ?? [];

  const handleStart = async (prompt: string, toolHints: ToolHint[]) => {
    setIsStarting(true);
    try {
      const run = await startAgentRun(prompt, domainId, toolHints);
      setActiveRunId(run.id);
    } finally {
      setIsStarting(false);
    }
  };

  return (
    <div className="space-y-4">
      {!activeRunId && (
        <AgentPromptForm onSubmit={handleStart} isLoading={isStarting} />
      )}

      {activeRunId && <AgentRunView runId={activeRunId} />}

      {domainRuns.length > 0 && (
        <Card className="rounded-xl">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Previous Runs
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {domainRuns
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
