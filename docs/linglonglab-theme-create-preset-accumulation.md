# LinglongLab Theme Create Preset Accumulation

## Purpose

This document defines how `Theme Create` Feature 2 output should be accumulated into reusable product assets for Feature 1.

The goal is to turn one-off strong creative explorations into:

- a structured `style report`
- a reusable `preset`
- a repeatable GM backend workflow

This is the first platformization layer for Theme Create.

## Product Direction

Feature 2 is not only an execution tool.

It is also a style mining system:

1. GM uploads or selects a high-quality source/reference pair.
2. Theme Create generates a strong result.
3. GM summarizes the useful visual logic into a compact report.
4. GM saves that report as a reusable preset.
5. Feature 1 can later load that preset directly.

This creates a compounding internal style library.

## Scope

This phase covers:

- a standard report template for Feature 2 output
- a preset data structure
- a GM save flow
- first-pass API and UI entry points

This phase does not yet cover:

- automatic Gemini summarization from generated assets
- preset performance ranking
- preset approval workflow
- preset analytics / recommendation engine

## Report Template

Each Theme Create style report should contain:

```json
{
  "title": "2026 World Cup Stadium Energy",
  "summary": "Sports broadcast treatment with floodlights, championship contrast, and high-energy celebratory particles.",
  "theme_create_mode": "style_modify",
  "prompt_template": "full reusable prompt text",
  "source_asset_id": "ast_xxx",
  "reference_asset_ids": ["ast_ref_1"],
  "source_job_id": "job_xxx",
  "recommended_preset_name": "2026 World Cup Edition",
  "visual_dna": [
    "dramatic stadium floodlights",
    "pitch green + gold + dark blue palette",
    "broadcast-style rim lighting"
  ],
  "composition_rules": [
    "preserve original subject placement",
    "do not alter headline hierarchy",
    "keep CTA footprint stable"
  ],
  "do_not_copy": [
    "do not import competitor logo",
    "do not copy reference text",
    "do not clone specific characters from inspiration image"
  ],
  "tags": ["theme-create", "sportsbook", "world-cup", "broadcast"],
  "taxonomy": {
    "vertical": ["sportsbook"],
    "medium": ["cinematic-photography"],
    "campaign": ["2026-world-cup"],
    "workflow": ["style_modify"]
  }
}
```

## Preset Data Structure

Preset is the reusable asset that Feature 1 consumes later.

Recommended fields:

```json
{
  "preset_id": "tcp_xxx",
  "name": "2026 World Cup Edition",
  "description": "Sports broadcast visual treatment for high-energy tournament campaigns.",
  "theme_create_mode": "style_modify",
  "visibility": "team",
  "prompt_template": "full reusable prompt text",
  "style_name": "2026 World Cup Edition",
  "style_details": "Packed stadium lights, championship greens and golds, sports-broadcast energy.",
  "workspace_id": "wsp_q2",
  "tags": ["theme-create", "sportsbook", "world-cup"],
  "taxonomy": {
    "vertical": ["sportsbook"],
    "medium": ["cinematic-photography"],
    "campaign": ["2026-world-cup"]
  },
  "source_report_id": "tcr_xxx",
  "source_job_id": "job_xxx",
  "source_asset_id": "ast_xxx",
  "created_by": "usr_xxx",
  "usage_count": 0,
  "is_official": false
}
```

## Taxonomy

The first version should standardize on these buckets:

- `vertical`
  - `gaming`
  - `fintech`
  - `sportsbook`
  - `ecommerce`
- `medium`
  - `3d-render`
  - `cinematic-photography`
  - `neon-cyber`
  - `vector-illustration`
- `campaign`
  - `2026-world-cup`
  - `black-friday`
  - `new-year`
  - `ramadan`
- `workflow`
  - `style_modify`
  - `style_transfer`

## GM Save Flow

The intended workflow is:

1. GM runs `Theme Create`.
2. GM reviews generated output and decides it is reusable.
3. GM enters:
   - preset name
   - short summary
4. System saves a `style report`.
5. System immediately saves a linked `preset`.
6. Preset appears in the Theme Create preset library.
7. Later, Feature 1 can consume the same preset inventory.

## Current Implementation

First-pass code has been added for:

- backend persistence tables
  - `theme_create_reports`
  - `theme_create_presets`
- backend APIs
  - `GET /theme-create/reports`
  - `POST /theme-create/reports`
  - `GET /theme-create/presets`
  - `POST /theme-create/presets`
  - `POST /theme-create/reports/{report_id}/save-as-preset`
- frontend API helpers
- Theme Create UI
  - preset library loading
  - load preset into form
  - GM `Save Preset Asset`

## Current Live Workflow

The current product flow should now be understood as two Theme Create lanes plus one accumulation lane:

1. `Style Modify`
   - upload `Source Image`
   - write the full style-modification prompt
   - optionally fill `Style Name` and `Style Details`
   - generate output
2. `Style Transfer`
   - upload `Source Image`
   - upload `Reference Image`
   - optionally add extra direction text
   - optionally fill `Style Name` and `Style Details`
   - generate output
3. `Preset Accumulation`
   - after a strong result, GM clicks `Draft Style Report`
   - system drafts reusable report metadata
   - GM reviews `Preset Asset Name` and `Style report summary`
   - GM clicks `Save Preset Asset`
   - preset becomes available in the Theme Create preset shelf for the same mode

`Asset & Text Replace` is no longer part of the live Theme Create workflow.

## Rollout Plan

Phase 1:

- manual GM summary
- manual save as preset
- team visibility by default

Phase 2:

- Gemini auto-draft report from successful outputs
- editable taxonomy suggestions
- report review queue

Phase 3:

- expose approved presets inside Feature 1 official preset shelf
- add usage and conversion analytics
- rank presets by adoption and output quality

## Recommendation

For storage organization, keep the preset/report system separate from GCS folder strategy.

- GCS foldering should optimize file storage and retrieval.
- preset/report objects should live as product metadata in DB.

For image assets themselves, date-based object paths under workspace are still the right default:

- `generated/{workspace}/{yyyy}/{mm}/{dd}/{job_id}/file.png`

For reusable styles, the authoritative object should be the DB preset record, not the GCS folder name.
