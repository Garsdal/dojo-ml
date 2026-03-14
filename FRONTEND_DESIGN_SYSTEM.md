# Frontend Design System

Reference for all styling decisions in the AgentML frontend.

## Colors

| Token | Hex | Usage |
|-------|-----|-------|
| `--wheat` | `#F5E0B7` | Accent, highlights, active states |
| `--wheat-bg` | `rgba(245,224,183,0.25)` | Page background |
| `--soft-fawn` | `#D6BA73` | Secondary accent, focus borders, hover |
| `--muted-teal` | `#8BBF9F` | Success, completed states, positive indicators |
| `--grey` | `#857E7B` | Muted text, disabled, secondary content |
| `--blackberry` | `#59344F` | Primary text, headings, primary buttons |
| `--white` | `#FEFCF8` | Card backgrounds (warm white) |
| `--surface` | `#FAF3E8` | Header, sidebar, elevated surfaces |
| `--danger` | `#C45D4A` | Errors, destructive actions |

**Background:** `linear-gradient(135deg, rgba(245,224,183,0.15), rgba(250,243,232,0.6))` over `#FEFCF8`. No dark mode.

## Typography

| Role | Font | Weight |
|------|------|--------|
| Headings | Nunito | 700, 800 |
| Body | Nunito Sans | 400, 600 |
| Code | JetBrains Mono | 400, 500 |

**Scale:** Page title `1.75rem/800`, section heading `1.25rem/700`, card title `1rem/600`, body `0.875rem/400`, small `0.75rem/400`.

## Spacing & Shape

- **Radius:** Cards `1rem`, buttons/inputs `0.75rem`, badges `9999px`
- **Shadow:** `0 2px 12px rgba(89,52,79,0.06)`
- **Spacing:** Cards `p-5`, section gaps `gap-5`, page padding `px-6 py-5`

## Component Patterns

### Buttons
- **Primary:** `bg-blackberry text-white hover:bg-blackberry/90 rounded-xl`
- **Secondary:** `bg-wheat/40 text-blackberry hover:bg-wheat/60`
- **Outline:** `border-soft-fawn text-blackberry hover:bg-wheat/20`
- **Destructive:** `bg-danger text-white`
- **Ghost:** `text-grey hover:text-blackberry hover:bg-wheat/20`

### Cards
- `bg-white rounded-2xl border border-soft-fawn/20 shadow-sm`
- Clickable: `hover:shadow-md hover:border-soft-fawn/40 transition-all`

### Inputs
- `bg-white border-soft-fawn/30 rounded-xl focus:ring-2 focus:ring-wheat focus:border-soft-fawn`

### Badges (Status)
| State | Style |
|-------|-------|
| `draft` | `bg-soft-fawn/20 text-soft-fawn` |
| `pending` | `bg-grey/15 text-grey` |
| `running` | `bg-wheat/50 text-blackberry` + pulse |
| `completed` | `bg-muted-teal/20 text-muted-teal` |
| `failed` | `bg-danger/15 text-danger` |
| `archived` | `bg-grey/10 text-grey` |

### Tabs
- Container: `bg-wheat/15 rounded-xl p-1`
- Active: `bg-white rounded-lg shadow-sm text-blackberry font-semibold`
- Inactive: `text-grey hover:text-blackberry`

## Agent Event Rendering

Each event type has a distinct label pill and container:

| Type | Label Style | Container |
|------|-------------|-----------|
| `TEXT` | `bg-wheat/20 text-blackberry` | `border-l-3 border-wheat pl-4`, body font, supports markdown |
| `TOOL` | `bg-blackberry/15 text-blackberry` + wrench icon | Tool name in mono bold, input in syntax-highlighted code block (`bg-blackberry/5 rounded-lg`) |
| `RESULT` | `bg-muted-teal/20 text-muted-teal` + check icon | `bg-muted-teal/5 border border-muted-teal/15 rounded-lg p-4`, auto-detect content type |
| `ERROR` | `bg-danger/15 text-danger` + alert icon | `bg-danger/5 border border-danger/20 rounded-lg`, mono font |
| `DONE` | `bg-muted-teal/20 text-muted-teal` + check icon | `bg-muted-teal/10 border border-muted-teal/20 rounded-xl p-5`, stats row |

- Long content (>6 lines text, >10 lines code/results) is **collapsible** by default
- Code blocks include a language label and copy button
- JSON inputs are pretty-printed
- Events spaced with `gap-3`, optional left timeline line `border-l-2 border-soft-fawn/30`

## Layout

- **Header:** `--surface` bg, bottom border `border-soft-fawn/20`, Nunito 800 logo in `--blackberry`
- **Sidebar:** `--surface` bg, nav items as `rounded-xl px-4 py-2` pills, active `bg-wheat/40`
- **Content:** `max-w-7xl mx-auto`, consistent page header with title + actions right-aligned
- **Agent input:** Fixed bottom, expandable textarea, circular send button `bg-blackberry text-white`

## Responsive Breakpoints

| Width | Behavior |
|-------|----------|
| `< 768px` | Sidebar collapses to hamburger, cards stack, tabs scroll horizontally |
| `768-1024px` | Narrow sidebar (icons only), 2-col card grid |
| `> 1024px` | Full sidebar, 3-col grid, side panels |

## Animations

- Card hover: `translateY(-1px)` + shadow increase
- Agent events: slide-in from left with opacity fade
- Running badge: gentle glow pulse
- Button press: `scale(0.98)` on active
- Tab content: opacity crossfade
