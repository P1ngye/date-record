from __future__ import annotations

import argparse
import csv
import math
import re
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.interpolate import PchipInterpolator

from export_pt_csv import export_pt_csv
from src.data import load_profile_data


REQUIRED_CSV_FIELDS = {
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
}
FACTOR_PATTERN = re.compile(r"factor\s*=\s*([^\s)]+)", re.IGNORECASE)


@dataclass(frozen=True)
class ProfileSeries:
    sample_index: int
    variable: str
    case_id: str
    paper_id: str
    profile_id: str
    delta: float
    t0_kev: float
    n0_1e19m3: float
    unit: str
    rho: np.ndarray
    values: np.ndarray
    mask: np.ndarray


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "\u5c06 clean PT \u6216 export_pt_csv.py \u751f\u6210\u7684\u957f\u8868 CSV \u7ed8\u5236\u4e3a\u9010\u5256\u9762\u9ad8\u6e05\u5ba1\u67e5\u56fe\uff1b"
            "\u56fe\u4e2d\u540c\u65f6\u663e\u793a\u539f\u59cb\u91c7\u6837\u70b9\u3001PCHIP \u66f2\u7ebf\u3001PT \u7f51\u683c\u70b9\u548c\u63d2\u503c\u6b8b\u5dee\u3002"
        )
    )
    parser.add_argument(
        "--input",
        "--dataset",
        dest="input_path",
        type=Path,
        required=True,
        help="clean .pt \u6587\u4ef6\u6216 PT \u5bfc\u51fa\u7684\u957f\u8868 .csv \u6587\u4ef6",
    )
    parser.add_argument("--output-dir", type=Path, help="\u56fe\u7247\u8f93\u51fa\u76ee\u5f55")
    parser.add_argument(
        "--raw-root",
        type=Path,
        help="\u5305\u542b data/ \u548c database_by_paper/ \u7684 raw \u6839\u76ee\u5f55\uff1bPT \u9ed8\u8ba4\u8bfb\u53d6 metadata.source_root",
    )
    parser.add_argument(
        "--conversion-log",
        type=Path,
        help="unit_conversion_log.csv\uff1b\u9ed8\u8ba4\u4ece clean \u6570\u636e\u76ee\u5f55\u63a8\u65ad",
    )
    parser.add_argument("--dpi", type=int, default=180, help="\u8f93\u51fa\u5206\u8fa8\u7387\uff0c\u9ed8\u8ba4 180 DPI")
    parser.add_argument(
        "--profiles-per-page", type=int, default=6, help="\u6bcf\u5f20\u603b\u89c8\u9875\u7684\u5256\u9762\u6570\uff0c\u9ed8\u8ba4 6"
    )
    parser.add_argument(
        "--max-profiles",
        type=int,
        help="\u4ec5\u5904\u7406\u524d N \u4e2a\u5256\u9762\uff0c\u9002\u5408\u5feb\u901f\u8bd5\u753b\uff1b\u9ed8\u8ba4\u5904\u7406\u5168\u90e8",
    )
    parser.add_argument(
        "--no-export-csv",
        action="store_true",
        help="\u8f93\u5165\u4e3a PT \u65f6\u4e0d\u5728\u56fe\u7247\u76ee\u5f55\u540c\u65f6\u751f\u6210 inspection_data.csv",
    )
    return parser.parse_args()


def _role_from_path(path: Path) -> str:
    if path.parent.name.lower() == "clean" and path.parent.parent.name.lower() in {
        "train",
        "test",
        "val",
    }:
        return path.parent.parent.name.lower()
    if path.parent.name.lower() in {"train", "test", "val"}:
        return path.parent.name.lower()
    return "dataset"


def _default_output_dir(input_path: Path) -> Path:
    return (
        Path("outputs")
        / "pt_visualizations"
        / _role_from_path(input_path)
        / input_path.stem
    )


def _target_unit(variable: str, metadata: dict[str, Any]) -> str:
    if metadata.get("units"):
        return str(metadata["units"])
    return "keV" if variable in {"Te", "Ti"} else "10^19 m^-3"


