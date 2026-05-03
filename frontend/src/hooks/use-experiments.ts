import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import type { Experiment } from "@/types";

export function useExperiments(domainId?: string) {
  const params = domainId ? `?domain_id=${domainId}` : "";
  return useSWR<Experiment[]>(`/experiments${params}`, (url: string) =>
    apiFetch<Experiment[]>(url),
  );
}

export function useExperiment(id: string | undefined) {
  return useSWR<Experiment>(id ? `/experiments/${id}` : null, (url: string) =>
    apiFetch<Experiment>(url),
  );
}
