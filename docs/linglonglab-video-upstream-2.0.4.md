# LinglongLab Video: selective Toonflow 2.0.4 adoption

## Approved scope

Keep the existing Vue / Next.js / FastAPI integration. Adopt the useful,
low-coupling parts of the upstream update, not the desktop/server distribution.
Order: file safety → document tabs/splits/search → copy isolation and canvas
arrangement → image annotation/grid splitting/masked edits.

Acceptance criteria:

- Reading a text document returns its content revision and encoding. Saving
  against an old revision returns 409 without overwriting the current file.
  The editor retains the draft and offers download or explicit reload.
- Repeated autosaves use the last successful revision; concurrent drafts do
  not accidentally reuse the initial revision. Existing raw/binary calls work.
- Canvas copies have new node/edge IDs and independent node-owned files;
  references to shared assets stay shared. Originals are never deleted.
- Selected root nodes can be arranged horizontally, vertically or in a grid,
  without breaking group membership; undo continues to work.
- A document can be downloaded as Markdown without writing to the workspace.
- Multiple documents stay open in tabs, with horizontal/vertical split views.
  Full-text search previews literal replacements; only checked files are
  changed after confirmation, using revisions captured by the search.
- Image annotation and grid splitting create new nodes, preserving originals.
  Masked editing uses the configured image model, with server-side compositing
  to preserve every unmasked original pixel. Unsupported providers fail closed.

## Boundaries

No model IDs, endpoints, credentials, persistent compatibility identifiers,
database schema or production data migrations. Preserve existing Agent changes.
No automatic commit, push or deployment. File extension plugins and
FFmpeg/audio-generation integration remain separate work. The user explicitly
added document tabs/splits/search and image annotation/grid/inpainting.

## Verification

API tests: `cd apps/api && PYTHONPATH=. .venv/bin/pytest tests/test_video*.py -q`

Vue checks: `pnpm --dir apps/video-vue typecheck`

Build: `pnpm prepare:video-vue`

Frontend behavior tests use Node's test runner for standalone TypeScript
helpers; browser smoke checks use isolated test project data when available.
Use existing TypeScript/Vue style and pytest fixtures; no new dependencies.

### Verified 2026-10-08

- 105 Video API regression tests passed, including concurrent/stale document
  saves, encoding and size bounds, canvas copy isolation, image selection
  validation and unchanged pixels outside the mask. Model calls were mocked.
- 12 document helper tests passed; image/grid/recovery and canvas arrangement,
  clipboard ownership and asset isolation helper checks passed.
- Workspace-wide Vue type checking and production embedded-Vue build passed.
- Local browser smoke used synthetic projects in a temporary data directory,
  with paid generation disabled: tabs, both split layouts, full-text search,
  open-draft protection, confirmed TXT replacement, brush/text annotation,
  undo/redo, independent image output and nine 3×3 grid output nodes passed.
- Final review fixed in-flight input loss on close, node-backed draft protection,
  duplicate backing-file tabs, node registration lookup, prompt length mismatch,
  SDK request timeout and preservation of staged assets after paid submission.

Limits: search covers Markdown/TXT, is literal and case-sensitive, and bounded
to 1000 files/directories, 20 MiB scanned text and 500 shown matches. Batch
replacement is sequential, not an all-files transaction; conflicts stop it.
The editor limit is 5 MiB encoded text and 12 tabs. Image tools support static
PNG/JPEG/WebP up to 25 MiB, 16 million pixels, 8192px per side and 64 tiles.
Real paid inpainting quality/latency is not verified; use one explicit small
test before production rollout. No production data, models or infrastructure
were migrated; these changes have not been committed or deployed.

### Agent material picker (2026-10-08)

The Agent composer now exposes an “上传素材” button with a multi-file picker,
and accepts files dragged onto its input area. Picker, clipboard and drop
inputs share validation: image/video only, up to 20 attachments per message,
each nonempty and at most 100 MiB. Known image/video extensions provide a
fallback when the browser omits MIME metadata. Selection creates removable
draft previews; existing project upload happens only on explicit send.
There are no model, endpoint, authentication or storage-format changes.

Verification: 3 selection/limit tests passed, including a mutation check that
detects an off-by-one limit regression; web Vue types and production build/sync
passed. An isolated browser project verified picker multi-select capability,
image preview, removal, reselecting the same file, clean console and a 321px
dialog width. OS file-drag and real model submission were not exercised.

## Upstream references

- https://github.com/HBAI-Ltd/Toonflow-app/compare/v2.0.3...v2.0.4
- https://github.com/HBAI-Ltd/Toonflow-app/blob/v2.0.4/apps/web/src/components/updateBox.md

This is selective adoption, not a claim that LinglongLab runs Toonflow 2.0.4.
