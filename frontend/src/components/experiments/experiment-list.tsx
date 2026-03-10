import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { StateBadge } from "@/components/state-badge";
import { useExperiments } from "@/hooks/use-experiments";
import type { Experiment } from "@/types";

interface ExperimentListProps {
  taskId?: string;
  onSelect: (experiment: Experiment) => void;
  selectedId?: string;
}

export function ExperimentList({
  taskId,
  onSelect,
  selectedId,
}: ExperimentListProps) {
  const { data: experiments, error, isLoading } = useExperiments(taskId);

  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <p className="text-sm text-red-400">
        Failed to load experiments: {error.message}
      </p>
    );
  }

  if (!experiments || experiments.length === 0) {
    return (
      <p className="text-sm text-muted-foreground py-8 text-center">
        No experiments found.
      </p>
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-[120px]">ID</TableHead>
          <TableHead className="w-[120px]">Task ID</TableHead>
          <TableHead className="w-[100px]">State</TableHead>
          <TableHead>Config</TableHead>
          <TableHead>Metrics</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {experiments.map((exp) => (
          <TableRow
            key={exp.id}
            onClick={() => onSelect(exp)}
            className={`cursor-pointer ${
              selectedId === exp.id ? "bg-muted" : ""
            }`}
          >
            <TableCell className="font-mono text-xs">
              {exp.id.slice(0, 8)}&hellip;
            </TableCell>
            <TableCell className="font-mono text-xs">
              {exp.task_id.slice(0, 8)}&hellip;
            </TableCell>
            <TableCell>
              <StateBadge state={exp.state} />
            </TableCell>
            <TableCell className="font-mono text-xs text-muted-foreground max-w-[200px] truncate">
              {JSON.stringify(exp.config).slice(0, 40)}
              {JSON.stringify(exp.config).length > 40 ? "\u2026" : ""}
            </TableCell>
            <TableCell className="font-mono text-xs">
              {exp.metrics
                ? Object.entries(exp.metrics)
                    .map(([k, v]) => `${k}: ${v.toFixed(3)}`)
                    .join(", ")
                : "\u2014"}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
