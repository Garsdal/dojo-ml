import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import type { MetricPoint } from "@/types";

export function useDomainMetrics(domainId: string | undefined) {
  return useSWR<MetricPoint[]>(
    domainId ? `/domains/${domainId}/metrics` : null,
    (url: string) => apiFetch<MetricPoint[]>(url),
  );
}
