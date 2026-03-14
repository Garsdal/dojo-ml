# Frontend: Workspace & Code Traceability Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add frontend support for workspace environments and code traceability — workspace config in domain creation, workspace status display with setup action, executable tool tier display with collapsible code, workspace scan integration, and a tabbed Code view on experiment detail panels showing all code runs with expandable source.

**Architecture:** Approach B — proper SWR hook layer with targeted UI additions. Workspace config is an optional collapsible section in the domain creation form. Workspace status lives in the domain detail header. Executable tools are distinguished by badge + collapsible code block. Experiment detail panels gain a Config/Metrics/Code/Error tab strip with lazy-loaded code runs.

**Tech Stack:** React 19, TypeScript 5.9, SWR 2, Tailwind CSS 4, Radix UI (Tabs, Dialog), Lucide React, `react-syntax-highlighter` (already installed). No test framework — verification via `npm run build` (TypeScript + ESLint) and manual browser testing.

---

## Background

The backend now exposes three new capabilities not yet reflected in the frontend:

1. **Workspace** — `Domain` now has a `workspace` field (path, source, ready, python_path, git_url). Three new endpoints: `POST /domains/{id}/workspace/setup`, `GET /domains/{id}/workspace/status`, `POST /domains/{id}/workspace/scan`.
2. **Executable domain tools** — `DomainTool` now has `executable: bool`, `code: str`, `return_description: str`. Tools are either hint-only (text in system prompt) or callable MCP tools (tier 2).
3. **Code traceability** — `GET /experiments/{id}/code` returns a list of `CodeRun` objects. `GET /experiments/{id}/code/{run_number}` returns the full source code of a specific run.

---

## File Structure

### New files

| File | Responsibility |
|------|---------------|
| `frontend/src/hooks/use-workspace.ts` | `useWorkspaceStatus` SWR hook (available for future polling) + `setupWorkspace`, `scanWorkspace` API functions |
| `frontend/src/hooks/use-experiment-code.ts` | `useExperimentCode` (list runs) + `useExperimentCodeRun` (fetch source) |

### Modified files

| File | What changes |
|------|-------------|
| `frontend/src/types.ts` | Add `Workspace`, `WorkspaceSource`, `CodeRun`, `CodeRunDetail`; extend `DomainTool` (executable, code, return_description); extend `Domain` (workspace); extend `Experiment` (hypothesis) |
| `frontend/src/hooks/use-domain.ts` | Extend `addDomainTool` to accept `executable`, `code`, `return_description` |
| `frontend/src/hooks/use-domains.ts` | Extend `createDomain` to accept optional `workspace` field |
| `frontend/src/components/domains/domain-form.tsx` | Add optional workspace section: source radio + conditional path/git fields |
| `frontend/src/pages/domain-overview.tsx` | Pass workspace from form data to the `POST /domains` call |
| `frontend/src/pages/domain-detail.tsx` | Add workspace status row beneath stat strip; `SetupWorkspaceButton` local component; pass `hasWorkspace` to `ToolsSection` |
| `frontend/src/components/domains/tools-section.tsx` | Add `hasWorkspace` prop; executable badge + collapsible code on tool cards; new fields in add-tool form; `ScanWorkspaceButton` component (only shown when workspace configured) |
| `frontend/src/components/domains/experiment-detail.tsx` | Replace flat layout with Tabs (Config / Metrics / Code / Error); lazy-load code runs on Code tab |

---

## Chunk 1: Types and Hooks

### Task 1: Update TypeScript types

**Files:**
- Modify: `frontend/src/types.ts`

- [ ] **Step 1: Replace the Domain and DomainTool blocks in `types.ts`**

The full updated `types.ts`:

