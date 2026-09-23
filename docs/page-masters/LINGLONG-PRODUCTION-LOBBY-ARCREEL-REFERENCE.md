# Linglong Production Lobby — reference-led visual plan

> Status: the earlier darkroom and lens-light candidates are rejected. The approved structural
> reference is the supplied ArcReel lobby composition only. The new target is a high-fidelity
> **light** Linglong lobby using the existing Image module’s white/charcoal visual system.

## Reference palette record

Source: `codex-clipboard-8369df37-a08e-44ce-a7b9-41a3abcd345e.png`.
Observed values are recorded in [ARCREEL-LOBBY-REFERENCE-palette.json](./ARCREEL-LOBBY-REFERENCE-palette.json) and are not yet global Linglong brand tokens.

| Observed color | Observed role | Approx. share / use budget |
| --- | --- | --- |
| `#0F1217` | Main darkroom canvas | 65–72% |
| `#17191E` | Header, featured-card and elevated surface | 15–20% |
| `#090B0F` | Recessed search/control fields | up to 5% |
| `#232432` / `#4C495D` | Hairlines, inactive controls and muted data | up to 8% |
| `#FFFFFF` | Editorial display type and primary content | under 4% |
| `#494E00`, `#3E4400`, `#2A3300`, `#6B6C00` | Original Linglong project-cover grid gradient only | cover art only |
| lavender, adapted from the observed pale purple control state | Create/open CTA and active filter only | under 3% |

## Direct observations

- A fixed, 72px dark header spans the page. It contains a left-aligned mark and product name, a wide recessed search field, then utility actions and one lavender primary action.
- The content begins with a very large editorial greeting: upright serif line followed by italic serif line. A compact operational sentence sits beneath it.
- A five-cell status ledger is aligned to the right of the greeting, with mono uppercase labels and large narrow figures.
- Filter pills occupy a dedicated horizontal row below a hairline divider. The sort treatment is tiny mono text at the far right.
- `NOW EDITING` is a short mono eyebrow above one dominant, wide project card—not a grid of equal SaaS cards.
- The featured card is split: a 56% project cover on the left and an information/action column on the right. The cover is a low-saturation grid treatment with large editorial project type; it must use original Linglong artwork, not ArcReel art.
- Typography contrasts an editorial display face for greeting/project title with a technical mono face for labels, figures, filters, status, and metadata. Body copy stays quiet and sparse.
- Borders are hairlines. Corners are modest (roughly 12–16px for the feature card, 8px for controls). Shadows are nearly absent; separation comes from luminosity and outlines.

## Superseded directions

`LINGLONG-PRODUCTION-LOBBY-DARKROOM-v1.png` and `LINGLONG-PRODUCTION-LOBBY-LENS-LIGHT-v1.png`
are retained only as rejected design history. They are not implementation references.

## Adapted Linglong direction — Image module light system

**Visual thesis:** a bright, high-energy production library with the same editorial hierarchy and
single-project focus as the supplied reference, built from Linglong Image’s clean white workspace,
charcoal primary controls and restrained gray structure.

### Adopted Image module UI tokens

These are the live Image module tokens and take precedence for this page: canvas/card `#FFFFFF`,
secondary surface `#FAFBFC`, muted fill `#F6F8FB`, primary text `#101318`, primary button
`#171A20`, muted text `#5F6673`, border `#E6E8EC`, strong border `#D7DBE2`, and optional small
blue interactive accent `#356FEC` / `#F2F6FF`.

- White owns canvas and cards; `#FAFBFC` owns the header/search wells and secondary bands.
- `#171A20` is the sole filled CTA and selected-filter color.
- The optional Image blue may occur only as small icon/highlight detail, never as a gradient or
  filled main action.

### Confirmed typography

- `PP Mori Regular` is the supplied brand typeface and is the UI/body foundation.
- The page’s high-energy character comes from scale, sharp line breaks, editorial contrast,
  uppercase mono labels, and lens intersections—not from substituting an unrelated display font.

### Fixed shell

1. Header: Linglong mark/name, `Search productions`, Asset library, optional Import library action, `Create production`, utility icons.
2. Image module white canvas, pale-gray secondary surfaces and delicate neutral dividers.
3. A lively, expressive display typeface for greeting/project title; technical mono only for labels/status/metadata; a high-energy Linglong sans for body and buttons.
4. Charcoal is the sole filled primary action/link treatment; Image-blue is a small optional detail only.

### Page composition

1. Header.
2. Greeting + five-cell production ledger.
3. Filter/sort strip.
4. `PICK UP WHERE YOU LEFT OFF · NOW EDITING` eyebrow.
5. One featured production card: original Linglong grid cover, title, type/style, stage progress, three data cells, `Open workspace` CTA.
6. `ALL PRODUCTIONS · LIBRARY` list below the fold using compact dark rows; no white cards, gradients, or marketing tiles.

### Content mapping

- `Preparation`, `Script`, `Production`, and `Completed` map to Linglong’s persisted production states; no fictional metrics.
- Cover art is generated only from each Linglong project title/type and original restrained mono/gray geometry. It contains no ArcReel logo, `now` wordmark, project title, copied text, or screenshots.
- The lobby keeps commercial video, original short drama, repair, and CTV composition as production types. Novel adaptation remains absent.

### Explicit exclusions

- No ArcReel logo, triangle mark, copy, asset-library icon treatment, imported project names, photos, source code, or cover artwork.
- No existing white Linglong dashboard shell, purple-on-white cards, three marketing capability cards, generic analytics/dashboard tiles, or large rounded SaaS cards.
- No teal/green/yellow lens gradient, no purple controls, no arbitrary gradients, and no darkroom canvas.

## Candidate master constraints

- Desktop 2048 × 976 inner viewport; Chinese product copy with English technical labels is permitted.
- The page master is a production-library state with six Linglong projects and one featured CTV project.
- Preserve the observed dark palette record, hierarchy, density and composition; adapt all identity/content to Linglong.
