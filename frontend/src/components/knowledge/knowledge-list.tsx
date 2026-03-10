import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { useKnowledge } from "@/hooks/use-knowledge";
import type { KnowledgeAtom } from "@/types";

interface KnowledgeListProps {
  atoms?: KnowledgeAtom[];
  onSelect: (atom: KnowledgeAtom) => void;
  selectedId?: string;
}

export function KnowledgeList({
  atoms: externalAtoms,
  onSelect,
  selectedId,
}: KnowledgeListProps) {
  const { data: fetchedAtoms, error, isLoading } = useKnowledge();
  const atoms = externalAtoms ?? fetchedAtoms;

  if (!externalAtoms && isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    );
  }

  if (!externalAtoms && error) {
    return (
      <p className="text-sm text-red-400">
        Failed to load knowledge: {error.message}
      </p>
    );
  }

  if (!atoms || atoms.length === 0) {
    return (
      <p className="text-sm text-muted-foreground py-8 text-center">
        No knowledge atoms found.
      </p>
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-[100px]">ID</TableHead>
          <TableHead>Context</TableHead>
          <TableHead>Claim</TableHead>
          <TableHead>Action</TableHead>
          <TableHead className="w-[100px]">Confidence</TableHead>
          <TableHead className="w-[80px]">Evidence</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {atoms.map((atom) => (
          <TableRow
            key={atom.id}
            onClick={() => onSelect(atom)}
            className={`cursor-pointer ${
              selectedId === atom.id ? "bg-muted" : ""
            }`}
          >
            <TableCell className="font-mono text-xs">
              {atom.id.slice(0, 8)}&hellip;
            </TableCell>
            <TableCell className="max-w-[150px] truncate text-sm">
              {atom.context}
            </TableCell>
            <TableCell className="max-w-[150px] truncate text-sm">
              {atom.claim}
            </TableCell>
            <TableCell className="max-w-[150px] truncate text-sm">
              {atom.action}
            </TableCell>
            <TableCell>
              <div className="flex items-center gap-2">
                <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
                  <div
                    className="h-full bg-foreground/60 rounded-full"
                    style={{ width: `${atom.confidence * 100}%` }}
                  />
                </div>
                <span className="font-mono text-xs">
                  {(atom.confidence * 100).toFixed(0)}%
                </span>
              </div>
            </TableCell>
            <TableCell className="font-mono text-xs">
              {atom.evidence_ids.length}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
