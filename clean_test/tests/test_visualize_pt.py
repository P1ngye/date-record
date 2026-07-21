import csv
from pathlib import Path

import torch

from visualize_pt import visualize_profiles


def _write_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    raw_root = tmp_path / "data" / "train" / "raw"
    raw_data = raw_root / "data" / "paper_1"
    raw_data.mkdir(parents=True)
    profile_id = "profile_1"
    (raw_data / f"{profile_id}.csv").write_text(
        "x,y\n0.75,2.5\n0.80,2.4\n0.90,2.2\n1.00,2.0\n",
        encoding="utf-8",
    )

    clean_dir = raw_root.parent / "clean"
    clean_dir.mkdir()
    conversion_log = clean_dir / "unit_conversion_log.csv"
    conversion_log.write_text(
        "profile_id,conversion\nprofile_1,keV -> keV (factor=1)\n",
        encoding="utf-8-sig",
    )
    rho = torch.linspace(0.8, 1.0, 64)
    dataset = clean_dir / "deeponet_dataset_Te.pt"
    torch.save(
        {
            "case_ids": ["case_1"],
            "paper_ids": ["paper_1"],
            "profile_ids": [profile_id],
            "branch_input": torch.tensor([[-0.3, 2.4, 4.0]]),
            "trunk_x": rho,
            "targets": (4.0 - 2.0 * rho).unsqueeze(0),
            "valid_mask": torch.ones(1, 64),
            "variable": "Te",
            "metadata": {"source_root": str(raw_root), "units": "keV"},
        },
        dataset,
    )
    return dataset, raw_root, conversion_log


def test_visualize_pt_creates_individual_plot_overview_csv_and_manifest(tmp_path: Path) -> None:
    dataset, _, _ = _write_fixture(tmp_path)
    output_dir = tmp_path / "pt_plots"

    artifacts = visualize_profiles(
        dataset, output_dir=output_dir, dpi=72, profiles_per_page=1
    )

    expected = {
        output_dir / "inspection_data.csv",
        output_dir / "profiles" / "000_profile_1.png",
        output_dir / "overview_page_001.png",
        output_dir / "visualization_manifest.csv",
    }
    assert expected.issubset(set(artifacts))
    assert all(path.is_file() and path.stat().st_size > 0 for path in expected)
    with (output_dir / "visualization_manifest.csv").open(
        "r", encoding="utf-8-sig", newline=""
    ) as handle:
        row = next(csv.DictReader(handle))
    assert row["profile_id"] == "profile_1"
    assert int(row["raw_point_count"]) == 4
    assert float(row["max_abs_error"]) < 1e-6


def test_visualize_exported_csv_also_uses_original_points(tmp_path: Path) -> None:
    dataset, raw_root, conversion_log = _write_fixture(tmp_path)
    first_output = tmp_path / "first"
    visualize_profiles(dataset, output_dir=first_output, dpi=72)

    csv_output = first_output / "inspection_data.csv"
    second_output = tmp_path / "from_csv"
    artifacts = visualize_profiles(
        csv_output,
        output_dir=second_output,
        raw_root=raw_root,
        conversion_log=conversion_log,
        dpi=72,
        export_csv=False,
    )

    profile_plot = second_output / "profiles" / "000_profile_1.png"
    assert profile_plot in artifacts
    assert profile_plot.stat().st_size > 0
