import { Badge } from "@/components/ui/badge";
import { useHealth } from "@/hooks/use-health";
import { cn } from "@/lib/utils";

export function Header() {
  const { data, error } = useHealth();
  const isHealthy = !!data && !error && data.status === "ok";

  return (
    <header className="flex items-center justify-between h-14 px-6 border-b border-soft-fawn/20 bg-surface">
      <div className="flex items-center gap-2.5">
        <img
          src="/assets/dojo-logo-no-bg.png"
          alt="Dojo.ml"
          className="h-8 w-auto"
        />
        <span className="font-heading font-extrabold text-blackberry text-xl tracking-tight">
          Dojo
        </span>
        <Badge className="bg-wheat/30 text-blackberry border-0 text-[10px] px-1.5 py-0">
          v0.1.0
        </Badge>
      </div>
      <div className="flex items-center gap-2">
        <div
          className={cn(
            "h-2 w-2 rounded-full",
            isHealthy ? "bg-muted-teal" : "bg-danger",
          )}
        />
        <span className="text-xs text-grey">
          {isHealthy ? "Connected" : "Disconnected"}
        </span>
      </div>
    </header>
  );
}
