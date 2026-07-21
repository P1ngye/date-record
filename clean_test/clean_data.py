from __future__ import annotations

import argparse
import logging
import os
import tempfile
from pathlib import Path

from src.data_layout import DatasetLayout
from src.raw_builder import build_clean_datasets, write_role_manifest
from src.utils import setup_logging, write_json


LOGGER = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Clean one already-organized raw split; this command never copies or splits data."
    )
    parser.add_argument("--split", choices=["train", "test"], required=True)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--raw-dir", type=Path, help="Override data/<split>/raw.")
    parser.add_argument("--clean-dir", type=Path, help="Override data/<split>/clean.")
    parser.add_argument(
        "--variables", nargs="+", choices=["Te", "ne", "Ti"], default=["Te", "ne", "Ti"]
    )
    parser.add_argument("--min-valid-points", type=int, default=4)
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    layout = DatasetLayout(args.data_root, args.split)
    raw_dir = (args.raw_dir or layout.raw).resolve()
    clean_dir = (args.clean_dir or layout.clean).resolve()
    if raw_dir == clean_dir:
        raise ValueError("raw and clean directories must be different")
    if raw_dir.is_symlink() or clean_dir.is_symlink():
        raise ValueError("raw/clean 顶层目录不能是符号链接。")
    if not (raw_dir / "database_by_paper").is_dir() or not (raw_dir / "data").is_dir():
        raise FileNotFoundError(
            f"{raw_dir} must contain database_by_paper/ and data/. Run organize_data.py first."
        )
    clean_dir.parent.mkdir(parents=True, exist_ok=True)
    clean_dir.mkdir(parents=True, exist_ok=True)
    setup_logging(clean_dir / "clean_data.log")
    with tempfile.TemporaryDirectory(
        prefix=f".{clean_dir.name}-staging-", dir=clean_dir.parent
    ) as temporary:
        staging = Path(temporary)
        report = build_clean_datasets(
            dataset_root=raw_dir,
            output_dir=staging,
            variables=args.variables,
            min_valid_points=args.min_valid_points,
            strict=args.strict,
            dataset_role=args.split,
        )
        missing = sorted(set(args.variables) - set(report["generated_files"]))
        if missing:
            raise ValueError(
                f"请求的变量没有全部生成: {missing}。旧 clean 目录保持不变；"
                "如数据确实不含这些变量，请用 --variables 显式指定。"
            )
        report["generated_files"] = {
            variable: str((clean_dir / f"deeponet_dataset_{variable}.pt").resolve())
            for variable in report["generated_files"]
        }
        report["clean_output"] = str(clean_dir.resolve())
        write_json(report, staging / "build_report.json")
        for variable in report["generated_files"]:
            write_role_manifest(
                staging / f"deeponet_dataset_{variable}.pt",
                staging / f"{variable}_{args.split}_manifest.csv",
                args.split,
            )
        staged_files = sorted(value for value in staging.iterdir() if value.is_file())
        stale_files = [
            clean_dir / filename
            for variable in {"Te", "ne", "Ti"} - set(args.variables)
            for filename in (
                f"deeponet_dataset_{variable}.pt",
                f"{variable}_{args.split}_manifest.csv",
            )
        ]
        destinations = [clean_dir / staged_file.name for staged_file in staged_files]
        for destination in destinations + stale_files:
            if destination.is_symlink():
                raise ValueError(f"拒绝覆盖符号链接 clean 文件: {destination}")
        for staged_file in staged_files:
            destination = clean_dir / staged_file.name
            os.replace(staged_file, destination)
        for stale_file in stale_files:
            stale_file.unlink(missing_ok=True)
    LOGGER.info(
        "Cleaned %s data: %s",
        args.split,
        ", ".join(f"{key}={value}" for key, value in report["sample_counts"].items()),
    )


if __name__ == "__main__":
    main()