def _load_pt(path: Path) -> tuple[list[ProfileSeries], dict[str, Any]]:
    data = load_profile_data(path)
    sample_count = len(data.profile_ids)
    if data.targets.ndim != 2 or data.targets.shape[0] != sample_count:
        raise ValueError("targets \u7684\u7b2c\u4e00\u7ef4\u5fc5\u987b\u4e0e profile_ids \u6570\u91cf\u4e00\u81f4\u3002")
    if data.valid_mask.shape != data.targets.shape:
        raise ValueError("valid_mask \u4e0e targets \u5f62\u72b6\u4e0d\u4e00\u81f4\u3002")
    if data.trunk_x.ndim != 1 or data.trunk_x.shape[0] != data.targets.shape[1]:
        raise ValueError("trunk_x \u957f\u5ea6\u5fc5\u987b\u4e0e targets \u7f51\u683c\u7ef4\u4e00\u81f4\u3002")
    if data.branch_input.shape != (sample_count, 3):
        raise ValueError(f"branch_input \u5e94\u4e3a [{sample_count}, 3]\u3002")

    metadata = data.metadata if isinstance(data.metadata, dict) else {}
    rho = data.trunk_x.detach().cpu().numpy().astype(np.float64, copy=False)
    branch = data.branch_input.detach().cpu().numpy()
    targets = data.targets.detach().cpu().numpy()
    masks = data.valid_mask.detach().cpu().numpy()
    variable = data.variable or ""
    unit = _target_unit(variable, metadata)
    series = [
        ProfileSeries(
            sample_index=index,
            variable=variable,
            case_id=data.case_ids[index],
            paper_id=data.paper_ids[index],
            profile_id=data.profile_ids[index],
            delta=float(branch[index, 0]),
            t0_kev=float(branch[index, 1]),
            n0_1e19m3=float(branch[index, 2]),
            unit=unit,
            rho=rho.copy(),
            values=np.asarray(targets[index], dtype=np.float64),
            mask=np.asarray(masks[index], dtype=bool),
        )
        for index in range(sample_count)
    ]
    return series, metadata


def _float(row: dict[str, str], field: str, line_no: int) -> float:
    try:
        value = float(row[field])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"CSV \u7b2c {line_no} \u884c\u7684 {field} \u4e0d\u662f\u6709\u6548\u6570\u5b57\u3002") from exc
    if not np.isfinite(value):
        raise ValueError(f"CSV \u7b2c {line_no} \u884c\u7684 {field} \u4e0d\u662f\u6709\u9650\u503c\u3002")
    return value


