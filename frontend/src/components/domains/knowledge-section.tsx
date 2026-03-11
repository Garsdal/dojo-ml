import type { KnowledgeAtom } from "@/types";

interface KnowledgeSectionProps {
  atoms: KnowledgeAtom[] | undefined;
  isLoading: boolean;
}

export function KnowledgeSection({ atoms, isLoading }: KnowledgeSectionProps) {
  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }

  if (!atoms || atoms.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No knowledge yet. The agent will accumulate knowledge during research
        runs.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {atoms.map((atom) => (
        <div key={atom.id} className="rounded-lg border p-3 text-sm space-y-1">
          <div className="flex items-center justify-between">
            <span className="font-medium">{atom.claim}</span>
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span>v{atom.version}</span>
              <ConfidenceBar value={atom.confidence} />
            </div>
          </div>
          <p className="text-xs text-muted-foreground">{atom.context}</p>
          {atom.action && (
            <p className="text-xs text-muted-foreground italic">
              → {atom.action}
            </p>
          )}
        </div>
      ))}
    </div>
  );
}

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  return (
    <div className="flex items-center gap-1">
      <div className="h-1.5 w-12 rounded-full bg-secondary overflow-hidden">
        <div
          className="h-full rounded-full bg-foreground/60"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-[10px] tabular-nums">{pct}%</span>
    </div>
  );
}
