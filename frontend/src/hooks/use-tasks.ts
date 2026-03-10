import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import type { Task } from "@/types";

export function useTasks() {
  return useSWR<Task[]>("/tasks", (url: string) => apiFetch<Task[]>(url));
}

export function useTask(id: string | undefined) {
  return useSWR<Task>(id ? `/tasks/${id}` : null, (url: string) =>
    apiFetch<Task>(url),
  );
}

export async function createTask(prompt: string): Promise<Task> {
  return apiFetch<Task>("/tasks", {
    method: "POST",
    body: JSON.stringify({ prompt }),
  });
}
