---
name: Lumina Vision
colors:
  surface: '#f8f9ff'
  surface-dim: '#cbdbf5'
  surface-bright: '#f8f9ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#eff4ff'
  surface-container: '#e5eeff'
  surface-container-high: '#dce9ff'
  surface-container-highest: '#d3e4fe'
  on-surface: '#0b1c30'
  on-surface-variant: '#464555'
  inverse-surface: '#213145'
  inverse-on-surface: '#eaf1ff'
  outline: '#777587'
  outline-variant: '#c7c4d8'
  surface-tint: '#4d44e3'
  primary: '#3525cd'
  on-primary: '#ffffff'
  primary-container: '#4f46e5'
  on-primary-container: '#dad7ff'
  inverse-primary: '#c3c0ff'
  secondary: '#565e74'
  on-secondary: '#ffffff'
  secondary-container: '#dae2fd'
  on-secondary-container: '#5c647a'
  tertiary: '#005338'
  on-tertiary: '#ffffff'
  tertiary-container: '#006e4b'
  on-tertiary-container: '#67f4b7'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#e2dfff'
  primary-fixed-dim: '#c3c0ff'
  on-primary-fixed: '#0f0069'
  on-primary-fixed-variant: '#3323cc'
  secondary-fixed: '#dae2fd'
  secondary-fixed-dim: '#bec6e0'
  on-secondary-fixed: '#131b2e'
  on-secondary-fixed-variant: '#3f465c'
  tertiary-fixed: '#6ffbbe'
  tertiary-fixed-dim: '#4edea3'
  on-tertiary-fixed: '#002113'
  on-tertiary-fixed-variant: '#005236'
  background: '#f8f9ff'
  on-background: '#0b1c30'
  surface-variant: '#d3e4fe'
typography:
  display:
    fontFamily: Geist
    fontSize: 3rem
    fontWeight: '600'
    lineHeight: '1.15'
    letterSpacing: -0.03em
  headline-lg:
    fontFamily: Geist
    fontSize: 2rem
    fontWeight: '600'
    lineHeight: '1.25'
    letterSpacing: -0.02em
  headline-lg-mobile:
    fontFamily: Geist
    fontSize: 1.5rem
    fontWeight: '600'
    lineHeight: '1.3'
    letterSpacing: -0.015em
  headline-md:
    fontFamily: Geist
    fontSize: 1.25rem
    fontWeight: '500'
    lineHeight: '1.4'
    letterSpacing: -0.01em
  headline-sm:
    fontFamily: Geist
    fontSize: 1rem
    fontWeight: '500'
    lineHeight: '1.4'
    letterSpacing: -0.005em
  body-lg:
    fontFamily: Inter
    fontSize: 1rem
    fontWeight: '400'
    lineHeight: '1.6'
    letterSpacing: 0em
  body-md:
    fontFamily: Inter
    fontSize: 0.875rem
    fontWeight: '400'
    lineHeight: '1.5'
    letterSpacing: 0em
  body-sm:
    fontFamily: Inter
    fontSize: 0.75rem
    fontWeight: '400'
    lineHeight: '1.5'
    letterSpacing: 0.01em
  label-md:
    fontFamily: Inter
    fontSize: 0.75rem
    fontWeight: '600'
    lineHeight: '1'
    letterSpacing: 0.02em
  code-md:
    fontFamily: JetBrains Mono
    fontSize: 0.8125rem
    fontWeight: '400'
    lineHeight: '1.5'
    letterSpacing: -0.01em
  code-sm:
    fontFamily: JetBrains Mono
    fontSize: 0.6875rem
    fontWeight: '500'
    lineHeight: '1.4'
    letterSpacing: 0em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  gutter: 1.5rem
  gutter-mobile: 0.75rem
  margin: 2rem
  margin-mobile: 1rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 1rem
  space-lg: 1.5rem
  space-xl: 2.5rem
---

## Brand & Style

This design system expresses quiet authority, extreme clarity, and scientific poise. Designed for analytical operators, product engineers, and data teams extracting dense tabular and semantic data from visual documents, the visual language prioritizes high information density without cognitive clutter.

The aesthetic fuses **Modern Technical Minimalism** with **Tactile Precision**:
- **Clarity over decorative noise:** Layouts are structural and utilitarian, drawing immediate focus to the source image and its parsed JSON/tabular outputs.
- **Micro-tactility:** Interactive surfaces feature hairline boundaries (1px) and razor-thin active indicators that mimic physical optical equipment and high-precision instrumentation.
- **Calm, intentional cadence:** The palette avoids aggressive saturation. Color is reserved almost exclusively for extraction confidence scores, actionable states, and critical bounding-box highlights.

## Colors

The system uses a neutral slate baseline to keep visual weight anchored to inspected imagery and structured extraction fields:

- **Primary (`#4F46E5`)**: Deep Electric Indigo. Reserved for the primary conversion path, active canvas inspection tools, selected document tokens, and primary interactive buttons.
- **Secondary (`#0F172A`)**: Deep Slate Black. Used for prominent headers, high-contrast dark badges, code-view backgrounds, and terminal headers.
- **Tertiary (`#10B981`)**: Precision Emerald. Serves strictly as a functional semantic accent for high confidence extractions (>95%), valid field statuses, and verified parsing jobs.
- **Neutral (`#64748B`)**: Slate Gray. Drives borders, disabled states, unselected breadcrumbs, and structural framing.

