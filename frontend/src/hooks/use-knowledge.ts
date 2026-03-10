import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import type { KnowledgeAtom } from "@/types";

export function useKnowledge() {
  return useSWR<KnowledgeAtom[]>("/knowledge", (url: string) =>
    apiFetch<KnowledgeAtom[]>(url),
  );
}

export function useKnowledgeSearch(query: string) {
  return useSWR<KnowledgeAtom[]>(
    query ? `/knowledge/relevant?query=${encodeURIComponent(query)}` : null,
    (url: string) => apiFetch<KnowledgeAtom[]>(url),
  );
}
