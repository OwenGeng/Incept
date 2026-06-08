# InterSight UI Brand Guideline

## 1. Product Positioning

**InterSight** is an internal BI and AI operating workspace. It is not a marketing site, not a decorative concept board, and not a generic SaaS dashboard. The interface should feel:

- calm
- operational
- premium
- trustworthy
- dense enough for repeated internal use
- AI-native without looking experimental

The product is primarily used to:

- review weekly business status
- inspect ranked company and app queues
- validate evidence behind those queues
- trigger AI-assisted follow-up and operational actions

---

## 2. Visual Direction

### 2.1 Design intent

The current direction is **structured split-surface workspace UI**:

- the left side is a stable navigation rail
- the right side is a clean white working canvas
- hierarchy comes from surface contrast, spacing, and typography
- blue is the primary action and insight color
- violet is reserved for small AI cues only

This is **not** a glassmorphism system anymore. Avoid heavy blur, translucent shells, and atmospheric purple fog.

### 2.2 Experience goals

Users should feel:

- they are inside a serious internal operating system
- the active project is obvious
- the current page is obvious
- the most important content is immediately visible
- AI is present, but not visually noisy

---

## 3. Surface Hierarchy

The product now uses a strict two-zone workspace.

### 3.1 Left navigation zone

The full left zone, including sidebar background, should use:

- **RGB:** `238, 243, 248`
- **HEX:** `#EEF3F8`

This area should read as a continuous navigation rail, not as a floating card.

### 3.2 Right working zone

The full right zone should use:

- **RGB:** `255, 255, 255`
- **HEX:** `#FFFFFF`

This area is the main work surface. It should fill top-to-bottom without exposing another background behind it.

### 3.3 Global page background

Do not introduce a third visible atmospheric layer around the main workspace. The left zone itself acts as the page background on the left, and the right zone acts as the working background on the right.

---

## 4. Color System

### 4.1 Primary brand blue

#### Action Blue
- **HEX:** `#1855B8`
- **Usage:** primary buttons, active tabs, important actions, key links, selected emphasis

#### Action Blue Hover
- **HEX:** `#164CA4`

#### Action Blue Soft
- **HEX:** `#EDF4FF`
- **Usage:** active navigation backgrounds, soft active state fills

#### Action Blue Border
- **HEX:** `#D6E4FF`

### 4.2 Supporting blue range

#### Secondary Blue
- **HEX:** `#4F6EE8`

#### Deep Hero Blue
- **HEX:** `#0F3B84`

#### Hero Mid Blue
- **HEX:** `#1650AE`

#### Hero Bright Blue
- **HEX:** `#1C63D3`

These blues are primarily for:

- hero summary cards
- KPI emphasis
- charts
- active states

### 4.3 Neutral structure palette

#### Left Rail Background
- **HEX:** `#EEF3F8`

#### App White
- **HEX:** `#FFFFFF`

#### App White Soft
- **HEX:** `#FCFDFE`

#### Soft Gray Border
- **HEX:** `#E3E8F0`

#### Card Border
- **HEX:** `#E8EDF4`

#### Hover Surface
- **HEX:** `#F7F9FC`

#### Soft Utility Surface
- **HEX:** `#F7FAFC`

### 4.4 Text colors

#### Primary Text
- **HEX:** `#1F2230`

#### Secondary Text
- **HEX:** `#5C6478`

#### Tertiary Text
- **HEX:** `#8B92A8`

#### Quiet Label Text
- **HEX:** `#98A2B3`

#### Inverse Text
- **HEX:** `#FFFFFF`

### 4.5 Semantic colors

#### Success
- **HEX:** `#2FA66A`

#### Warning
- **HEX:** `#E59A2F`

#### Error
- **HEX:** `#D85C5C`

### 4.6 AI accent colors

Use violet sparingly and only in small AI-specific places:

#### AI Violet
- **HEX:** `#6366F1`

#### AI Soft Surface
- **HEX:** `#F2F6FD`

Do **not** use violet as a major page background, sidebar color, or hero gradient base.

---

## 5. Layout Principles

### 5.1 Workspace split

The app should read as:

1. left navigation rail
2. right content workspace

The left and right regions should feel integrated, but not identical.

### 5.2 Navigation should be flat

Sidebar and page header are **not** floating cards.

Avoid:

- heavy blur
- detached glass shells
- oversized shadows on navigation surfaces
- large outer cards around the whole header

Use:

- flat sections
- divider lines
- restrained padding
- subtle active fills

### 5.3 Data surfaces remain cards

Tables, KPI blocks, highlight cards, and supporting modules can remain card-based inside the white workspace.

---

## 6. Sidebar Guidelines

### 6.1 Sidebar behavior

The sidebar should feel like a fixed workspace rail.

Rules:

- background stays `#EEF3F8`
- right edge divider defines the split
- no floating shell effect
- no visible outer card around the entire sidebar

### 6.2 Sidebar selection state

Selected sidebar item:

- soft blue background
- dark text, not blue text
- stronger font weight

Recommended selection:

