# The suite design system

The six products in `MVP/` are built for one distributor, Hengtai Industrial
Supply. They share one design system so a person moving between them sees one
operations suite.

**The single source of truth is `QuoteAgent/frontend/src/design/` plus this
file.** The other five products are self-contained (no shared package), so
each one carries a copy of the folder. Change the system here first, then copy
the folder again; never fork a copy.

```
frontend/src/design/
  tokens.css         every colour, type, shape and motion variable; the six accents
  components.css     every ds-* class: bands, cards, buttons, chips, header, feed,
                     chain, rail, meter, tabs, tables, trace sheet
  fonts.ts           Poppins and JetBrains Mono, bundled with next/font/local
  fonts/             the woff2 files and their SIL Open Font Licences
  motion.ts          easing, useInView, useReducedMotion, useScrollProgress
  canvas.ts          Canvas 2D helpers: glowing node, solid line, comet, seeded random
  Constellation.tsx  the signature canvas (nodes, links, pulses, pointer)
  Reveal.tsx         reveal on view, with stagger
  CountUp.tsx        numbers that count up, exact on the last frame
  LiveFeedCard.tsx   "LIVE ..." card cycling real records
  ScrollHeader.tsx   fixed header, scroll progress, mobile menu
  StatusChip.tsx     solid status chips and the live dot
  NodeChain.tsx      vertical chain of nodes with a travelling pulse
  StepRail.tsx       a record's lifecycle, left to right (vertical on phones)
  Meter.tsx          a bar that fills on view, with a pass mark
  Tabs.tsx           tabs with a sliding indicator and arrow-key navigation
  TraceSheet.tsx     the panel every clickable number opens
  Surface.tsx        Band, Card, Button, LinkButton, Stat, Banner, Empty, Stamp
  index.ts           one import for all of the above (fonts excepted)
```

No dependencies beyond Next.js and React. Tailwind 4 is optional: the
components style themselves through `components.css`, and `tokens.css` also
maps the colours into Tailwind (`bg-ink`, `text-accent-ink`, `border-line`).

---

## 1. The look

| Element | Value |
|---|---|
| Ink bands (hero, page tops, closing band, trace head) | `#0D1B1B` |
| Heading ink on light | `#021318` |
| Work surface (page) | `#FAF8F5` warm off-white; cards `#FFFFFF` with a 1px `#E7E2DA` line |
| QuoteAgent accent | orange `#F86F11`; text on light `#AD4700` (5.4:1) |
| Face | Poppins 300, 400, 500, 600, 700 for headings and interface |
| Data face | JetBrains Mono for labels, part numbers, timestamps, formulas, money columns |
| Corners | buttons and inputs square (0); cards 4px; chips 3px |
| Cards | white, 1px line, a short accent rule on the left edge |

Each product presents itself only under its own name, for Hengtai Industrial
Supply. No vendor names, no "demo" framing, no sales copy anywhere on screen.

### Accents

| Product | Accent |
|---|---|
| QuoteAgent | orange `#F86F11` |
| LedgerFlow | emerald `#10B981` |
| StockSense | cobalt `#2F6BFF` |
| FrontDeskAI | coral `#FF6B4A` |
| PortalBot | violet `#8B5CF6` |
| OpsAgent | teal `#14B8A6` |

---

## 2. Tokens

All variables are on `:root` in `tokens.css`. Use the variables, never the hex
values, in product code.

### Ink and surfaces

| Variable | Value | Use |
|---|---|---|
| `--ds-ink` | `#0D1B1B` | bands, trace head, stamps, formulas |
| `--ds-ink-2` / `-3` | `#132424` / `#1B2E2E` | cards and hover on a band |
| `--ds-ink-line` | `#283B3B` | 1px lines on a band |
| `--ds-ink-text` / `-muted` / `-faint` | `#F6F3EE` / `#A3AFAE` / `#8A9897` | text on a band (muted 7.8:1, faint 5.9:1) |
| `--ds-page` | `#FAF8F5` | the work surface |
| `--ds-surface` | `#FFFFFF` | cards |
| `--ds-sunk` | `#F2EFEA` | insets, tracks |
| `--ds-line` / `-strong` | `#E7E2DA` / `#CFC8BD` | 1px borders |
| `--ds-text` / `-2` / `-3` | `#021318` / `#4A5656` / `#5F6B6A` | text on light (7.2:1 and 5.2:1 for the lighter two) |

### Semantic colours (the same in every product)

| Verdict | Fill | Text on light | Soft | Used for |
|---|---|---|---|---|
| pass | `#22C55E` | `#157A41` | `#DCF5E5` | met, won, approved, priced |
| fail | `#F2555A` | `#C2262B` | `#FDE3E3` | below the bar, lost, rejected, re-opened |
| warn | `#F5A524` (amber, kept clear of the orange accent) | `#8F5300` | `#FFF1D6` | waiting, draft, needs a person |
| info | `#5F6B6A` | `#4A5656` | `#EEEBE5` | neutral facts |

