# AgentML Frontend Implementation Plan

> A React frontend for the AgentML experiment orchestration platform.
> Styled with shadcn/ui in a muted dark/grey/black/white palette.
> Launched alongside the backend via `agentml start`.

---

## 1. Overview

### Goal

Add a lightweight React dashboard that surfaces the full AgentML API:

| API Endpoint | Purpose | Frontend View |
|---|---|---|
| `GET /health` | Server heartbeat | Status indicator in header |
| `POST /tasks` | Create a task | Task submission form |
| `GET /tasks` | List tasks | Task list table |
| `GET /tasks/{id}` | Task detail | Task detail panel |
| `GET /experiments` | List experiments | Experiments table |
| `GET /experiments/{id}` | Experiment detail | Experiment detail panel |
| `GET /knowledge` | List knowledge atoms | Knowledge list |
| `GET /knowledge/relevant?query=` | Search knowledge | Knowledge search |

### Design Principles

- **Muted dark theme** — black/grey/white palette, no bright accent colors
- **Rounded borders** — `rounded-lg` or `rounded-xl` on all cards/panels
- **Minimal** — clean spacing, no visual clutter
- **shadcn/ui** — built on Radix primitives + Tailwind CSS
- **Single-page app** — React Router with 4 top-level routes

---

## 2. Tech Stack

| Layer | Tool | Reason |
|---|---|---|
| Framework | React 19 + TypeScript | Industry standard, fast DX |
| Build tool | Vite | Fast dev server, quick builds |
| Styling | Tailwind CSS 4 | shadcn/ui dependency |
| Components | shadcn/ui | Accessible, themeable, copy-paste components |
| Routing | React Router v7 | Standard client-side routing |
| HTTP client | Native `fetch` + `swr` | Lightweight data fetching with caching and revalidation |
| Package manager | npm | As specified |
| Dev server port | `5173` (Vite default) | Avoids conflict with backend on `8000` |

---

## 3. Project Structure

```
frontend/                          # lives at repo root alongside src/
├── index.html
├── package.json
├── tsconfig.json
├── tsconfig.app.json
├── tsconfig.node.json
├── vite.config.ts
├── tailwind.config.ts             # shadcn dark theme
├── components.json                # shadcn config
├── postcss.config.js
├── public/
│   └── favicon.svg
└── src/
    ├── main.tsx                   # React entry
    ├── App.tsx                    # Router + layout shell
    ├── index.css                  # Tailwind directives + shadcn vars
    │
    ├── lib/
    │   ├── api.ts                 # API client (fetch wrappers)
    │   └── utils.ts               # shadcn cn() helper
    │
    ├── hooks/
    │   ├── use-tasks.ts           # SWR hooks for /tasks
    │   ├── use-experiments.ts     # SWR hooks for /experiments
    │   ├── use-knowledge.ts       # SWR hooks for /knowledge
    │   └── use-health.ts          # SWR hook for /health
    │
    ├── components/
    │   ├── ui/                    # shadcn generated components
    │   │   ├── button.tsx
    │   │   ├── card.tsx
    │   │   ├── input.tsx
    │   │   ├── badge.tsx
    │   │   ├── table.tsx
    │   │   ├── tabs.tsx
    │   │   ├── dialog.tsx
    │   │   ├── textarea.tsx
    │   │   ├── separator.tsx
    │   │   └── skeleton.tsx
    │   │
    │   ├── layout/
    │   │   ├── header.tsx         # Top bar with logo + health indicator
    │   │   ├── sidebar.tsx        # Nav links: Tasks, Experiments, Knowledge
    │   │   └── shell.tsx          # Layout wrapper (sidebar + main area)
    │   │
    │   ├── tasks/
    │   │   ├── task-form.tsx      # Create task form (prompt textarea + submit)
    │   │   ├── task-list.tsx      # Task table
    │   │   └── task-detail.tsx    # Task detail with linked experiments
    │   │
    │   ├── experiments/
    │   │   ├── experiment-list.tsx # Experiment table
    │   │   └── experiment-detail.tsx # Config, metrics, logs
    │   │
    │   └── knowledge/
    │       ├── knowledge-list.tsx  # Knowledge atom table
    │       └── knowledge-search.tsx # Search bar + results
    │
    └── pages/
        ├── dashboard.tsx           # Home — summary cards
        ├── tasks.tsx               # Tasks page
        ├── experiments.tsx         # Experiments page
        └── knowledge.tsx           # Knowledge page
```

