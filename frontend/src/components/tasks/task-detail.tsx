import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { StateBadge } from "@/components/state-badge";
import { Separator } from "@/components/ui/separator";
import type { Task } from "@/types";

interface TaskDetailProps {
  task: Task;
}

export function TaskDetail({ task }: TaskDetailProps) {
  return (
    <Card className="rounded-xl">
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium text-muted-foreground">
            Task Detail
          </CardTitle>
          <StateBadge state={task.status} />
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <p className="text-xs text-muted-foreground mb-1">ID</p>
          <p className="font-mono text-sm">{task.id}</p>
        </div>

        <Separator />

        <div>
          <p className="text-xs text-muted-foreground mb-1">Prompt</p>
          <p className="text-sm whitespace-pre-wrap">{task.prompt}</p>
        </div>

        {task.summary && (
          <>
            <Separator />
            <div>
              <p className="text-xs text-muted-foreground mb-1">Summary</p>
              <p className="text-sm">{task.summary}</p>
            </div>
          </>
        )}

        {task.metrics && Object.keys(task.metrics).length > 0 && (
          <>
            <Separator />
            <div>
              <p className="text-xs text-muted-foreground mb-1">Metrics</p>
              <div className="grid grid-cols-2 gap-2">
                {Object.entries(task.metrics).map(([key, value]) => (
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

        {task.experiments.length > 0 && (
          <>
            <Separator />
            <div>
              <p className="text-xs text-muted-foreground mb-1">
                Linked Experiments ({task.experiments.length})
              </p>
              <div className="space-y-1">
                {task.experiments.map((exp) => (
                  <div
                    key={exp.id}
                    className="flex items-center justify-between bg-muted/50 rounded-lg px-3 py-2"
                  >
                    <span className="font-mono text-xs">
                      {exp.id.slice(0, 8)}&hellip;
                    </span>
                    <StateBadge state={exp.state} />
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