A chip on a band is a solid fill with dark ink text; on a white card it is the
soft tint with the text colour. Always with a word: colour is never the only
signal.

### The product accent (one block per product)

| Product | `--ds-accent` | `--ds-accent-ink` (on light) | `--ds-on-accent` | `--ds-accent-rgb` | `--ds-accent-hi` (nodes on ink) |
|---|---|---|---|---|---|
| QuoteAgent | `#F86F11` | `#AD4700` | `#0D1B1B` | `248, 111, 17` | `#FF9A4D` |
| LedgerFlow | `#10B981` | `#047857` | `#0D1B1B` | `16, 185, 129` | `#4EE0AE` |
| StockSense | `#2F6BFF` | `#1D4ED8` | `#FFFFFF` | `47, 107, 255` | `#7AA2FF` |
| FrontDeskAI | `#FF6B4A` | `#B93A12` | `#0D1B1B` | `255, 107, 74` | `#FF9A82` |
| PortalBot | `#8B5CF6` | `#6D28D9` | `#0D1B1B` | `139, 92, 246` | `#B294FF` |
| OpsAgent | `#14B8A6` | `#0F766E` | `#0D1B1B` | `20, 184, 166` | `#5BE3D3` |

Plus `--ds-accent-soft` (solid tint) and `--ds-accent-line` (accent border).
Every accent text colour is at least 4.5:1 on the page colour. A product
selects its block with `data-product` on `<html>`; QuoteAgent's is the
default in `:root`.

### Type

| Class | Face | Use |
|---|---|---|
| `.ds-display` | Poppins 600, tight tracking | band titles, hero (a second line in 300 light for contrast) |
| `.ds-title` | Poppins 600 | section headings |
| `.ds-card-title` | Poppins 600, 16px | card titles |
| `.ds-mono-label` | JetBrains Mono 11px, uppercase, 0.14em | every field name and eyebrow |
| `.ds-num` | tabular figures where the face has them | any column of numbers; right-aligned table cells are set in the mono, because Poppins figures are proportional |
| `.ds-stat-value` | Poppins 600, 28-38px | big numbers on a band |

### Shape and motion

`--ds-radius` 4px (cards), `--ds-radius-sm` 3px, `--ds-radius-chip` 3px,
`--ds-radius-control` 0 (buttons and inputs are square). The header is
`--ds-header-bar` (64px), plus `--ds-header-top` (0 by default) when the
optional strip above it is used.

`--ds-ease` is expo-out `cubic-bezier(0.16, 1, 0.3, 1)`; entrances run
`--ds-reveal-duration` 800ms over `--ds-reveal-y` 32px with a 70ms stagger.

---

## 3. Components

All client components live in `src/design` and are imported from
`@/design/<File>` (or `@/design`).

| Component | What it does | Key props |
|---|---|---|
| `Band` | Ink band; `top` runs it up behind the fixed header; `canvas` draws behind | `top`, `canvas` |
| `Card` | White card, 1px line, short accent rule on the left edge; `tone="accent"` makes the rule full height | `eyebrow`, `title`, `subtitle`, `action`, `flush`, `tone` |
| `Button`, `LinkButton` | Square buttons: `primary` (accent), `secondary`, `ink` (on a band), `danger`, `ghost` | `tone`, `size`, `busy`, `arrow` |
| `Stat` | Big number with a mono label, for bands | `label`, `value`, `unit`, `tone` |
| `StatusChip`, `LiveDot` | Solid chip with an optional beating dot | `tone`, `pulse`, `surface`, `size` |
| `Constellation` | The signature canvas: drifting glowing nodes, solid links that fade with distance, an ambient field, pulses along links, pointer lines | `nodes`, `links`, `traffic`, `ambient`, `surface`; handle `pulse(path)`, `flash(id)` |
| `LiveFeedCard` | "LIVE ..." card: chip, mono timestamp, title, progress dashes that drive the timing | `title`, `source`, `items`, `interval`, `onIndex` |
| `ScrollHeader` | Fixed header; transparent over the band, solid once scrolled; accent scroll bar; folding menu under 1260px; optional strip above | `brand`, `nav`, `status`, `actions`, `topLine` |
| `Reveal` | Rise on view with stagger; works on table rows (`as="tr"`) | `index`, `y`, `from`, `as` |
| `CountUp` | Counts up when seen; the last frame is the exact text given | `to`, `final`, `decimals` |
| `NodeChain` | Vertical chain: the line fills, items rise, a pulse runs down and rings each node | `items`, `live`, `fill` |
| `StepRail` | Lifecycle rail: done steps filled, the current one rings, a pulse runs into it | `steps`, `current`, `tone` |
| `Meter` | Bar that fills on view, with a pass mark | `value`, `mark`, `markLabel`, `tone` |
| `Tabs` | Tabs with a sliding indicator, arrow keys, Home and End | `tabs`, `value`, `onChange` |
| `TraceSheet` | Slides in from the right; ink head with the figure and a small constellation of the sum; steps on a node chain; inputs light up in turn | `heading`, `figure`, `steps`, `closing`, `onClose`, `onExited` |