```typescript
// --- Domain ---

export type DomainStatus =
  | "draft"
  | "active"
  | "paused"
  | "completed"
  | "archived";

export type WorkspaceSource = "local" | "git" | "empty";

export interface Workspace {
  path: string;
  source: WorkspaceSource;
  ready: boolean;
  python_path: string | null;
  git_url: string | null;
}

export interface DomainTool {
  id: string;
  name: string;
  description: string;
  type: string;
  example_usage: string;
  parameters: Record<string, unknown>;
  created_by: string;
  created_at: string;
  executable: boolean;
  code: string;
  return_description: string;
}

export interface Domain {
  id: string;
  name: string;
  description: string;
  prompt: string;
  status: DomainStatus;
  config: Record<string, unknown>;
  metadata: Record<string, unknown>;
  experiment_ids: string[];
  tools: DomainTool[];
  workspace: Workspace | null;
  created_at: string;
  updated_at: string;
}

// --- Experiments ---

export interface Experiment {
  id: string;
  domain_id: string;
  hypothesis: string | null;
  state: "pending" | "running" | "completed" | "failed" | "archived";
  config: Record<string, unknown>;
  metrics: Record<string, number> | null;
  error: string | null;
}

export interface CodeRun {
  run_number: number;
  code_path: string;
  description: string;
  exit_code: number;
  duration_ms: number;
  timestamp: string;
}

export interface CodeRunDetail extends CodeRun {
  code: string;
}

// --- Knowledge ---

export interface KnowledgeAtom {
  id: string;
  context: string;
  claim: string;
  action: string;
  confidence: number;
  evidence_ids: string[];
  version: number;
  supersedes: string | null;
}

export interface KnowledgeLink {
  id: string;
  atom_id: string;
  experiment_id: string;
  domain_id: string;
  link_type: string;
  related_atom_id: string | null;
  created_at: string;
}

export interface KnowledgeDetail {
  atom: KnowledgeAtom;
  links: KnowledgeLink[];
}

export interface LinkingResult {
  atom_id: string;
  action: "created";
  version: number;
  confidence: number;
  related_to: string[] | null;
}

// --- Metrics ---

export interface MetricPoint {
  experiment_id: string;
  timestamp: string;
  metrics: Record<string, number>;
}

// --- Agent ---

export interface AgentRun {
  id: string;
  domain_id: string;
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

// --- Health / Config ---

export interface HealthStatus {
  status: "ok" | "error";
}

export interface AppConfig {
  api: { host: string; port: number };
  storage: { base_dir: string };
  llm: { provider: string; model: string };
  tracking: { enabled: boolean };
}
```

- [ ] **Step 2: Verify types compile**

```bash
cd frontend && npm run build
```

Expected: TypeScript compilation success. If there are downstream errors from components consuming the old type shapes (e.g., accessing `tool.executable` that didn't exist), those will be fixed in subsequent tasks.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types.ts
git commit -m "feat(frontend): add Workspace, CodeRun types; extend DomainTool and Experiment"
```

---

### Task 2: Create `use-workspace.ts` hook

**Files:**
- Create: `frontend/src/hooks/use-workspace.ts`

- [ ] **Step 1: Create the file**

```typescript
import useSWR from "swr";
import { apiFetch } from "@/lib/api";

export interface WorkspaceStatus {
  configured: boolean;
  ready?: boolean;
  path?: string;
  python_path?: string | null;
  source?: string;
  error?: string;
}

export interface WorkspaceScanSuggestion {
  name: string;
  description: string;
  type: string;
  code: string;
  example_usage: string;
  parameters: Record<string, unknown>;
}

export interface WorkspaceScanResult {
  summary: {
    data_files: string[];
    python_modules: string[];
    has_requirements: boolean;
    has_pyproject: boolean;
  };
  suggestions: WorkspaceScanSuggestion[];
}

/**
 * Fetch workspace status for a domain.
 * Note: The domain detail page reads workspace.ready from the existing useDomain
 * response, so this hook is not consumed there. It is exported here for future use
 * (e.g. polling after triggering a long-running setup).
 */
export function useWorkspaceStatus(domainId: string | undefined) {
  return useSWR<WorkspaceStatus>(
    domainId ? `/domains/${domainId}/workspace/status` : null,
    (url: string) => apiFetch<WorkspaceStatus>(url),
  );
}

export async function setupWorkspace(
  domainId: string,
): Promise<{ status: string; path: string; python_path: string | null }> {
  return apiFetch(`/domains/${domainId}/workspace/setup`, { method: "POST" });
}

export async function scanWorkspace(domainId: string): Promise<WorkspaceScanResult> {
  return apiFetch(`/domains/${domainId}/workspace/scan`, { method: "POST" });
}
```

- [ ] **Step 2: Verify compilation**

```bash
cd frontend && npm run build
```

Expected: no new errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/hooks/use-workspace.ts
git commit -m "feat(frontend): add useWorkspaceStatus hook and workspace API functions"
```

---

### Task 3: Create `use-experiment-code.ts` hook

**Files:**
- Create: `frontend/src/hooks/use-experiment-code.ts`

- [ ] **Step 1: Create the file**

```typescript
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import type { CodeRun, CodeRunDetail } from "@/types";

/**
 * Fetch all code runs for an experiment.
 * Pass `enabled=false` to skip fetching (e.g. when the Code tab is not active).
 */
export function useExperimentCode(
  experimentId: string | undefined,
  enabled: boolean,
) {
  return useSWR<CodeRun[]>(
    experimentId && enabled ? `/experiments/${experimentId}/code` : null,
    (url: string) => apiFetch<CodeRun[]>(url),
  );
}

/**
 * Fetch the source code + metadata for a specific code run.
 * Pass `runNumber=null` to skip fetching (e.g. when no run is expanded).
 */
export function useExperimentCodeRun(
  experimentId: string | undefined,
  runNumber: number | null,
) {
  return useSWR<CodeRunDetail>(
    experimentId && runNumber !== null
      ? `/experiments/${experimentId}/code/${runNumber}`
      : null,
    (url: string) => apiFetch<CodeRunDetail>(url),
  );
}
```

- [ ] **Step 2: Verify compilation**

```bash
cd frontend && npm run build
```

Expected: no new errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/hooks/use-experiment-code.ts
git commit -m "feat(frontend): add useExperimentCode and useExperimentCodeRun hooks"
```

---

### Task 4: Extend `createDomain` in `use-domains.ts` and `addDomainTool` in `use-domain.ts`

**Files:**
- Modify: `frontend/src/hooks/use-domains.ts:9-19`
- Modify: `frontend/src/hooks/use-domain.ts:27-44`

**4a: Extend `createDomain` in `use-domains.ts`**

The existing `createDomain` doesn't accept `workspace`. Extend it so `domain-overview.tsx` can pass workspace through without bypassing the hook layer.

- [ ] **Step 1: Replace `createDomain` in `use-domains.ts`**

```typescript
import type { Domain, WorkspaceSource } from "@/types";

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
```

**4b: Extend `addDomainTool` in `use-domain.ts`**

The existing `addDomainTool` doesn't accept the new `executable`, `code`, `return_description` fields. Update its parameter type.

- [ ] **Step 2: Update the function signature and body**

Replace the existing `addDomainTool` function with:

```typescript
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
```

- [ ] **Step 3: Verify compilation**

```bash
cd frontend && npm run build
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/hooks/use-domains.ts frontend/src/hooks/use-domain.ts
git commit -m "feat(frontend): extend createDomain and addDomainTool with workspace/executable fields"
```

---

## Chunk 2: Domain Creation Form

### Task 5: Add workspace section to domain creation form

**Files:**
- Modify: `frontend/src/components/domains/domain-form.tsx`
- Modify: `frontend/src/pages/domain-overview.tsx`

The workspace section is hidden by default. Clicking "▸ Workspace Environment" expands a panel with source radio buttons and conditional fields. The form's `onSubmit` callback is updated to accept an optional workspace payload.

- [ ] **Step 1: Replace `domain-form.tsx` with the updated version**

```tsx
import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Plus } from "lucide-react";
import type { Domain, WorkspaceSource } from "@/types";

