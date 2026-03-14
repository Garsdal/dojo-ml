import { useState, useEffect } from "react";
import type { AgentEvent } from "@/types";

const API_BASE = import.meta.env.VITE_API_URL ?? "";

// Pure SSE event collection — no revalidation logic.
// Polling is handled at the page level (domain-detail) so it works
// regardless of which tab is active.
export function useAgentEvents(runId: string | undefined) {
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (!runId) return;

    setEvents([]);
    setDone(false);

    const es = new EventSource(`${API_BASE}/agent/runs/${runId}/events`);

    const handleEvent = (e: MessageEvent) => {
      try {
        const parsed = JSON.parse(e.data) as AgentEvent;
        setEvents((prev) => [...prev, parsed]);
      } catch {
        // Ignore malformed events
      }
    };

    es.addEventListener("tool_call", handleEvent);
    es.addEventListener("tool_result", handleEvent);
    es.addEventListener("text", handleEvent);
    es.addEventListener("error", handleEvent);
    es.addEventListener("result", handleEvent);
    es.addEventListener("done", () => {
      setDone(true);
      es.close();
    });
    es.onerror = () => {
      setDone(true);
      es.close();
    };

    return () => {
      es.close();
    };
  }, [runId]);

  return { events, done };
}