### Every number opens

The rule "every number can be clicked" is carried by the product, not the
design system: each product wraps `TraceSheet` in its own provider and figure
button (QuoteAgent's is `src/components/trace.tsx`), because only the product
knows where its numbers come from. The pattern:

- A figure is a `<button class="ds-figure">`: underlined in the accent, a
  tint on hover, filled with the accent while its sheet is open. The table row
  holding it lights up too (`tr:has(.ds-figure[data-open])`).
- A computed figure passes the server's own trace (steps, formula, inputs,
  sources). A counted figure passes an `explain`: the rule in words, and the
  records it was counted from.
- The sheet's foot says what produced the figure ("From the pricing engine",
  "Counted by the server", "Measured by the evaluation").
- Codes in the server's wording (`key_account`) are shown as words.

---

## 4. Motion rules

- **Alive, not subtle.** Every screen has a living element: a constellation,
  a chain with a travelling pulse, a live feed, count-ups, bars that fill.
- **Connections are thin solid lines.** Motion is glowing nodes travelling
  along them, nodes lighting in sequence, slow orbit and drift, and the
  pointer drawing a line to the nearest nodes. **No dashed or dotted lines
  with moving dots, anywhere.**
- Entrances: expo-out, 0.5 to 0.9 s, 24 to 40 px of travel, 60 to 90 ms
  stagger. Count-ups 1.2 to 1.4 s.
- Only `transform` and `opacity` are animated.
- Loops pause off screen (IntersectionObserver) and in a background tab.
- **prefers-reduced-motion**: loops stop, entrances are instant, count-ups
  show the final figure, every canvas draws one still frame with all nodes in
  their final state. Everything still works and still opens.
- Solid colours only: no gradients, no glass, no glow haze. Glow is only on
  small canvas nodes.

---

## 5. Page anatomy

1. Header (64px): brand, navigation, which engine is active, account.
2. A top `Band` with an eyebrow, a display title (second line in the
   accent), a plain lede, actions, and the page's living element.
3. The work surface (`.ds-work`): white cards on warm paper, mono labels,
   ledgers with a coloured mark per row.
4. Where it helps, a closing ink band that points to the next thing to do in
   the product (QuoteAgent's overview points to the walkthrough and the
   acceptance check). Never sales copy.
5. Footer: the product, and the six products of the suite.

Every product also keeps the suite's rules on screen: plain words only (no
abbreviations), a guided first run with visible progress, the engine that
produced each result named, and pass or fail measured and shown with the
misses.

---

## 6. Adopting it in another product

1. **Copy the folder.** Copy `QuoteAgent/frontend/src/design/` to
   `<Product>/frontend/src/design/`, unchanged.
2. **Import the styles.** At the top of `src/app/globals.css`:

   ```css
   @import "tailwindcss";
   @import "../design/tokens.css";
   @import "../design/components.css" layer(components);
   ```

   Product-specific classes go below, inside `@layer components`, prefixed
   with the product's own short name.
3. **Fonts and accent.** In `src/app/layout.tsx`:

   ```tsx
   import { fontVariables } from "@/design/fonts";
   <html lang="en" data-product="ledgerflow" className={fontVariables}>
   ```

   `data-product` picks the accent block in `tokens.css`. Nothing else in
   `tokens.css` changes.
4. **The shell.** Use `ScrollHeader`, a `<div className="ds-header-spacer" />`
   before `<main>`, and an ink footer after it (see QuoteAgent's
   `src/components/shell.tsx`).
5. **Every page opens on a `Band top`**, with an eyebrow naming the product
   and Hengtai Industrial Supply.
6. **Numbers open.** Wrap `TraceSheet` in the product's own provider and
   figure button (copy QuoteAgent's `components/trace.tsx` and adapt
   `toSteps` to the product's trace shape).
7. **The signature.** Build the product's own constellation scene from real
   data with `Constellation` (QuoteAgent's is the quote-assembly canvas in
   `components/quote-assembly.tsx`): nodes from the product's records, pulses
   for the work it does, the accent for what matters.
8. **Check** at 1440 and 390 wide: no sideways scroll, keyboard reaches every
   control, reduced motion shows a still frame, no console errors.

To change the system: change it in QuoteAgent, update this file, then copy
the folder to the other products again.

---

## 7. Accessibility

- Text colours on light meet 4.5:1 on the page colour; text on ink meets at
  least 5.3:1. Accent fills carry dark ink text (6.1:1 on the QuoteAgent orange).
- Focus is a 2px outline in the accent text colour (the accent on bands).
- Tabs, the menu, the account menu and the trace sheet work from the
  keyboard; Escape closes them and focus returns to what opened them.
- Canvases are decorative to screen readers unless given a `label`; the same
  facts are always on the page as text. Count-ups expose only the final value.
