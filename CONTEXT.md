# Incept domain language

This file records the product terms that are deliberately stable across the
GamingPlayable UI, API, and persistence layer.

- **Playable Project** — one user's editable playable configuration. It can
  retain the project's private uploaded artwork.
- **Playable Template** — a reusable, versioned configuration snapshot. It
  never includes an uploader's client artwork; those inputs become slots for
  the next creator.
- **Template Version** — the immutable numbered snapshot represented by a
  Playable Template. Editing a fork never changes its source template.
- **Template Fork** — a new, independently owned Playable Project created from
  a template snapshot.
- **Workspace Template** — a template visible to authenticated members of the
  same Studio workspace. It is not a public-community publication.
- **Template Favorite** — a per-user bookmark for ranking and retrieval. It
  does not grant permission to modify the template.
- **Playable Hub** — the GamingPlayable home for a creator's projects, recent
  activity, and entry points into a new project or reusable template.
- **Playable Creation** — the guided setup that turns a brief and reference
  materials into one Playable Project. It is not a second kind of project.
- **Asset Kit** — the project-scoped, approved collection of game art, logo,
  UI and audio inputs. A template describes slots; an Asset Kit fills them.
- **Delivery Build** — one generated HTML artifact and its validation result.
  It is an output of a Playable Project, not the editable project itself.

## Video Production

- **Video Project** — one editable video-production record that contains its
  brief, attached references, shot plan, generated takes, review state, and
  any final delivery. It is the only video object a creator selects or opens.
- **Production Mode** — the intended outcome of a Video Project: **Generate**
  (a new video), **Repair** (an existing video that needs safe replacements),
  or **CTV Composition** (a deterministic landscape composition around an
  approved video). It does not create a separate project type.
- **Shot Plan** — the ordered, editable set of shots in a Video Project. Each
  shot specifies its action, camera direction, continuity, duration, and
  generation state.
- **Take** — one generated video candidate belonging to a single shot. A Take
  is never silently substituted for another Take.
- **Project Asset** — an image, video, logo, recording, or other reference
  explicitly attached to a Video Project. It remains visible to Copilot when
  it prepares or refines that project.
- **Take Review** — a non-destructive assessment of a Take with its reasons
  and recommendation. It does not remove the source material.
- **Final Delivery** — the selected rendered output of a Video Project after
  review. It remains linked to the project that produced it.
- **Product Truth Anchor** — an immutable uploaded image that records what the
  advertised product actually looks like. Generated or standardized product
  assets retain lineage to this anchor and never replace it.
- **Standardized Product Asset** — a generation-ready product image derived
  from a Product Truth Anchor. It is a candidate until the user selects it.
- **Production Revision** — an immutable, numbered snapshot of an approved or
  draft script, shot plan, keyframe, motion prompt, or edit. Approval supersedes
  an older approved sibling without deleting history.
- **Delivery Manifest** — the machine-readable record that connects a Final
  Delivery to its approved edit, QA report, source files, revision fingerprints,
  subtitle sidecar, and rendered MP4.

## AI Video research

- **Research Brief** — the project-scoped, editable advertising intake: the
  advertiser vertical, delivery channel, product webpage or product assets,
  and market. It is evidence intake, not a prompt pack.
- **Research Source** — a traceable product page, competitor video, uploaded
  reference video, or brand-guideline asset. It records provenance and the
  uploader's rights acknowledgement; it is never treated as a license to copy.
- **Research Finding** — an evidence-linked observation such as a visible
  hook, product-proof mechanism, pacing pattern, or CTA structure. A finding
  is distinct from an unverified product claim.
- **Creative Direction** — an editable, project-specific recommendation for a
  format, playbook, visual direction, and script direction, linked back to
  research evidence.
- **Approved Creative Brief** — the one Creative Direction the user approves
  for a project. It becomes production context while the source research stays
  visible and editable for auditability.
- **Project Entry Mode** — either **Research** (the default, requiring a
  user-approved Creative Direction before production) or **Preset** (a future
  governed template supplies its own pre-approved direction). It is not a
  legacy compatibility escape hatch.
