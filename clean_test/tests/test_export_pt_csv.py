import csv
from pathlib import Path

import torch

from export_pt_csv import CSV_FIELDS, export_pt_csv


def test_export_pt_csv_preserves_values_and_mask(tmp_path: Path) -> None:
    dataset = tmp_path / "deeponet_dataset_Te.pt"
    mask = torch.ones(2, 64)
    mask[1, -1] = 0
    torch.save(
        {
            "case_ids": ["C1", "=FORMULA"],
            "paper_ids": ["P1", "P2"],
            "profile_ids": ["profile_1", "profile_2"],
            "branch_input": torch.tensor([[-0.3, 1.0, 2.0], [-0.4, 1.2, 2.4]]),
            "trunk_x": torch.linspace(0.8, 1.0, 64),
            "targets": torch.stack(
                [torch.linspace(1.0, 0.2, 64), torch.linspace(1.2, 0.3, 64)]
            ),
            "valid_mask": mask,
            "variable": "Te",
            "metadata": {"units": "keV"},
        },
        dataset,
    )
    output = tmp_path / "inspection.csv"

    result = export_pt_csv(dataset, output)

    with result.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 128
    assert list(rows[0]) == CSV_FIELDS
    assert rows[0]["case_id"] == "C1"
    assert rows[64]["case_id"] == "'=FORMULA"
    assert rows[-1]["valid_mask"] == "0"
    assert float(rows[-1]["target_value"]) == float(torch.tensor(0.3, dtype=torch.float32))
