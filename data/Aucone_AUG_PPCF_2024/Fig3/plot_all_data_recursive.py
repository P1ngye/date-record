# -*- coding: utf-8 -*-
"""
把本脚本放在“数据总文件夹”中运行：
- 自动递归扫描当前文件夹及其所有子文件夹中的数据文件
- 支持: .csv .tsv .txt .dat .xls .xlsx
- 自动识别前两列可用数值列进行绘图
- 图片输出到当前文件夹下的 plots_output 文件夹中
- 输出目录会尽量保留原始子文件夹层级

运行方式：
    python plot_all_data_recursive.py
"""

from pathlib import Path
import warnings
import pandas as pd
import matplotlib.pyplot as plt

warnings.filterwarnings("ignore", category=UserWarning)

# ====== 可按需修改的参数 ======
OUTPUT_DIR_NAME = "plots_output"   # 输出图片文件夹名称
DPI = 220
FIGSIZE = (9.6, 5.8)
LINE_WIDTH = 2.0
MARKER_SIZE = 3.5
MIN_VALID_POINTS = 3
SUPPORTED_EXTS = {".csv", ".tsv", ".txt", ".dat", ".xls", ".xlsx"}
# ============================


def set_chinese_font():
    """尽量兼容中文标题显示。"""
    plt.rcParams["font.sans-serif"] = [
        "Microsoft YaHei",
        "SimHei",
        "Noto Sans CJK SC",
        "Arial Unicode MS",
        "DejaVu Sans",
    ]
    plt.rcParams["axes.unicode_minus"] = False


def try_read_text_table(file_path: Path):
    """尝试读取文本类表格。"""
    last_error = None
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk", "latin1"):
        try:
            return pd.read_csv(
                file_path,
                sep=None,              # 自动识别分隔符
                engine="python",
                encoding=encoding,
                comment="#",
            )
        except Exception as e:
            last_error = e
    raise last_error


def read_table(file_path: Path) -> pd.DataFrame:
    """读取 csv/txt/dat/xlsx 等文件。"""
    suffix = file_path.suffix.lower()
    if suffix in {".xls", ".xlsx"}:
        return pd.read_excel(file_path)
    return try_read_text_table(file_path)


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """去掉全空行列，清理列名。"""
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    df = df.dropna(axis=0, how="all").dropna(axis=1, how="all")
    return df


def pick_xy_columns(df: pd.DataFrame):
    """
    自动选择两列用于绘图：
    1. 优先找列名中明确包含 x / y 的列
    2. 否则选择前两列“可转成数值且有效点足够多”的列
    """
    if df.empty or len(df.columns) < 2:
        raise ValueError("表格为空，或少于两列。")

    # 优先处理常见的 x / y 列名
    lower_name_map = {c.lower(): c for c in df.columns}
    if "x" in lower_name_map and "y" in lower_name_map:
        x_col = lower_name_map["x"]
        y_col = lower_name_map["y"]
        x = pd.to_numeric(df[x_col], errors="coerce")
        y = pd.to_numeric(df[y_col], errors="coerce")
        valid = x.notna() & y.notna()
        if valid.sum() >= MIN_VALID_POINTS:
            return x[valid], y[valid], x_col, y_col

    # 转数值，找有效列
    numeric_df = df.apply(pd.to_numeric, errors="coerce")
    valid_counts = numeric_df.notna().sum()

    usable_cols = [col for col in numeric_df.columns if valid_counts[col] >= MIN_VALID_POINTS]
    if len(usable_cols) < 2:
        raise ValueError("找不到两列可用于绘图的数值列。")

    x_col, y_col = usable_cols[:2]
    x = numeric_df[x_col]
    y = numeric_df[y_col]
    valid = x.notna() & y.notna()

    if valid.sum() < MIN_VALID_POINTS:
        raise ValueError("有效数据点过少，无法绘图。")

    return x[valid], y[valid], x_col, y_col


def build_title(file_path: Path, base_dir: Path) -> str:
    rel_path = file_path.relative_to(base_dir)
    parent = rel_path.parent.as_posix()
    if parent == ".":
        return file_path.stem
    return f"{file_path.stem}\n[{parent}]"


def save_plot(x, y, x_label, y_label, src_file: Path, base_dir: Path, output_dir: Path):
    """绘图并保存。"""
    # 按 x 排序，保证折线更自然
    plot_df = pd.DataFrame({"x": x, "y": y}).sort_values("x")

    rel_path = src_file.relative_to(base_dir)
    rel_parent = rel_path.parent
    save_dir = output_dir / rel_parent
    save_dir.mkdir(parents=True, exist_ok=True)

    save_path = save_dir / f"{src_file.stem}.png"

    plt.figure(figsize=FIGSIZE, dpi=DPI)
    plt.plot(
        plot_df["x"],
        plot_df["y"],
        linewidth=LINE_WIDTH,
        marker="o",
        markersize=MARKER_SIZE,
        label=src_file.stem,
    )

    plt.title(build_title(src_file, base_dir), fontsize=14, pad=12)
    plt.xlabel(str(x_label), fontsize=11)
    plt.ylabel(str(y_label), fontsize=11)
    plt.grid(True, alpha=0.3)
    plt.legend(frameon=True)
    plt.tight_layout()
    plt.savefig(save_path, bbox_inches="tight")
    plt.close()

    return save_path


def find_data_files(base_dir: Path, output_dir: Path):
    """递归查找所有数据文件，排除输出目录和本脚本自己。"""
    script_path = Path(__file__).resolve()
    files = []
    for p in base_dir.rglob("*"):
        if not p.is_file():
            continue
        if p.resolve() == script_path:
            continue
        if output_dir in p.resolve().parents:
            continue
        if p.suffix.lower() in SUPPORTED_EXTS:
            files.append(p)
    return sorted(files)


def main():
    set_chinese_font()

    base_dir = Path(__file__).resolve().parent
    output_dir = base_dir / OUTPUT_DIR_NAME
    output_dir.mkdir(exist_ok=True)

    data_files = find_data_files(base_dir, output_dir)
    if not data_files:
        print("未找到可处理的数据文件。")
        return

    print(f"扫描目录: {base_dir}")
    print(f"共找到 {len(data_files)} 个数据文件。")
    print(f"图片输出目录: {output_dir}")
    print("-" * 60)

    success = 0
    failed = 0

    for file_path in data_files:
        try:
            df = read_table(file_path)
            df = clean_dataframe(df)
            x, y, x_label, y_label = pick_xy_columns(df)
            saved = save_plot(x, y, x_label, y_label, file_path, base_dir, output_dir)
            print(f"[成功] {file_path.relative_to(base_dir)} -> {saved.relative_to(base_dir)}")
            success += 1
        except Exception as e:
            print(f"[失败] {file_path.relative_to(base_dir)} -> {e}")
            failed += 1

    print("-" * 60)
    print(f"处理完成：成功 {success} 个，失败 {failed} 个。")


if __name__ == "__main__":
    main()