---

## 4. Theme & Styling

### 4.1 shadcn/ui Dark Theme

shadcn/ui uses CSS custom properties. We define a muted dark palette in `index.css`:

```css
@layer base {
  :root {
    /* Light mode (unused, but required by shadcn) */
    --background: 0 0% 100%;
    --foreground: 0 0% 3.9%;
    /* ... defaults ... */
  }

  .dark {
    --background: 0 0% 5%;          /* near-black */
    --foreground: 0 0% 95%;         /* off-white text */
    --card: 0 0% 8%;                /* dark grey cards */
    --card-foreground: 0 0% 95%;
    --popover: 0 0% 8%;
    --popover-foreground: 0 0% 95%;
    --primary: 0 0% 90%;            /* white-ish primary */
    --primary-foreground: 0 0% 5%;
    --secondary: 0 0% 14%;          /* medium-dark grey */
    --secondary-foreground: 0 0% 90%;
    --muted: 0 0% 14%;
    --muted-foreground: 0 0% 60%;   /* subdued text */
    --accent: 0 0% 14%;
    --accent-foreground: 0 0% 90%;
    --destructive: 0 60% 50%;
    --destructive-foreground: 0 0% 95%;
    --border: 0 0% 18%;             /* subtle borders */
    --input: 0 0% 18%;
    --ring: 0 0% 40%;
    --radius: 0.75rem;              /* rounded-xl */
  }
}
```

The `<html>` element will always have `class="dark"` — no light mode toggle for v1.

### 4.2 Design Language

| Element | Style |
|---|---|
| Cards | `rounded-xl border bg-card` |
| Buttons | `rounded-lg` muted variants, white text on dark bg |
| Tables | Striped rows with `bg-muted/50` on odd rows |
| Badges | Muted colors — grey for pending, white for completed, dim red for failed |
| Typography | `font-mono` for IDs and metrics, `font-sans` for body |
| Spacing | Generous padding (`p-6` on cards, `gap-6` on grids) |

### 4.3 Status Badges

```
pending    → bg-muted text-muted-foreground border
running    → bg-secondary text-foreground border animate-pulse
completed  → bg-white/10 text-white border-white/20
failed     → bg-red-950 text-red-300 border-red-800
archived   → bg-muted text-muted-foreground/50 border
```

---

## 5. API Client Layer

### 5.1 Base Client (`lib/api.ts`)

```typescript
const API_BASE = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000";

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  return res.json();
}
```

### 5.2 SWR Hooks

Each domain gets a hook file that returns `{ data, error, isLoading, mutate }`:

```typescript
// hooks/use-tasks.ts
import useSWR from "swr";
import { apiFetch } from "@/lib/api";

export function useTasks() {
  return useSWR("/tasks", (url) => apiFetch(url));
}

export function useTask(id: string) {
  return useSWR(`/tasks/${id}`, (url) => apiFetch(url));
}

export async function createTask(prompt: string) {
  return apiFetch("/tasks", {
    method: "POST",
    body: JSON.stringify({ prompt }),
  });
}
```

Same pattern for `use-experiments.ts`, `use-knowledge.ts`, `use-health.ts`.

---

## 6. Pages & Components

### 6.1 Layout Shell

```
┌────────────────────────────────────────────────────────┐
│  ● AgentML                               ● Health: OK  │  ← Header
├──────────┬─────────────────────────────────────────────┤
│          │                                             │
│  Tasks   │           Main Content Area                 │
│  Exps    │                                             │
│  Know    │                                             │
│          │                                             │
│          │                                             │
└──────────┴─────────────────────────────────────────────┘
   Sidebar                  Outlet
```

