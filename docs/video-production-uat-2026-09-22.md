# Video Production local UAT — 2026-09-22

## Scope

Local, non-billable verification of the canonical Video Production route. The
temporary frontend used `AUTH_DEV_SKIP_SIGN_IN=true` only in its process; no
checked-in or user `.env.local` setting was changed. No Gemini, Veo, audio, or
render request was made.

## Environment

- API: `http://127.0.0.1:8000/health` returned `{"status":"ok","mode":"live"}`.
- Web UAT: `http://127.0.0.1:3001/video-production` returned 200 and rendered
  the authenticated-development workspace.
- The active canonical routes were `/video-production`, `/video-production/new`,
  `/video-production/projects/[productionId]`, `/video-production/assets`, and
  `/video-production/delivery`.

## Executed evidence

| Contract hand-off | Result | Visible or durable evidence |
| --- | --- | --- |
| Create non-billable project | verified | Four-step setup presented validated server model choices and explicitly stated that creation starts no jobs. The UAT project was created at `vprod_5b7df3e21efc`. |
| Save editable working script | verified | UI reported “Working script saved”; the project stored an attributed `Manual working-script save` checkpoint. |
| Refresh/reopen | verified | Reload retained the UAT project, the script text, and revision receipt. |
| Restore script checkpoint | verified | The UI confirmation and recovery notice reported a new editable draft. The local API record advanced the state revision and appended `Restored checkpoint r1` receipts with full structured snapshots. |
| Asset library empty state | verified | `/video-production/assets` showed upload/attach controls, explicit project role and rights fields, and `No shared assets yet`. |
| Delivery/QA prerequisite state | verified | `/video-production/delivery` listed the UAT project as in production, `0 / 0 selected takes`, `QA not_run`, and `Final render pending`. |
| Generation safety | verified for the empty project | Render, audio generation, and shot-generation controls were disabled until their explicit prerequisites were met. No paid model was called. |

## Not exercised in this UAT

- Upload/attach a real customer asset (requires a supplied non-sensitive test
  file and a separate upload acceptance case).
- Agent-assisted plan generation, image/keyframe generation, Veo takes, audio
  generation, final render and delivery. These are intentionally excluded from
  this run because they can use configured paid models.
- Production authentication/authorization roles and deployed Cloud SQL/GCP
  behavior; the temporary process used the documented local development auth
  bypass only.

## Repeat locally

```sh
# terminal 1
cd apps/api
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# terminal 2 — temporary UAT login bypass only; do not use in production
cd apps/web
AUTH_DEV_SKIP_SIGN_IN=true pnpm dev --hostname 127.0.0.1 --port 3001
```

Open `http://127.0.0.1:3001/video-production`. To test media generation, use
the project’s configured models only after explicitly approving the associated
cost.
