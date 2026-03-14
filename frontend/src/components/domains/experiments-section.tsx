import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { StateBadge } from "@/components/state-badge";
import { ExperimentDetailPanel } from "@/components/domains/experiment-detail";
import type { Experiment } from "@/types";

interface ExperimentsSectionProps {
  experiments: Experiment[] | undefined;
  isLoading: boolean;
  highlightId?: string;
}

export function ExperimentsSection({ experiments, isLoading, highlightId }: ExperimentsSectionProps) {
  const [expandedId, setExpandedId] = useState<string | null>(highlightId ?? null);

  if (isLoading) {
    return <p className="text-sm text-grey">Loading…</p>;
  }

  if (!experiments || experiments.length === 0) {
    return (
      <p className="text-sm text-grey">
        No experiments yet. Start an agent run to create experiments.
      </p>
    );
  }

  return (
    <div className="rounded-2xl border border-soft-fawn/20 overflow-hidden bg-white">
      <Table>
        <TableHeader>
          <TableRow className="bg-wheat/10 hover:bg-wheat/10 border-b border-soft-fawn/20">
            <TableHead className="w-6" />
            <TableHead className="text-grey font-semibold uppercase text-xs tracking-wide">ID</TableHead>
            <TableHead className="text-grey font-semibold uppercase text-xs tracking-wide">State</TableHead>
            <TableHead className="text-grey font-semibold uppercase text-xs tracking-wide">Config</TableHead>
            <TableHead className="text-grey font-semibold uppercase text-xs tracking-wide text-right">Metrics</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {experiments.map((exp) => {
            const isExpanded = expandedId === exp.id;
            return (
              <>
                <TableRow
                  key={exp.id}
                  onClick={() => setExpandedId(isExpanded ? null : exp.id)}
                  className="hover:bg-wheat/5 border-b border-soft-fawn/10 cursor-pointer"
                >
                  <TableCell className="w-6 pl-3">
                    {isExpanded ? (
                      <ChevronDown className="h-3.5 w-3.5 text-grey" />
                    ) : (
                      <ChevronRight className="h-3.5 w-3.5 text-grey" />
                    )}
                  </TableCell>
                  <TableCell className="font-mono text-xs text-grey">
                    {exp.id.slice(0, 12)}…
                  </TableCell>
                  <TableCell>
                    <StateBadge state={exp.state} />
                  </TableCell>
                  <TableCell className="max-w-[200px]">
                    {Object.keys(exp.config).length > 0 ? (
                      <div className="flex flex-wrap gap-1">
                        {Object.entries(exp.config)
                          .slice(0, 3)
                          .map(([k, v]) => (
                            <span
                              key={k}
                              className="inline-flex items-center bg-wheat/20 text-blackberry rounded-full text-xs px-2 py-0.5"
                            >
                              {k}: {String(v).slice(0, 10)}
                            </span>
                          ))}
                      </div>
                    ) : (
                      <span className="text-xs text-grey">—</span>
                    )}
                  </TableCell>
                  <TableCell className="text-right">
                    {exp.metrics && Object.keys(exp.metrics).length > 0 ? (
                      <div className="flex flex-col items-end gap-0.5">
                        {Object.entries(exp.metrics)
                          .slice(0, 2)
                          .map(([k, v]) => (
                            <span key={k} className="text-xs text-blackberry">
                              <span className="text-grey mr-1">{k}:</span>
                              <span className="font-semibold">
                                {typeof v === "number" ? v.toFixed(3) : String(v)}
                              </span>
                            </span>
                          ))}
                      </div>
                    ) : (
                      <span className="text-xs text-grey">—</span>
                    )}
                  </TableCell>
                </TableRow>
                {isExpanded && (
                  <tr key={`${exp.id}-detail`}>
                    <td colSpan={5} className="p-0">
                      <ExperimentDetailPanel experiment={exp} />
                    </td>
                  </tr>
                )}
              </>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
