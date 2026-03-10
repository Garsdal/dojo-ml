import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import type { Experiment } from "@/types";

export function useExperiments(taskId?: string) {
  const params = taskId ? `?task_id=${taskId}` : "";
  return useSWR<Experiment[]>(`/experiments${params}`, (url: string) =>
    apiFetch<Experiment[]>(url),
  );
}

export function useExperiment(id: string | undefined) {
  return useSWR<Experiment>(id ? `/experiments/${id}` : null, (url: string) =>
    apiFetch<Experiment>(url),
  );
}