def _load_csv(path: Path) -> tuple[list[ProfileSeries], dict[str, Any]]:
    grouped: dict[int, list[tuple[int, dict[str, str]]]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = REQUIRED_CSV_FIELDS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV \u7f3a\u5c11\u5b57\u6bb5: {sorted(missing)}")
        for line_no, row in enumerate(reader, start=2):
            sample_index = int(_float(row, "sample_index", line_no))
            grouped.setdefault(sample_index, []).append((line_no, row))
    if not grouped:
        raise ValueError("CSV \u4e2d\u6ca1\u6709\u6570\u636e\u884c\u3002")

    result: list[ProfileSeries] = []
    identity_fields = (
        "variable",
        "case_id",
        "paper_id",
        "profile_id",
        "delta",
        "T0_keV",
        "n0_1e19m3",
        "target_unit",
    )
    for sample_index in sorted(grouped):
        rows = sorted(grouped[sample_index], key=lambda item: _float(item[1], "grid_index", item[0]))
        first = rows[0][1]
        for line_no, row in rows[1:]:
            if any(row[field] != first[field] for field in identity_fields):
                raise ValueError(f"sample_index={sample_index} \u5728\u7b2c {line_no} \u884c\u7684\u6807\u8bc6\u5b57\u6bb5\u4e0d\u4e00\u81f4\u3002")
        result.append(
            ProfileSeries(
                sample_index=sample_index,
                variable=first["variable"],
                case_id=first["case_id"],
                paper_id=first["paper_id"],
                profile_id=first["profile_id"],
                delta=float(first["delta"]),
                t0_kev=float(first["T0_keV"]),
                n0_1e19m3=float(first["n0_1e19m3"]),
                unit=first["target_unit"],
                rho=np.asarray([_float(row, "rho", line_no) for line_no, row in rows]),
                values=np.asarray(
                    [_float(row, "target_value", line_no) for line_no, row in rows]
                ),
                mask=np.asarray(
                    [bool(int(_float(row, "valid_mask", line_no))) for line_no, row in rows]
                ),
            )
        )
    return result, {}


def _infer_project_root(path: Path) -> Path | None:
    for parent in path.parents:
        if parent.name.lower() == "outputs":
            return parent.parent
    return None


def _resolve_raw_root(
    input_path: Path, metadata: dict[str, Any], explicit: Path | None
) -> Path:
    if explicit is not None:
        raw_root = explicit.resolve()
    elif metadata.get("source_root"):
        raw_root = Path(str(metadata["source_root"])).resolve()
    else:
        project_root = _infer_project_root(input_path)
        role = _role_from_path(input_path)
        if project_root is None or role == "dataset":
            raise ValueError("CSV \u8f93\u5165\u65e0\u6cd5\u63a8\u65ad raw \u76ee\u5f55\uff0c\u8bf7\u663e\u5f0f\u63d0\u4f9b --raw-root\u3002")
        raw_root = (project_root / "data" / role / "raw").resolve()
    if not raw_root.is_dir() or not (raw_root / "data").is_dir():
        raise FileNotFoundError(f"raw \u6839\u76ee\u5f55\u5fc5\u987b\u5b58\u5728\u4e14\u5305\u542b data/: {raw_root}")
    return raw_root


def _resolve_conversion_log(
    input_path: Path, raw_root: Path, explicit: Path | None
) -> Path:
    if explicit is not None:
        path = explicit.resolve()
    elif input_path.suffix.lower() == ".pt":
        path = (input_path.parent / "unit_conversion_log.csv").resolve()
    else:
        path = (raw_root.parent / "clean" / "unit_conversion_log.csv").resolve()
    if not path.is_file():
        raise FileNotFoundError(
            f"\u627e\u4e0d\u5230\u5355\u4f4d\u8f6c\u6362\u8bb0\u5f55 {path}\uff1b\u4e3a\u907f\u514d\u628a\u4e0d\u540c\u5355\u4f4d\u753b\u5728\u540c\u4e00\u5750\u6807\u8f74\u4e0a\uff0c\u4e0d\u4f1a\u731c\u6d4b\u3002"
        )
    return path


def _load_conversion_factors(path: Path) -> dict[str, float]:
    factors: dict[str, float] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not {"profile_id", "conversion"}.issubset(reader.fieldnames or []):
            raise ValueError(f"{path} \u7f3a\u5c11 profile_id \u6216 conversion \u5b57\u6bb5\u3002")
        for row in reader:
            match = FACTOR_PATTERN.search(row["conversion"])
            if not match:
                raise ValueError(f"\u65e0\u6cd5\u4ece\u5355\u4f4d\u8f6c\u6362\u8bb0\u5f55\u89e3\u6790\u500d\u7387: {row['conversion']!r}")
            factor = float(match.group(1))
            if not np.isfinite(factor):
                raise ValueError(f"\u5355\u4f4d\u8f6c\u6362\u500d\u7387\u4e0d\u662f\u6709\u9650\u503c: {row['conversion']!r}")
            factors[row["profile_id"]] = factor
    return factors


def _raw_csv_index(raw_root: Path) -> dict[str, list[Path]]:
    result: dict[str, list[Path]] = {}
    for path in (raw_root / "data").rglob("*.csv"):
        result.setdefault(path.stem, []).append(path.resolve())
    return result


def _read_raw_xy(path: Path) -> tuple[np.ndarray, np.ndarray]:
    if path.is_symlink():
        raise ValueError(f"\u62d2\u7edd\u8bfb\u53d6\u7b26\u53f7\u94fe\u63a5 CSV: {path}")
    rows: list[tuple[float, float]] = []
    numeric_started = False
    for line_no, raw_line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        parts = [part for part in re.split(r"[,;\s]+", raw_line.strip()) if part]
        if len(parts) < 2:
            if numeric_started and parts:
                raise ValueError(f"{path} \u7b2c {line_no} \u884c\u4e0d\u662f\u6709\u6548\u7684 x,y \u6570\u636e\u3002")
            continue
        try:
            pair = (float(parts[0]), float(parts[1]))
        except ValueError:
            if numeric_started:
                raise ValueError(f"{path} \u7b2c {line_no} \u884c\u4e0d\u662f\u6709\u6548\u7684 x,y \u6570\u636e\u3002")
            continue
        if not np.isfinite(pair).all():
            raise ValueError(f"{path} \u7b2c {line_no} \u884c\u5305\u542b NaN/Inf\u3002")
        rows.append(pair)
        numeric_started = True
    if len(rows) < 2:
        raise ValueError(f"{path} \u81f3\u5c11\u9700\u8981\u4e24\u884c\u6570\u503c x,y\u3002")
    array = np.asarray(rows, dtype=np.float64)
    order = np.argsort(array[:, 0], kind="stable")
    x, y = array[order, 0], array[order, 1]
    unique_x, inverse, counts = np.unique(x, return_inverse=True, return_counts=True)
    if np.any(counts > 1):
        averaged = np.zeros_like(unique_x)
        np.add.at(averaged, inverse, y)
        x, y = unique_x, averaged / counts
    if len(x) < 2 or np.any(np.diff(x) <= 0):
        raise ValueError(f"{path} \u7684 x \u65e0\u6cd5\u6574\u7406\u4e3a\u4e25\u683c\u9012\u589e\u5e8f\u5217\u3002")
    return x, y


def _safe_name(value: str, limit: int = 120) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    return (cleaned or "profile")[:limit]


def _prepare_profile(
    profile: ProfileSeries,
    raw_index: dict[str, list[Path]],
    factors: dict[str, float],
) -> dict[str, Any]:
    matches = raw_index.get(profile.profile_id, [])
    if len(matches) != 1:
        raise ValueError(
            f"{profile.profile_id}: \u9700\u8981\u6070\u597d\u4e00\u4e2a\u540c\u540d\u539f\u59cb CSV\uff0c\u5b9e\u9645\u627e\u5230 {len(matches)} \u4e2a\u3002"
        )
    if profile.profile_id not in factors:
        raise ValueError(f"{profile.profile_id}: unit_conversion_log.csv \u4e2d\u6ca1\u6709\u8f6c\u6362\u500d\u7387\u3002")
    raw_x, raw_y = _read_raw_xy(matches[0])
    raw_y = raw_y * factors[profile.profile_id]
    valid = profile.mask & np.isfinite(profile.rho) & np.isfinite(profile.values)
    if not np.any(valid):
        raise ValueError(f"{profile.profile_id}: PT/CSV \u4e2d\u6ca1\u6709\u6709\u6548\u7f51\u683c\u70b9\u3002")

    interpolator = PchipInterpolator(raw_x, raw_y, extrapolate=False)
    valid_x = profile.rho[valid]
    expected = np.asarray(interpolator(valid_x), dtype=np.float64)
    if not np.isfinite(expected).all():
        raise ValueError(f"{profile.profile_id}: \u6709\u6548 PT \u7f51\u683c\u8d85\u51fa\u539f\u59cb\u6570\u636e\u8986\u76d6\u8303\u56f4\u3002")
    residual = profile.values[valid] - expected
    dense_x = np.linspace(raw_x[0], raw_x[-1], max(800, len(raw_x) * 4))
    dense_y = np.asarray(interpolator(dense_x), dtype=np.float64)
    return {
        "profile": profile,
        "raw_path": matches[0],
        "raw_x": raw_x,
        "raw_y": raw_y,
        "valid": valid,
        "expected": expected,
        "residual": residual,
        "dense_x": dense_x,
        "dense_y": dense_y,
        "max_abs_error": float(np.max(np.abs(residual))),
        "rmse": float(np.sqrt(np.mean(residual**2))),
    }


def _plot_profile(item: dict[str, Any], output_path: Path, dpi: int) -> None:
    profile: ProfileSeries = item["profile"]
    valid = item["valid"]
    fig = plt.figure(figsize=(15, 9), constrained_layout=True)
    grid = fig.add_gridspec(2, 2, height_ratios=(2.2, 1.0))
    full_ax = fig.add_subplot(grid[0, 0])
    zoom_ax = fig.add_subplot(grid[0, 1])
    residual_ax = fig.add_subplot(grid[1, :])

    for axis in (full_ax, zoom_ax):
        axis.plot(
            item["dense_x"], item["dense_y"], color="#1769aa", linewidth=2.0,
            label="PCHIP curve from raw samples", zorder=2,
        )
        axis.scatter(
            item["raw_x"], item["raw_y"], s=24, facecolors="white", edgecolors="#222222",
            linewidths=0.9, label="Original samples", zorder=3,
        )
        axis.scatter(
            profile.rho[valid], profile.values[valid], s=18, color="#d32f2f", marker="x",
            linewidths=0.9, label="Stored PT/CSV grid values", zorder=4,
        )
        axis.set_xlabel("Normalized radius")
        axis.set_ylabel(f"{profile.variable} [{profile.unit}]")
        axis.grid(True, alpha=0.25)

    full_ax.set_title("Full raw-profile coverage")
    full_ax.axvspan(float(np.min(profile.rho)), float(np.max(profile.rho)), color="#ffcc80", alpha=0.18)
    zoom_ax.set_title("Clean-grid inspection window")
    zoom_ax.set_xlim(float(np.min(profile.rho)), float(np.max(profile.rho)))
    zoom_ax.legend(loc="best", fontsize=8)
    stats = (
        f"raw points: {len(item['raw_x'])}\n"
        f"valid grid: {int(np.sum(valid))}/{len(valid)}\n"
        f"max |PT-PCHIP|: {item['max_abs_error']:.3e}\n"
        f"RMSE: {item['rmse']:.3e}"
    )
    zoom_ax.text(
        0.02, 0.02, stats, transform=zoom_ax.transAxes, va="bottom", ha="left", fontsize=9,
        bbox={"boxstyle": "round", "facecolor": "white", "alpha": 0.88, "edgecolor": "#aaaaaa"},
    )

    residual_ax.axhline(0.0, color="#333333", linewidth=1.0)
    residual_ax.plot(profile.rho[valid], item["residual"], color="#7b1fa2", marker="o", markersize=3)
    residual_ax.set_xlabel("Normalized radius")
    residual_ax.set_ylabel("PT - PCHIP")
    residual_ax.set_title("Interpolation reconstruction residual")
    residual_ax.grid(True, alpha=0.25)

    title = f"[{profile.sample_index:03d}] {profile.profile_id}"
    subtitle = (
        f"case={profile.case_id} | delta={profile.delta:.4g} | "
        f"T0={profile.t0_kev:.4g} keV | n0={profile.n0_1e19m3:.4g} x10^19 m^-3"
    )
    fig.suptitle("\n".join(textwrap.wrap(title, 110)) + "\n" + subtitle, fontsize=13)
    if output_path.is_symlink():
        raise ValueError(f"\u62d2\u7edd\u8986\u76d6\u7b26\u53f7\u94fe\u63a5: {output_path}")
    fig.savefig(output_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)


def _plot_overview_page(
    items: list[dict[str, Any]], page_path: Path, dpi: int, page_number: int
) -> None:
    columns = 2
    rows = math.ceil(len(items) / columns)
    fig, axes = plt.subplots(rows, columns, figsize=(15, 4.8 * rows), squeeze=False)
    for axis, item in zip(axes.flat, items):
        profile: ProfileSeries = item["profile"]
        valid = item["valid"]
        axis.plot(item["dense_x"], item["dense_y"], color="#1769aa", linewidth=1.5)
        axis.scatter(item["raw_x"], item["raw_y"], s=12, facecolors="white", edgecolors="#222222")
        axis.scatter(profile.rho[valid], profile.values[valid], s=11, color="#d32f2f", marker="x")
        axis.set_xlim(float(np.min(profile.rho)), float(np.max(profile.rho)))
        axis.set_title(f"[{profile.sample_index:03d}] {profile.profile_id}", fontsize=9)
        axis.set_xlabel("Normalized radius")
        axis.set_ylabel(f"{profile.variable} [{profile.unit}]")
        axis.grid(True, alpha=0.25)
        axis.text(
            0.02, 0.03, f"max error={item['max_abs_error']:.2e}", transform=axis.transAxes,
            fontsize=8, bbox={"facecolor": "white", "alpha": 0.8, "edgecolor": "none"},
        )
    for axis in axes.flat[len(items):]:
        axis.set_visible(False)
    fig.suptitle(f"Profile interpolation review - overview page {page_number}", fontsize=14)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(page_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)


def _write_manifest(rows: list[dict[str, Any]], path: Path) -> None:
    fields = [
        "sample_index", "variable", "profile_id", "case_id", "raw_csv", "profile_plot",
        "raw_point_count", "valid_grid_count", "max_abs_error", "rmse",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def visualize_profiles(
    input_path: Path,
    output_dir: Path | None = None,
    raw_root: Path | None = None,
    conversion_log: Path | None = None,
    dpi: int = 180,
    profiles_per_page: int = 6,
    max_profiles: int | None = None,
    export_csv: bool = True,
) -> list[Path]:
    input_path = input_path.resolve()
    if input_path.suffix.lower() not in {".pt", ".csv"}:
        raise ValueError("\u8f93\u5165\u6587\u4ef6\u5fc5\u987b\u4f7f\u7528 .pt \u6216 .csv \u540e\u7f00\u3002")
    if dpi < 72 or dpi > 600:
        raise ValueError("dpi \u5fc5\u987b\u5728 72 \u5230 600 \u4e4b\u95f4\u3002")
    if profiles_per_page < 1 or profiles_per_page > 20:
        raise ValueError("profiles_per_page \u5fc5\u987b\u5728 1 \u5230 20 \u4e4b\u95f4\u3002")
    if max_profiles is not None and max_profiles < 1:
        raise ValueError("max_profiles \u5fc5\u987b\u662f\u6b63\u6574\u6570\u3002")

    if input_path.suffix.lower() == ".pt":
        profiles, metadata = _load_pt(input_path)
    else:
        profiles, metadata = _load_csv(input_path)
    if max_profiles is not None:
        profiles = profiles[:max_profiles]

    output_dir = (output_dir or _default_output_dir(input_path)).resolve()
    if output_dir.is_symlink():
        raise ValueError(f"\u62d2\u7edd\u5199\u5165\u7b26\u53f7\u94fe\u63a5\u76ee\u5f55: {output_dir}")
    profile_dir = output_dir / "profiles"
    profile_dir.mkdir(parents=True, exist_ok=True)

    resolved_raw_root = _resolve_raw_root(input_path, metadata, raw_root)
    conversion_path = _resolve_conversion_log(input_path, resolved_raw_root, conversion_log)
    factors = _load_conversion_factors(conversion_path)
    raw_index = _raw_csv_index(resolved_raw_root)
    prepared = [_prepare_profile(profile, raw_index, factors) for profile in profiles]

    artifacts: list[Path] = []
    if input_path.suffix.lower() == ".pt" and export_csv:
        inspection_csv = output_dir / "inspection_data.csv"
        export_pt_csv(input_path, inspection_csv)
        artifacts.append(inspection_csv)

    manifest_rows: list[dict[str, Any]] = []
    for item in prepared:
        profile: ProfileSeries = item["profile"]
        filename = f"{profile.sample_index:03d}_{_safe_name(profile.profile_id)}.png"
        plot_path = profile_dir / filename
        _plot_profile(item, plot_path, dpi)
        artifacts.append(plot_path)
        manifest_rows.append(
            {
                "sample_index": profile.sample_index,
                "variable": profile.variable,
                "profile_id": profile.profile_id,
                "case_id": profile.case_id,
                "raw_csv": str(item["raw_path"]),
                "profile_plot": str(plot_path),
                "raw_point_count": len(item["raw_x"]),
                "valid_grid_count": int(np.sum(item["valid"])),
                "max_abs_error": item["max_abs_error"],
                "rmse": item["rmse"],
            }
        )

    for start in range(0, len(prepared), profiles_per_page):
        page_number = start // profiles_per_page + 1
        page_path = output_dir / f"overview_page_{page_number:03d}.png"
        _plot_overview_page(
            prepared[start : start + profiles_per_page], page_path, dpi, page_number
        )
        artifacts.append(page_path)

    manifest_path = output_dir / "visualization_manifest.csv"
    _write_manifest(manifest_rows, manifest_path)
    artifacts.append(manifest_path)
    return artifacts


def main() -> None:
    args = parse_args()
    artifacts = visualize_profiles(
        input_path=args.input_path,
        output_dir=args.output_dir,
        raw_root=args.raw_root,
        conversion_log=args.conversion_log,
        dpi=args.dpi,
        profiles_per_page=args.profiles_per_page,
        max_profiles=args.max_profiles,
        export_csv=not args.no_export_csv,
    )
    profile_count = sum(path.parent.name == "profiles" for path in artifacts)
    print(f"\u5df2\u751f\u6210 {profile_count} \u5f20\u9010\u5256\u9762\u9ad8\u6e05\u56fe\uff1b\u5168\u90e8\u4ea7\u7269\u4f4d\u4e8e: {artifacts[-1].parent}")


if __name__ == "__main__":
    main()

