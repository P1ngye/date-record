import pytest
import torch

from src.data import ProfileData
from src.split import resolve_dedicated_split, resolve_split


def make_data():
    return ProfileData(
        case_ids=["A", "B", "C"],
        paper_ids=["P1", "P1", "P2"],
        profile_ids=["a", "b", "c"],
        branch_input=torch.ones(3, 3),
        trunk_x=torch.linspace(0.8, 1.0, 64),
        targets=torch.ones(3, 64),
        valid_mask=torch.ones(3, 64),
    )


def test_train_only_is_allowed():
    result = resolve_split(make_data(), {"A": "train", "B": "train"})
    assert result.indices["test"] == []
    assert result.unassigned_case_ids == ["C"]


def test_dedicated_test_dataset_assigns_every_row_without_random_split():
    result = resolve_dedicated_split(make_data(), "test")
    assert result.indices["train"] == []
    assert result.indices["val"] == []
    assert result.indices["test"] == [0, 1, 2]


def test_train_test_case_mapping_cannot_conflict():
    # A dict cannot represent two mappings; CSV parser tests this before resolution.
    result = resolve_split(make_data(), {"A": "train", "C": "test"})
    assert set(result.indices["train"]).isdisjoint(result.indices["test"])


def test_paper_overlap_is_rejected_by_default():
    with pytest.raises(ValueError, match="论文级泄漏"):
        resolve_split(make_data(), {"A": "train", "B": "test"})
