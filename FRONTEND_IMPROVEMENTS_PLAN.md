# Frontend Improvements Plan

> Addresses bugs, missing features, and UX issues identified in the current AgentML frontend.
> Reference: MASTER_PLAN.md (Phase 4), FRONTEND_DESIGN_SYSTEM.md

---

## 1. Bug Fixes

### 1.1 Metrics Tab Crash

**Problem:** Clicking the Metrics tab on the domain page crashes the frontend.

**Root cause:** The `MetricEvolutionChart` component initializes `selectedMetric` with `metricKeys[0]` on first render, but `metricKeys` is derived from `data` which is `undefined` while loading. When data arrives, `metricKeys` updates but `useState` doesn't re-initialize — so `selectedMetric` stays `""`. The crash likely happens when Recharts tries to render with no valid data, or when the `/domains/{id}/metrics` endpoint returns an unexpected shape (e.g. `null`, an error response, or metrics with non-numeric values that `.toFixed()` chokes on).

**Fix:**
- Add a `useEffect` to sync `selectedMetric` when `metricKeys` changes and current selection is invalid
- Add null/type guards in `CustomTooltip` and `tickFormatter` — `toFixed()` on a non-number crashes
- Wrap the chart in an error boundary to prevent tab crash from propagating
- Verify the API response shape — if `/domains/{id}/metrics` returns 404 or error body when no experiments exist, handle it gracefully in the hook

**Files:**
- `frontend/src/components/charts/metric-evolution-chart.tsx`
- `frontend/src/hooks/use-domain-metrics.ts`
- (New) `frontend/src/components/ui/error-boundary.tsx`

### 1.2 Experiment Count Mismatch

**Problem:** The stat strip shows `domain.experiment_ids.length` for the experiment count, but this may not match the actual number of experiments in the list (from `useDomainExperiments`). The `experiment_ids` array on the domain model may be stale or out of sync with what the API returns for `/domains/{id}/experiments`.

**Fix:**
- Use `experiments?.length ?? domain.experiment_ids.length` as the displayed count — prefer the actual fetched list length, fall back to domain model
- Or simpler: always use `experiments?.length` with a loading indicator

**Files:**
- `frontend/src/pages/domain-detail.tsx` — stat strip section (line 109)

---

## 2. Missing: Dashboard with Metrics Progression Chart

**Problem:** When entering a domain, there is no dashboard/overview showing a summary of how experiments are progressing. The user expects to see a metrics progression chart front and center on the domain page — not buried in a tab.

**Design:**
- Add a new **Dashboard tab** (or make it the default landing view before the tabs) that shows:
  - **Metrics progression chart** — The same `MetricEvolutionChart` but embedded in a card on the dashboard. Each data point is an experiment. Clicking a data point navigates to that experiment's detail (or switches to Experiments tab and highlights it).
  - **Quick stats** — Running experiments, latest metric values, recent knowledge atoms
  - **Recent activity feed** — Last 5 experiment completions, knowledge atoms created

**Implementation:**
- Create `frontend/src/components/domains/domain-dashboard.tsx`
- Reuse `MetricEvolutionChart` with an `onPointClick` callback
- Add it as the default tab content (value="dashboard") or as a section above the tabs
- The chart data points should be clickable — on click, switch to experiments tab and scroll to / expand that experiment

**Interaction:** Clicking a data point in the chart → sets active tab to "experiments" and passes the experiment ID to highlight/expand.

**Files:**
- (New) `frontend/src/components/domains/domain-dashboard.tsx`
- `frontend/src/pages/domain-detail.tsx` — add Dashboard tab or top section
- `frontend/src/components/charts/metric-evolution-chart.tsx` — add `onPointClick` prop

---

## 3. Missing: Knowledge Atom Timeline

**Problem:** There is no visualization of knowledge evolution over time. The MASTER_PLAN specifies a "Knowledge Evolution Chart" showing new atoms created, existing atoms updated, and confidence changes over time as experiments run.

**Design:**
- A timeline/chart component showing knowledge accumulation over time
- X-axis: time (or experiment index)
- Y-axis: could show:
  - Cumulative atom count (area chart)
  - Individual atom confidence changes (scatter/line)
  - New vs updated atoms per experiment (stacked bar)
- Each point is linked to the experiment that created/updated the atom
- Clicking a point drills into the atom's version history

**Implementation:**
- Create `frontend/src/components/charts/knowledge-evolution-chart.tsx`
- Create hook `frontend/src/hooks/use-knowledge-evolution.ts` calling `GET /domains/{id}/knowledge/evolution`
- If the backend endpoint doesn't exist yet, derive a basic timeline from the knowledge atoms' `created_at` / `updated_at` fields and `version` numbers
- Place in the Dashboard section and/or as its own sub-section in the Knowledge tab

**API dependency:** Check if `GET /domains/{id}/knowledge/evolution` exists on the backend. If not, build a client-side approximation from existing atom data, and note the backend endpoint as a TODO.

