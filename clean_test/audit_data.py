from __future__ import annotations

import argparse
from pathlib import Path

from src.audit import audit_dataset, raise_if_audit_failed, save_audit
from src.data import load_profile_data
from src.split import (
    read_split_definition,
    resolve_dedicated_split,
    resolve_split,
    write_resolved_split,
)
from src.utils import setup_logging


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="训练前独立数据审计。")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--split-manifest", type=Path)
    parser.add_argument("--train-ids", type=Path)
    parser.add_argument("--val-ids", type=Path)
    parser.add_argument("--test-ids", type=Path)
    parser.add_argument("--variable", choices=["Te", "ne", "Ti"], required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--min-valid-points", type=int, default=4)
    parser.add_argument("--allow-paper-overlap", action="store_true")
    parser.add_argument(
        "--dataset-role",
        choices=["train", "val", "test"],
        default="train",
        help="Used only when no split manifest/ID files are supplied.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir or Path("outputs") / f"audit_{args.variable}"
    setup_logging(output_dir / "audit.log")
    data = load_profile_data(args.dataset)
    if data.variable is not None and data.variable != args.variable:
        raise ValueError(f"数据变量为 {data.variable}，命令行却指定 {args.variable}。")
    split_args = (args.split_manifest, args.train_ids, args.val_ids, args.test_ids)
    if any(value is not None for value in split_args):
        mapping = read_split_definition(*split_args)
        split = resolve_split(data, mapping, args.allow_paper_overlap)
    else:
        split = resolve_dedicated_split(data, args.dataset_role)
    report = audit_dataset(data, split, args.min_valid_points)
    save_audit(report, output_dir)
    write_resolved_split(data, split, output_dir / "split_resolved.csv")
    raise_if_audit_failed(report)


if __name__ == "__main__":
    main()