### Semantic Confidence Tokens
- **High Confidence (90-100%):** Background `#ECFDF5`, text/stroke `#059669`.
- **Medium Confidence (70-89%):** Background `#FFFBEB`, text/stroke `#D97706`.
- **Low Confidence (<70%):** Background `#FEF2F2`, text/stroke `#DC2626`.

### Dark Mode Transitions
In dark mode, the canvas background shifts to `#090D16` (Obsidian Slate), surfaces elevate to `#0F172A`, borders adjust to `#1E293B`, and the primary indigo lifts to `#6366F1` to maintain WCAG AAA luminance against deep backgrounds.

## Typography

The type hierarchy coordinates structural geometric headings with a neutral, highly legible reading text and dedicated monospaced tokens:

- **Headlines (Geist):** Tight letter tracking (`-0.02em` to `-0.03em`) creates a disciplined, modern software footprint suited for document headings and dashboard metrics.
- **Body & Controls (Inter):** Highly uniform vertical metrics allow predictable alignment across complex tabular data displays and form-heavy toolbars.
- **Data & Extracted Keys (JetBrains Mono):** Dedicated to extracted key-value pairs, coordinate displays, regex patterns, raw JSON previews, and confidence metric tags.

## Layout & Spacing

The layout is built for desktop-first analytical workflows utilizing a split-pane workstation paradigm:

- **Desktop Workstation (>= 1280px):** Fixed-width left navigation (64px collapsed, 240px expanded), an interactive zoom/pan viewport (flexible 50-60% width), and a structured tabular/chat panel on the right (40-50% width).
- **Tablet Reflow (768px - 1279px):** Stacks the preview canvas and data inspection drawer into vertical split view with a draggable divider bar.
- **Mobile Handheld (< 768px):** Switches to a segmented tabbed interface (View Canvas / Parsed Data / Prompt Chat) with compact `0.75rem` margins.

Content uses an 8px baseline rhythm (`0.5rem`, `1rem`, `1.5rem`, `2.5rem`), reserving `0.25rem` micro-steps exclusively for internal badge padding, button insets, and key-value pairings.

## Elevation & Depth

Visual hierarchy uses **hairline structural borders combined with restrained micro-shadows** to avoid visual heaviness:

- **Level 0 (Base Canvas):** Background `#F8FAFC` (Dark: `#090D16`), flat with zero elevation.
- **Level 1 (Panels & Workspaces):** Pure white `#FFFFFF` (Dark: `#0F172A`) backed by a 1px border (`#E2E8F0` / Dark: `#1E293B`) and an ambient micro-shadow: `0 1px 3px 0 rgba(15, 23, 42, 0.04), 0 1px 2px -1px rgba(15, 23, 42, 0.03)`.
- **Level 2 (Interactive Floating Tools & Popovers):** Used for viewport zoom bars, annotation tooltips, and column filters. Shadow: `0 4px 6px -1px rgba(15, 23, 42, 0.07), 0 2px 4px -2px rgba(15, 23, 42, 0.05)`, border: `#CBD5E1`.
- **Level 3 (Modals & Overlays):** Used for schema builders and full-screen export previews. Shadow: `0 20px 25px -5px rgba(15, 23, 42, 0.12), 0 8px 10px -6px rgba(15, 23, 42, 0.08)`.

## Shapes

The system uses crisp, subtle corner radii (`roundedness: 1`, `0.25rem` / 4px base):

- **Data cells, text inputs, segmented pills:** 4px radius (`0.25rem`) to maintain precision and dense structural grid integrity.
- **Cards, preview viewports, dialogs:** 8px radius (`0.5rem`) for perimeter edges, balancing software utility with clean ergonomics.
- **Confidence pills & tag indicators:** Retain a subtle 4px corner to match technical code aesthetics rather than rounded pills.

## Components

### Buttons
- **Primary:** Solid `#4F46E5` background, `#FFFFFF` text, 1px subtle top highlight `rgba(255, 255, 255, 0.2)` inset, hover background `#4338CA`. Height: 36px for desktop dense view, 44px on mobile.
- **Secondary / Outline:** Background `#FFFFFF`, 1px border `#E2E8F0`, text `#0F172A`. Hover background `#F8FAFC` with border `#CBD5E1`.
- **Ghost Tool Buttons:** Borderless, text `#64748B`, hover background `#F1F5F9` and text `#0F172A` (used for image pan, crop, and zoom triggers).

### Input Fields & Extraction Prompts
- Single-line and multi-line fields feature a 1px `#E2E8F0` border, `#FFFFFF` fill, `#0F172A` text, and `#94A3B8` placeholder.
- Focus state removes default browser outlines, replacing them with a crisp 1px `#4F46E5` border accompanied by an indigo ring glow: `0 0 0 3px rgba(79, 70, 229, 0.15)`.

### Cards & Parsed Entity Containers
- Framed in 1px `#E2E8F0`, interior surface `#FFFFFF`.
- Header areas feature a muted secondary background `#F8FAFC`, a 1px bottom border, and monospaced schema property names (`JetBrains Mono`, `0.8125rem`).

### Confidence Badges & Chips
- Compact, monospaced numeric scores (`label-font`).
- Standardized format: `98.4%` with a fixed status dot (6px circle).
- Styling conforms strictly to the semantic color tokens, using low-saturation tinted backgrounds and solid, accessible text tokens.

### Image Annotation Overlays
- Document extraction boxes use a 1.5px stroke in `#4F46E5` with an internal fill of `rgba(79, 70, 229, 0.08)`.
- Active or hovered bounding boxes display an anchor pill in `#4F46E5` containing the field key and confidence score in `#FFFFFF`.