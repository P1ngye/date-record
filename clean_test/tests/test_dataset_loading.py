from pathlib import Path

import torch

from src.data import load_profile_data


def test_pt_loader_ignores_precomputed_scaled_fields(tmp_path: Path):
    path = tmp_path / "data.pt"
    torch.save(
        {
            "case_ids": ["A"],
            "paper_ids": ["P"],
            "branch_input": torch.tensor([[1.0, 2.0, 3.0]]),
            "branch_scaled": torch.tensor([[999.0, 999.0, 999.0]]),
            "scaler_mean": torch.tensor([999.0, 999.0, 999.0]),
            "scaler_std": torch.tensor([999.0, 999.0, 999.0]),
            "trunk_x": torch.linspace(0.8, 1.0, 64),
            "targets": torch.ones(1, 64),
            "valid_mask": torch.ones(1, 64),
        },
        path,
    )
    loaded = load_profile_data(path)
    assert loaded.branch_input.tolist() == [[1.0, 2.0, 3.0]]


def test_npz_is_supported(tmp_path: Path):
    import numpy as np

    path = tmp_path / "data.npz"
    np.savez(
        path,
        case_ids=np.array(["A"]),
        paper_ids=np.array(["P"]),
        branch_input=np.ones((1, 3)),
        trunk_x=np.linspace(0.8, 1.0, 64),
        targets=np.ones((1, 64)),
        valid_mask=np.ones((1, 64)),
    )
    assert load_profile_data(path).targets.shape == (1, 64)
