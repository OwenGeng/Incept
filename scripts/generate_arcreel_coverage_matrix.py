#!/usr/bin/env python3
"""Generate a complete, non-derivative ArcReel source-coverage ledger.

The ledger intentionally stores paths and Incept-owned audit metadata only. It
does not extract or reproduce source code from the reference repository.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import shutil
import subprocess


SOURCE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}
IGNORED_DIRS = {
    ".git",
    ".codegraph",
    "node_modules",
    "venv",
    ".venv",
    "dist",
    "build",
    ".next",
    "coverage",
}
HEADER = [
    "source_path",
    "module",
    "disposition",
    "audit_status",
    "responsibility",
    "incept_requirement",
    "incept_target",
    "acceptance_evidence",
    "reviewed_at",
    "notes",
    "classification_method",
    "audit_tier",
    "responsibility_cluster",
    "cluster_anchor",
]
LEGACY_HEADER = HEADER[:10]
CLUSTER_HEADER = [
    "responsibility_cluster",
    "module",
    "files",
    "deep",
    "cluster",
    "evidence",
    "anchors",
    "codegraph_nodes",
]


def classify(path: str) -> str:
    if path.startswith((".agents/", ".claude/", "website/")):
        return "non-product tooling — excluded"
    if path.startswith("tests/"):
        lowered = path.lower()
        rules = (
            ("script", "A-05 script domain"),
            ("asset", "A-06 asset library"),
            ("reference", "A-07 reference analysis"),
            ("storyboard", "A-08 storyboard and editor"),
            ("grid", "A-08 storyboard and editor"),
            ("project", "A-02 to A-04 project domain"),
            ("generation", "A-09 to A-10 generation jobs"),
            ("task", "A-09 to A-10 generation jobs"),
            ("artifact", "A-11 to A-12 edit and delivery"),
            ("usage", "A-13 usage and audit"),
            ("sse", "A-13 project event stream"),
            ("provider", "A-14 provider adapters"),
            ("endpoint", "A-14 provider adapters"),
            ("agent", "A-16 agent runtime"),
            ("mcp", "A-17/A-18 remote automation"),
            ("db", "A-20 persistence and migrations"),
            ("migration", "A-20 persistence and migrations"),
        )
        for marker, module in rules:
            if marker in lowered:
                return module
        return "cross-cutting test evidence"
    rules = (
        ("frontend/src/components/canvas/", "A-08 storyboard and editor"),
        ("frontend/src/components/pages/", "A-01 to A-04 product surfaces"),
        ("frontend/src/components/assets/", "A-06 asset library"),
        ("frontend/src/components/agent/", "A-16 scoped copilot"),
        ("frontend/src/components/copilot/", "A-16 scoped copilot"),
        ("frontend/src/components/usage/", "A-13 usage and audit"),
        ("frontend/src/components/", "A-21 shared UI and interaction"),
        ("frontend/src/api/", "A-13 client transport"),
        ("frontend/src/stores/", "A-13 client state"),
        ("frontend/src/hooks/", "A-01 to A-21 shared client behavior"),
        ("frontend/src/types/", "A-13 client contracts"),
        ("frontend/src/i18n/", "A-22 localisation"),
        ("frontend/src/", "A-01 application host"),
        ("server/routers/", "A-01 to A-20 HTTP contracts"),
        ("server/agent_runtime/", "A-16 agent runtime"),
        ("server/media_tools/", "A-09 to A-12 media operations"),
        ("server/", "A-01 to A-20 service host"),
        ("lib/project/", "A-02 to A-04 project domain"),
        ("lib/script/", "A-05 script domain"),
        ("lib/generation/", "A-09 to A-10 generation jobs"),
        ("lib/workflow/", "A-08 storyboard domain"),
        ("lib/artifacts/", "A-11 to A-12 edit and delivery"),
        ("lib/references/", "A-07 reference analysis"),
        ("lib/db/", "A-20 persistence and migrations"),
        ("lib/backends/", "A-14 provider adapters"),
        ("lib/custom_provider/", "A-14 provider adapters"),
        ("lib/agent/", "A-16 agent sessions"),
        ("alembic/", "A-20 database migrations"),
    )
    for prefix, module in rules:
        if path.startswith(prefix):
            return module
    return "unassigned — triage required"


def is_test_evidence(path: str) -> bool:
    parts = path.split("/")
    filename = parts[-1]
    return (
        "tests" in parts
        or "fixtures" in parts
        or "__mocks__" in parts
        or filename.endswith((".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx"))
        or filename.startswith("test_")
    )


def is_non_product_tooling(path: str) -> bool:
    return path.startswith((".agents/", ".claude/", "website/"))


def cluster_for(path: str, module: str) -> str:
    """Return a stable responsibility cluster, not a source similarity group."""
    parts = path.split("/")
    if path.startswith("frontend/src/components/") and len(parts) >= 4:
        return f"ui:{parts[3]}"
    if path.startswith("frontend/src/") and len(parts) >= 3:
        return f"client:{parts[2]}"
    if path.startswith("server/") and len(parts) >= 2:
        return f"server:{parts[1]}"
    if path.startswith("lib/") and len(parts) >= 2:
        return f"domain:{parts[1]}"
    if path.startswith("alembic/"):
        return "persistence:alembic"
    if path.startswith("tests/"):
        return f"evidence:{module.split(' ', 1)[0].lower()}"
    if is_non_product_tooling(path):
        return "excluded:reference-tooling"
    return module.replace(" ", "-").replace("/", "-").lower()


def tier_for(path: str) -> str:
    """Choose audit depth based on change authority, not file size alone."""
    filename = path.rsplit("/", 1)[-1]
    if is_test_evidence(path):
        return "evidence"
    deep_markers = (
        "/routers/", "/stores/", "/api/", "/agent_runtime/", "/db/",
        "/backends/", "/custom_provider/", "/generation/", "/workflow/",
        "/artifacts/", "/references/", "/project/",
    )
    if any(marker in f"/{path}" for marker in deep_markers) or filename in {
        "app.py", "auth.py", "dependencies.py", "remote_mcp.py", "tool_runtime.py",
        "models.py", "engine.py", "router.tsx", "main.tsx", "transport.ts",
    }:
        return "deep"
    return "cluster"


def codegraph_node_counts(reference_root: Path) -> dict[str, int]:
    """Read only graph metadata; source contents remain in the reference repo."""
    executable = shutil.which("codegraph")
    if executable is None:
        return {}
    try:
        result = subprocess.run(
            [executable, "files", "--path", str(reference_root), "--format", "flat", "--json"],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        payload = json.loads(result.stdout)
        return {
            str(item["path"]): int(item.get("nodeCount", 0))
            for item in payload
            if isinstance(item, dict) and isinstance(item.get("path"), str)
        }
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError):
        return {}


def iter_sources(reference_root: Path) -> list[str]:
    paths: list[str] = []
    for source in reference_root.rglob("*"):
        if not source.is_file() or source.suffix not in SOURCE_SUFFIXES:
            continue
        relative = source.relative_to(reference_root)
        if any(part in IGNORED_DIRS for part in relative.parts):
            continue
        paths.append(relative.as_posix())
    return sorted(paths)


def read_existing(output: Path) -> dict[str, dict[str, str]]:
    if not output.exists():
        return {}
    with output.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        if reader.fieldnames != HEADER and reader.fieldnames != LEGACY_HEADER:
            raise SystemExit(f"Unexpected ledger header in {output}")
        rows: dict[str, dict[str, str]] = {}
        for row in reader:
            path = row["source_path"]
            if path in rows:
                raise SystemExit(f"Duplicate source_path in {output}: {path}")
            rows[path] = {column: row.get(column, "") for column in HEADER}
        return rows


def verify(output: Path, paths: list[str]) -> int:
    existing = read_existing(output)
    expected = set(paths)
    actual = set(existing)
    missing = sorted(expected - actual)
    orphaned = sorted(actual - expected)
    invalid = [
        path
        for path, row in existing.items()
        if row["disposition"] not in {"pending", "mapped", "merged", "excluded"}
        or not row["module"]
        or not row["audit_status"]
        or row["audit_tier"] not in {"deep", "cluster", "evidence"}
        or not row["responsibility_cluster"]
        or not row["cluster_anchor"]
    ]
    if missing or orphaned or invalid:
        if missing:
            print(f"Missing rows ({len(missing)}): {', '.join(missing[:8])}")
        if orphaned:
            print(f"Orphaned rows ({len(orphaned)}): {', '.join(orphaned[:8])}")
        if invalid:
            print(f"Invalid rows ({len(invalid)}): {', '.join(invalid[:8])}")
        return 1
    counts: dict[str, int] = {}
    for row in existing.values():
        counts[row["disposition"]] = counts.get(row["disposition"], 0) + 1
    print(f"Coverage ledger valid: {len(paths)} paths; dispositions={counts}")
    return 0


def choose_cluster_anchors(paths: list[str], node_counts: dict[str, int]) -> dict[str, str]:
    grouped: dict[str, list[str]] = {}
    for path in paths:
        grouped.setdefault(cluster_for(path, classify(path)), []).append(path)
    anchors: dict[str, str] = {}
    for cluster, members in grouped.items():
        candidates = [path for path in members if tier_for(path) == "deep"]
        if not candidates:
            candidates = [path for path in members if tier_for(path) == "cluster"]
        if not candidates:
            # A leaf mock/test still needs a visible owner. Its own test path
            # is the honest anchor until a production implementation is mapped.
            candidates = list(members)
        candidates.sort(key=lambda path: (-node_counts.get(path, 0), len(path), path))
        anchors[cluster] = "; ".join(candidates[:3])
    return anchors


def expected_cluster_rows(
    paths: list[str], anchors: dict[str, str], node_counts: dict[str, int],
) -> dict[str, dict[str, str]]:
    """Return the deterministic, source-derived cluster manifest.

    The manifest is a companion integrity record: the file ledger proves every
    path is classified, while this table proves every path rolls up into exactly
    one review queue with an inspectable anchor.
    """
    rows: dict[str, dict[str, str]] = {}
    for cluster in sorted(anchors):
        members = [path for path in paths if cluster_for(path, classify(path)) == cluster]
        counts = {tier: sum(tier_for(path) == tier for path in members) for tier in ("deep", "cluster", "evidence")}
        rows[cluster] = {
            "responsibility_cluster": cluster,
            "module": classify(members[0]),
            "files": str(len(members)),
            "deep": str(counts["deep"]),
            "cluster": str(counts["cluster"]),
            "evidence": str(counts["evidence"]),
            "anchors": anchors[cluster],
            "codegraph_nodes": str(sum(node_counts.get(path, 0) for path in members)),
        }
    return rows


def verify_cluster_manifest(
    output: Path, paths: list[str], anchors: dict[str, str], node_counts: dict[str, int],
) -> int:
    if not output.exists():
        print(f"Missing cluster manifest: {output}")
        return 1
    with output.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        if reader.fieldnames != CLUSTER_HEADER:
            print(f"Unexpected cluster manifest header in {output}")
            return 1
        actual: dict[str, dict[str, str]] = {}
        duplicate: list[str] = []
        for row in reader:
            cluster = row.get("responsibility_cluster", "")
            if not cluster or cluster in actual:
                duplicate.append(cluster or "<blank>")
                continue
            actual[cluster] = {column: row.get(column, "") for column in CLUSTER_HEADER}
    expected = expected_cluster_rows(paths, anchors, node_counts)
    missing = sorted(set(expected) - set(actual))
    orphaned = sorted(set(actual) - set(expected))
    # Node counts are informative metadata that legitimately change when the
    # local CodeGraph index is refreshed; structure and anchors are the gate.
    stale = [
        cluster
        for cluster in sorted(set(expected) & set(actual))
        if any(actual[cluster][column] != expected[cluster][column] for column in CLUSTER_HEADER[:-1])
    ]
    if duplicate or missing or orphaned or stale:
        if duplicate:
            print(f"Duplicate cluster rows ({len(duplicate)}): {', '.join(duplicate[:8])}")
        if missing:
            print(f"Missing cluster rows ({len(missing)}): {', '.join(missing[:8])}")
        if orphaned:
            print(f"Orphaned cluster rows ({len(orphaned)}): {', '.join(orphaned[:8])}")
        if stale:
            print(f"Stale cluster rows ({len(stale)}): {', '.join(stale[:8])}")
        return 1
    print(f"Cluster manifest valid: {len(expected)} responsibility clusters")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference-root", type=Path, default=Path("ArcReel"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/arcreel-source-file-coverage.tsv"),
    )
    parser.add_argument(
        "--clusters-output",
        type=Path,
        default=Path("docs/arcreel-audit-clusters.tsv"),
        help="write cluster-level triage manifest alongside the per-file ledger",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="verify exact source-path coverage without writing the ledger",
    )
    args = parser.parse_args()

    reference_root = args.reference_root.resolve()
    if not reference_root.is_dir():
        raise SystemExit(f"Reference root does not exist: {reference_root}")

    paths = iter_sources(reference_root)
    node_counts = codegraph_node_counts(reference_root)
    anchors = choose_cluster_anchors(paths, node_counts)
    if args.verify:
        ledger_status = verify(args.output, paths)
        manifest_status = verify_cluster_manifest(args.clusters_output, paths, anchors, node_counts)
        return 1 if ledger_status or manifest_status else 0

    existing = read_existing(args.output)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
        writer.writerow(HEADER)
        for path in paths:
            row = existing.get(path)
            if row is None:
                row = dict.fromkeys(HEADER, "")
                row.update(
                    {
                        "source_path": path,
                        "module": classify(path),
                        "disposition": "pending",
                        "audit_status": "pending",
                    }
                )
            module = classify(path)
            cluster = cluster_for(path, module)
            row["module"] = row["module"] or module
            row["classification_method"] = "path-taxonomy+codegraph-index"
            row["audit_tier"] = tier_for(path)
            row["responsibility_cluster"] = cluster
            row["cluster_anchor"] = anchors[cluster]
            if is_non_product_tooling(path) and row["disposition"] == "pending":
                row["disposition"] = "excluded"
                row["audit_status"] = "auto_classified"
                row["responsibility"] = "Local reference tooling outside the independently rebuilt product runtime."
                row["incept_requirement"] = "No Incept product feature; retain only as an explicit inventory exclusion."
                row["notes"] = "Automatically classified by repository boundary; not used to infer product equivalence."
            elif row["audit_status"] == "pending":
                row["audit_status"] = "auto_classified"
            writer.writerow([row[column] for column in HEADER])
    args.clusters_output.parent.mkdir(parents=True, exist_ok=True)
    with args.clusters_output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
        writer.writerow(CLUSTER_HEADER)
        for row in expected_cluster_rows(paths, anchors, node_counts).values():
            writer.writerow([row[column] for column in CLUSTER_HEADER])
    print(f"Wrote {len(paths)} source rows to {args.output} and {len(anchors)} clusters to {args.clusters_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
