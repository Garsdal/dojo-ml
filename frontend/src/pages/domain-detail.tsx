import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useSWRConfig } from "swr";
import { useDomain, updateDomain } from "@/hooks/use-domain";
import { useDomainExperiments } from "@/hooks/use-domain-experiments";
import { useDomainKnowledge } from "@/hooks/use-domain-knowledge";
import { useDomainMetrics } from "@/hooks/use-domain-metrics";
import { useAgentRuns } from "@/hooks/use-agent";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { StateBadge } from "@/components/state-badge";
import { Breadcrumb } from "@/components/layout/breadcrumb";
import { ExperimentsSection } from "@/components/domains/experiments-section";
import { KnowledgeSection } from "@/components/domains/knowledge-section";
import { ToolsSection } from "@/components/domains/tools-section";
import { AgentSection } from "@/components/domains/agent-section";
import { DomainDashboard } from "@/components/domains/domain-dashboard";
import { MetricEvolutionChart } from "@/components/charts/metric-evolution-chart";
import { ErrorBoundary } from "@/components/ui/error-boundary";
import { cn } from "@/lib/utils";
import {
  PauseCircle,
  PlayCircle,
  CheckCircle,
  Archive,
  LayoutDashboard,
  Bot,
  FlaskConical,
  Brain,
  BarChart3,
  Wrench,
  CheckCircle2,
  AlertCircle,
} from "lucide-react";
import { setupWorkspace } from "@/hooks/use-workspace";

