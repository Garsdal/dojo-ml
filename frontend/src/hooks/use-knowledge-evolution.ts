import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import type { KnowledgeSnapshot } from "@/types";

export function useKnowledgeEvolution(domainId: string | undefined) {
  return useSWR<KnowledgeSnapshot[]>(
    domainId ? `/domains/${domainId}/knowledge/evolution` : null,
    (url: string) => apiFetch<KnowledgeSnapshot[]>(url),
  );
}
