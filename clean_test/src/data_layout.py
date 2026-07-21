from __future__ import annotations

import csv
import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .utils import csv_safe


DATASET_ROLES = ("train", "test")


@dataclass(frozen=True)
class DatasetLayout:
    """Canonical paths for one manually assigned dataset role."""

    root: Path
    role: str

    def __post_init__(self) -> None:
        if self.role not in DATASET_ROLES:
            raise ValueError(f"role must be one of {DATASET_ROLES}, got {self.role!r}")

    @property
    def role_root(self) -> Path:
        return self.root / self.role

    @property
    def raw(self) -> Path:
        return self.role_root / "raw"

    @property
    def raw_workbooks(self) -> Path:
        return self.raw / "database_by_paper"

    @property
    def raw_profiles(self) -> Path:
        return self.raw / "data"

    @property
    def clean(self) -> Path:
        return self.role_root / "clean"

    def create(self) -> None:
        self.raw_workbooks.mkdir(parents=True, exist_ok=True)
        self.raw_profiles.mkdir(parents=True, exist_ok=True)
        self.clean.mkdir(parents=True, exist_ok=True)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _source_files(source: Path) -> Iterable[tuple[Path, Path]]:
    """Yield (source file, canonical relative destination) for raw data."""
    workbook_dir = source / "database_by_paper"
    if workbook_dir.is_dir():
        for path in sorted(workbook_dir.rglob("*.xlsx")):
            yield path, Path("database_by_paper") / path.relative_to(workbook_dir)
    else:
        for path in sorted(source.glob("*.xlsx")):
            yield path, Path("database_by_paper") / path.name

    profile_dir = source / "data"
    if profile_dir.is_dir():
        for path in sorted(value for value in profile_dir.rglob("*") if value.is_file()):
            yield path, Path("data") / path.relative_to(profile_dir)
    else:
        reserved = {"database_by_paper", "clean", "raw", "train", "test"}
        for child in sorted(source.iterdir()):
            if not child.is_dir() or child.name.lower() in reserved:
                continue
            for path in sorted(value for value in child.rglob("*") if value.is_file()):
                yield path, Path("data") / path.relative_to(source)


def _copy_file(source: Path, destination: Path, allowed_root: Path, overwrite: bool) -> str:
    if source.is_symlink():
        raise ValueError(f"Refusing to copy symbolic link: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    root_resolved = allowed_root.resolve()
    try:
        destination.parent.resolve().relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError(f"Destination escapes canonical data root: {destination}") from exc
    if destination.is_symlink():
        raise ValueError(f"Refusing to overwrite symbolic link: {destination}")
    if destination.exists():
        if _sha256(source) == _sha256(destination):
            return "unchanged"
        if not overwrite:
            raise FileExistsError(
                f"Destination exists with different content: {destination}. "
                "Use --overwrite only after reviewing the conflict."
            )
    shutil.copy2(source, destination)
    return "copied"


def _write_manifest(rows: list[dict[str, Any]], csv_path: Path, json_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["source", "destination", "bytes", "sha256", "status"]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(
            {key: csv_safe(value) for key, value in row.items()} for row in rows
        )
    json_path.write_text(
        json.dumps({"files": rows, "count": len(rows)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def organize_raw_data(
    source: Path,
    layout: DatasetLayout,
    overwrite: bool = False,
) -> list[dict[str, Any]]:
    """Copy a flat or canonical raw source into the role's raw directory."""
    source = source.resolve()
    if not source.is_dir():
        raise FileNotFoundError(f"Raw source directory does not exist: {source}")
    layout.create()
    rows: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for input_path, relative in _source_files(source):
        try:
            input_path.resolve().relative_to(source)
        except ValueError as exc:
            raise ValueError(f"Source file escapes input root: {input_path}") from exc
        if relative in seen:
            raise ValueError(f"Multiple source files map to the same destination: {relative}")
        seen.add(relative)
        destination = layout.raw / relative
        status = _copy_file(input_path, destination, layout.raw, overwrite)
        rows.append(
            {
                "source": str(input_path),
                "destination": str(destination.resolve()),
                "bytes": input_path.stat().st_size,
                "sha256": _sha256(input_path),
                "status": status,
            }
        )
    if not rows:
        raise ValueError(f"No .xlsx metadata or profile files found under {source}")
    if not any(Path(row["destination"]).suffix.lower() == ".xlsx" for row in rows):
        raise ValueError(f"No metadata workbook found under {source}")
    if not any(Path(row["destination"]).suffix.lower() == ".csv" for row in rows):
        raise ValueError(f"No profile CSV found under {source}")
    _write_manifest(rows, layout.raw / "raw_manifest.csv", layout.raw / "raw_manifest.json")
    return rows


def adopt_clean_data(
    source: Path,
    layout: DatasetLayout,
    overwrite: bool = False,
) -> list[dict[str, Any]]:
    """Copy already-clean artifacts without pretending that they are raw data."""
    source = source.resolve()
    if not source.is_dir():
        raise FileNotFoundError(f"Clean source directory does not exist: {source}")
    layout.create()
    if source == layout.clean.resolve():
        raise ValueError("Clean source is already the canonical destination; adoption is unnecessary.")
    rows: list[dict[str, Any]] = []
    for input_path in sorted(value for value in source.rglob("*") if value.is_file()):
        try:
            input_path.resolve().relative_to(source)
        except ValueError as exc:
            raise ValueError(f"Source file escapes input root: {input_path}") from exc
        relative = input_path.relative_to(source)
        destination = layout.clean / relative
        status = _copy_file(input_path, destination, layout.clean, overwrite)
        rows.append(
            {
                "source": str(input_path),
                "destination": str(destination.resolve()),
                "bytes": input_path.stat().st_size,
                "sha256": _sha256(input_path),
                "status": status,
            }
        )
    if not any(Path(row["destination"]).suffix.lower() in {".pt", ".npz"} for row in rows):
        raise ValueError(f"No cleaned .pt/.npz dataset found under {source}")
    _write_manifest(
        rows,
        layout.clean / "adopted_clean_manifest.csv",
        layout.clean / "adopted_clean_manifest.json",
    )
    return rows


def write_missing_raw_notice(layout: DatasetLayout, reason: str) -> Path:
    """Record missing raw lineage explicitly instead of fabricating source data."""
    layout.create()
    path = layout.raw / "RAW_DATA_MISSING.md"
    path.write_text(
        "# Raw training data not present\n\n"
        f"{reason.strip()}\n\n"
        "The files in the sibling `clean/` directory are preserved clean artifacts. "
        "They must not be treated as raw measurements. Restore the original Excel/CSV "
        "files here before rebuilding the training clean datasets.\n",
        encoding="utf-8",
    )
    return path
