import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import type { Domain, DomainTool } from "@/types";

export function useDomain(id: string | undefined) {
  return useSWR<Domain>(id ? `/domains/${id}` : null, (url: string) =>
    apiFetch<Domain>(url),
  );
}

export async function updateDomain(
  id: string,
  data: {
    name?: string;
    description?: string;
    prompt?: string;
    status?: string;
    config?: Record<string, unknown>;
  },
): Promise<Domain> {
  return apiFetch<Domain>(`/domains/${id}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export async function addDomainTool(
  domainId: string,
  tool: {
    name: string;
    description?: string;
    type?: string;
    example_usage?: string;
    parameters?: Record<string, unknown>;
    created_by?: string;
    executable?: boolean;
    code?: string;
    return_description?: string;
  },
): Promise<DomainTool> {
  return apiFetch<DomainTool>(`/domains/${domainId}/tools`, {
    method: "POST",
    body: JSON.stringify(tool),
  });
}

export async function removeDomainTool(
  domainId: string,
  toolId: string,
): Promise<void> {
  await apiFetch(`/domains/${domainId}/tools/${toolId}`, {
    method: "DELETE",
  });
}
