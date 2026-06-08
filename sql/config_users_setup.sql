-- Run once to create the RBAC users table in the sandbox project.
-- BQ dataset "config" must exist first:
--   bq mk --dataset ads-bpd-guard-sandbox:config

CREATE TABLE IF NOT EXISTS `ads-bpd-guard-sandbox.config.users` (
  email            STRING    NOT NULL,
  role             STRING    NOT NULL,   -- 'admin' | 'user' | 'agency'
  allowed_projects ARRAY<STRING>,        -- NULL means all projects
  created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
  created_by       STRING
);

-- Seed: grant yourself admin access
INSERT INTO `ads-bpd-guard-sandbox.config.users` (email, role, allowed_projects, created_by)
VALUES
  ('owen.geng@moloco.com', 'admin', NULL, 'bootstrap');

-- Example agency user with restricted project access:
-- INSERT INTO `ads-bpd-guard-sandbox.config.users` (email, role, allowed_projects, created_by)
-- VALUES ('agency-user@example.com', 'agency', ['supply-smb'], 'owen.geng@moloco.com');