**Files:**
- (New) `frontend/src/components/charts/knowledge-evolution-chart.tsx`
- (New) `frontend/src/hooks/use-knowledge-evolution.ts`
- `frontend/src/pages/domain-detail.tsx` — integrate into dashboard/knowledge tab

---

## 4. UX: Clickable Stat Strip

**Problem:** The stat strip shows "Experiments: 1", "Knowledge: 1" etc. but they aren't clickable. The user expects clicking "Experiments: 1" to navigate to the Experiments tab, and "Knowledge: 1" to navigate to the Knowledge tab.

**Design:**
- Make each stat in the strip a clickable button
- On click, programmatically switch the active tab to the corresponding tab
- Add a hover state to indicate clickability (cursor pointer, subtle background shift)
- Remove the stat strip as a passive display — make it navigation

**Implementation:**
- Convert `Tabs` to controlled mode: `value={activeTab}` + `onValueChange={setActiveTab}`
- Each stat div gets `onClick={() => setActiveTab("experiments")}` etc.
- Add `cursor-pointer hover:bg-wheat/20 transition-colors` to stat items
- The "Created" stat doesn't need a click target

**Files:**
- `frontend/src/pages/domain-detail.tsx` — stat strip + tabs state management

---

## 5. Experiment Detail: Expandable Row

**Problem:** The experiments list is a flat table with no way to drill into an experiment. The user wants to click an experiment and see an expanded overview: chat/agent interaction, tool calls, reasoning, code, metrics.

**Design:**
- Click a row → row expands inline (accordion style) or opens a slide-over panel from the right
- **Expanded view sections:**
  - **Summary** — Hypothesis (from config), state badge, duration
  - **Metrics** — All metrics as key-value cards
  - **Agent Activity** — If we can link back to the agent run events for this experiment, show the relevant tool calls, reasoning text, and code blocks. This requires filtering agent events by experiment ID.
  - **Error** — If failed, show error with stack trace
  - **Knowledge produced** — List of knowledge atoms linked to this experiment (via `evidence_ids` or knowledge links)
- If agent events aren't linkable per-experiment, show the raw config and metrics as the primary content

**Implementation:**
- Option A (recommended): **Accordion row expansion** — clicking a table row expands a detail panel below it within the table. Simpler, keeps context.
- Option B: **Slide-over drawer** — opens from the right side. More space, but loses table context.
- Add state tracking for which experiment ID is expanded
- Create `frontend/src/components/domains/experiment-detail.tsx`
- Fetch experiment detail via `GET /experiments/{id}` when expanded (or use already-fetched data if sufficient)
- For agent activity: check if experiment events can be filtered from agent run data. If not, show a link to the agent run that created it.

**Files:**
- (New) `frontend/src/components/domains/experiment-detail.tsx`
- `frontend/src/components/domains/experiments-section.tsx` — add row click + expansion
- May need `frontend/src/hooks/use-experiment-detail.ts` if more data is needed

---

## 6. Knowledge Cards Redesign

**Problem:** The knowledge list is text-heavy and hard to scan. Cards show claim, context, action, confidence, version, and evidence count all at once. Needs to be cleaner with a click-to-expand pattern.

**Design — Collapsed card (default view):**
- Compact horizontal card
- Left: confidence indicator (colored dot or small bar, not a full vertical bar)
- Center: **Claim text** (1-2 lines, truncated) as the primary content. Context shown as a subtle subtitle.
- Right: confidence percentage + version badge
- No action text visible in collapsed state
- Hover: subtle lift + border color change (per design system)

**Design — Expanded view (on click):**
- Card expands inline (accordion) to reveal:
  - **Full claim text** (untruncated)
  - **Context** — full text with label
  - **Recommended action** — full text with label
  - **Evidence** — list of linked experiment IDs (clickable → navigate to experiment)
  - **Version history** — if available, show version number and "Updated X times" with a link to version history
  - **Confidence breakdown** — visual bar showing confidence level

**Implementation:**
- Redesign `KnowledgeSection` cards with collapsed/expanded states
- Add `expandedAtomId` state management
- Create `frontend/src/components/domains/knowledge-atom-card.tsx` as a dedicated component
- Fetch detail via `useKnowledgeDetail(atomId)` when expanded (already exists in `use-domain-knowledge.ts`)
- Style per FRONTEND_DESIGN_SYSTEM.md card patterns

**Files:**
- (New) `frontend/src/components/domains/knowledge-atom-card.tsx`
- `frontend/src/components/domains/knowledge-section.tsx` — use new card component
- `frontend/src/hooks/use-domain-knowledge.ts` — already has `useKnowledgeDetail`

---

## 7. Missing: Global Knowledge Tab (Cross-Domain)

**Problem:** There is no way to see all accumulated knowledge across all domains. The MASTER_PLAN mentions cross-domain knowledge search as a key feature.

