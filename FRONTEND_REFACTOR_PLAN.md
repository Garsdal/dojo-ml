# Frontend Refactor & Design System Plan

## Current State Summary

The AgentML frontend is a React 19 + Vite SPA using Tailwind CSS 4, Radix UI primitives, and SWR for data fetching. It currently has a dark-mode-first design with monochrome OKLCH color tokens, system fonts, and two routes: a domain overview grid and a domain detail page with tabbed sections (Agent, Experiments, Knowledge, Metrics, Tools). The agent panel displays a raw event stream in monospace — functional but lacking structured UX for different response types.

---

## 1. Design System Overhaul

### 1.1 Color Palette

Replace the current monochrome OKLCH palette with the warm, Claude-inspired scheme:

| Token | Hex | Usage |
|-------|-----|-------|
| `--wheat` | `#F5E0B7` | Accent, highlights, active states |
| `--wheat-bg` | `#F5E0B7` at 25% opacity | Page background (pastel orange/white) |
| `--soft-fawn` | `#D6BA73` | Secondary accent, borders on focus, hover states |
| `--muted-teal` | `#8BBF9F` | Success indicators, positive badges, completed states |
| `--grey` | `#857E7B` | Muted text, secondary content, disabled states |
| `--blackberry` | `#59344F` | Primary text, headings, buttons, strong emphasis |
| `--white` | `#FEFCF8` | Card backgrounds (warm white, not pure white) |
| `--surface` | `#FAF3E8` | Elevated surface (sidebar, header) |
| `--danger` | `#C45D4A` | Destructive actions, error states (warm red) |

**Background treatment:** The page body gets a subtle warm gradient — `linear-gradient(135deg, rgba(245,224,183,0.15), rgba(250,243,232,0.6))` over `#FEFCF8`. Cards sit on `--white` with soft shadows.

**Dark mode:** Remove dark-mode-first approach. This palette is designed for light mode. If dark mode is desired later, it can be a separate effort. Remove the `class="dark"` from `index.html`.

### 1.2 Typography

Replace system font stack with a playful, rounded font pairing:

