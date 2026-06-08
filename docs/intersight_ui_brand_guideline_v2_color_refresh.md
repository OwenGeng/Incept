# InterSight UI Brand Guideline v2
## Color Refresh Edition

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
- freshness comes from button color, status color, and soft support-card tints

This is **not** a glassmorphism system. Avoid heavy blur, translucent shells, and atmospheric purple fog.

### 2.2 Experience goals

Users should feel:

- they are inside a serious internal operating system
- the active project is obvious
- the current page is obvious
- the most important content is immediately visible
- AI is present, but not visually noisy
- the interface feels alive without becoming decorative

---

## 3. Surface Hierarchy

The product uses a strict two-zone workspace.

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

### 3.4 Controlled color energy

The base architecture should remain restrained. Visual energy should come from:

- primary buttons
- active states
- badges and chips
- AI accents
- support-card tints
- chart series
- status markers

Do **not** inject energy through large decorative page backgrounds.

---

## 4. Color System

### 4.1 Primary brand blue

#### Action Blue
- **HEX:** `#2563EB`
- **Usage:** primary buttons, active tabs, important actions, key links, selected emphasis

#### Action Blue Hover
- **HEX:** `#1D4ED8`

#### Action Blue Pressed
- **HEX:** `#1E40AF`

#### Action Blue Soft
- **HEX:** `#EFF6FF`
- **Usage:** active navigation backgrounds, soft active state fills, info chips

#### Action Blue Border
- **HEX:** `#DBEAFE`

### 4.2 Supporting blue range

#### Secondary Blue
- **HEX:** `#4F6EE8`

#### Deep Hero Blue
- **HEX:** `#0F3B84`

#### Hero Mid Blue
- **HEX:** `#1650AE`

#### Hero Bright Blue
- **HEX:** `#2563C9`

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
- **HEX:** `#F8FAFC`

#### Soft Blue Support Surface
- **HEX:** `#F8FBFF`

#### Soft Green Support Surface
- **HEX:** `#F4FBF6`

#### Soft Orange Support Surface
- **HEX:** `#FFF8F1`

These support surfaces are used sparingly to prevent the workspace from feeling flat.

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
- **HEX:** `#16A34A`

#### Success Soft
- **HEX:** `#EDFDF3`

#### Warning
- **HEX:** `#EA580C`

#### Warning Soft
- **HEX:** `#FFF7ED`

#### Error
- **HEX:** `#DC2626`

#### Error Soft
- **HEX:** `#FEF2F2`

#### Info
- **HEX:** `#2563EB`

#### Info Soft
- **HEX:** `#EFF6FF`

### 4.6 AI accent colors

Use violet sparingly and only in small AI-specific places:

#### AI Violet
- **HEX:** `#6366F1`

#### AI Violet Soft
- **HEX:** `#F3F2FF`

#### AI Border
- **HEX:** `#E0E7FF`

Use these on:

- AI badges
- Ask AI icon cues
- AI follow-up labels
- AI suggestion cards

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

Selected sidebar item should feel more intentional than before.

Recommended selection:

- background: `#F7FAFF`
- border: `#D6E4FF`
- text: `#1F2230`
- icon: `#1F2230`
- optional left accent bar: `#2563EB`

Do not rely on blue text alone for selected state.

### 6.3 Live and utility badges

Use small, vivid badges to prevent the sidebar from feeling too static.

#### Live operational badge
- background: `#ECFDF3`
- text: `#15803D`

#### AI live badge
- background: `#EEF2FF`
- text: `#4F46E5`

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

- text color: `#2563EB`
- underline: straight line
- no rounded pill background

Inactive tab:

- text color: `#5C6478`
- hover can tint text, but should stay subtle

---

## 8. Buttons and Controls

### 8.1 Primary button

Use a brighter, cleaner blue than the rest of the document chrome.

- background: `#2563EB`
- hover: `#1D4ED8`
- pressed: `#1E40AF`
- text: `#FFFFFF`
- radius: `12px`
- shadow: `0 2px 8px rgba(37,99,235,0.18)`

Use for `Ask AI`, Apply, Confirm, and main CTAs.

### 8.2 AI primary button

`Ask AI` can use the same blue body but should carry a small AI cue:

- background: `#2563EB`
- text: `#FFFFFF`
- icon accent: `#E0E7FF`
- optional subtle hover edge glow

Do not make the full button purple.

### 8.3 Secondary button

Secondary buttons should be less flat than plain white.

