import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useTasks } from "@/hooks/use-tasks";
import { useExperiments } from "@/hooks/use-experiments";
import { useKnowledge } from "@/hooks/use-knowledge";
import { useHealth } from "@/hooks/use-health";
import { ListTodo, FlaskConical, Brain, Server } from "lucide-react";

export default function DashboardPage() {
  const { data: tasks, isLoading: tasksLoading } = useTasks();
  const { data: experiments, isLoading: expsLoading } = useExperiments();
  const { data: knowledge, isLoading: knowledgeLoading } = useKnowledge();
  const { data: health } = useHealth();

  const cards = [
    {
      title: "Tasks",
      icon: ListTodo,
      loading: tasksLoading,
      value: tasks?.length ?? 0,
      detail: tasks
        ? `${tasks.filter((t) => t.status === "completed").length} completed`
        : "",
    },
    {
      title: "Experiments",
      icon: FlaskConical,
      loading: expsLoading,
      value: experiments?.length ?? 0,
      detail: experiments
        ? `${experiments.filter((e) => e.state === "completed").length} completed`
        : "",
    },
    {
      title: "Knowledge",
      icon: Brain,
      loading: knowledgeLoading,
      value: knowledge?.length ?? 0,
      detail: "atoms stored",
    },
    {
      title: "Server",
      icon: Server,
      loading: false,
      value: health?.status === "ok" ? "Online" : "Offline",
      detail: "http://127.0.0.1:8000",
    },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground text-sm mt-1">
          Overview of your AgentML workspace
        </p>
      </div>
      <div className="grid gap-6 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
        {cards.map((card) => (
          <Card key={card.title} className="rounded-xl">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                {card.title}
              </CardTitle>
              <card.icon className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              {card.loading ? (
                <Skeleton className="h-8 w-20" />
              ) : (
                <>
                  <div className="text-2xl font-bold">{card.value}</div>
                  <p className="text-xs text-muted-foreground mt-1">
                    {card.detail}
                  </p>
                </>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
