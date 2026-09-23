# Incept Data Durability & Cloud SQL Migration

## Status — 2026-07-27

The current persistence implementation is SQLite at `apps/api/data/incept.db`.
Media assets are designed to live in the `incept-assets` GCS bucket, while the
SQLite file stores the application metadata that connects a production to its
script, design packs, storyboard, generated assets, and jobs.

### Incident record

On 2026-07-27, a startup restore path downloaded `gs://incept-assets/data/incept.db`
over an already existing local SQLite database. The GCS object was an older
snapshot, so newer Video Production rows disappeared from the local database.

The immediate fixes are:

1. Startup restore now runs only for a missing or empty local database. It never
   replaces an existing local database.
2. A downloaded database is validated in a temporary file and atomically moved
   into place only after validation.
3. The application creates a local immutable daily SQLite snapshot at
   `apps/api/data/backups/incept-YYYY-MM-DD.db`, using SQLite's consistent
   backup API. The first valid snapshot of a day is retained and not replaced.
4. GCS backups update the bootstrap object after writes and create one
   timestamped immutable application-level snapshot under `data/backups/` at
   most every hour. This is defense in depth; Bucket Object Versioning
   remains required.

### Recovery limits for this incident

The only currently discovered GCS database generation is the 2026-07-20
snapshot. No previous object generation or application snapshot exists for the
missing 2026-07-27 Production rows. Asset bytes and asset records remain
available in GCS, but a lost Production's script-to-asset/storyboard bindings
cannot be reconstructed exactly from media objects alone.

On 2026-07-27, four application-level database backups were later found under
`gs://incept-assets/data/backups/` (06:48–07:39 UTC). All passed SQLite
integrity checks, but every copy contained the same already-overwritten state:
2 Video Productions, 695 Assets, and a newest Production update timestamp of
2026-07-20. They are valid recovery points for that older state, not for the
missing 2026-07-27 Production records.

### GCS catalog reconstruction

The generated-object path retains more than the database backup did. For
example, a path contains its workspace, calendar date, job ID, generated asset
ID, dimensions, and media extension. This makes it possible to rebuild the
Asset Library and Generation Job index for the missing period. It does **not**
recover prompt text, user-entered Pack names, selected panels, source-image
bindings, scripts, or storyboard ordering because those values were stored only
in the database.

Use the recovery tool in dry-run mode first:

```bash
cd apps/api
.venv/bin/python scripts/recover_gcs_assets.py \
  --prefix generated/wsp_q2/2026/07/27/ \
  --manifest /tmp/incept-gcs-recovery-2026-07-27.json
```

After reviewing the JSON manifest, re-run the exact command with `--apply`.
It imports only missing Asset and Job rows; it never modifies a matching
existing row and it does not fabricate a Video Production, script, or
storyboard.

## Local development durability

### Recovery locations

| Data | Location | Purpose |
| --- | --- | --- |
| Active database | `apps/api/data/incept.db` | Current local runtime state |
| Daily local snapshots | `apps/api/data/backups/incept-YYYY-MM-DD.db` | Recovery after bad restart, code change, or local DB corruption |
| GCS bootstrap copy | `gs://incept-assets/data/incept.db` | Fresh runtime bootstrap only |
| GCS immutable snapshots | `gs://incept-assets/data/backups/incept-*.db` | Off-machine recovery |

### Operating rules

- Do not delete `apps/api/data/incept.db` or its `backups/` directory while the
  API is running.
- Do not use a remote database restore to overwrite a non-empty local database.
- Restore into a new filename first, validate it, then explicitly select it as
  the recovery source.
- Before schema migrations, create an additional named snapshot and record the
  row count of `video_productions`, `assets`, and `jobs`.
- Daily snapshots are immutable by name. Retention should be managed explicitly
  after Cloud SQL cutover; do not silently prune recovery data.
- GCS immutable snapshots are rate-limited to one per hour. The canonical
  GCS bootstrap object can update more often, while Object Versioning retains
  its overwritten generations once it is enabled.

## GCS asset storage

### Current behavior

`INCEPT_ASSET_BUCKET=incept-assets` configures the target bucket. For each
generated or uploaded image/video/audio, the API attempts to write bytes to a
`gs://incept-assets/...` object and stores that URI in the asset record.

If GCS upload cannot initialize or fails, the current default is **fallback to
local temporary storage**. This is convenient for development but unsafe for
durable work: a local restart, container replacement, or temporary-directory
cleanup can make the preview unavailable.

