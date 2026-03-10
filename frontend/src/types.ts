export interface Task {
  id: string;
  prompt: string;
  status: "pending" | "running" | "completed" | "failed";
  summary: string | null;
  experiments: ExperimentSummary[];
  metrics: Record<string, number> | null;
}

export interface ExperimentSummary {
  id: string;
  state: string;
  metrics: Record<string, number> | null;
}

export interface Experiment {
  id: string;
  task_id: string;
  state: "pending" | "running" | "completed" | "failed" | "archived";
  config: Record<string, unknown>;
  metrics: Record<string, number> | null;
  error: string | null;
}

export interface KnowledgeAtom {
  id: string;
  context: string;
  claim: string;
  action: string;
  confidence: number;
  evidence_ids: string[];
}

export interface HealthStatus {
  status: "ok" | "error";
}

export interface AppConfig {
  api: { host: string; port: number };
  storage: { base_dir: string };
  llm: { provider: string; model: string };
  tracking: { enabled: boolean };
}

export interface AgentRun {
  id: string;
  task_id: string;
  prompt: string;
  status: "pending" | "running" | "completed" | "failed" | "stopped";
  events: AgentEvent[];
  started_at: string | null;
  completed_at: string | null;
  total_cost_usd: number | null;
  num_turns: number;
  error: string | null;
}

export interface AgentEvent {
  id: string;
  timestamp: string;
  event_type: string;
  data: Record<string, unknown>;
}

export interface ToolHint {
  name: string;
  description: string;
  source: string;
  code_template?: string;
}
