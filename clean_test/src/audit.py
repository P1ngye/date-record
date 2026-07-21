from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import torch

from .data import ProfileData
from .split import ResolvedSplit
from .utils import csv_safe, write_json


def _stats(values: torch.Tensor) -> dict[str, float]:
    array = values.detach().cpu().numpy().astype(float)
    return {
        "min": float(array.min()),
        "max": float(array.max()),
        "mean": float(array.mean()),
        "std": float(array.std()),
    }


def audit_dataset(
    data: ProfileData,
    split: ResolvedSplit | None,
    min_valid_points: int = 4,
) -> dict[str, Any]:
    """Audit dataset structure, masks, identifiers, split and extrapolation."""
    errors: list[str] = []
    warnings: list[str] = []
    n_samples = len(data.case_ids)
    if data.branch_input.shape != (n_samples, 3):
        errors.append(f"branch_input 应为 [{n_samples},3]，收到 {list(data.branch_input.shape)}")
    if data.targets.ndim != 2 or data.targets.shape[0] != n_samples or data.targets.shape[1] != 64:
        errors.append(f"targets 应为 [{n_samples},64]，收到 {list(data.targets.shape)}")
    if data.valid_mask.shape != data.targets.shape:
        errors.append("valid_mask 与 targets 形状不一致。")
    if data.trunk_x.shape != (64,):
        errors.append(f"trunk_x 应为 [64]，收到 {list(data.trunk_x.shape)}")
    if not (len(data.paper_ids) == len(data.profile_ids) == n_samples):
        errors.append("case_ids/paper_ids/profile_ids 与张量第一维长度不一致。")
    if not torch.isfinite(data.branch_input).all():
        errors.append("branch_input 包含 NaN 或 Inf。")
    if not torch.isfinite(data.targets[data.valid_mask.bool()]).all():
        errors.append("有效 targets 包含 NaN 或 Inf。")
    mask_values = set(torch.unique(data.valid_mask).tolist())
    if not mask_values.issubset({0.0, 1.0}):
        errors.append(f"valid_mask 只能包含 0/1，发现 {sorted(mask_values)}")
    if data.trunk_x.numel() > 1 and not torch.all(data.trunk_x[1:] > data.trunk_x[:-1]):
        errors.append("trunk_x 必须严格单调递增。")
    if data.trunk_x.numel() and (float(data.trunk_x.min()) < 0.8 - 1e-6 or float(data.trunk_x.max()) > 1.0 + 1e-6):
        errors.append("trunk_x 必须处于 [0.8,1.0]。")
    valid_counts = data.valid_mask.sum(dim=1)
    bad_profiles = [data.profile_ids[i] for i, count in enumerate(valid_counts) if int(count) < min_valid_points]
    if bad_profiles:
        errors.append(f"以下 profile 有效点少于 {min_valid_points}: {bad_profiles}")
    duplicate_profiles = sorted(key for key, count in Counter(data.profile_ids).items() if count > 1)
    if duplicate_profiles:
        errors.append(f"profile_id 重复: {duplicate_profiles}")
    duplicate_cases = sorted(key for key, count in Counter(data.case_ids).items() if count > 1)
    if duplicate_cases:
        warnings.append(
            "同一 case_id 有多条 profile；已保留全部并依赖 profile_id 区分，split 仍按 case_id 锁定: "
            + ", ".join(duplicate_cases)
        )

    report: dict[str, Any] = {
        "status": "error" if errors else "ok",
        "errors": errors,
        "warnings": warnings,
        "dataset": {
            "samples": n_samples,
            "unique_cases": len(set(data.case_ids)),
            "unique_papers": len(set(data.paper_ids)),
            "variable": data.variable,
            "valid_point_ratio": float(data.valid_mask.mean()) if data.valid_mask.numel() else 0.0,
            "duplicate_case_ids": duplicate_cases,
            "branch_statistics": {
                "delta": _stats(data.branch_input[:, 0]) if n_samples else {},
                "T_0_keV": _stats(data.branch_input[:, 1]) if n_samples else {},
                "n_0_1e19m3": _stats(data.branch_input[:, 2]) if n_samples else {},
            },
        },
    }
    if split is not None:
        warnings.extend(split.warnings)
        split_stats: dict[str, Any] = {}
        for name, indices in split.indices.items():
            split_stats[name] = {
                "samples": len(indices),
                "cases": len({data.case_ids[i] for i in indices}),
                "papers": len({data.paper_ids[i] for i in indices}),
                "valid_point_ratio": (
                    float(data.valid_mask[indices].mean()) if indices else None
                ),
            }
        report["split"] = split_stats
        report["unassigned_case_ids"] = split.unassigned_case_ids
        train_indices = split.indices["train"]
        test_indices = split.indices["test"]
        extrapolated: list[dict[str, Any]] = []
        if train_indices and test_indices:
            train_branch = data.branch_input[train_indices]
            low = train_branch.min(dim=0).values
            high = train_branch.max(dim=0).values
            for index in test_indices:
                outside = (data.branch_input[index] < low) | (data.branch_input[index] > high)
                if outside.any():
                    extrapolated.append(
                        {
                            "profile_id": data.profile_ids[index],
                            "case_id": data.case_ids[index],
                            "outside_features": [
                                name
                                for flag, name in zip(outside.tolist(), ["delta", "T_0", "n_0"])
                                if flag
                            ],
                        }
                    )
            if extrapolated:
                warnings.append(f"{len(extrapolated)} 个 test profile 超出 train branch 范围。")
        report["test_extrapolation"] = extrapolated
    report["warnings"] = warnings
    return report


def save_audit(report: dict[str, Any], output_dir: Path) -> None:
    """Save nested JSON plus a flat summary CSV."""
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(report, output_dir / "data_audit.json")
    rows: list[tuple[str, str, Any]] = []
    rows.append(("status", "", report["status"]))
    for message in report.get("errors", []):
        rows.append(("error", "", message))
    for message in report.get("warnings", []):
        rows.append(("warning", "", message))
    for key, value in report.get("dataset", {}).items():
        if not isinstance(value, (dict, list)):
            rows.append(("dataset", key, value))
    for split, values in report.get("split", {}).items():
        for key, value in values.items():
            rows.append((f"split:{split}", key, value))
    with (output_dir / "data_audit.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["section", "metric", "value"])
        writer.writerows(tuple(csv_safe(value) for value in row) for row in rows)


def raise_if_audit_failed(report: dict[str, Any]) -> None:
    """Stop training on serious audit errors; never silently repair them."""
    if report.get("errors"):
        joined = "\n- ".join(str(value) for value in report["errors"])
        raise ValueError(f"数据审计失败:\n- {joined}")