interface WorkspaceFormData {
  source: WorkspaceSource;
  path: string;
  git_url: string;
  git_ref: string;
}

interface DomainFormProps {
  onSubmit: (data: {
    name: string;
    description: string;
    prompt: string;
    workspace?: WorkspaceFormData;
  }) => Promise<Domain | void>;
  isLoading?: boolean;
}

export function DomainForm({ onSubmit, isLoading }: DomainFormProps) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [prompt, setPrompt] = useState("");
  const [showPrompt, setShowPrompt] = useState(false);

  // Workspace state
  const [showWorkspace, setShowWorkspace] = useState(false);
  const [wsSource, setWsSource] = useState<WorkspaceSource>("local");
  const [wsPath, setWsPath] = useState("");
  const [wsGitUrl, setWsGitUrl] = useState("");
  const [wsGitRef, setWsGitRef] = useState("");

  const reset = () => {
    setName("");
    setDescription("");
    setPrompt("");
    setShowPrompt(false);
    setShowWorkspace(false);
    setWsSource("local");
    setWsPath("");
    setWsGitUrl("");
    setWsGitRef("");
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;

    const workspace: WorkspaceFormData | undefined = showWorkspace
      ? { source: wsSource, path: wsPath, git_url: wsGitUrl, git_ref: wsGitRef }
      : undefined;

    await onSubmit({ name: name.trim(), description, prompt, workspace });
    reset();
    setOpen(false);
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <Plus className="h-4 w-4" />
          New Domain
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="font-heading font-bold text-blackberry">
            Create Research Domain
          </DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4 mt-2">
          {/* Name */}
          <div>
            <label className="text-sm font-medium text-blackberry mb-1.5 block">
              Name <span className="text-danger">*</span>
            </label>
            <Input
              placeholder="e.g. Sentiment Analysis"
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={80}
            />
            <span className="text-xs text-grey mt-1 block text-right">
              {name.length}/80
            </span>
          </div>

          {/* Description */}
          <div>
            <label className="text-sm font-medium text-blackberry mb-1.5 block">
              Description
            </label>
            <Textarea
              placeholder="Brief description of this research domain"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="min-h-[80px]"
            />
          </div>

          {/* System Prompt (advanced, collapsible) */}
          <div>
            <button
              type="button"
              onClick={() => setShowPrompt(!showPrompt)}
              className="text-sm text-grey hover:text-blackberry transition-colors flex items-center gap-1"
            >
              <span>{showPrompt ? "▾" : "▸"}</span>
              Advanced: System Prompt
            </button>
            {showPrompt && (
              <Textarea
                className="mt-2 min-h-[100px]"
                placeholder="Steering prompt for the AI agent (optional)"
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
              />
            )}
          </div>

          {/* Workspace (collapsible) */}
          <div>
            <button
              type="button"
              onClick={() => setShowWorkspace(!showWorkspace)}
              className="text-sm text-grey hover:text-blackberry transition-colors flex items-center gap-1"
            >
              <span>{showWorkspace ? "▾" : "▸"}</span>
              Workspace Environment
            </button>
            {showWorkspace && (
              <div className="mt-3 space-y-3 rounded-xl border border-soft-fawn/20 p-4">
                {/* Source radio */}
                <div>
                  <label className="text-xs font-medium text-grey mb-2 block">
                    Source
                  </label>
                  <div className="flex gap-4">
                    {(["local", "git", "empty"] as const).map((src) => (
                      <label
                        key={src}
                        className="flex items-center gap-1.5 cursor-pointer"
                      >
                        <input
                          type="radio"
                          name="wsSource"
                          value={src}
                          checked={wsSource === src}
                          onChange={() => setWsSource(src)}
                          className="accent-blackberry"
                        />
                        <span className="text-sm text-blackberry">{src}</span>
                      </label>
                    ))}
                  </div>
                </div>

                {/* Local / Empty: path input */}
                {wsSource !== "git" && (
                  <div>
                    <label className="text-xs font-medium text-grey mb-1 block">
                      {wsSource === "empty"
                        ? "Directory path (will be created)"
                        : "Local path"}
                    </label>
                    <Input
                      placeholder="/Users/me/projects/my-ml-project"
                      value={wsPath}
                      onChange={(e) => setWsPath(e.target.value)}
                      className="font-mono text-xs"
                    />
                  </div>
                )}

                {/* Git: URL + ref */}
                {wsSource === "git" && (
                  <>
                    <div>
                      <label className="text-xs font-medium text-grey mb-1 block">
                        Git URL
                      </label>
                      <Input
                        placeholder="https://github.com/user/repo.git"
                        value={wsGitUrl}
                        onChange={(e) => setWsGitUrl(e.target.value)}
                        className="font-mono text-xs"
                      />
                    </div>
                    <div>
                      <label className="text-xs font-medium text-grey mb-1 block">
                        Branch / Tag / Commit{" "}
                        <span className="font-normal">(optional, default: main)</span>
                      </label>
                      <Input
                        placeholder="main"
                        value={wsGitRef}
                        onChange={(e) => setWsGitRef(e.target.value)}
                        className="font-mono text-xs"
                      />
                    </div>
                  </>
                )}
              </div>
            )}
          </div>

          <div className="flex gap-2 justify-end pt-2">
            <Button
              type="button"
              variant="ghost"
              onClick={() => { reset(); setOpen(false); }}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={!name.trim() || isLoading}>
              {isLoading ? "Creating…" : "Create Domain"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 2: Update the `onSubmit` handler in `domain-overview.tsx`**

The existing `handleCreate` in `domain-overview.tsx` calls `createDomain(data)`. Update its type signature and body to forward `workspace`:

```tsx
// In DomainOverviewPage:
const handleCreate = async (data: {
  name: string;
  description: string;
  prompt: string;
  workspace?: WorkspaceFormData;
}) => {
  setIsCreating(true);
  try {
    await createDomain({
      name: data.name,
      description: data.description,
      prompt: data.prompt,
      workspace: data.workspace
        ? {
            source: data.workspace.source,
            path: data.workspace.path || undefined,
            git_url: data.workspace.git_url || null,
            git_ref: data.workspace.git_ref || null,
          }
        : undefined,
    });
    await mutate();
  } finally {
    setIsCreating(false);
  }
};
```

Add `import type { WorkspaceFormData } from "@/components/domains/domain-form"` to `domain-overview.tsx`, and export `WorkspaceFormData` from `domain-form.tsx` (change `interface WorkspaceFormData` to `export interface WorkspaceFormData`).

- [ ] **Step 3: Verify compilation**

```bash
cd frontend && npm run build
```

- [ ] **Step 4: Manual test** — open the app, click "New Domain", expand "Workspace Environment", verify source radio switches correctly, cancel without errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/domains/domain-form.tsx frontend/src/pages/domain-overview.tsx
git commit -m "feat(frontend): add workspace section to domain creation form"
```

---

## Chunk 3: Domain Detail — Workspace Status

### Task 6: Workspace status row on domain detail page

**Files:**
- Modify: `frontend/src/pages/domain-detail.tsx`

The `domain.workspace` is already in the existing `useDomain` response (the API returns it). No new data fetching is needed for display — only the "Set up" action calls the API.

- [ ] **Step 1: Add imports to `domain-detail.tsx`**

```tsx
import { CheckCircle2, AlertCircle } from "lucide-react";
import { setupWorkspace } from "@/hooks/use-workspace";
```

- [ ] **Step 2: Add workspace status row between the stat strip and the tab content**

After the closing `</div>` of the stat strip and before `<Tabs ...>`, insert:

```tsx
{/* Workspace status row */}
{domain.workspace && (
  <div className="flex items-center gap-3 flex-wrap px-1">
    <span className="text-xs text-grey font-medium">Workspace</span>
    {domain.workspace.ready ? (
      <span className="inline-flex items-center gap-1 bg-muted-teal/20 text-muted-teal rounded-full text-xs px-2.5 py-0.5 font-medium">
        <CheckCircle2 className="h-3 w-3" />
        ready
      </span>
    ) : (
      <span className="inline-flex items-center gap-1 bg-wheat/40 text-soft-fawn rounded-full text-xs px-2.5 py-0.5 font-medium">
        <AlertCircle className="h-3 w-3" />
        not ready
      </span>
    )}
    <span className="font-mono text-xs text-grey truncate max-w-[280px]">
      {domain.workspace.path}
    </span>
    {!domain.workspace.ready && (
      <SetupWorkspaceButton domainId={domain.id} onDone={() => mutate()} />
    )}
  </div>
)}
```

- [ ] **Step 3: Add `SetupWorkspaceButton` as a local component at the bottom of `domain-detail.tsx`** (before the `export default`)

```tsx
function SetupWorkspaceButton({
  domainId,
  onDone,
}: {
  domainId: string;
  onDone: () => void;
}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSetup = async () => {
    setLoading(true);
    setError(null);
    try {
      await setupWorkspace(domainId);
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Setup failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex items-center gap-2">
      <Button size="sm" variant="outline" onClick={handleSetup} disabled={loading}>
        {loading ? "Setting up…" : "Set up"}
      </Button>
      {error && <span className="text-xs text-danger">{error}</span>}
    </div>
  );
}
```

- [ ] **Step 4: Verify compilation**

```bash
cd frontend && npm run build
```

- [ ] **Step 5: Manual test** — navigate to a domain that has a workspace. Verify the status row appears. For a domain without workspace, verify nothing appears.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/domain-detail.tsx
git commit -m "feat(frontend): add workspace status indicator and setup action to domain detail"
```

---

## Chunk 4: Tools Section

### Task 7: Update tools section — executable display + scan

**Files:**
- Modify: `frontend/src/components/domains/tools-section.tsx`

Three changes in one task: (a) executable badge + collapsible code on tool cards, (b) new fields in the Add Tool form, (c) `ScanWorkspaceButton` component.

- [ ] **Step 1: Add state for code expand and new form fields**

Add to `ToolsSection` component state:

```tsx
const [expandedToolId, setExpandedToolId] = useState<string | null>(null);
const [isExecutable, setIsExecutable] = useState(false);
const [code, setCode] = useState("");
const [returnDescription, setReturnDescription] = useState("");
```

Reset them in `handleAdd` after submit:

```tsx
setIsExecutable(false);
setCode("");
setReturnDescription("");
```

Pass new fields in `handleAdd`:

```tsx
await addDomainTool(domainId, {
  name: name.trim(),
  description,
  example_usage: exampleUsage,
  type: "custom",
  created_by: "human",
  executable: isExecutable,
  code,
  return_description: returnDescription,
});
```

- [ ] **Step 2: Update tool card to show executable badge and collapsible code**

In the tool card's badge row (where `tool.type` and `tool.created_by` badges live), add:

```tsx
{tool.executable && (
  <span className="bg-muted-teal/20 text-muted-teal rounded-full text-xs px-2 py-0.5 font-medium">
    executable
  </span>
)}
```

Below `tool.description`, add the expand toggle and code block:

```tsx
{tool.executable && tool.code && (
  <>
    <button
      type="button"
      className="text-xs text-grey hover:text-blackberry transition-colors flex items-center gap-1 mt-1"
      onClick={(e) => {
        e.stopPropagation();
        setExpandedToolId(expandedToolId === tool.id ? null : tool.id);
      }}
    >
      <span>{expandedToolId === tool.id ? "▾" : "▸"}</span>
      {expandedToolId === tool.id ? "Hide code" : "View code"}
    </button>
    {expandedToolId === tool.id && (
      <pre className="mt-2 text-[10px] font-mono bg-blackberry/5 rounded-lg text-blackberry p-3 max-h-[200px] overflow-auto whitespace-pre-wrap">
        {tool.code}
      </pre>
    )}
  </>
)}
{tool.return_description && (
  <p className="text-[10px] text-grey mt-1">
    Returns: {tool.return_description}
  </p>
)}
```

- [ ] **Step 3: Update the Add Tool form with executable fields**

After the `example_usage` Textarea and before the action buttons, insert:

```tsx
{/* Executable toggle */}
<div className="flex items-center gap-2">
  <input
    type="checkbox"
    id="executable-toggle"
    checked={isExecutable}
    onChange={(e) => setIsExecutable(e.target.checked)}
    className="accent-blackberry"
  />
  <label
    htmlFor="executable-toggle"
    className="text-sm text-blackberry cursor-pointer"
  >
    Executable (callable MCP tool)
  </label>
</div>

{isExecutable && (
  <>
    <Textarea
      placeholder="Python function body — code that runs in the workspace"
      value={code}
      onChange={(e) => setCode(e.target.value)}
      className="min-h-[120px] resize-y font-mono text-xs"
    />
    <Input
      placeholder="Return description (e.g. Dict with shape, columns, head)"
      value={returnDescription}
      onChange={(e) => setReturnDescription(e.target.value)}
    />
  </>
)}
```

- [ ] **Step 4: Add `ScanWorkspaceButton` component**

First, add this import to the **top** of `tools-section.tsx` alongside the existing imports:

```tsx
import { scanWorkspace, type WorkspaceScanSuggestion } from "@/hooks/use-workspace";
```

Then add the component definition at the bottom of `tools-section.tsx` (after `GenerateToolsButton`):

```tsx

function ScanWorkspaceButton({
  domainId,
  onMutate,
}: {
  domainId: string;
  onMutate: () => void;
}) {
  const [isScanning, setIsScanning] = useState(false);
  const [suggestions, setSuggestions] = useState<WorkspaceScanSuggestion[]>([]);
  const [isAdding, setIsAdding] = useState<string | null>(null);

  const handleScan = async () => {
    setIsScanning(true);
    try {
      const result = await scanWorkspace(domainId);
      setSuggestions(result.suggestions);
    } catch {
      setSuggestions([]);
    } finally {
      setIsScanning(false);
    }
  };

  const handleApprove = async (s: WorkspaceScanSuggestion) => {
    setIsAdding(s.name);
    try {
      await addDomainTool(domainId, {
        name: s.name,
        description: s.description,
        type: s.type,
        example_usage: s.example_usage,
        parameters: s.parameters,
        code: s.code,
        executable: !!s.code,
        created_by: "ai",
      });
      setSuggestions((prev) => prev.filter((x) => x.name !== s.name));
      onMutate();
    } finally {
      setIsAdding(null);
    }
  };

  if (suggestions.length > 0) {
    return (
      <div className="space-y-3 w-full">
        <div className="flex items-center justify-between">
          <span className="text-xs font-medium text-grey">
            Workspace Scan Suggestions (review & approve)
          </span>
          <Button
            variant="ghost"
            size="sm"
            className="text-xs"
            onClick={() => setSuggestions([])}
          >
            Dismiss
          </Button>
        </div>
        {suggestions.map((s) => (
          <div
            key={s.name}
            className="rounded-xl border border-dashed border-muted-teal/40 bg-muted-teal/5 p-4 space-y-2"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="font-mono font-bold text-blackberry text-sm">
                  {s.name}
                </span>
                <span className="bg-wheat/20 text-blackberry rounded-full text-xs px-2 py-0.5">
                  {s.type}
                </span>
                {s.code && (
                  <span className="bg-muted-teal/20 text-muted-teal rounded-full text-xs px-2 py-0.5">
                    executable
                  </span>
                )}
              </div>
              <Button
                size="sm"
                variant="outline"
                onClick={() => handleApprove(s)}
                disabled={isAdding === s.name}
              >
                {isAdding === s.name ? "Adding…" : "Approve"}
              </Button>
            </div>
            <p className="text-grey text-xs">{s.description}</p>
            {s.code && (
              <pre className="text-[10px] font-mono bg-blackberry/5 rounded-lg text-blackberry p-2 max-h-[120px] overflow-auto whitespace-pre-wrap">
                {s.code}
              </pre>
            )}
          </div>
        ))}
      </div>
    );
  }

  return (
    <Button variant="outline" size="sm" onClick={handleScan} disabled={isScanning}>
      {isScanning ? "Scanning…" : "🔍 Scan Workspace"}
    </Button>
  );
}
```

- [ ] **Step 5: Add `hasWorkspace` to `ToolsSectionProps` and wire up `ScanWorkspaceButton`**

Update `ToolsSectionProps` to accept `hasWorkspace`:

```tsx
interface ToolsSectionProps {
  domainId: string;
  tools: DomainTool[];
  hasWorkspace: boolean;
  onMutate: () => void;
}
```

Update the buttons row to only show the scan button when a workspace is configured:

```tsx
<div className="flex gap-2 flex-wrap">
  <Button variant="outline" size="sm" onClick={() => setShowForm(true)}>
    + Add Tool
  </Button>
  <GenerateToolsButton domainId={domainId} onMutate={onMutate} />
  {hasWorkspace && (
    <ScanWorkspaceButton domainId={domainId} onMutate={onMutate} />
  )}
</div>
```

Update the call site in `domain-detail.tsx` (the `<ToolsSection>` usage in the Tools tab) to pass `hasWorkspace={domain.workspace !== null}`.

- [ ] **Step 6: Verify compilation**

```bash
cd frontend && npm run build
```

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/domains/tools-section.tsx frontend/src/hooks/use-domain.ts
git commit -m "feat(frontend): executable tool display, collapsible code, workspace scan in tools section"
```

---

## Chunk 5: Experiment Detail Tabs

### Task 8: Replace flat experiment detail panel with tabbed layout

**Files:**
- Modify: `frontend/src/components/domains/experiment-detail.tsx`

The experiment detail panel (the inline expand in `ExperimentsSection`) currently shows Config, Metrics, and Error as flat sections. Replace this with a tab strip: **Config | Metrics | Code | Error**.

- The **Code tab** uses `useExperimentCode` with `enabled = activeTab === "code"` — no fetching until the tab is clicked.
- Expanding a specific code run fetches `/experiments/{id}/code/{run_number}` via `useExperimentCodeRun`.
- The **Error tab** is only rendered when `experiment.error` is non-null.

- [ ] **Step 1: Replace `experiment-detail.tsx` with the tabbed version**

```tsx
import { useState } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { StateBadge } from "@/components/state-badge";
import {
  useExperimentCode,
  useExperimentCodeRun,
} from "@/hooks/use-experiment-code";
import type { Experiment } from "@/types";

interface ExperimentDetailPanelProps {
  experiment: Experiment;
}

export function ExperimentDetailPanel({ experiment }: ExperimentDetailPanelProps) {
  const [activeTab, setActiveTab] = useState("config");
  const [expandedRun, setExpandedRun] = useState<number | null>(null);

  const codeEnabled = activeTab === "code";
  const { data: codeRuns, isLoading: codeLoading } = useExperimentCode(
    experiment.id,
    codeEnabled,
  );
  const { data: codeRunDetail } = useExperimentCodeRun(
    codeEnabled ? experiment.id : undefined,
    expandedRun,
  );

  const hasMetrics =
    experiment.metrics && Object.keys(experiment.metrics).length > 0;
  const hasConfig = Object.keys(experiment.config).length > 0;

  const handleTabChange = (tab: string) => {
    setActiveTab(tab);
    setExpandedRun(null);
  };

  return (
    <div className="bg-wheat/5 border-t border-soft-fawn/20 px-4 py-4">
      {/* Summary row */}
      <div className="flex items-center gap-3 flex-wrap mb-3">
        <StateBadge state={experiment.state} />
        <span className="font-mono text-xs text-grey">{experiment.id}</span>
        {experiment.hypothesis && (
          <span className="text-xs text-blackberry italic truncate max-w-[400px]">
            "{experiment.hypothesis}"
          </span>
        )}
      </div>

      <Tabs value={activeTab} onValueChange={handleTabChange}>
        <TabsList className="mb-3 h-7">
          <TabsTrigger value="config" className="text-xs h-6 px-2.5">
            Config
          </TabsTrigger>
          <TabsTrigger value="metrics" className="text-xs h-6 px-2.5">
            Metrics
          </TabsTrigger>
          <TabsTrigger value="code" className="text-xs h-6 px-2.5">
            Code
          </TabsTrigger>
          {experiment.error && (
            <TabsTrigger
              value="error"
              className="text-xs h-6 px-2.5 text-danger data-[state=active]:text-danger"
            >
              Error
            </TabsTrigger>
          )}
        </TabsList>

        {/* Config tab */}
        <TabsContent value="config">
          {hasConfig ? (
            <div className="space-y-1">
              {Object.entries(experiment.config).map(([k, v]) => (
                <div key={k} className="flex items-start gap-2">
                  <span className="text-xs text-grey shrink-0 pt-0.5">{k}:</span>
                  <span className="text-xs text-blackberry font-mono break-all">
                    {String(v).slice(0, 120)}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-grey">No config recorded.</p>
          )}
        </TabsContent>

        {/* Metrics tab */}
        <TabsContent value="metrics">
          {hasMetrics ? (
            <div className="space-y-1 max-w-xs">
              {Object.entries(experiment.metrics!).map(([k, v]) => (
                <div key={k} className="flex items-center justify-between">
                  <span className="text-xs text-grey">{k}</span>
                  <span className="text-xs font-semibold text-blackberry font-mono">
                    {typeof v === "number" ? v.toFixed(4) : String(v)}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-grey">No metrics recorded.</p>
          )}
        </TabsContent>

        {/* Code tab */}
        <TabsContent value="code">
          {codeLoading && (
            <p className="text-xs text-grey">Loading code runs…</p>
          )}
          {!codeLoading && (!codeRuns || codeRuns.length === 0) && (
            <p className="text-xs text-grey">
              No code runs recorded for this experiment.
            </p>
          )}
          {codeRuns && codeRuns.length > 0 && (
            <div className="space-y-1.5">
              {codeRuns.map((run) => {
                const isExpanded = expandedRun === run.run_number;
                const isLoadingCode =
                  isExpanded &&
                  codeRunDetail?.run_number !== run.run_number;

                return (
                  <div
                    key={run.run_number}
                    className="rounded-lg border border-soft-fawn/20 overflow-hidden"
                  >
                    {/* Run header row */}
                    <button
                      type="button"
                      className="w-full flex items-center gap-3 px-3 py-2 text-left hover:bg-wheat/10 transition-colors"
                      onClick={() =>
                        setExpandedRun(isExpanded ? null : run.run_number)
                      }
                    >
                      <span className="text-xs font-mono text-grey shrink-0 w-6">
                        #{run.run_number}
                      </span>
                      <span className="text-xs text-blackberry flex-1 truncate">
                        {run.description || "—"}
                      </span>
                      <span
                        className={`text-xs font-mono px-1.5 py-0.5 rounded shrink-0 ${
                          run.exit_code === 0
                            ? "bg-muted-teal/15 text-muted-teal"
                            : "bg-danger/10 text-danger"
                        }`}
                      >
                        exit {run.exit_code}
                      </span>
                      <span className="text-xs text-grey shrink-0">
                        {(run.duration_ms / 1000).toFixed(1)}s
                      </span>
                      <span className="text-grey shrink-0 text-xs">
                        {isExpanded ? "▾" : "▸"}
                      </span>
                    </button>

                    {/* Code viewer */}
                    {isExpanded && (
                      <div className="border-t border-soft-fawn/20">
                        {isLoadingCode ? (
                          <p className="text-xs text-grey p-3">Loading…</p>
                        ) : (
                          <pre className="text-[10px] font-mono bg-blackberry/5 text-blackberry p-3 max-h-[320px] overflow-auto whitespace-pre-wrap leading-relaxed">
                            {codeRunDetail?.code ?? ""}
                          </pre>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </TabsContent>

        {/* Error tab */}
        {experiment.error && (
          <TabsContent value="error">
            <pre className="text-xs font-mono bg-danger/10 text-danger rounded-lg p-3 overflow-auto max-h-40 whitespace-pre-wrap">
              {experiment.error}
            </pre>
          </TabsContent>
        )}
      </Tabs>
    </div>
  );
}
```

- [ ] **Step 2: Verify compilation**

```bash
cd frontend && npm run build
```

Expected: clean build. If there are Tabs import issues, check that `@radix-ui/react-tabs` is installed (it is — confirmed in `package.json`).

- [ ] **Step 3: Manual test** — expand an experiment row. Verify the four tabs appear. Click Code tab and verify it loads runs (or shows "No code runs"). Expand a code run and verify source code appears.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/domains/experiment-detail.tsx frontend/src/hooks/use-experiment-code.ts
git commit -m "feat(frontend): tabbed experiment detail panel with Code tab and lazy-loaded code runs"
```

---

## Summary

| Task | Files | Done when |
|------|-------|-----------|
| 1: Types | `types.ts` | `npm run build` passes |
| 2: Workspace hook | `use-workspace.ts` | `npm run build` passes |
| 3: Code hooks | `use-experiment-code.ts` | `npm run build` passes |
| 4: `addDomainTool` extension | `use-domain.ts` | `npm run build` passes |
| 5: Domain form workspace section | `domain-form.tsx`, `domain-overview.tsx` | Create domain with workspace via UI |
| 6: Workspace status indicator | `domain-detail.tsx` | Domain with workspace shows status + "Set up" button |
| 7: Executable tools + scan | `tools-section.tsx` | Tools show executable badge; scan button surfaces suggestions |
| 8: Experiment code tab | `experiment-detail.tsx` | Expanding experiment shows Config/Metrics/Code/Error tabs |

### Key API endpoints consumed

| Endpoint | Used in |
|----------|---------|
| `POST /domains` with `workspace` body | `domain-overview.tsx` (via form) |
| `POST /domains/{id}/workspace/setup` | `SetupWorkspaceButton` in `domain-detail.tsx` |
| `POST /domains/{id}/workspace/scan` | `ScanWorkspaceButton` in `tools-section.tsx` |
| `GET /experiments/{id}/code` | `useExperimentCode` hook |
| `GET /experiments/{id}/code/{n}` | `useExperimentCodeRun` hook |
