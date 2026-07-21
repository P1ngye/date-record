from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest
import torch

import clean_data


def _arguments(tmp_path: Path, variables: list[str]) -> Namespace:
    raw = tmp_path / "data" / "test" / "raw"
    (raw / "database_by_paper").mkdir(parents=True)
    (raw / "data").mkdir()
    return Namespace(
        split="test",
        data_root=tmp_path / "data",
        raw_dir=None,
        clean_dir=None,
        variables=variables,
        min_valid_points=4,
        strict=False,
    )


def _fake_report(output_dir: Path, variables: list[str]) -> dict[str, object]:
    files: dict[str, str] = {}
    for variable in variables:
        path = output_dir / f"deeponet_dataset_{variable}.pt"
        torch.save({"case_ids": ["A"]}, path)
        files[variable] = str(path)
    return {
        "status": "ok",
        "dataset_role": "test",
        "clean_output": str(output_dir),
        "generated_files": files,
        "sample_counts": {variable: 1 for variable in variables},
    }


def test_clean_subset_removes_stale_unrequested_variable(tmp_path: Path, monkeypatch) -> None:
    args = _arguments(tmp_path, ["Te"])
    clean = args.data_root / "test" / "clean"
    clean.mkdir(parents=True)
    stale_dataset = clean / "deeponet_dataset_Ti.pt"
    stale_manifest = clean / "Ti_test_manifest.csv"
    stale_dataset.write_bytes(b"old")
    stale_manifest.write_text("old", encoding="utf-8")
    monkeypatch.setattr(clean_data, "parse_args", lambda: args)
    monkeypatch.setattr(
        clean_data,
        "build_clean_datasets",
        lambda dataset_root, output_dir, **kwargs: _fake_report(output_dir, ["Te"]),
    )

    clean_data.main()

    assert (clean / "deeponet_dataset_Te.pt").is_file()
    assert (clean / "Te_test_manifest.csv").is_file()
    assert not stale_dataset.exists()
    assert not stale_manifest.exists()


def test_missing_requested_variable_preserves_existing_clean(tmp_path: Path, monkeypatch) -> None:
    args = _arguments(tmp_path, ["Te", "ne"])
    clean = args.data_root / "test" / "clean"
    clean.mkdir(parents=True)
    existing = clean / "deeponet_dataset_Te.pt"
    existing.write_bytes(b"previous-clean")
    monkeypatch.setattr(clean_data, "parse_args", lambda: args)
    monkeypatch.setattr(
        clean_data,
        "build_clean_datasets",
        lambda dataset_root, output_dir, **kwargs: _fake_report(output_dir, ["Te"]),
    )

    with pytest.raises(ValueError, match="没有全部生成"):
        clean_data.main()

    assert existing.read_bytes() == b"previous-clean"
