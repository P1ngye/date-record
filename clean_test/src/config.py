from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml


def _positive_int(value: Any, name: str) -> int:
    number = int(value)
    if number <= 0:
        raise ValueError(f"{name} 必须是正整数，收到 {value!r}")
    return number


def validate_config(config: dict[str, Any]) -> None:
    """Validate configuration values that would otherwise fail silently or late."""
    if config.get("variable") not in {"Te", "ne", "Ti"}:
        raise ValueError("配置 variable 必须是 Te、ne 或 Ti。")
    data = config.get("data", {})
    if data.get("target_scaling") not in {"none", "standard"}:
        raise ValueError("data.target_scaling 只能是 none 或 standard。")
    if float(data.get("scaler_eps", 0.0)) <= 0:
        raise ValueError("data.scaler_eps 必须大于 0。")
    _positive_int(data.get("min_valid_points", 0), "data.min_valid_points")

    model = config.get("model", {})
    if int(model.get("branch_input_dim", 0)) != 3 or int(model.get("trunk_input_dim", 0)) != 1:
        raise ValueError("当前物理定义要求 branch_input_dim=3 且 trunk_input_dim=1。")
    _positive_int(model.get("latent_dim", 0), "model.latent_dim")
    for name in ("branch_hidden_dims", "trunk_hidden_dims"):
        values = model.get(name)
        if not isinstance(values, list) or not values:
            raise ValueError(f"model.{name} 必须是非空列表。")
        for index, value in enumerate(values):
            _positive_int(value, f"model.{name}[{index}]")
    dropout = float(model.get("dropout", 0.0))
    if not 0.0 <= dropout < 1.0:
        raise ValueError("model.dropout 必须处于 [0,1)。")
    if bool(model.get("nonnegative_output", False)) and data.get("target_scaling") == "standard":
        raise ValueError(
            "nonnegative_output 不能与 standard target scaling 同时使用；"
            "否则约束作用于标准化空间而不是物理空间。"
        )

    loss = config.get("loss", {})
    weights = [
        float(loss.get(name, 0.0))
        for name in ("mse_weight", "relative_l2_weight", "boundary_weight", "smoothness_weight")
    ]
    if any(value < 0 for value in weights) or not any(value > 0 for value in weights):
        raise ValueError("loss 权重必须非负，且至少一个权重大于 0。")

    training = config.get("training", {})
    _positive_int(training.get("epochs", 0), "training.epochs")
    _positive_int(training.get("batch_size", 0), "training.batch_size")
    if float(training.get("learning_rate", 0.0)) <= 0:
        raise ValueError("training.learning_rate 必须大于 0。")
    if float(training.get("weight_decay", -1.0)) < 0:
        raise ValueError("training.weight_decay 不能为负。")
    if str(training.get("optimizer", "")).lower() != "adamw":
        raise ValueError("training.optimizer 目前只支持 adamw。")
    if str(training.get("scheduler", "")).lower() not in {"none", "reduce_on_plateau", "cosine"}:
        raise ValueError("training.scheduler 只能是 none、reduce_on_plateau 或 cosine。")
    if int(training.get("num_workers", 0)) < 0:
        raise ValueError("training.num_workers 不能为负。")


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge *override* into a copy of *base*."""
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def load_config(path: Path) -> dict[str, Any]:
    """Load default.yaml and then apply one variable-specific YAML file."""
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在: {path}")
    if path.stat().st_size > 1024 * 1024:
        raise ValueError(f"配置文件超过 1 MiB，已拒绝加载: {path}")
    default_path = path.parent / "default.yaml"
    if not default_path.exists():
        raise FileNotFoundError(f"缺少基础配置: {default_path}")
    with default_path.open("r", encoding="utf-8") as handle:
        base = yaml.safe_load(handle) or {}
    if path.resolve() == default_path.resolve():
        validate_config(base)
        return base
    with path.open("r", encoding="utf-8") as handle:
        override = yaml.safe_load(handle) or {}
    resolved = deep_merge(base, override)
    validate_config(resolved)
    return resolved


def save_config(config: dict[str, Any], path: Path) -> None:
    """Save a resolved configuration in a human-readable form."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(config, handle, allow_unicode=True, sort_keys=False)
