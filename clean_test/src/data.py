from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import torch
from torch.utils.data import Dataset

from .utils import safe_torch_load, validate_archive_size


REQUIRED_KEYS = {
    "case_ids",
    "paper_ids",
    "branch_input",
    "trunk_x",
    "targets",
    "valid_mask",
}


@dataclass
class ProfileData:
    """Validated in-memory representation of a cleaned DeepONet dataset."""

    case_ids: list[str]
    paper_ids: list[str]
    profile_ids: list[str]
    branch_input: torch.Tensor
    trunk_x: torch.Tensor
    targets: torch.Tensor
    valid_mask: torch.Tensor
    variable: str | None = None
    metadata: dict[str, Any] | None = None

    def subset(self, indices: Sequence[int]) -> "ProfileData":
        idx = torch.as_tensor(list(indices), dtype=torch.long)
        return ProfileData(
            case_ids=[self.case_ids[i] for i in idx.tolist()],
            paper_ids=[self.paper_ids[i] for i in idx.tolist()],
            profile_ids=[self.profile_ids[i] for i in idx.tolist()],
            branch_input=self.branch_input[idx],
            trunk_x=self.trunk_x,
            targets=self.targets[idx],
            valid_mask=self.valid_mask[idx],
            variable=self.variable,
            metadata=self.metadata,
        )


def _safe_torch_load(path: Path) -> dict[str, Any]:
    return safe_torch_load(path, map_location="cpu")


def load_profile_data(path: Path) -> ProfileData:
    """Load .pt or .npz while intentionally ignoring stored scaled fields."""
    if not path.exists():
        raise FileNotFoundError(f"数据集不存在: {path}")
    if path.suffix.lower() == ".pt":
        raw = _safe_torch_load(path)
    elif path.suffix.lower() == ".npz":
        validate_archive_size(path)
        try:
            with np.load(path, allow_pickle=False) as archive:
                raw = {key: archive[key] for key in archive.files}
        except ValueError as exc:
            raise ValueError(
                f"{path} 包含需要 pickle 的 object 数组；为避免任意代码执行，"
                "请把字符串 ID 保存为 NumPy Unicode 数组（dtype='<U...'）。"
            ) from exc
    else:
        raise ValueError("数据集只支持 .pt 或 .npz。")
    missing = REQUIRED_KEYS - set(raw)
    if missing:
        raise KeyError(f"数据集缺少字段: {sorted(missing)}")

    # Deliberately do not read branch_scaled/scaler_mean/scaler_std.
    case_ids = [str(value) for value in list(raw["case_ids"])]
    paper_ids = [str(value) for value in list(raw["paper_ids"])]
    profile_values = raw.get("profile_ids", [f"{case_id}__row{i}" for i, case_id in enumerate(case_ids)])
    profile_ids = [str(value) for value in list(profile_values)]
    variable_raw = raw.get("variable")
    if isinstance(variable_raw, np.ndarray) and variable_raw.ndim == 0:
        variable_raw = variable_raw.item()
    return ProfileData(
        case_ids=case_ids,
        paper_ids=paper_ids,
        profile_ids=profile_ids,
        branch_input=torch.as_tensor(raw["branch_input"], dtype=torch.float32).clone(),
        trunk_x=torch.as_tensor(raw["trunk_x"], dtype=torch.float32).flatten().clone(),
        targets=torch.as_tensor(raw["targets"], dtype=torch.float32).clone(),
        valid_mask=torch.as_tensor(raw["valid_mask"], dtype=torch.float32).clone(),
        variable=str(variable_raw) if variable_raw is not None else None,
        metadata=raw.get("metadata", {}),
    )


class EdgeProfileDataset(Dataset[dict[str, Any]]):
    """One item is one measured profile; trunk_x is shared and not duplicated."""

    def __init__(
        self,
        data: ProfileData,
        indices: Sequence[int],
        branch_values: torch.Tensor,
        target_values: torch.Tensor,
    ) -> None:
        self.data = data
        self.indices = list(indices)
        if len(self.indices) != branch_values.shape[0] or len(self.indices) != target_values.shape[0]:
            raise ValueError("indices、branch_values 和 target_values 的样本数不一致。")
        self.branch_values = branch_values
        self.target_values = target_values

    def __len__(self) -> int:
        return len(self.indices)

    def __getitem__(self, item: int) -> dict[str, Any]:
        source_index = self.indices[item]
        return {
            "case_id": self.data.case_ids[source_index],
            "paper_id": self.data.paper_ids[source_index],
            "profile_id": self.data.profile_ids[source_index],
            "branch": self.branch_values[item],
            "target": self.target_values[item],
            "mask": self.data.valid_mask[source_index],
            "source_index": source_index,
        }
