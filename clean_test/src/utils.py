from __future__ import annotations

import json
import logging
import random
import re
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
import torch


MIN_SAFE_TORCH_LOAD_VERSION = (2, 6, 0)
MAX_SERIALIZED_FILE_BYTES = 2 * 1024**3
MAX_SERIALIZED_UNCOMPRESSED_BYTES = 4 * 1024**3


def _torch_version_tuple() -> tuple[int, int, int]:
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", torch.__version__)
    if match is None:
        raise RuntimeError(f"无法解析 PyTorch 版本: {torch.__version__!r}")
    return tuple(int(value) for value in match.groups())


def validate_archive_size(
    path: Path,
    *,
    max_file_bytes: int = MAX_SERIALIZED_FILE_BYTES,
    max_uncompressed_bytes: int = MAX_SERIALIZED_UNCOMPRESSED_BYTES,
    max_members: int = 10_000,
) -> None:
    """Reject oversized files and ZIP archives before a parser allocates memory."""
    if not path.is_file():
        raise FileNotFoundError(path)
    size = path.stat().st_size
    if size > max_file_bytes:
        raise ValueError(f"文件过大 ({size} bytes): {path}")
    if not zipfile.is_zipfile(path):
        return
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        if len(members) > max_members:
            raise ValueError(f"压缩包成员过多 ({len(members)}): {path}")
        total = sum(member.file_size for member in members)
        if total > max_uncompressed_bytes:
            raise ValueError(f"压缩包解压后过大 ({total} bytes): {path}")
        if any(member.flag_bits & 0x1 for member in members):
            raise ValueError(f"不支持加密压缩成员: {path}")


def safe_torch_load(path: Path, map_location: str | torch.device = "cpu") -> dict[str, Any]:
    """Load a tensor/state dictionary with the patched restricted unpickler only."""
    if _torch_version_tuple() < MIN_SAFE_TORCH_LOAD_VERSION:
        raise RuntimeError(
            "安全策略拒绝 torch.load：PyTorch < 2.6 受 CVE-2025-32434 影响，"
            f"当前版本为 {torch.__version__}。请先安装 torch>=2.6。"
        )
    validate_archive_size(path)
    value = torch.load(path, map_location=map_location, weights_only=True)
    if not isinstance(value, dict):
        raise TypeError(f"{path} 顶层必须是 dict。")
    return value


def safe_output_subdir(root: Path, name: str, prefix: str = "") -> Path:
    """Return a child output directory while rejecting path traversal names."""
    if not name or len(name) > 128 or any(ord(char) < 32 for char in name):
        raise ValueError("输出名称不能为空、不能超过 128 字符或包含控制字符。")
    if name in {".", ".."} or Path(name).is_absolute() or any(char in name for char in "/\\:"):
        raise ValueError(f"输出名称必须是单个安全目录名，收到 {name!r}")
    root_resolved = root.resolve()
    result = (root_resolved / f"{prefix}{name}").resolve()
    if result.parent != root_resolved:
        raise ValueError(f"输出目录越出根目录: {result}")
    return result


def csv_safe(value: Any) -> Any:
    """Prevent spreadsheet formula execution when CSV reports are opened manually."""
    if not isinstance(value, str):
        return value
    if value.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value


def csv_restore(value: str) -> str:
    """Undo this project's CSV formula-escape prefix when reading identifiers."""
    if len(value) >= 2 and value[0] == "'" and value[1] in "=+-@\t\r":
        return value[1:]
    return value


def setup_logging(log_file: Path | None = None, level: int = logging.INFO) -> None:
    """Configure console logging and, optionally, a UTF-8 file log."""
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=handlers,
        force=True,
    )


def set_seed(seed: int, deterministic: bool = True) -> None:
    """Seed Python, NumPy, PyTorch and all CUDA devices."""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    if deterministic:
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False


def select_device(requested: str) -> torch.device:
    """Resolve auto/cpu/cuda/mps into an available torch device."""
    requested = requested.lower()
    if requested == "auto":
        if torch.cuda.is_available():
            return torch.device("cuda")
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return torch.device("mps")
        return torch.device("cpu")
    device = torch.device(requested)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("配置要求 CUDA，但当前 PyTorch 检测不到 CUDA。")
    if device.type == "mps" and not (
        hasattr(torch.backends, "mps") and torch.backends.mps.is_available()
    ):
        raise RuntimeError("配置要求 MPS，但当前设备不支持 MPS。")
    return device


def dtype_from_name(name: str) -> torch.dtype:
    """Convert a configuration dtype name to torch.dtype."""
    mapping = {"float32": torch.float32, "float64": torch.float64}
    if name not in mapping:
        raise ValueError(f"仅支持 dtype={list(mapping)}，收到 {name!r}")
    return mapping[name]


def json_safe(value: Any) -> Any:
    """Convert NumPy/PyTorch/path objects into JSON-serializable values."""
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, torch.Tensor):
        return value.detach().cpu().tolist()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return value


def write_json(data: Any, path: Path) -> None:
    """Write indented UTF-8 JSON with scientific values safely converted."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(json_safe(data), ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
