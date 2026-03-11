import { useState } from "react";
import { useDomains, createDomain } from "@/hooks/use-domains";
import { useHealth } from "@/hooks/use-health";
import { DomainCard } from "@/components/domains/domain-card";
import { DomainForm } from "@/components/domains/domain-form";
import { Button } from "@/components/ui/button";

export default function DomainOverviewPage() {
  const { data: domains, isLoading, mutate } = useDomains();
  const { data: health } = useHealth();
  const [showForm, setShowForm] = useState(false);
  const [isCreating, setIsCreating] = useState(false);

  const handleCreate = async (data: {
    name: string;
    description: string;
    prompt: string;
  }) => {
    setIsCreating(true);
    try {
      await createDomain(data);
      await mutate();
      setShowForm(false);
    } finally {
      setIsCreating(false);
    }
  };

  const activeDomains = domains?.filter((d) => d.status !== "archived") ?? [];
  const archivedDomains = domains?.filter((d) => d.status === "archived") ?? [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">
            Research Domains
          </h1>
          <p className="text-muted-foreground text-sm mt-1">
            {health?.status === "ok" ? "Server connected" : "Connecting…"}
            {domains &&
              ` · ${domains.length} domain${domains.length !== 1 ? "s" : ""}`}
          </p>
        </div>
        {!showForm && (
          <Button onClick={() => setShowForm(true)}>+ New Domain</Button>
        )}
      </div>

      {/* Create form */}
      {showForm && (
        <div className="space-y-2">
          <DomainForm onSubmit={handleCreate} isLoading={isCreating} />
          <Button variant="ghost" size="sm" onClick={() => setShowForm(false)}>
            Cancel
          </Button>
        </div>
      )}

      {/* Loading state */}
      {isLoading && (
        <p className="text-sm text-muted-foreground">Loading domains…</p>
      )}

      {/* Empty state */}
      {!isLoading && domains && domains.length === 0 && !showForm && (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <p className="text-muted-foreground mb-4">
            No research domains yet. Create one to begin.
          </p>
          <Button onClick={() => setShowForm(true)}>Create First Domain</Button>
        </div>
      )}

      {/* Active domains grid */}
      {activeDomains.length > 0 && (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {activeDomains.map((domain) => (
            <DomainCard key={domain.id} domain={domain} />
          ))}
        </div>
      )}

      {/* Archived domains */}
      {archivedDomains.length > 0 && (
        <div>
          <h2 className="text-sm font-medium text-muted-foreground mb-3">
            Archived
          </h2>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3 opacity-60">
            {archivedDomains.map((domain) => (
              <DomainCard key={domain.id} domain={domain} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
