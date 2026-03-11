import { useMemo } from "react";
import type { KnowledgeSnapshot } from "@/types";

interface KnowledgeEvolutionChartProps {
  data: KnowledgeSnapshot[] | undefined;
  isLoading: boolean;
}

export function KnowledgeEvolutionChart({
  data,
  isLoading,
}: KnowledgeEvolutionChartProps) {
  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }

  if (!data || data.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No knowledge evolution data yet.
      </p>
    );
  }

  // Group by atom_id to show evolution per atom
  const atomGroups = useMemo(() => {
    const groups = new Map<string, KnowledgeSnapshot[]>();
    data.forEach((s) => {
      const existing = groups.get(s.atom_id) ?? [];
      existing.push(s);
      groups.set(s.atom_id, existing);
    });
    return Array.from(groups.entries()).map(([atomId, snapshots]) => ({
      atomId,
      snapshots: snapshots.sort(
        (a, b) =>
          new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
      ),
    }));
  }, [data]);

  return (
    <div className="space-y-4">
      {atomGroups.map((group) => (
        <div key={group.atomId} className="space-y-1">
          <div className="text-xs font-mono text-muted-foreground">
            {group.atomId.slice(0, 12)}…
          </div>

          {/* Timeline */}
          <div className="flex items-center gap-1">
            {group.snapshots.map((snap, i) => (
              <div key={snap.id} className="flex items-center gap-1">
                {i > 0 && <div className="w-4 h-px bg-border" />}
                <div className="relative group">
                  <div
                    className="w-3 h-3 rounded-full border-2 border-foreground/40"
                    style={{
                      backgroundColor: `oklch(0.7 0.15 ${(snap.confidence * 120).toFixed(0)})`,
                    }}
                  />
                  {/* Tooltip */}
                  <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 hidden group-hover:block whitespace-nowrap rounded bg-popover border px-2 py-1 text-[10px] shadow-md z-10">
                    <div>
                      v{snap.version} — {(snap.confidence * 100).toFixed(0)}%
                    </div>
                    <div className="text-muted-foreground max-w-[200px] truncate">
                      {snap.claim}
                    </div>
                    <div className="text-muted-foreground">
                      {new Date(snap.timestamp).toLocaleString()}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Latest claim */}
          <p className="text-xs text-muted-foreground truncate">
            {group.snapshots[group.snapshots.length - 1]?.claim}
          </p>
        </div>
      ))}
    </div>
  );
}