- **Header**: Logo text "AgentML" + version + green/red health dot
- **Sidebar**: 3 nav items, vertical, `w-56`, collapsible on mobile
- **Main**: React Router `<Outlet />`

### 6.2 Dashboard Page (`/`)

Four summary cards in a 2×2 grid:

| Card | Content |
|---|---|
| Tasks | Count of total tasks + latest status |
| Experiments | Count + breakdown by state |
| Knowledge | Count of knowledge atoms |
| Server | Uptime, backend URL, storage path |

### 6.3 Tasks Page (`/tasks`)

1. **Create Task** card at top — textarea for prompt + "Run Task" button
2. **Task List** table below:
   - Columns: ID (truncated), Prompt (truncated), Status (badge), Created
   - Click row → expands Task Detail inline or navigates to detail panel
3. **Task Detail** panel:
   - Full prompt
   - Status + summary
   - Linked experiments table
   - Metrics display

### 6.4 Experiments Page (`/experiments`)

1. **Experiments Table**:
   - Columns: ID, Task ID, State (badge), Config (truncated JSON), Metrics
   - Filter by task ID (optional dropdown)
2. **Experiment Detail** panel:
   - Hypothesis display
   - Config (JSON viewer or table)
   - Metrics (key-value table)
   - Logs/error display

### 6.5 Knowledge Page (`/knowledge`)

1. **Search bar** at top — input + "Search" button → calls `/knowledge/relevant?query=`
2. **Knowledge Table**:
   - Columns: ID, Context, Claim, Action, Confidence (progress bar), Evidence
3. Click row → expands to full atom detail

---

## 7. Backend Changes

### 7.1 CORS Middleware

The React dev server runs on `localhost:5173`, the API on `localhost:8000`. We need CORS.

**File: `src/agentml/api/app.py`**

Add `fastapi.middleware.cors.CORSMiddleware`:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 7.2 Static File Serving (Production)

For production, serve the built frontend from FastAPI:

```python
from fastapi.staticfiles import StaticFiles
from pathlib import Path

frontend_dist = Path(__file__).parent.parent.parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
```

This is optional for v1 — dev mode uses Vite's proxy.

### 7.3 Config Endpoint

Add a new endpoint to expose configuration to the frontend:

**File: `src/agentml/api/routers/config.py`** (new)

```python
@router.get("/config")
async def get_config(request: Request) -> dict:
    settings = request.app.state.settings
    return {
        "api": {"host": settings.api.host, "port": settings.api.port},
        "storage": {"base_dir": str(settings.storage.base_dir)},
        "llm": {"provider": settings.llm.provider, "model": settings.llm.model},
        "tracking": {"enabled": settings.tracking.enabled},
    }
```

### 7.4 Frontend Settings

Add frontend config to `Settings` and `defaults.py`:

```python
class FrontendSettings(BaseSettings):
    """Frontend dev server configuration."""
    enabled: bool = True
    port: int = 5173
```

---

## 8. CLI Changes — `agentml start`

### 8.1 Launch Both Servers

Modify `src/agentml/cli/start.py` to:

1. Start the Vite dev server (or serve built files) as a subprocess
2. Start the uvicorn backend
3. Print a colorful status banner

### 8.2 Colorful Startup Banner

Using `rich` (already a dependency), the banner will look like this:

```
  ┌─────────────────────────────────────────────────────┐
  │                                                     │
  │   AgentML v0.1.0                                    │
  │                                                     │
  │   ● Backend API    http://127.0.0.1:8000            │
  │   ● API Docs       http://127.0.0.1:8000/docs       │
  │   ● Frontend       http://localhost:5173             │
  │   ● Storage        .agentml/                         │
  │   ● Config         .agentml/config.yaml              │
  │   ● Experiments    .agentml/experiments/              │
  │   ● Artifacts      .agentml/artifacts/               │
  │   ● Knowledge      .agentml/memory/                  │
  │                                                     │
  │   Press Ctrl+C to stop all services.                │
  │                                                     │
  └─────────────────────────────────────────────────────┘
```

