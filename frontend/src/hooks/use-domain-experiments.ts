import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import type { Experiment } from "@/types";

export function useDomainExperiments(domainId: string | undefined) {
  return useSWR<Experiment[]>(
    domainId ? `/domains/${domainId}/experiments` : null,
    (url: string) => apiFetch<Experiment[]>(url),
  );
}