- background: `#F7FAFF`
- border: `#D6E4FF`
- text: `#1F2230`
- icon: `#1F2230`

Do not rely on blue text alone for selected state.

---

## 7. Header and Tab Guidelines

### 7.1 Page header

The page header is part of the white workspace.

Rules:

- no floating header card
- use bottom divider line
- title and subtitle align with content grid
- controls sit on the right in a clean utility row

### 7.2 Tabs

Tabs such as `Weekly Brief`, `Top Lists`, and `Detailed Analysis` should be flat text tabs.

Active tab:

- text color: `#1855B8`
- underline: straight line
- no rounded pill background

Inactive tab:

- text color: `#5C6478`
- hover can tint text, but should stay subtle

---

## 8. Buttons and Controls

### 8.1 Primary button

- background: `#1855B8`
- hover: `#164CA4`
- text: `#FFFFFF`
- radius: `12px`
- use for `Ask AI`, Apply, Confirm, and main CTAs

### 8.2 Secondary button

- background: `#FFFFFF`
- border: `#E5E8F1`
- text: `#1F2230`

### 8.3 Inputs and selects

- background: `#FFFFFF`
- border: `#E5E8F1`
- focus ring: pale blue
- keep them crisp and solid, not translucent

---

## 9. Hero / Weekly Brief Card

The large weekly brief card should remain the visual anchor.

Recommended gradient:

- `#0F3B84`
- `#1650AE`
- `#1C63D3`

Rules:

- keep text highly readable
- use white or near-white text only on the hero
- use subtle internal borders, not strong glowing outlines
- avoid violet in the main hero background

---

## 10. Data Cards

Standard content cards should use:

- white background
- soft border
- restrained shadow

Recommended:

- background: `#FFFFFF`
- border: `#E8EDF4`
- shadow: subtle only

Cards should feel cleaner than the navigation layer, because the work happens here.

---

## 11. Table Guidelines

Top Lists is a real operating table, not a decorative block.

Tables should support:

- sorting
- filtering
- search
- clear row hover
- stable headers

Colors:

- header text: `#8B92A8`
- row text: `#1F2230` / `#5C6478`
- row hover: `#F4F7FB`
- active links / next actions: `#1855B8`

---

## 12. Chart Guidelines

Suggested chart palette:

- primary series: `#1855B8`
- secondary series: `#4F6EE8`
- tertiary series: `#58B97A`
- fourth series: `#F0A24B`
- supporting neutral series: `#CBD2E6` or `#5D708F`

Gridlines should remain light and quiet.

---

## 13. Typography

### 13.1 Font

- Primary UI font: **Inter**

### 13.2 General rules

- Avoid pure black
- Use weight and spacing to create hierarchy
- Dense analytical text should still have comfortable line-height
- KPI numbers should dominate their cards

### 13.3 Type scale

- Page title: `28-30px`
- Section title: `18-20px`
- Card label: `12-14px`
- Body: `14-15px`
- KPI large: `36-42px`

---

## 14. Elevation and Borders

### 14.1 Navigation surfaces

- mostly flat
- rely on fills and dividers
- avoid heavy shadow

### 14.2 Content cards

- light shadow only
- one clean border

### 14.3 Outer workspace

- if an outer shell exists, it must remain subtle
- avoid obvious floating stage effects

---

## 15. AI Styling Rules

AI should be visible but controlled.

Use AI accent styling on:

- `Ask AI` button
- small badges
- AI follow-up cards
- insight labels

Avoid:

- violet page backgrounds
- violet sidebars
- violet hero cards
- excessive glow

---

## 16. What to Avoid

- decorative glassmorphism
- foggy purple backgrounds
- floating sidebar shells
- floating header cards
- blue text as the only selected-state cue in sidebar
- pill-shaped active tabs
- too many competing surface tones

---

## 17. Quick Token Reference

```yaml
surface:
  left_rail: "#EEF3F8"
  workspace: "#FFFFFF"
  workspace_soft: "#FCFDFE"
  hover: "#F7F9FC"
  utility: "#F7FAFC"

brand:
  primary: "#1855B8"
  primary_hover: "#164CA4"
  primary_soft: "#EDF4FF"
  primary_border: "#D6E4FF"
  blue_2: "#4F6EE8"
  hero_1: "#0F3B84"
  hero_2: "#1650AE"
  hero_3: "#1C63D3"

text:
  primary: "#1F2230"
  secondary: "#5C6478"
  tertiary: "#8B92A8"
  quiet: "#98A2B3"
  inverse: "#FFFFFF"

border:
  rail_divider: "#E3E8F0"
  card: "#E8EDF4"
  soft: "#E5E8F1"

semantic:
  success: "#2FA66A"
  warning: "#E59A2F"
  error: "#D85C5C"

ai:
  accent: "#6366F1"
  tint: "#F2F6FD"
```

---

## 18. Final Principle

InterSight should feel like a **clean white operating canvas attached to a stable cool-gray navigation rail**, with **blue carrying authority and interaction**, and **AI expressed through small, disciplined accents**.
