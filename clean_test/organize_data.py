from __future__ import annotations

import argparse
import logging
from pathlib import Path

from src.data_layout import (
    DatasetLayout,
    adopt_clean_data,
    organize_raw_data,
    write_missing_raw_notice,
)
from src.utils import setup_logging


LOGGER = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Safely copy manually assigned data into data/<train|test>/{raw,clean}."
    )
    parser.add_argument("--split", choices=["train", "test"], required=True)
    parser.add_argument("--raw-source", type=Path)
    parser.add_argument("--clean-source", type=Path)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--missing-raw-reason",
        help="Write an explicit RAW_DATA_MISSING.md when only legacy clean data is available.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.raw_source is None and args.clean_source is None:
        raise ValueError("Provide --raw-source and/or --clean-source.")
    layout = DatasetLayout(args.data_root, args.split)
    setup_logging(layout.role_root / "organize_data.log")
    layout.create()
    if args.raw_source is not None:
        rows = organize_raw_data(args.raw_source, layout, args.overwrite)
        LOGGER.info("Organized %d raw files into %s", len(rows), layout.raw)
    elif args.missing_raw_reason:
        notice = write_missing_raw_notice(layout, args.missing_raw_reason)
        LOGGER.warning("Raw source is missing; lineage notice written to %s", notice)
    if args.clean_source is not None:
        rows = adopt_clean_data(args.clean_source, layout, args.overwrite)
        LOGGER.info("Adopted %d clean artifacts into %s", len(rows), layout.clean)


if __name__ == "__main__":
    main()
