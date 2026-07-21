from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .data import ProfileData
from .utils import csv_restore, csv_safe


VALID_SPLITS = {"train", "val", "test"}


@dataclass
class ResolvedSplit:
    """Resolved row indices and warnings for a user-controlled split."""

    indices: dict[str, list[int]]
    case_to_split: dict[str, str]
    unassigned_case_ids: list[str]
    warnings: list[str]


def resolve_dedicated_split(data: ProfileData, role: str) -> ResolvedSplit:
    """Assign every row to the role declared by its train/test directory.

    This is deterministic and does not create a statistical split.  It is only
    for datasets that the user has already placed under data/<role>/clean.
    """
    if role not in VALID_SPLITS:
        raise ValueError(f"Unsupported dataset role: {role}")
    indices = {name: [] for name in ("train", "val", "test")}
    indices[role] = list(range(len(data.case_ids)))
    return ResolvedSplit(
        indices=indices,
        case_to_split={case_id: role for case_id in sorted(set(data.case_ids))},
        unassigned_case_ids=[],
        warnings=[
            f"Dedicated {role} dataset: all rows use the manually assigned directory role; "
            "no random split was generated."
        ],
    )


def _read_id_file(path: Path | None) -> list[str]:
    if path is None:
        return []
    if not path.exists():
        raise FileNotFoundError(f"split ID 文件不存在: {path}")
    return [line.strip() for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def read_split_definition(
    manifest: Path | None = None,
    train_ids: Path | None = None,
    val_ids: Path | None = None,
    test_ids: Path | None = None,
) -> dict[str, str]:
    """Read either one CSV manifest or legacy one-ID-per-line files."""
    if manifest is not None and any(path is not None for path in (train_ids, val_ids, test_ids)):
        raise ValueError("--split-manifest 不能和 --train-ids/--val-ids/--test-ids 同时使用。")
    result: dict[str, str] = {}
    if manifest is not None:
        if not manifest.exists():
            raise FileNotFoundError(f"split manifest 不存在: {manifest}")
        with manifest.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None or not {"case_id", "split"}.issubset(reader.fieldnames):
                raise ValueError("split_manifest.csv 必须包含 case_id,split 两列。")
            for line_no, row in enumerate(reader, start=2):
                case_id = csv_restore((row.get("case_id") or "").strip())
                split = (row.get("split") or "").strip().lower()
                if not case_id or split not in VALID_SPLITS:
                    raise ValueError(f"split manifest 第 {line_no} 行无效: {row}")
                if case_id in result and result[case_id] != split:
                    raise ValueError(f"同一 case_id 出现在多个 split: {case_id}")
                result[case_id] = split
        return result
    for split, path in (("train", train_ids), ("val", val_ids), ("test", test_ids)):
        for case_id in _read_id_file(path):
            if case_id in result and result[case_id] != split:
                raise ValueError(f"同一 case_id 出现在多个 split: {case_id}")
            result[case_id] = split
    if not result:
        raise ValueError("必须提供 split manifest 或至少 --train-ids。")
    return result


def resolve_split(
    data: ProfileData,
    case_to_split: dict[str, str],
    allow_paper_overlap: bool = False,
) -> ResolvedSplit:
    """Validate a split. Train is required; val/test are intentionally optional."""
    dataset_cases = set(data.case_ids)
    unknown = sorted(set(case_to_split) - dataset_cases)
    if unknown:
        raise ValueError(f"split 中存在数据集没有的 case_id: {unknown}")
    if "train" not in set(case_to_split.values()):
        raise ValueError("当前项目至少需要 train split。val/test 可以暂时缺省。")
    indices = {name: [] for name in ("train", "val", "test")}
    for index, case_id in enumerate(data.case_ids):
        split = case_to_split.get(case_id)
        if split is not None:
            indices[split].append(index)
    unassigned = sorted(dataset_cases - set(case_to_split))
    warnings: list[str] = []
    if unassigned:
        warnings.append(f"{len(unassigned)} 个未分配 case 已排除: {unassigned}")

    papers = {
        split: {data.paper_ids[i] for i in split_indices}
        for split, split_indices in indices.items()
    }
    train_test_overlap = sorted(papers["train"] & papers["test"])
    if train_test_overlap and not allow_paper_overlap:
        raise ValueError(
            "检测到 train/test 论文级泄漏: "
            f"{train_test_overlap}。如确有科学理由，显式使用 --allow-paper-overlap。"
        )
    train_val_overlap = sorted(papers["train"] & papers["val"])
    if train_val_overlap:
        warnings.append(
            "train/val 共享论文，调参指标可能偏乐观: " + ", ".join(train_val_overlap)
        )
    return ResolvedSplit(indices, case_to_split, unassigned, warnings)


def write_resolved_split(data: ProfileData, split: ResolvedSplit, path: Path) -> None:
    """Write the exact profile rows used by the run."""
    path.parent.mkdir(parents=True, exist_ok=True)
    reverse = {index: name for name, values in split.indices.items() for index in values}
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["row_index", "profile_id", "case_id", "paper_id", "split"])
        for index in sorted(reverse):
            writer.writerow(
                [
                    index,
                    csv_safe(data.profile_ids[index]),
                    csv_safe(data.case_ids[index]),
                    csv_safe(data.paper_ids[index]),
                    reverse[index],
                ]
            )


def grouped_paper_folds(
    data: ProfileData,
    train_indices: Iterable[int],
    n_folds: int,
) -> list[tuple[list[int], list[int]]]:
    """Create deterministic tuning folds; every paper stays in one validation fold."""
    indices = list(train_indices)
    papers = sorted({data.paper_ids[i] for i in indices})
    if n_folds < 2:
        raise ValueError("cv_folds 必须至少为 2。")
    if len(papers) < n_folds:
        raise ValueError(f"只有 {len(papers)} 篇论文，不能做 {n_folds} 折论文分组交叉验证。")
    fold_papers = [set() for _ in range(n_folds)]
    paper_counts = {paper: sum(data.paper_ids[i] == paper for i in indices) for paper in papers}
    for paper in sorted(papers, key=lambda value: (-paper_counts[value], value)):
        target = min(range(n_folds), key=lambda fold: sum(paper_counts[p] for p in fold_papers[fold]))
        fold_papers[target].add(paper)
    result = []
    for held_out in fold_papers:
        val = [i for i in indices if data.paper_ids[i] in held_out]
        train = [i for i in indices if data.paper_ids[i] not in held_out]
        result.append((train, val))
    return result
