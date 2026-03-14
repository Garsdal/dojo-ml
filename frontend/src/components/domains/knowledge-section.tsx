import { useState, useMemo } from "react";
import { Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import { KnowledgeAtomCard } from "@/components/domains/knowledge-atom-card";
import type { KnowledgeAtom } from "@/types";

interface KnowledgeSectionProps {
  atoms: KnowledgeAtom[] | undefined;
  isLoading: boolean;
  onEvidenceClick?: (experimentId: string) => void;
}

export function KnowledgeSection({ atoms, isLoading, onEvidenceClick }: KnowledgeSectionProps) {
  const [search, setSearch] = useState("");

  const filtered = useMemo(() => {
    if (!atoms) return [];
    const q = search.toLowerCase();
    if (!q) return atoms;
    return atoms.filter(
      (a) =>
        a.claim.toLowerCase().includes(q) ||
        a.context.toLowerCase().includes(q),
    );
  }, [atoms, search]);

  if (isLoading) {
    return <p className="text-sm text-grey">Loading…</p>;
  }

  if (!atoms || atoms.length === 0) {
    return (
      <p className="text-sm text-grey">
        No knowledge yet. The agent will accumulate knowledge during research runs.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-grey" />
        <Input
          placeholder="Search claims and context…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="pl-9 text-sm"
        />
      </div>

      {/* Results count */}
      {search && (
        <p className="text-xs text-grey">
          {filtered.length} of {atoms.length} results
        </p>
      )}

      {/* Knowledge cards */}
      {filtered.length === 0 && search ? (
        <p className="text-sm text-grey py-4 text-center">No matching knowledge found.</p>
      ) : (
        <div className="space-y-2">
          {filtered.map((atom) => (
            <KnowledgeAtomCard
              key={atom.id}
              atom={atom}
              onEvidenceClick={onEvidenceClick}
            />
          ))}
        </div>
      )}
    </div>
  );
}
