from pathlib import Path

import pytest

from src.data_layout import DatasetLayout, organize_raw_data


def test_flat_source_is_copied_to_canonical_raw_layout(tmp_path: Path):
    source = tmp_path / "incoming"
    source.mkdir()
    (source / "Paper_profile_database.xlsx").write_bytes(b"workbook")
    profile_dir = source / "Paper" / "Fig1"
    profile_dir.mkdir(parents=True)
    (profile_dir / "Paper__Fig1__Te__case.csv").write_text("x,y\n0.8,1\n", encoding="utf-8")

    layout = DatasetLayout(tmp_path / "data", "test")
    rows = organize_raw_data(source, layout)

    assert len(rows) == 2
    assert (layout.raw_workbooks / "Paper_profile_database.xlsx").is_file()
    assert (layout.raw_profiles / "Paper" / "Fig1" / "Paper__Fig1__Te__case.csv").is_file()
    assert (layout.raw / "raw_manifest.csv").is_file()


def test_organizer_refuses_conflicting_overwrite(tmp_path: Path):
    source = tmp_path / "incoming"
    source.mkdir()
    (source / "Paper_profile_database.xlsx").write_bytes(b"one")
    profile_dir = source / "Paper"
    profile_dir.mkdir()
    (profile_dir / "Paper__Fig1__Te__case.csv").write_text("x,y\n0.8,1\n", encoding="utf-8")
    layout = DatasetLayout(tmp_path / "data", "test")
    organize_raw_data(source, layout)
    (source / "Paper_profile_database.xlsx").write_bytes(b"two")

    with pytest.raises(FileExistsError, match="different content"):
        organize_raw_data(source, layout)