Colors (via Rich markup):

| Element | Color |
|---|---|
| `AgentML` | `bold cyan` |
| Version | `dim white` |
| Bullets (●) | `green` when running |
| URLs | `bold white underline` |
| Paths | `dim yellow` |
| Box border | `dim white` |
| "Press Ctrl+C" | `dim italic` |

### 8.3 Implementation Detail

```python
# src/agentml/cli/start.py

import subprocess
import signal
import sys
from pathlib import Path

def start(host, port, no_frontend=False):
    settings = Settings.load()
    
    frontend_process = None
    
    if not no_frontend:
        frontend_dir = Path(__file__).parent.parent.parent.parent / "frontend"
        if (frontend_dir / "package.json").exists():
            frontend_process = subprocess.Popen(
                ["npm", "run", "dev", "--", "--port", str(settings.frontend.port)],
                cwd=str(frontend_dir),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    
    # Print banner (see §8.2)
    print_startup_banner(settings, frontend_running=frontend_process is not None)
    
    # Graceful shutdown
    def shutdown(sig, frame):
        if frontend_process:
            frontend_process.terminate()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    
    # Start uvicorn (blocking)
    app = create_app(settings)
    uvicorn.run(app, host=host, port=port, log_level="info")
```

Add a `--no-frontend` flag:

```python
@app.command()
def start(
    host: str = typer.Option("127.0.0.1", help="Host to bind to"),
    port: int = typer.Option(8000, help="Port to listen on"),
    no_frontend: bool = typer.Option(False, "--no-frontend", help="Skip launching the frontend dev server"),
) -> None:
```

---

## 9. Vite Configuration

### 9.1 API Proxy

The Vite dev server proxies `/api` requests to the backend:

```typescript
// vite.config.ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ""),
      },
    },
  },
});
```

With this proxy, the frontend uses relative paths like `/api/tasks` which map to `http://127.0.0.1:8000/tasks`.

Update `lib/api.ts` accordingly:

```typescript
const API_BASE = import.meta.env.VITE_API_URL ?? "/api";
```

---

## 10. Implementation Phases

### Phase 1 — Scaffolding (Steps 1–5)

| Step | Task | Files |
|---|---|---|
| 1 | Initialize React project with Vite + TypeScript | `frontend/` scaffold |
| 2 | Install dependencies: `swr`, `react-router-dom` | `package.json` |
| 3 | Initialize shadcn/ui with dark theme | `components.json`, `tailwind.config.ts`, `index.css` |
| 4 | Install shadcn components: button, card, input, badge, table, tabs, separator, skeleton, textarea, dialog | `components/ui/` |
| 5 | Set up Vite proxy to backend | `vite.config.ts` |

### Phase 2 — Layout & API Layer (Steps 6–9)

| Step | Task | Files |
|---|---|---|
| 6 | Create API client (`apiFetch`) | `lib/api.ts` |
| 7 | Create SWR hooks for all endpoints | `hooks/use-*.ts` |
| 8 | Build layout shell: header, sidebar, shell | `components/layout/` |
| 9 | Set up React Router with 4 pages | `App.tsx`, `pages/` |

### Phase 3 — Pages (Steps 10–13)

| Step | Task | Files |
|---|---|---|
| 10 | Dashboard page — summary cards | `pages/dashboard.tsx` |
| 11 | Tasks page — form + list + detail | `pages/tasks.tsx`, `components/tasks/` |
| 12 | Experiments page — table + detail | `pages/experiments.tsx`, `components/experiments/` |
| 13 | Knowledge page — search + list | `pages/knowledge.tsx`, `components/knowledge/` |

### Phase 4 — Backend Integration (Steps 14–17)

| Step | Task | Files |
|---|---|---|
| 14 | Add CORS middleware to FastAPI | `src/agentml/api/app.py` |
| 15 | Add `/config` endpoint | `src/agentml/api/routers/config.py` |
| 16 | Add `FrontendSettings` to config | `src/agentml/config/settings.py`, `defaults.py` |
| 17 | Update `agentml start` to launch frontend + colorful banner | `src/agentml/cli/start.py`, `src/agentml/cli/main.py` |

