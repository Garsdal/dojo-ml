import { useState } from "react";
import { Search, Brain } from "lucide-react";
import { Input } from "@/components/ui/input";
import { KnowledgeAtomCard } from "@/components/domains/knowledge-atom-card";
import { useKnowledge, useKnowledgeSearch } from "@/hooks/use-knowledge";
import { useDomains } from "@/hooks/use-domains";

export default function KnowledgeOverviewPage() {
  const [query, setQuery] = useState("");

  const { data: allAtoms, isLoading: allLoading } = useKnowledge();
  const { data: searchResults, isLoading: searchLoading } = useKnowledgeSearch(query);
  const { data: domains } = useDomains();

  const domainNameById = Object.fromEntries(
    (domains ?? []).map((d) => [d.id, d.name]),
  );

  const isSearching = query.trim().length > 0;
  const atoms = isSearching ? searchResults : allAtoms;
  const isLoading = isSearching ? searchLoading : allLoading;

  const avgConfidence =
    allAtoms && allAtoms.length > 0
      ? Math.round((allAtoms.reduce((s, a) => s + a.confidence, 0) / allAtoms.length) * 100)
      : null;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <div className="flex items-center gap-3 mb-1">
          <Brain className="h-6 w-6 text-blackberry" />
          <h1 className="font-heading font-extrabold text-blackberry text-[1.75rem] leading-tight">
            Knowledge
          </h1>
        </div>
        <p className="text-grey text-sm">All accumulated knowledge across domains</p>
      </div>

      {/* Stats header */}
      {allAtoms && allAtoms.length > 0 && (
        <div className="flex items-center gap-0 bg-wheat/10 rounded-xl overflow-hidden border border-soft-fawn/20">
          {[
            { label: "Total Atoms", value: allAtoms.length },
            { label: "Avg Confidence", value: avgConfidence !== null ? `${avgConfidence}%` : "—" },
            { label: "Domains", value: domains?.length ?? "—" },
          ].map((stat, i) => (
            <div
              key={stat.label}
              className={`flex-1 px-5 py-3 ${i < 2 ? "border-r border-soft-fawn/20" : ""}`}
            >
              <div className="text-xs text-grey font-medium">{stat.label}</div>
              <div className="text-lg font-bold text-blackberry mt-0.5">{stat.value}</div>
            </div>
          ))}
        </div>
      )}

      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-grey" />
        <Input
          placeholder="Search knowledge across all domains…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="pl-9 text-sm"
        />
      </div>

      {/* Results */}
      {isLoading ? (
        <p className="text-sm text-grey">Loading…</p>
      ) : !atoms || atoms.length === 0 ? (
        <p className="text-sm text-grey py-8 text-center">
          {isSearching ? "No matching knowledge found." : "No knowledge yet. Run experiments to accumulate knowledge."}
        </p>
      ) : (
        <div className="space-y-2">
          {isSearching && (
            <p className="text-xs text-grey">{atoms.length} result{atoms.length !== 1 ? "s" : ""}</p>
          )}
          {atoms.map((atom) => {
            // Try to find domain name from evidence_ids if no direct domain link
            // For now show a placeholder if we can't resolve it
            const domainBadge =
              domainNameById[atom.id] ?? undefined;
            return (
              <KnowledgeAtomCard
                key={atom.id}
                atom={atom}
                domainBadge={domainBadge}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}
