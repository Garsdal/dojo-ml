import type { AgentEvent } from "@/types";
import { useRef, useEffect } from "react";
import { cn } from "@/lib/utils";

const eventStyles: Record<string, string> = {
  tool_call: "text-blue-400",
  tool_result: "text-green-400",
  text: "text-foreground",
  error: "text-red-400",
  result: "text-yellow-400",
};

const eventLabels: Record<string, string> = {
  tool_call: "TOOL",
  tool_result: "RESULT",
  text: "TEXT",
  error: "ERROR",
  result: "DONE",
};

function formatEventContent(event: AgentEvent): string {
  const d = event.data;
  switch (event.event_type) {
    case "tool_call":
      return `${d.tool as string}(${JSON.stringify(d.input ?? {})})`;
    case "tool_result":
      return String(d.content ?? "");
    case "text":
      return String(d.text ?? "");
    case "error":
      return String(d.error ?? "Unknown error");
    case "result":
      return `Turns: ${d.turns ?? 0} | Cost: $${d.cost_usd ?? 0}`;
    default:
      return JSON.stringify(d);
  }
}

export function EventFeed({ events }: { events: AgentEvent[] }) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events.length]);

  if (events.length === 0) {
    return (
      <div className="py-8 text-center text-sm text-muted-foreground">
        Waiting for events...
      </div>
    );
  }

  return (
    <div className="max-h-[500px] overflow-y-auto space-y-1 font-mono text-xs">
      {events.map((event) => (
        <div key={event.id} className="flex gap-2 py-0.5">
          <span
            className={cn(
              "shrink-0 w-14 text-right font-semibold",
              eventStyles[event.event_type] ?? "text-muted-foreground",
            )}
          >
            {eventLabels[event.event_type] ?? event.event_type.toUpperCase()}
          </span>
          <span className="text-muted-foreground shrink-0">|</span>
          <span className="break-all">{formatEventContent(event)}</span>
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
