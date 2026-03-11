import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { StateBadge } from "@/components/state-badge";
import type { Experiment } from "@/types";

interface ExperimentsSectionProps {
  experiments: Experiment[] | undefined;
  isLoading: boolean;
}

export function ExperimentsSection({
  experiments,
  isLoading,
}: ExperimentsSectionProps) {
  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }

  if (!experiments || experiments.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No experiments yet. Start an agent run to create experiments.
      </p>
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>ID</TableHead>
          <TableHead>State</TableHead>
          <TableHead>Config</TableHead>
          <TableHead className="text-right">Metrics</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {experiments.map((exp) => (
          <TableRow key={exp.id}>
            <TableCell className="font-mono text-xs">
              {exp.id.slice(0, 12)}…
            </TableCell>
            <TableCell>
              <StateBadge state={exp.state} />
            </TableCell>
            <TableCell className="text-xs text-muted-foreground max-w-[200px] truncate">
              {Object.keys(exp.config).length > 0
                ? JSON.stringify(exp.config).slice(0, 60)
                : "—"}
            </TableCell>
            <TableCell className="text-right text-xs">
              {exp.metrics
                ? Object.entries(exp.metrics)
                    .map(
                      ([k, v]) =>
                        `${k}: ${typeof v === "number" ? v.toFixed(3) : v}`,
                    )
                    .join(", ")
                : "—"}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
