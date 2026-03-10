import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const stateStyles: Record<string, string> = {
  pending: "bg-muted text-muted-foreground border-border",
  running: "bg-secondary text-foreground border-border animate-pulse",
  completed: "bg-white/10 text-white border-white/20",
  failed: "bg-red-950 text-red-300 border-red-800",
  archived: "bg-muted text-muted-foreground/50 border-border",
};

export function StateBadge({ state }: { state: string }) {
  return (
    <Badge
      variant="outline"
      className={cn(
        "text-xs capitalize",
        stateStyles[state] ?? stateStyles.pending,
      )}
    >
      {state}
    </Badge>
  );
}