### Phase 5 — Polish (Steps 18–20)

| Step | Task | Files |
|---|---|---|
| 18 | Add loading skeletons & error states | all components |
| 19 | Add auto-refresh (SWR polling) for running tasks | hooks |
| 20 | Update Makefile with frontend targets | `Makefile` |

---

## 11. Makefile Additions

```makefile
# Frontend
frontend-install:
	cd frontend && npm install

frontend-dev:
	cd frontend && npm run dev

frontend-build:
	cd frontend && npm run build

# Full stack
dev-all: dev
	@echo "Starting frontend..."
	cd frontend && npm run dev &
	uv run agentml start
```

---

## 12. TypeScript Types

Mirror the API response models:

```typescript
// src/types.ts

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
```

---

## 13. Component Sketches

### 13.1 Header

```tsx
<header className="flex items-center justify-between h-14 px-6 border-b bg-background">
  <div className="flex items-center gap-2">
    <span className="text-lg font-bold tracking-tight">AgentML</span>
    <Badge variant="outline" className="text-xs font-mono">v0.1.0</Badge>
  </div>
  <div className="flex items-center gap-2">
    <div className={cn(
      "h-2 w-2 rounded-full",
      isHealthy ? "bg-green-500" : "bg-red-500"
    )} />
    <span className="text-xs text-muted-foreground">
      {isHealthy ? "Connected" : "Disconnected"}
    </span>
  </div>
</header>
```

### 13.2 Task Form

```tsx
<Card className="rounded-xl">
  <CardHeader>
    <CardTitle className="text-sm font-medium text-muted-foreground">
      New Task
    </CardTitle>
  </CardHeader>
  <CardContent className="space-y-4">
    <Textarea
      placeholder="Describe your ML experiment task..."
      value={prompt}
      onChange={(e) => setPrompt(e.target.value)}
      className="min-h-[100px] rounded-lg bg-muted/50 border-border"
    />
    <Button
      onClick={handleSubmit}
      disabled={!prompt.trim() || loading}
      className="rounded-lg"
    >
      {loading ? "Running..." : "Run Task"}
    </Button>
  </CardContent>
</Card>
```

### 13.3 Experiment Table Row

```tsx
<TableRow className="hover:bg-muted/50 cursor-pointer">
  <TableCell className="font-mono text-xs">{exp.id.slice(0, 8)}…</TableCell>
  <TableCell className="font-mono text-xs">{exp.task_id.slice(0, 8)}…</TableCell>
  <TableCell><StateBadge state={exp.state} /></TableCell>
  <TableCell className="font-mono text-xs text-muted-foreground">
    {JSON.stringify(exp.config).slice(0, 40)}…
  </TableCell>
  <TableCell className="font-mono text-xs">
    {exp.metrics ? Object.entries(exp.metrics).map(([k, v]) =>
      `${k}: ${v.toFixed(3)}`
    ).join(", ") : "—"}
  </TableCell>
</TableRow>
```

---

## 14. Dependency List

### Frontend (`frontend/package.json`)

```json
{
  "dependencies": {
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "react-router-dom": "^7.0.0",
    "swr": "^2.3.0",
    "class-variance-authority": "^0.7.0",
    "clsx": "^2.1.0",
    "tailwind-merge": "^3.0.0",
    "lucide-react": "^0.400.0",
    "@radix-ui/react-slot": "^1.1.0",
    "@radix-ui/react-dialog": "^1.1.0",
    "@radix-ui/react-separator": "^1.1.0",
    "@radix-ui/react-tabs": "^1.1.0"
  },
  "devDependencies": {
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "@vitejs/plugin-react": "^4.0.0",
    "autoprefixer": "^10.4.0",
    "postcss": "^8.4.0",
    "tailwindcss": "^4.0.0",
    "typescript": "^5.7.0",
    "vite": "^6.0.0"
  }
}
```

