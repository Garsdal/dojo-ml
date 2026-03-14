import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import type { Domain, WorkspaceSource } from "@/types";

export function useDomains() {
  return useSWR<Domain[]>("/domains", (url: string) => apiFetch<Domain[]>(url));
}

export async function createDomain(data: {
  name: string;
  description?: string;
  prompt?: string;
  config?: Record<string, unknown>;
  workspace?: {
    source: WorkspaceSource;
    path?: string;
    git_url?: string | null;
    git_ref?: string | null;
  };
}): Promise<Domain> {
  return apiFetch<Domain>("/domains", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function deleteDomain(id: string): Promise<void> {
  await apiFetch(`/domains/${id}`, { method: "DELETE" });
}
