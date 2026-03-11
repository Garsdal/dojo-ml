import { useParams, useNavigate } from "react-router-dom";
import { useDomain, updateDomain } from "@/hooks/use-domain";
import { useDomainExperiments } from "@/hooks/use-domain-experiments";
import { useDomainKnowledge } from "@/hooks/use-domain-knowledge";
import { useDomainMetrics } from "@/hooks/use-domain-metrics";
import { useKnowledgeEvolution } from "@/hooks/use-knowledge-evolution";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { StateBadge } from "@/components/state-badge";
import { ExperimentsSection } from "@/components/domains/experiments-section";
import { KnowledgeSection } from "@/components/domains/knowledge-section";
import { ToolsSection } from "@/components/domains/tools-section";
import { AgentSection } from "@/components/domains/agent-section";
import { MetricEvolutionChart } from "@/components/charts/metric-evolution-chart";
import { KnowledgeEvolutionChart } from "@/components/charts/knowledge-evolution-chart";

export default function DomainDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: domain, isLoading, mutate } = useDomain(id);
  const { data: experiments, isLoading: expLoading } = useDomainExperiments(id);
  const { data: knowledge, isLoading: knLoading } = useDomainKnowledge(id);
  const { data: metrics, isLoading: metLoading } = useDomainMetrics(id);
  const { data: evolution, isLoading: evoLoading } = useKnowledgeEvolution(id);

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Loading domain…</p>;
  }

  if (!domain) {
    return (
      <div className="space-y-4">
        <p className="text-sm text-muted-foreground">Domain not found.</p>
        <Button variant="ghost" onClick={() => navigate("/")}>
          ← Back to domains
        </Button>
      </div>
    );
  }

  const handleStatusChange = async (status: string) => {
    await updateDomain(domain.id, { status });
    await mutate();
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <button
            onClick={() => navigate("/")}
            className="text-xs text-muted-foreground hover:text-foreground transition-colors mb-1 block"
          >
            ← All Domains
          </button>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold tracking-tight">{domain.name}</h1>
            <StateBadge state={domain.status} />
          </div>
          {domain.description && (
            <p className="text-muted-foreground text-sm mt-1">
              {domain.description}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          {domain.status === "active" && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => handleStatusChange("paused")}
            >
              Pause
            </Button>
          )}
          {domain.status === "paused" && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => handleStatusChange("active")}
            >
              Resume
            </Button>
          )}
          {(domain.status === "active" || domain.status === "paused") && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => handleStatusChange("completed")}
            >
              Complete
            </Button>
          )}
        </div>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-4 gap-4">
        <StatCard label="Experiments" value={domain.experiment_ids.length} />
        <StatCard label="Knowledge" value={knowledge?.length ?? 0} />
        <StatCard label="Tools" value={domain.tools.length} />
        <StatCard
          label="Created"
          value={new Date(domain.created_at).toLocaleDateString()}
        />
      </div>

      {/* Tabbed content */}
      <Tabs defaultValue="agent" className="space-y-4">
        <TabsList>
          <TabsTrigger value="agent">Agent</TabsTrigger>
          <TabsTrigger value="experiments">Experiments</TabsTrigger>
          <TabsTrigger value="knowledge">Knowledge</TabsTrigger>
          <TabsTrigger value="metrics">Metrics</TabsTrigger>
          <TabsTrigger value="tools">Tools</TabsTrigger>
        </TabsList>

        <TabsContent value="agent">
          <Card className="rounded-xl">
            <CardHeader>
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Agent Research
              </CardTitle>
            </CardHeader>
            <CardContent>
              <AgentSection domainId={domain.id} />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="experiments">
          <Card className="rounded-xl">
            <CardHeader>
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Experiments ({experiments?.length ?? 0})
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ExperimentsSection
                experiments={experiments}
                isLoading={expLoading}
              />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="knowledge" className="space-y-4">
          <Card className="rounded-xl">
            <CardHeader>
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Accumulated Knowledge ({knowledge?.length ?? 0})
              </CardTitle>
            </CardHeader>
            <CardContent>
              <KnowledgeSection atoms={knowledge} isLoading={knLoading} />
            </CardContent>
          </Card>

          <Card className="rounded-xl">
            <CardHeader>
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Knowledge Evolution
              </CardTitle>
            </CardHeader>
            <CardContent>
              <KnowledgeEvolutionChart
                data={evolution}
                isLoading={evoLoading}
              />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="metrics">
          <Card className="rounded-xl">
            <CardHeader>
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Metric Evolution
              </CardTitle>
            </CardHeader>
            <CardContent>
              <MetricEvolutionChart data={metrics} isLoading={metLoading} />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="tools">
          <Card className="rounded-xl">
            <CardHeader>
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Domain Tools ({domain.tools.length})
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ToolsSection
                domainId={domain.id}
                tools={domain.tools}
                onMutate={() => mutate()}
              />
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <Card className="rounded-xl">
      <CardContent className="pt-4">
        <div className="text-xs text-muted-foreground">{label}</div>
        <div className="text-xl font-bold mt-0.5">{value}</div>
      </CardContent>
    </Card>
  );
}
