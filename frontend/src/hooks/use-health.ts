import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import type { HealthStatus } from "@/types";

export function useHealth() {
  return useSWR<HealthStatus>(
    "/health",
    (url: string) => apiFetch<HealthStatus>(url),
    { refreshInterval: 10000 },
  );
}