| Role | Font | Weight | Fallback |
|------|------|--------|----------|
| **Headings** | [Nunito](https://fonts.google.com/specimen/Nunito) | 700, 800 | `system-ui, sans-serif` |
| **Body** | [Nunito Sans](https://fonts.google.com/specimen/Nunito+Sans) | 400, 600 | `system-ui, sans-serif` |
| **Code / Agent** | [JetBrains Mono](https://fonts.google.com/specimen/JetBrains+Mono) | 400, 500 | `monospace` |

Load via Google Fonts link in `index.html` or self-host via `@fontsource`.

**Scale:**
- Page titles: 1.75rem / 28px, Nunito 800
- Section headings: 1.25rem / 20px, Nunito 700
- Card titles: 1rem / 16px, Nunito Sans 600
- Body: 0.875rem / 14px, Nunito Sans 400
- Small / meta: 0.75rem / 12px, Nunito Sans 400

### 1.3 Spacing & Radius

- **Border radius:** Increase to `1rem` (16px) for cards, `0.75rem` (12px) for buttons/inputs, `9999px` for badges/pills
- **Shadows:** Replace sharp shadows with soft, warm ones: `0 2px 12px rgba(89,52,79,0.06)`
- **Spacing grid:** Keep Tailwind's 4px grid but standardize: cards use `p-5`, sections gap `gap-5`, page padding `px-6 py-5`

### 1.4 Component Variant Updates

All existing CVA components need updated variants:

**Button:**
- `default` — `bg-blackberry text-white hover:bg-blackberry/90` rounded-xl
- `secondary` — `bg-wheat/40 text-blackberry hover:bg-wheat/60`
- `outline` — `border-soft-fawn text-blackberry hover:bg-wheat/20`
- `destructive` — `bg-danger text-white`
- `ghost` — `text-grey hover:text-blackberry hover:bg-wheat/20`

**Badge / StateBadge:**
- `pending` — `bg-grey/15 text-grey`
- `running` — `bg-wheat/50 text-blackberry` + subtle pulse
- `completed` — `bg-muted-teal/20 text-muted-teal`
- `failed` — `bg-danger/15 text-danger`
- `draft` — `bg-soft-fawn/20 text-soft-fawn`
- `archived` — `bg-grey/10 text-grey`

**Card:**
- `bg-white rounded-2xl border border-soft-fawn/20 shadow-sm`
- Hover state for clickable cards: `hover:shadow-md hover:border-soft-fawn/40 transition-all`

**Input / Textarea:**
- `bg-white border-soft-fawn/30 rounded-xl focus:ring-2 focus:ring-wheat focus:border-soft-fawn`

---

## 2. Layout & Navigation Revamp

### 2.1 Header

**Current:** Dark bar with "AgentML" text, version badge, health dot.

**Proposed:**
- Warm surface background (`--surface`) with bottom border `border-soft-fawn/20`
- Logo: "AgentML" in Nunito 800, `text-blackberry`, with a small flask/beaker icon (lucide `flask-conical`) in `text-muted-teal`
- Version badge: pill shape, `bg-wheat/30 text-blackberry`
- Health indicator: keep the dot but use `--muted-teal` for healthy, `--danger` for unhealthy
- Add breadcrumb navigation: `Domains > Domain Name > Agent` using `text-grey` with `text-blackberry` for current

### 2.2 Sidebar

**Current:** Minimal sidebar with a single "Domains" link.

**Proposed:**
- Background: `--surface` to match header
- Navigation items styled as pills: `rounded-xl px-4 py-2`
- Active state: `bg-wheat/40 text-blackberry font-semibold`
- Hover: `bg-wheat/20`
- Add icons to nav items (lucide: `layout-grid` for Domains)
- Add a collapsible toggle for narrow screens
- Bottom section: Settings gear icon + version info

### 2.3 Page Layout

- Max-width container: `max-w-7xl mx-auto` for content areas
- Consistent page header pattern: Title + description + action buttons on the right
- Breadcrumb trail below the header on detail pages

---

## 3. Domain Overview Page

### 3.1 Page Header

- Title: "Research Domains" in Nunito 800
- Subtitle: `text-grey` — "Manage your AI research domains"
- "New Domain" button positioned top-right (primary style)

### 3.2 Domain Cards

**Current:** Basic card with name, description, counts, and date.

**Proposed:**
- **Left accent bar**: 3px left border colored by status (muted-teal=active, grey=draft, wheat=paused, etc.)
- **Header row:** Domain name (Nunito 700) + status badge pill
- **Description:** 2-line clamp with `text-grey`
- **Stats row:** Inline pills showing `{count} experiments`, `{count} tools`, `{count} knowledge` with small icons
- **Footer:** `Created {date}` in `text-xs text-grey` + arrow icon for navigation hint
- **Hover:** Lift with shadow transition + border color shift

### 3.3 Create Domain Form

**Current:** Inline expanding form.

**Proposed:**
- Move to a **Dialog/Modal** triggered by the "New Domain" button
- Clean form layout with labeled fields
- Name field with character count
- Description as textarea
- System prompt as optional collapsible section (advanced)
- "Create Domain" primary button + "Cancel" ghost button
- Form validation with inline error messages

### 3.4 Sections

- Replace "Active Domains" / "Archived Domains" headers with filter tabs/pills at the top: `All | Active | Draft | Completed | Archived`
- Show empty state illustration + text when no domains match filter

---

## 4. Domain Detail Page

### 4.1 Domain Header

**Current:** Title, description, status badge, action buttons, stat cards.

**Proposed:**
- Compact header card with:
  - Domain name (large, Nunito 800) + editable status badge
  - Description below in `text-grey`
  - Action buttons row: `Pause` / `Resume` / `Complete` / `Archive` as outline buttons with icons
- **Stat strip** below header: horizontal row of 4 stats in small pill-style containers
  - Each stat: icon + label + value, separated by subtle dividers
  - Remove the full card treatment for stats (too heavy)

### 4.2 Tab Navigation

**Current:** Standard Radix tabs with underline style.

**Proposed:**
- **Pill-style tabs** inside a `bg-wheat/15 rounded-xl p-1` container
- Active tab: `bg-white rounded-lg shadow-sm text-blackberry font-semibold`
- Inactive: `text-grey hover:text-blackberry`
- Icons next to tab labels: Agent (bot), Experiments (flask), Knowledge (brain), Metrics (chart-bar), Tools (wrench)
- Tab content area gets a subtle top margin for visual separation

---

## 5. Agent Chat Panel (Major Revamp)

This is the highest-impact section. The current raw event stream needs structured, differentiated UX for each response type.

### 5.1 Layout Structure

```
+--------------------------------------------------+
|  Agent Research Panel                             |
|  [Status Badge]  [Turn: 5/12]  [Cost: $0.003]   |
+--------------------------------------------------+
|                                                  |
|  +----- Scrollable Event Timeline --------+      |
|  |                                        |      |
|  |  [PROMPT]  User's research prompt      |      |
|  |                                        |      |
|  |  [TEXT]  Agent reasoning text...        |      |
|  |                                        |      |
|  |  [TOOL]  execute_python               |      |
|  |  +-- Code Block --+                   |      |
|  |  | import pandas  |                   |      |
|  |  | df = pd.read   |                   |      |
|  |  +----------------+                   |      |
|  |                                        |      |
|  |  [RESULT]  Tool output card            |      |
|  |  +-- Output Block --+                 |      |
|  |  | DataFrame(5x3)   |                 |      |
|  |  +------------------+                 |      |
|  |                                        |      |
|  |  [TEXT]  More reasoning...             |      |
|  |                                        |      |
|  |  [ERROR]  Error alert card             |      |
|  |                                        |      |
|  |  [DONE]  Summary card                  |      |
|  |                                        |      |
|  +----------------------------------------+      |
|                                                  |
+--------------------------------------------------+
|  [Textarea: Enter research prompt...]   [Send]   |
+--------------------------------------------------+
```

### 5.2 Event Type Rendering

Each event type gets a distinct visual treatment:

#### TEXT Events
- Clean paragraph rendering in body font (Nunito Sans)
- Left border accent: `border-l-3 border-wheat pl-4`
- Label: `TEXT` badge in `bg-wheat/20 text-blackberry` rounded pill
- Support for basic markdown rendering (bold, italic, lists) if the text contains it
- Long text gets a "Show more" collapse after ~6 lines

#### TOOL Events (tool_call)
- **Label:** `TOOL` badge in `bg-blackberry/15 text-blackberry` pill with wrench icon
- **Tool name** displayed prominently: `font-mono font-semibold text-blackberry`
- **Code input:** Rendered in a proper syntax-highlighted code block:
  - Background: `bg-blackberry/5 rounded-lg`
  - Font: JetBrains Mono
  - Header bar with language label + copy button
  - If input is JSON, pretty-print it
  - If input contains code (python, SQL, etc.), render with syntax highlighting
  - Use a lightweight highlighter like `prism-react-renderer` or `shiki`
- **Collapsible:** Long tool inputs are collapsed by default with "Show full input" toggle

#### RESULT Events (tool_result)
- **Label:** `RESULT` badge in `bg-muted-teal/20 text-muted-teal` pill with check-circle icon
- **Output rendering:**
  - If output looks like code/data → code block with monospace
  - If output is plain text → body font with subtle background card
  - If output contains tabular data → render as a simple table
  - If output is an error → red-tinted card (see ERROR below)
- Container: `bg-muted-teal/5 rounded-lg border border-muted-teal/15 p-4`
- Collapsible for long outputs (>10 lines)

#### ERROR Events
- **Label:** `ERROR` badge in `bg-danger/15 text-danger` pill with alert-triangle icon
- Red-tinted card: `bg-danger/5 border border-danger/20 rounded-lg`
- Error message in monospace
- Stack trace collapsible if present

#### DONE / Result Events
- **Summary card** with completion styling:
  - `bg-muted-teal/10 border border-muted-teal/20 rounded-xl p-5`
  - Checkmark icon header
  - Stats row: turns, cost, duration
  - If there's a final summary text, render it prominently

### 5.3 Event Timeline Styling

- Each event is a **discrete card/block** with consistent spacing (`gap-3`)
- Events have a subtle left timeline line connecting them (optional):
  - Thin `border-l-2 border-soft-fawn/30` running down the left side
  - Each event label sits on the line as a dot/badge
- Timestamps shown as subtle `text-xs text-grey` on the right side of each event
- Auto-scroll behavior with a "scroll to bottom" floating button if user has scrolled up
- Increase max-height from 500px to fill available space (use flex-grow)

### 5.4 Prompt Input Area

**Current:** Textarea with tool hints section and "Start Research" button.

**Proposed:**
- **Fixed at bottom** of the agent panel (chat-style)
- Single-line textarea that expands on focus (up to 4 lines)
- Send button: circular, `bg-blackberry text-white`, arrow-up icon
- Tool hints: move to a collapsible "Advanced" section or a popover
- While running: replace input with a status bar showing "Agent is researching..." + stop button
- Previous runs: move to a separate "History" sub-tab or side panel

### 5.5 Agent Run History

**Current:** Simple list of previous runs below the active run.

**Proposed:**
- Move to a separate "History" view accessible via a small icon button or tab
- List format: each run shows prompt preview (1-line truncated), status badge, date, cost
- Clicking a run loads it into the main event timeline view
- Search/filter by date or status

### 5.6 Technical Implementation Notes

**New dependencies needed:**
- `react-markdown` or `marked` — for rendering markdown in TEXT events
- `prism-react-renderer` or `react-syntax-highlighter` — for code syntax highlighting in TOOL events
- Consider `framer-motion` for smooth event entrance animations (optional, low priority)

**Event parsing logic:**
Create a dedicated `parseEventContent(event: AgentEvent)` utility that:
1. Detects content type (code, JSON, markdown, plain text, tabular data)
2. Returns a typed object indicating how to render
3. Extracts language hints from tool names (e.g., `execute_python` → python)

**Component structure:**
```
agent-section.tsx
├── agent-prompt-form.tsx (bottom input)
├── agent-run-view.tsx (main container)
│   ├── event-timeline.tsx (scrollable list)
│   │   ├── event-text.tsx
│   │   ├── event-tool-call.tsx (with code block)
│   │   ├── event-tool-result.tsx
│   │   ├── event-error.tsx
│   │   └── event-done.tsx
│   └── run-status-bar.tsx (top status)
└── agent-run-history.tsx (side panel / separate view)
```

---

## 6. Experiments Section

### 6.1 Table Improvements

**Current:** Basic table with rows showing experiment state, config, metrics.

**Proposed:**
- Add table header styling: `bg-wheat/10 text-grey font-semibold uppercase text-xs`
- Row hover: `hover:bg-wheat/8`
- State column uses the updated StateBadge pills
- Config column: show key params as mini pills (`max_iter: 100`, `lr: 0.01`)
- Metrics column: show top metric as value with a tiny inline sparkline or trend arrow
- Add sorting by column headers (click to sort)
- Add bulk actions row (e.g., "Archive selected")

### 6.2 Experiment Detail

- Expand in a slide-over panel from the right (instead of inline expansion or navigation)
- Sections: Config, Metrics, Error (if any)
- Metrics displayed as a mini dashboard with cards

---

## 7. Knowledge Section

### 7.1 Knowledge Cards

**Current:** Grid of cards showing context, claim, confidence.

**Proposed:**
- Card layout: compact horizontal card (not full grid card)
- Left side: confidence bar (vertical, color-coded from `--danger` to `--muted-teal`)
- Content: claim text (primary), context (secondary, `text-grey`)
- Right side: version badge, evidence count pill
- Hover: show full text in a popover/tooltip if truncated

### 7.2 Search

- Move search bar to the top of the section
- Add filter pills: by confidence range, by version, by context
- Real-time filtering as you type

---

## 8. Metrics Section

### 8.1 Chart Improvements

**Current:** Custom bar chart with basic hover tooltips.

**Proposed:**
- Replace custom chart with a lightweight charting library: `recharts` (already React-compatible)
- Line chart as default (better for metric evolution over time)
- Multi-metric overlay option (plot 2-3 metrics on the same chart)
- Metric selector as pill buttons: `bg-wheat/20 text-blackberry` active, `text-grey` inactive
- Hover tooltip styled to match design system
- Y-axis labels in `text-grey`, grid lines in `border-soft-fawn/10`

---

## 9. Tools Section

### 9.1 Tool Management

**Current:** List of tools with add/remove and AI generation.

**Proposed:**
- Tool cards in a compact list format
- Each tool: name (bold), description, type badge, source badge
- Add tool: button opens a dialog with two paths:
  - "Add Manually" — form with name, description, type, params
  - "Generate with AI" — prompt input that generates tool config
- Remove tool: confirmation dialog
- Tool cards have a subtle icon based on type

---

## 10. Responsive Design

Add breakpoint handling (currently not addressed):

| Breakpoint | Layout |
|------------|--------|
| `< 768px` | Sidebar collapses to hamburger, cards stack vertically, tabs become scrollable |
| `768-1024px` | Sidebar narrow (icons only), 2-column card grid |
| `> 1024px` | Full sidebar, 3-column card grid, side panels |

---

## 11. Animations & Micro-interactions

Keep it subtle and purposeful:

- **Page transitions:** Fade-in on route change (CSS `@starting-style` or simple opacity transition)
- **Card hover:** `transform: translateY(-1px)` + shadow increase
- **Agent events:** Slide-in from left with opacity fade (CSS `@keyframes slideIn`)
- **Running state pulse:** Gentle glow animation on status badge
- **Button press:** `transform: scale(0.98)` on active
- **Tab switch:** Content opacity crossfade

---

## 12. Implementation Phases

### Phase 1: Design System Foundation
1. Update `index.css` with new color tokens, font imports, base styles
2. Remove dark mode from `index.html`
3. Update all CVA component variants (button, badge, card, input, textarea)
4. Update `shell.tsx`, `header.tsx`, `sidebar.tsx` with new styling

### Phase 2: Page Layout & Navigation
5. Restyle domain overview page (cards, filters, create modal)
6. Restyle domain detail header and tab navigation
7. Add breadcrumb component

### Phase 3: Agent Panel Revamp
8. Create event type components (`event-text.tsx`, `event-tool-call.tsx`, etc.)
9. Add code syntax highlighting (install `react-syntax-highlighter` or `prism-react-renderer`)
10. Add markdown rendering for text events (install `react-markdown`)
11. Restyle prompt input area (bottom-fixed chat input)
12. Implement event timeline layout with labels and collapsible sections
13. Add agent run history panel

### Phase 4: Section Polish
14. Restyle experiments table
15. Restyle knowledge cards and search
16. Replace custom chart with `recharts`
17. Restyle tools section

### Phase 5: Polish & Responsive
18. Add responsive breakpoints
19. Add micro-animations
20. Cross-browser testing and polish

---

## 13. New Dependencies

| Package | Purpose | Size |
|---------|---------|------|
| `react-syntax-highlighter` | Code blocks in agent events | ~30KB |
| `react-markdown` | Markdown rendering in text events | ~15KB |
| `recharts` | Chart library for metrics | ~50KB |
| `@fontsource/nunito` | Heading font | ~20KB |
| `@fontsource/nunito-sans` | Body font | ~20KB |
| `@fontsource/jetbrains-mono` | Code font | ~15KB |

**Optional:**
| `framer-motion` | Animations | ~30KB |

---

## 14. Files to Modify

| File | Changes |
|------|---------|
| `index.html` | Remove `class="dark"`, add font preloads |
| `src/index.css` | Complete rewrite of color tokens, base styles |
| `src/components/ui/button.tsx` | Update CVA variants |
| `src/components/ui/badge.tsx` | Update CVA variants |
| `src/components/ui/card.tsx` | Update styling |
| `src/components/ui/input.tsx` | Update styling |
| `src/components/ui/textarea.tsx` | Update styling |
| `src/components/ui/tabs.tsx` | Restyle as pill tabs |
| `src/components/shell.tsx` | Layout updates |
| `src/components/header.tsx` | Full restyle |
| `src/components/sidebar.tsx` | Full restyle |
| `src/components/state-badge.tsx` | New color mappings |
| `src/components/domain-card.tsx` | Full restyle |
| `src/components/domain-form.tsx` | Convert to dialog |
| `src/pages/domain-overview.tsx` | Filter tabs, layout |
| `src/pages/domain-detail.tsx` | Header, tab styling |
| `src/components/agent-section.tsx` | Major restructure |
| `src/components/agent-run-view.tsx` | Major restructure |
| `src/components/event-feed.tsx` | **Replace with event timeline + typed components** |
| `src/components/agent-prompt-form.tsx` | Bottom-fixed input |
| `src/components/run-summary.tsx` | Restyle |
| `src/components/experiments-section.tsx` | Table restyle |
| `src/components/knowledge-section.tsx` | Card restyle |
| `src/components/metric-evolution-chart.tsx` | Replace with recharts |
| `src/components/tools-section.tsx` | Restyle |

**New files:**
| File | Purpose |
|------|---------|
| `src/components/event-text.tsx` | TEXT event renderer |
| `src/components/event-tool-call.tsx` | TOOL event renderer with code blocks |
| `src/components/event-tool-result.tsx` | RESULT event renderer |
| `src/components/event-error.tsx` | ERROR event renderer |
| `src/components/event-done.tsx` | DONE/completion renderer |
| `src/components/event-timeline.tsx` | Timeline container |
| `src/components/breadcrumb.tsx` | Breadcrumb navigation |
| `src/components/agent-run-history.tsx` | Run history panel |
| `src/lib/parse-event.ts` | Event content type detection utility |
