import { Badge } from "@/components/ui/badge";
import { useHealth } from "@/hooks/use-health";
import { cn } from "@/lib/utils";

export function Header() {
  const { data, error } = useHealth();
  const isHealthy = !!data && !error && data.status === "ok";

  return (
    <header className="flex items-center justify-between h-14 px-6 border-b bg-background">
      <div className="flex items-center gap-2">
        <span className="text-lg font-bold tracking-tight">AgentML</span>
        <Badge variant="outline" className="text-xs font-mono">
          v0.1.0
        </Badge>
      </div>
      <div className="flex items-center gap-2">
        <div
          className={cn(
            "h-2 w-2 rounded-full",
            isHealthy ? "bg-green-500" : "bg-red-500",
          )}
        />
        <span className="text-xs text-muted-foreground">
          {isHealthy ? "Connected" : "Disconnected"}
        </span>
      </div>
    </header>
  );
}
