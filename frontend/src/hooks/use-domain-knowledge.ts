import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import type { KnowledgeAtom, KnowledgeDetail } from "@/types";

export function useDomainKnowledge(domainId: string | undefined) {
  return useSWR<KnowledgeAtom[]>(
    domainId ? `/domains/${domainId}/knowledge` : null,
    (url: string) => apiFetch<KnowledgeAtom[]>(url),
  );
}

export function useKnowledgeDetail(atomId: string | undefined) {
  return useSWR<KnowledgeDetail>(
    atomId ? `/knowledge/${atomId}` : null,
    (url: string) => apiFetch<KnowledgeDetail>(url),
  );
}
