from pathlib import Path

import numpy as np
import pytest
import torch

from src.config import validate_config
from src.data import load_profile_data
from src.raw_builder import RawProfile, _locate_csv, _match_reference, _read_xy
from src.utils import csv_restore, csv_safe, safe_output_subdir, safe_torch_load


def test_output_name_cannot_escape_root(tmp_path: Path):
    for name in ("..", "../escape", "nested/name", "C:\\escape"):
        with pytest.raises(ValueError):
            safe_output_subdir(tmp_path, name)


def test_npz_object_arrays_are_rejected_without_pickle(tmp_path: Path):
    path = tmp_path / "unsafe.npz"
    np.savez(
        path,
        case_ids=np.asarray(["A"], dtype=object),
        paper_ids=np.asarray(["P"], dtype=object),
        branch_input=np.ones((1, 3)),
        trunk_x=np.linspace(0.8, 1.0, 64),
        targets=np.ones((1, 64)),
        valid_mask=np.ones((1, 64)),
    )
    with pytest.raises(ValueError, match="object"):
        load_profile_data(path)


def test_restricted_torch_loader_accepts_plain_state_dict(tmp_path: Path):
    path = tmp_path / "safe.pt"
    torch.save({"tensor": torch.ones(2), "value": 3}, path)
    loaded = safe_torch_load(path)
    assert loaded["value"] == 3


def test_metadata_csv_path_cannot_escape_raw_root(tmp_path: Path):
    profile = {
        "profile_id": "Paper__Fig1__Te__case",
        "paper_id": "Paper",
        "variable": "Te",
        "target_points_csv_relpath": "../../outside.csv",
    }
    path, warnings = _locate_csv(tmp_path, profile, [])
    assert path is None
    assert any("越出 raw 根目录" in warning for warning in warnings)


def test_profile_csv_name_mismatch_is_not_fuzzily_matched(tmp_path: Path):
    existing = tmp_path / "Paper__Fig2d__ne__28008.csv"
    existing.write_text("x,y\n0.8,1\n1.0,2\n", encoding="utf-8")
    profile = {
        "profile_id": "Paper__Fig2c__ne__28008",
        "paper_id": "Paper",
        "variable": "ne",
    }

    path, warnings = _locate_csv(tmp_path, profile, [existing])

    assert path is None
    assert any("拒绝模糊匹配" in warning for warning in warnings)


def test_malformed_numeric_row_after_data_start_is_not_silently_skipped(tmp_path: Path):
    path = tmp_path / "profile.csv"
    path.write_text("x,y\n0.8,1.0\nnot-a-number,2.0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="不是有效"):
        _read_xy(path)


def test_ambiguous_reference_does_not_use_heuristic_matching(tmp_path: Path):
    def profile(profile_id: str, variable: str) -> RawProfile:
        return RawProfile(
            profile_id=profile_id,
            paper_id="P",
            case_id="C",
            variable=variable,
            coord_name="rho",
            unit_raw="keV",
            status="ready",
            csv_path=tmp_path / f"{profile_id}.csv",
            x=np.asarray([0.8, 1.0]),
            y=np.asarray([1.0, 0.0]),
        )

    target = profile("P__Fig3__Ti__phase", "Ti")
    candidates = [
        profile("P__Fig1__Te__phase_a", "Te"),
        profile("P__Fig2__Te__phase_b", "Te"),
    ]
    with pytest.raises(ValueError, match="拒绝启发式匹配"):
        _match_reference(target, candidates)


def test_csv_formula_escape_round_trip():
    value = "=HYPERLINK(\"bad\")"
    assert csv_restore(csv_safe(value)) == value


def test_nonnegative_constraint_rejected_in_standardized_space():
    config = {
        "variable": "Te",
        "data": {"target_scaling": "standard", "scaler_eps": 1e-8, "min_valid_points": 4},
        "model": {
            "branch_input_dim": 3,
            "trunk_input_dim": 1,
            "latent_dim": 8,
            "branch_hidden_dims": [8],
            "trunk_hidden_dims": [8],
            "dropout": 0.0,
            "nonnegative_output": True,
        },
        "loss": {"mse_weight": 1.0},
        "training": {
            "epochs": 1,
            "batch_size": 1,
            "learning_rate": 1e-3,
            "weight_decay": 0.0,
            "optimizer": "adamw",
            "scheduler": "none",
            "num_workers": 0,
        },
    }
    with pytest.raises(ValueError, match="标准化空间"):
        validate_config(config)