**Design:**
- Add a new top-level page/route: `/knowledge` — "All Knowledge"
- Add a sidebar nav item: "Knowledge" with a Brain icon
- Page layout:
  - **Search bar** at top (uses `GET /knowledge/relevant?query=`)
  - **Filter pills**: by domain (dropdown), by confidence range, by version
  - **Knowledge cards** — same redesigned cards from section 6, but with an additional "Domain" badge on each card showing which domain it belongs to
  - **Stats header**: total atoms, average confidence, domains contributing

**Implementation:**
- Create `frontend/src/pages/knowledge-overview.tsx`
- Add route in `App.tsx`: `/knowledge` → `KnowledgeOverviewPage`
- Add sidebar nav item in `frontend/src/components/layout/sidebar.tsx`
- Reuse `KnowledgeAtomCard` component from section 6
- Use existing hooks: `useKnowledge()` and `useKnowledgeSearch(query)` from `use-knowledge.ts`
- Add domain name resolution — need to map `domain_id` from knowledge links to domain names (may need to fetch domains list)

**Files:**
- (New) `frontend/src/pages/knowledge-overview.tsx`
- `frontend/src/App.tsx` — add route
- `frontend/src/components/layout/sidebar.tsx` — add nav item
- Reuse `knowledge-atom-card.tsx` from section 6

---

## 8. Implementation Order

Prioritized by impact and dependency chain:

| Priority | Task | Section | Effort | Dependencies |
|----------|------|---------|--------|-------------|
| **P0** | Fix metrics tab crash | 1.1 | Small | None |
| **P0** | Fix experiment count mismatch | 1.2 | Tiny | None |
| **P1** | Clickable stat strip → tab navigation | 4 | Small | None |
| **P1** | Knowledge cards redesign (collapsed/expanded) | 6 | Medium | None |
| **P1** | Experiment detail expandable rows | 5 | Medium | None |
| **P2** | Domain dashboard with metrics chart | 2 | Medium | 1.1 (metrics fix) |
| **P2** | Knowledge atom timeline chart | 3 | Medium | Backend check needed |
| **P2** | Global knowledge page | 7 | Medium | 6 (reuse card component) |

### Phase 1: Bug Fixes + Quick Wins (P0)
1. Fix metrics tab crash (error boundary + state sync)
2. Fix experiment count in stat strip
3. Make stat strip clickable (controlled tabs)

### Phase 2: Core UX Improvements (P1)
4. Redesign knowledge cards with expand/collapse
5. Add experiment detail expansion
6. Extract reusable `KnowledgeAtomCard` component

### Phase 3: Missing Features (P2)
7. Domain dashboard with clickable metrics chart
8. Knowledge evolution timeline chart
9. Global knowledge overview page + sidebar nav

---

## 9. Component Architecture (New/Modified)

```
frontend/src/
├── pages/
│   ├── domain-overview.tsx          # Unchanged
│   ├── domain-detail.tsx            # Modified: controlled tabs, clickable stats, dashboard tab
│   └── knowledge-overview.tsx       # NEW: global knowledge page
│
├── components/
│   ├── domains/
│   │   ├── domain-dashboard.tsx     # NEW: dashboard with metrics chart + activity feed
│   │   ├── experiment-detail.tsx    # NEW: expandable experiment detail panel
│   │   ├── experiments-section.tsx  # Modified: clickable rows with expansion
│   │   ├── knowledge-section.tsx    # Modified: use KnowledgeAtomCard
│   │   └── knowledge-atom-card.tsx  # NEW: redesigned card with expand/collapse
│   │
│   ├── charts/
│   │   ├── metric-evolution-chart.tsx    # Modified: fix crash, add onPointClick
│   │   └── knowledge-evolution-chart.tsx # NEW: knowledge timeline visualization
│   │
│   ├── layout/
│   │   └── sidebar.tsx              # Modified: add Knowledge nav item
│   │
│   └── ui/
│       └── error-boundary.tsx       # NEW: React error boundary wrapper
│
├── hooks/
│   └── use-knowledge-evolution.ts   # NEW: fetch knowledge evolution data
│
└── App.tsx                          # Modified: add /knowledge route
```

---

## 10. Design System Reference

All new components should follow FRONTEND_DESIGN_SYSTEM.md:

- **Cards:** `bg-white rounded-2xl border border-soft-fawn/20 shadow-sm`, clickable: `hover:shadow-md hover:border-soft-fawn/40 transition-all`
- **Badges:** Status-colored pills per the badge table
- **Tabs (controlled):** `bg-wheat/15 rounded-xl p-1`, active: `bg-white rounded-lg shadow-sm`
- **Charts:** Recharts with `stroke="#59344F"` (blackberry), grid `rgba(214,186,115,0.15)`, tooltip styled per existing pattern
- **Typography:** Headings in font-heading (Inter/Plus Jakarta Sans), body in default font, code in JetBrains Mono
- **Colors:** wheat, soft-fawn, muted-teal, grey, blackberry, white, surface, danger