### Required local configuration

Set these in the environment that starts the FastAPI process:

```dotenv
INCEPT_ASSET_BUCKET=incept-assets
INCEPT_REQUIRE_GCS_UPLOAD=true
GOOGLE_CLOUD_PROJECT=ads-bpd-guard-sandbox
# GOOGLE_APPLICATION_CREDENTIALS=/absolute/path/to/a/service-account-key.json
# or use gcloud Application Default Credentials for the same user/service account.
```

With `INCEPT_REQUIRE_GCS_UPLOAD=true`, generation fails visibly if the runtime
cannot write to GCS. It must not claim a durable asset was created while only a
temporary local file exists.

The local identity and the Cloud Run service account require, at minimum,
object create/read/list permissions on `incept-assets`; deleting an asset also
requires object delete. Bucket Object Versioning requires the separate
`storage.buckets.update` permission.

## Cloud SQL target

Discovered target (do not change without an explicit infrastructure decision):

| Setting | Value |
| --- | --- |
| Project | `ads-bpd-guard-sandbox` |
| Instance | `linglonglab-tokyo-prod-main-1` |
| Engine | PostgreSQL 17 |
| Region | `asia-northeast1` |
| Connection name | `ads-bpd-guard-sandbox:asia-northeast1:linglonglab-tokyo-prod-main-1` |
| Intended database | `linglonglab` |

The existing API has not yet been switched to this instance: its deployed
environment currently exposes no database URL and its Cloud Run revision does
not have a Cloud SQL instance attachment.

## Prerequisites before migration

1. Enable **Object Versioning** on `gs://incept-assets`.
2. Grant the deployment/runtime identity:
   - GCS: `storage.buckets.update` for the one-time versioning change, then
     `storage.objects.get`, `storage.objects.list`, and `storage.objects.create`.
   - Cloud SQL connectivity: `roles/cloudsql.client`.
   - Secret access: `secretmanager.versions.access` for the existing database
     connection secret.
   - PostgreSQL: a dedicated application role with schema migration and runtime
     read/write permissions on `linglonglab`.
3. Decide the connection contract explicitly. Preferred production contract:
   - Cloud Run is attached to the exact instance connection name.
   - `DATABASE_URL` is provided from Secret Manager, never committed to `.env`.
   - The API uses a PostgreSQL driver and a connection pool.
4. Keep the local SQLite database read-only during the final data copy window.

## Safe migration sequence

1. **Freeze and inventory.** Stop writes briefly; create a named SQLite backup;
   record counts and IDs for all tables, especially `video_productions`,
   `assets`, `jobs`, `workflows`, and `workflow_runs`.
2. **Create PostgreSQL schema.** Apply versioned migrations in a transaction.
   Do not run ad-hoc table creation from multiple API replicas.
3. **Import.** Copy SQLite data into staging tables, preserving IDs, JSON
   payloads, timestamps, and GCS URIs; validate type conversions first.
4. **Verify.** Compare source and destination row counts, primary-key sets, and
   a checksum of each JSON payload table. Verify a representative production,
   asset download, and workflow run.
5. **Cut over.** Configure Cloud Run with the Cloud SQL attachment and
   secret-backed `DATABASE_URL`; deploy one revision; run read/write health
   checks; only then direct all API writes to PostgreSQL.
6. **Rollback path.** Keep SQLite and immutable GCS snapshots untouched until
   the PostgreSQL service has been stable and verified. Rollback means changing
   the runtime connection setting, never copying an old database over a newer
   one.
7. **Post-cutover verification.** Restart an API instance and confirm it loads
   the same production list, asset metadata, and workflow state from Cloud SQL.

## Acceptance checklist

- [ ] GCS Object Versioning enabled and verified by listing object generations.
- [ ] Local daily snapshot exists after an API write.
- [ ] A deliberate GCS upload permission failure causes a visible API error,
      not a temporary-only asset.
- [ ] PostgreSQL migrations are versioned and idempotent.
- [ ] SQLite-to-PostgreSQL import reports matching counts and checksums.
- [ ] Cloud Run has the approved Cloud SQL attachment and secret-backed URL.
- [ ] Restart test preserves Productions, scripts, storyboards, assets, and jobs.
- [ ] A documented restore test succeeds without overwriting the active DB.
