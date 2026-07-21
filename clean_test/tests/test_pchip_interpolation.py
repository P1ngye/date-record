from pathlib import Path

import numpy as np
import pytest

from src.raw_builder import (
    BOUNDARY_ATOL,
    MIN_X_SPACING,
    RawProfile,
    _evaluate_pchip,
    _interpolate_value,
    _read_xy,
    _resample,
)


def _profile(x: list[float], y: list[float]) -> RawProfile:
    return RawProfile(
        profile_id="P__Fig1__Te__case",
        paper_id="P",
        case_id="C",
        variable="Te",
        coord_name="rho",
        unit_raw="keV",
        status="ready",
        csv_path=Path("profile.csv"),
        x=np.asarray(x, dtype=np.float64),
        y=np.asarray(y, dtype=np.float64),
    )


def test_pchip_is_used_and_preserves_endpoints_without_overshoot() -> None:
    profile = _profile([0.8, 0.9, 1.0], [1.0, 0.9, 0.0])
    points = np.linspace(0.8, 1.0, 101)
    values = _evaluate_pchip(profile, points)

    assert values[0] == pytest.approx(1.0)
    assert values[-1] == pytest.approx(0.0)
    assert values.min() >= 0.0
    assert values.max() <= 1.0
    assert _interpolate_value(profile, 0.85) != pytest.approx(
        float(np.interp(0.85, profile.x, profile.y))
    )


def test_boundary_roundoff_is_clipped_but_real_extrapolation_is_rejected() -> None:
    within_tolerance = _profile(
        [0.8 + BOUNDARY_ATOL / 2, 0.9, 1.0],
        [1.0, 0.5, 0.1],
    )
    outside_tolerance = _profile(
        [0.8 + BOUNDARY_ATOL * 2, 0.9, 1.0],
        [1.0, 0.5, 0.1],
    )

    assert _interpolate_value(within_tolerance, 0.8) == pytest.approx(1.0)
    with pytest.raises(ValueError, match="不覆盖"):
        _interpolate_value(outside_tolerance, 0.8)


def test_resample_masks_uncovered_boundaries_and_does_not_extrapolate() -> None:
    profile = _profile([0.85, 0.9, 0.95], [1.0, 0.6, 0.2])
    grid = np.asarray([0.8, 0.85, 0.9, 0.95, 1.0])

    target, mask = _resample(profile, grid)

    assert mask.tolist() == [0.0, 1.0, 1.0, 1.0, 0.0]
    assert target[[0, 4]].tolist() == [0.0, 0.0]
    assert target[1:4].tolist() == pytest.approx([1.0, 0.6, 0.2])


def test_near_duplicate_coordinates_are_rejected_before_pchip(tmp_path: Path) -> None:
    csv_path = tmp_path / "profile.csv"
    csv_path.write_text(
        f"x,y\n0.8,1.0\n{0.8 + MIN_X_SPACING / 2:.12f},0.9\n0.9,0.5\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="病态斜率"):
        _read_xy(csv_path)
