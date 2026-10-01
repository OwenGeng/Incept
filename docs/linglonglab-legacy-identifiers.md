# LinglongLab legacy identifiers

The product and repository brand is **LinglongLab**. The identifiers below keep
the former `incept` name because production data or deployed infrastructure
already depends on them. They are compatibility contracts, not product branding.

Do not rename them with a search-and-replace operation:

- Python and frontend source paths: `app.incept`, `routers/incept.py`,
  `components/incept`, and `lib/incept-api.ts`
- Legacy browser route `/incept` redirects to `/linglonglab`; the API route
  `/api/incept` remains a compatibility contract
- Environment variables and request headers: `INCEPT_*`, `X-Incept-*`
- Cloud resources: `incept-api`, `incept-web`, `incept-assets`, the `incept`
  Artifact Registry repository, and the existing service account
- Existing Git remote/check-out names, currently `OwenGeng/Incept` and the local
  `Projects/Incept` directory
- BigQuery datasets currently named `Incept`
- SQLite/GCS database objects such as `incept.db` and existing backup names
- Stored workflow/MCP identifiers such as `incept.*`, `incept-workflow.v1`, and
  `incept-video-production`

These identifiers may be removed only through a separately reviewed data and
infrastructure migration with verified rollback. New user-facing copy, package
names, documentation, and non-persistent identifiers must use `LinglongLab`,
`linglonglab`, or `LINGLONGLAB` as appropriate.