- background: `#F8FAFC`
- border: `#DCE4EE`
- text: `#334155`
- hover background: `#F1F5F9`
- radius: `12px`

### 8.4 Tertiary / ghost action

- background: transparent
- text: `#5C6478`
- hover background: `#F5F8FC`

### 8.5 Inputs and selects

- background: `#FFFFFF`
- border: `#E5E8F1`
- focus ring: pale blue
- placeholder: `#98A2B3`
- keep them crisp and solid, not translucent

---

## 9. Hero / Weekly Brief Card

The large weekly brief card should remain the visual anchor.

Recommended gradient:

- `#0F3B84`
- `#1650AE`
- `#2563C9`

Rules:

- keep text highly readable
- use white or near-white text only on the hero
- use subtle internal borders, not strong glowing outlines
- avoid violet in the main hero background
- use supporting chips inside the hero with translucent white or very light blue treatment

Suggested internal chip style:

- background: `rgba(255,255,255,0.10)`
- border: `rgba(255,255,255,0.18)`
- text: `#FFFFFF`

---

## 10. Data Cards

Standard content cards should no longer all feel identical.

### 10.1 Standard card

Recommended:

- background: `#FFFFFF`
- border: `#E8EDF4`
- shadow: subtle only

### 10.2 Soft emphasis card

Use for support modules, queue explanations, helper blocks, and operational context:

- background: `#F8FBFF`
- border: `#DCE8FA`

### 10.3 AI support card

Use for AI follow-up or recommendation modules:

- background: `#F6F5FF`
- border: `#E2E0FF`

### 10.4 Warning support card

Use for risk or data quality blocks:

- background: `#FFF8F1`
- border: `#F3DFC7`

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
- active links / next actions: `#2563EB`

### 11.1 Row status accents

Use compact functional accents, not loud rows.

#### info row chip
- background: `#EFF6FF`
- text: `#2563EB`

#### success row chip
- background: `#EDFDF3`
- text: `#15803D`

#### warning row chip
- background: `#FFF7ED`
- text: `#C2410C`

#### AI row chip
- background: `#F3F2FF`
- text: `#5B5BD6`

---

## 12. Chart Guidelines

Suggested chart palette:

- primary series: `#2563EB`
- secondary series: `#4F6EE8`
- tertiary series: `#58B97A`
- fourth series: `#F0A24B`
- AI / model comparison series: `#8B5CF6`
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
- AI-related row chips

Avoid:

- violet page backgrounds
- violet sidebars
- violet hero cards
- excessive glow

Principle:

- blue remains the product authority color
- violet remains the small AI intelligence signal

---

## 16. What to Avoid

- decorative glassmorphism
- foggy purple backgrounds
- floating sidebar shells
- floating header cards
- blue text as the only selected-state cue in sidebar
- pill-shaped active tabs
- too many competing surface tones
- making every card tinted

Only a minority of support cards should use tinted surfaces.

---

## 17. Quick Token Reference

```yaml
surface:
  left_rail: "#EEF3F8"
  workspace: "#FFFFFF"
  workspace_soft: "#FCFDFE"
  hover: "#F7F9FC"
  utility: "#F8FAFC"
  support_blue: "#F8FBFF"
  support_green: "#F4FBF6"
  support_orange: "#FFF8F1"
  ai_support: "#F6F5FF"

brand:
  primary: "#2563EB"
  primary_hover: "#1D4ED8"
  primary_pressed: "#1E40AF"
  primary_soft: "#EFF6FF"
  primary_border: "#DBEAFE"
  blue_2: "#4F6EE8"
  hero_1: "#0F3B84"
  hero_2: "#1650AE"
  hero_3: "#2563C9"

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
  soft_blue: "#DCE8FA"
  ai: "#E2E0FF"

semantic:
  success: "#16A34A"
  success_soft: "#EDFDF3"
  warning: "#EA580C"
  warning_soft: "#FFF7ED"
  error: "#DC2626"
  error_soft: "#FEF2F2"
  info: "#2563EB"
  info_soft: "#EFF6FF"

ai:
  accent: "#6366F1"
  tint: "#F3F2FF"
  border: "#E0E7FF"
```

---

## 18. Final Principle

InterSight should feel like a **clean white operating canvas attached to a stable cool-gray navigation rail**, with **blue carrying authority and interaction**, **small supporting tints adding energy**, and **AI expressed through disciplined violet accents rather than heavy themed surfaces**.