export default function DomainDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: domain, isLoading, mutate } = useDomain(id);
  const { data: experiments, isLoading: expLoading } = useDomainExperiments(id);
  const { data: knowledge, isLoading: knLoading } = useDomainKnowledge(id);
  const { data: metrics, isLoading: metLoading } = useDomainMetrics(id);
  const [activeTab, setActiveTab] = useState("dashboard");
  const [highlightExpId, setHighlightExpId] = useState<string | undefined>(
    undefined,
  );

  const { data: agentRuns } = useAgentRuns();
  const hasActiveRun =
    agentRuns?.some((r) => r.domain_id === id && r.status === "running") ??
    false;
  const { mutate: globalMutate } = useSWRConfig();

  // Poll domain data every 3 seconds while an agent run is active for this domain.
  // Lives here (not inside the Agent tab) so it works regardless of which tab is visible.
  useEffect(() => {
    if (!hasActiveRun || !id) return;
    const interval = setInterval(() => {
      void globalMutate(
        (key) => typeof key === "string" && key.startsWith(`/domains/${id}`),
        undefined,
        { revalidate: true },
      );
    }, 3000);
    return () => clearInterval(interval);
  }, [hasActiveRun, id, globalMutate]);

  const handleExperimentClick = (experimentId: string) => {
    setHighlightExpId(experimentId);
    setActiveTab("experiments");
  };

  if (isLoading) {
    return <p className="text-sm text-grey">Loading domain…</p>;
  }

  if (!domain) {
    return (
      <div className="space-y-4">
        <p className="text-sm text-grey">Domain not found.</p>
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
      {/* Breadcrumb */}
      <Breadcrumb
        items={[{ label: "Domains", href: "/" }, { label: domain.name }]}
      />

      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-3 flex-wrap">
            <h1 className="font-heading font-extrabold text-blackberry text-[1.75rem] leading-tight">
              {domain.name}
            </h1>
            <StateBadge state={domain.status} />
          </div>
          {domain.description && (
            <p className="text-grey text-sm mt-1">{domain.description}</p>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {domain.status === "active" && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => handleStatusChange("paused")}
            >
              <PauseCircle className="h-4 w-4" />
              Pause
            </Button>
          )}
          {domain.status === "paused" && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => handleStatusChange("active")}
            >
              <PlayCircle className="h-4 w-4" />
              Resume
            </Button>
          )}
          {(domain.status === "active" || domain.status === "paused") && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => handleStatusChange("completed")}
            >
              <CheckCircle className="h-4 w-4" />
              Complete
            </Button>
          )}
          {domain.status !== "archived" && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => handleStatusChange("archived")}
            >
              <Archive className="h-4 w-4" />
              Archive
            </Button>
          )}
        </div>
      </div>

      {/* Stat strip */}
      <div className="flex items-center gap-0 bg-wheat/10 rounded-xl overflow-hidden border border-soft-fawn/20">
        {[
          {
            label: "Experiments",
            value: experiments?.length ?? domain.experiment_ids.length,
            tab: "experiments",
          },
          {
            label: "Knowledge",
            value: knowledge?.length ?? "—",
            tab: "knowledge",
          },
          { label: "Tools", value: domain.tools.length, tab: "tools" },
          {
            label: "Created",
            value: new Date(domain.created_at).toLocaleDateString(),
            tab: null,
          },
        ].map((stat, i) => (
          <div
            key={stat.label}
            onClick={() => stat.tab && setActiveTab(stat.tab)}
            className={cn(
              "flex-1 px-5 py-3",
              i < 3 ? "border-r border-soft-fawn/20" : "",
              stat.tab
                ? "cursor-pointer hover:bg-wheat/20 transition-colors"
                : "",
            )}
          >
            <div className="text-xs text-grey font-medium">{stat.label}</div>
            <div className="text-lg font-bold text-blackberry mt-0.5">
              {stat.value}
            </div>
          </div>
        ))}
      </div>

      {/* Workspace status row */}
      {domain.workspace && (
        <div className="flex items-center gap-3 flex-wrap px-1">
          <span className="text-xs text-grey font-medium">Workspace</span>
          {domain.workspace.ready ? (
            <span className="inline-flex items-center gap-1 bg-muted-teal/20 text-muted-teal rounded-full text-xs px-2.5 py-0.5 font-medium">
              <CheckCircle2 className="h-3 w-3" />
              ready
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 bg-wheat/40 text-soft-fawn rounded-full text-xs px-2.5 py-0.5 font-medium">
              <AlertCircle className="h-3 w-3" />
              not ready
            </span>
          )}
          <span className="font-mono text-xs text-grey truncate max-w-[280px]">
            {domain.workspace.path}
          </span>
          {!domain.workspace.ready && (
            <SetupWorkspaceButton
              domainId={domain.id}
              onDone={() => mutate()}
            />
          )}
        </div>
      )}

      {/* Tabbed content */}
      <Tabs
        value={activeTab}
        onValueChange={setActiveTab}
        className="space-y-4"
      >
        <TabsList>
          <TabsTrigger value="dashboard" className="flex items-center gap-1.5">
            <LayoutDashboard className="h-3.5 w-3.5" />
            Dashboard
          </TabsTrigger>
          <TabsTrigger value="agent" className="flex items-center gap-1.5">
            <Bot className="h-3.5 w-3.5" />
            Agent
          </TabsTrigger>
          <TabsTrigger
            value="experiments"
            className="flex items-center gap-1.5"
          >
            <FlaskConical className="h-3.5 w-3.5" />
            Experiments
          </TabsTrigger>
          <TabsTrigger value="knowledge" className="flex items-center gap-1.5">
            <Brain className="h-3.5 w-3.5" />
            Knowledge
          </TabsTrigger>
          <TabsTrigger value="metrics" className="flex items-center gap-1.5">
            <BarChart3 className="h-3.5 w-3.5" />
            Metrics
          </TabsTrigger>
          <TabsTrigger value="tools" className="flex items-center gap-1.5">
            <Wrench className="h-3.5 w-3.5" />
            Tools
          </TabsTrigger>
        </TabsList>

        <TabsContent value="dashboard">
          <DomainDashboard
            experiments={experiments}
            knowledge={knowledge}
            metrics={metrics}
            metricsLoading={metLoading}
            onExperimentClick={handleExperimentClick}
          />
        </TabsContent>

        <TabsContent value="agent">
          <AgentSection domainId={domain.id} />
        </TabsContent>

        <TabsContent value="experiments">
          <ExperimentsSection
            experiments={experiments}
            isLoading={expLoading}
            highlightId={highlightExpId}
          />
        </TabsContent>

        <TabsContent value="knowledge">
          <KnowledgeSection
            atoms={knowledge}
            isLoading={knLoading}
            onEvidenceClick={handleExperimentClick}
          />
        </TabsContent>

        <TabsContent value="metrics">
          <ErrorBoundary
            fallback={
              <p className="text-sm text-grey">Failed to load metrics chart.</p>
            }
          >
            <MetricEvolutionChart data={metrics} isLoading={metLoading} />
          </ErrorBoundary>
        </TabsContent>

        <TabsContent value="tools">
          <ToolsSection
            domainId={domain.id}
            tools={domain.tools}
            hasWorkspace={domain.workspace !== null}
            onMutate={() => mutate()}
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function SetupWorkspaceButton({
  domainId,
  onDone,
}: {
  domainId: string;
  onDone: () => void;
}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSetup = async () => {
    setLoading(true);
    setError(null);
    try {
      await setupWorkspace(domainId);
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Setup failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex items-center gap-2">
      <Button
        size="sm"
        variant="outline"
        onClick={handleSetup}
        disabled={loading}
      >
        {loading ? "Setting up…" : "Set up"}
      </Button>
      {error && <span className="text-xs text-danger">{error}</span>}
    </div>
  );
}