---

## 15. File Change Summary

### New Files

| File | Purpose |
|---|---|
| `frontend/` (entire directory) | React application |
| `src/agentml/api/routers/config.py` | Config endpoint for frontend |

### Modified Files

| File | Change |
|---|---|
| `src/agentml/api/app.py` | Add CORS middleware, register config router, optional static mount |
| `src/agentml/config/settings.py` | Add `FrontendSettings` |
| `src/agentml/config/defaults.py` | Add frontend defaults |
| `src/agentml/cli/start.py` | Launch frontend subprocess + colorful banner |
| `src/agentml/cli/main.py` | Add `--no-frontend` flag |
| `Makefile` | Add frontend targets |
| `.gitignore` | Add `frontend/node_modules`, `frontend/dist` |

---

## 16. Startup Flow

```
┌────────────────────────────────────────────────────────┐
│  $ agentml start                                       │
│                                                        │
│  1. Load Settings                                      │
│  2. Check if frontend/package.json exists              │
│  3. If yes → spawn `npm run dev` subprocess            │
│  4. Print Rich startup banner with all URLs + paths    │
│  5. Start uvicorn (blocking)                           │
│  6. On Ctrl+C → terminate frontend subprocess + exit   │
└────────────────────────────────────────────────────────┘
```

---

## 17. Startup Banner Implementation

```python
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

def print_startup_banner(settings, frontend_running=False):
    console = Console()
    
    lines = Text()
    lines.append("\n")
    lines.append("  AgentML", style="bold cyan")
    lines.append(f" v{__version__}\n\n", style="dim")
    
    host = settings.api.host
    port = settings.api.port
    
    entries = [
        ("Backend API ", f"http://{host}:{port}"),
        ("API Docs    ", f"http://{host}:{port}/docs"),
    ]
    
    if frontend_running:
        entries.append(("Frontend    ", f"http://localhost:{settings.frontend.port}"))
    
    for label, url in entries:
        lines.append("  ● ", style="green")
        lines.append(label, style="white")
        lines.append(f" {url}\n", style="bold white underline")
    
    lines.append("\n")
    
    paths = [
        ("Storage     ", str(settings.storage.base_dir) + "/"),
        ("Config      ", str(settings.storage.base_dir) + "/config.yaml"),
        ("Experiments ", str(settings.storage.base_dir) + "/experiments/"),
        ("Artifacts   ", str(settings.storage.base_dir) + "/artifacts/"),
        ("Knowledge   ", str(settings.storage.base_dir) + "/memory/"),
    ]
    
    for label, path in paths:
        lines.append("  ● ", style="green")
        lines.append(label, style="white")
        lines.append(f" {path}\n", style="dim yellow")
    
    lines.append("\n")
    lines.append("  Press Ctrl+C to stop all services.\n", style="dim italic")
    
    console.print(Panel(lines, border_style="dim", padding=(0, 1)))
```

---

## 18. Open Questions / Future Enhancements

- **WebSocket support** — real-time experiment status updates (replace polling)
- **Production build serving** — serve `frontend/dist` from FastAPI when `NODE_ENV=production`
- **Auth** — API key or session auth for multi-user setups
- **Experiment comparison view** — side-by-side metrics comparison
- **Artifact viewer** — inline display of model outputs, plots, etc.
- **Dark/light mode toggle** — currently dark-only

---

## 19. Acceptance Criteria

1. `cd frontend && npm install && npm run dev` starts the React dev server on `:5173`
2. `agentml start` launches both backend (`:8000`) and frontend (`:5173`) with a colorful Rich banner
3. `agentml start --no-frontend` launches backend only (existing behavior)
4. Dashboard shows task/experiment/knowledge counts
5. Tasks page can create a new task and display the result
6. Experiments page lists experiments with state badges and metrics
7. Knowledge page lists atoms and supports search
8. All components use shadcn/ui dark theme with muted grey/black/white palette
9. CORS works correctly between frontend and backend in dev mode
10. `Ctrl+C` cleanly shuts down both processes
