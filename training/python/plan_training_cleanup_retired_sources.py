"""Prepare a bounded cleanup of retired sources and verified redundant copies."""
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
TRAINING = ROOT / "training"
REPORT = ROOT / "docs/training-cleanup-2026-10-29-retired-sources-plan.json"
RETIRED = [TRAINING / "data/raw" / name for name in ("wesad", "pamap2", "bidmc")]
EXTRACTED = TRAINING / "data/raw/unimib-shar/extracted"
ARCHIVE = EXTRACTED.parent / "UniMiB-SHAR.zip"
entries = []


def safe(path):
    resolved = path.resolve(strict=True)
    assert resolved.is_relative_to(TRAINING.resolve())
    for item in (path, *path.parents):
        if item == ROOT:
            break
        assert not item.is_symlink()
        assert not (getattr(item.lstat(), "st_file_attributes", 0) & 0x400)
    return resolved


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def add(path, reason, **evidence):
    resolved = safe(path)
    entries.append({"path": str(resolved), "bytes": path.stat().st_size,
                    "sha256": digest(path), "reason": reason, **evidence})


for folder in RETIRED:
    if not folder.exists():
        continue
    safe(folder)
    for path in sorted(folder.rglob("*")):
        safe(path)
        if path.is_file():
            add(path, "retired_source_excluded_from_current_pipeline",
                evidence="docs/ai-real-data-audit.md: Motivo del reemplazo; no current code or source-lock references")
    print(f"Hashed retired source: {folder.name}", flush=True)

for temporary in sorted((TRAINING / "data/fatigue-research").glob("*/selection.tmp")):
    final = temporary.with_name("selection.json")
    if not final.is_file():
        continue
    previous = json.loads(temporary.read_text(encoding="utf-8"))
    complete = json.loads(final.read_text(encoding="utf-8"))
    changed = [key for key in previous.keys() | complete.keys()
               if previous.get(key) != complete.get(key)]
    if (complete.get("status") == "complete" and changed == ["status"]
            and previous.get("status") == "running"):
        add(temporary, "completed_selection_temporary_copy_status_only_difference",
            retained_copy=str(safe(final)), retained_sha256=digest(final),
            differing_fields=changed)

if EXTRACTED.is_dir():
    safe(EXTRACTED)
    with ZipFile(ARCHIVE) as archive:
        archive_hash = digest(ARCHIVE)
        for path in sorted(EXTRACTED.rglob("*")):
            safe(path)
            if not path.is_file():
                continue
            member = path.relative_to(EXTRACTED).as_posix()
            original = archive.getinfo(member)
            assert original.file_size == path.stat().st_size
            with archive.open(original) as stream:
                member_hash = hashlib.file_digest(stream, "sha256").hexdigest()
            assert member_hash == digest(path), str(path)
            add(path, "redundant_extraction_identical_to_retained_archive_member",
                retained_copy=str(safe(ARCHIVE)), retained_sha256=archive_hash,
                retained_archive_member=member, member_sha256=member_hash)
    print("Verified every extracted UniMiB file against retained ZIP", flush=True)

deleted_paths = {row["path"] for row in entries}
assert len(deleted_paths) == len(entries)
protected = []
for base, directories, files in os.walk(TRAINING, followlinks=False):
    folder = Path(base)
    directories[:] = [name for name in directories
                       if not (folder/name).is_symlink()]
    for name in files:
        path = folder/name
        if path.is_symlink() or str(path.resolve()) in deleted_paths:
            continue
        stat = path.stat()
        row = {"path": str(path.resolve()), "bytes": stat.st_size,
               "mtime_ns": stat.st_mtime_ns}
        if path.is_relative_to(TRAINING / "data/fatigue-research") or path.is_relative_to(TRAINING / "data/public"):
            row["sha256"] = digest(path)
        protected.append(row)

plan = {"created_at": datetime.now(timezone.utc).isoformat(),
        "workspace": str(ROOT), "scope": str(TRAINING),
        "files": entries, "file_count": len(entries),
        "bytes": sum(row["bytes"] for row in entries),
        "retired_source_roots": [str(p.resolve()) for p in RETIRED],
        "redundant_extraction_root": str(EXTRACTED.resolve()),
        "protected_files": protected,
        "protected_file_count": len(protected),
        "protected_content_hash_count": sum("sha256" in p for p in protected),
        "installed_xlrd_wheel_preserved": True,
        "current_datasets_models_and_results_deleted": False}
REPORT.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"report": str(REPORT), "files": len(entries),
                  "bytes": plan["bytes"], "protected_files": len(protected),
                  "protected_hashes": plan["protected_content_hash_count"]}), flush=True)
