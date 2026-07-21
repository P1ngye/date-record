from __future__ import annotations

import argparse
import csv
from pathlib import Path

from src.data import ProfileData, load_profile_data
from src.utils import csv_safe


CSV_FIELDS = [
    "sample_index",
    "grid_index",
    "variable",
    "case_id",
    "paper_id",
    "profile_id",
    "delta",
    "T0_keV",
    "n0_1e19m3",
    "rho",
    "target_value",
    "target_unit",
    "valid_mask",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="将一个 clean DeepONet .pt 数据集展开为人工查验 CSV。"
    )
    parser.add_argument("--dataset", type=Path, required=True, help="clean .pt 文件路径")
    parser.add_argument(
        "--output",
        type=Path,
        help="CSV 输出路径；默认写入 outputs/pt_csv/<train|test>/<pt文件名>.csv",
    )
    return parser.parse_args()


def _default_output_path(dataset_path: Path) -> Path:
    role = "dataset"
    if dataset_path.parent.name.lower() == "clean" and dataset_path.parent.parent.name in {
        "train",
        "test",
    }:
        role = dataset_path.parent.parent.name
    return Path("outputs") / "pt_csv" / role / f"{dataset_path.stem}.csv"


def _target_unit(data: ProfileData) -> str:
    if isinstance(data.metadata, dict) and data.metadata.get("units"):
        return str(data.metadata["units"])
    return "keV" if data.variable in {"Te", "Ti"} else "10^19 m^-3"


def _validate_shapes(data: ProfileData) -> None:
    sample_count = len(data.case_ids)
    if len(data.paper_ids) != sample_count or len(data.profile_ids) != sample_count:
        raise ValueError("case_ids、paper_ids、profile_ids 的长度不一致。")
    if data.branch_input.shape != (sample_count, 3):
        raise ValueError(
            f"branch_input 应为 [{sample_count},3]，收到 {list(data.branch_input.shape)}"
        )
    if data.targets.ndim != 2 or data.targets.shape[0] != sample_count:
        raise ValueError("targets 的第一维必须与 profile 数量一致。")
    if data.valid_mask.shape != data.targets.shape:
        raise ValueError("valid_mask 与 targets 形状不一致。")
    if data.trunk_x.ndim != 1 or data.trunk_x.shape[0] != data.targets.shape[1]:
        raise ValueError("trunk_x 长度必须与 targets 的网格维一致。")


def export_pt_csv(dataset_path: Path, output_path: Path) -> Path:
    dataset_path = dataset_path.resolve()
    if dataset_path.suffix.lower() != ".pt":
        raise ValueError("只支持 clean .pt 文件。")
    data = load_profile_data(dataset_path)
    _validate_shapes(data)

    output_path = output_path.resolve()
    if output_path.suffix.lower() != ".csv":
        raise ValueError("输出文件必须使用 .csv 后缀。")
    if output_path.is_symlink():
        raise ValueError(f"拒绝覆盖符号链接: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    branch = data.branch_input.detach().cpu()
    trunk = data.trunk_x.detach().cpu()
    targets = data.targets.detach().cpu()
    masks = data.valid_mask.detach().cpu()
    variable = data.variable or ""
    unit = _target_unit(data)

    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for sample_index in range(len(data.profile_ids)):
            identifiers = {
                "variable": csv_safe(variable),
                "case_id": csv_safe(data.case_ids[sample_index]),
                "paper_id": csv_safe(data.paper_ids[sample_index]),
                "profile_id": csv_safe(data.profile_ids[sample_index]),
                "delta": float(branch[sample_index, 0]),
                "T0_keV": float(branch[sample_index, 1]),
                "n0_1e19m3": float(branch[sample_index, 2]),
                "target_unit": csv_safe(unit),
            }
            for grid_index in range(trunk.numel()):
                writer.writerow(
                    {
                        "sample_index": sample_index,
                        "grid_index": grid_index,
                        **identifiers,
                        "rho": float(trunk[grid_index]),
                        "target_value": float(targets[sample_index, grid_index]),
                        "valid_mask": int(bool(masks[sample_index, grid_index])),
                    }
                )
    return output_path


def main() -> None:
    args = parse_args()
    output_path = args.output or _default_output_path(args.dataset)
    result = export_pt_csv(args.dataset, output_path)
    with result.open("r", encoding="utf-8-sig") as handle:
        row_count = sum(1 for _ in handle) - 1
    print(f"Generated CSV: {result} ({row_count} rows)")


if __name__ == "__main__":
    main()
