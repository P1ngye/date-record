# DeepONet 数据整理、清洗与审计工具

- `organize_data.py`：把人工指定的 train/test 原始数据整理到规范目录。
- `clean_data.py`：使用禁止外推的 PCHIP 生成 clean PT。
- `audit_data.py`：独立审计 clean PT、mask 和 split。
- `export_pt_csv.py`：把 clean PT 展开为人工查验 CSV。
- `visualize_pt.py`：把 PT 或上述长表 CSV 绘制为逐剖面高清插值审查图。

## 1. 创建独立环境

Windows PowerShell：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools
.\.venv\Scripts\python.exe -m pip install -r requirements_preprocessing.txt
```

如果 `py` 不存在，请把第一行改成机器上可用的 `python -m venv .venv`。后续始终使用新建环境中的 Python。

## 2. 输入格式

手工选定 train/test，程序不会随机拆分。每个原始来源目录应包含：

```text
train/ 或 test/
├── *_profile_database.xlsx
└── <paper_id>/**/*.csv
```

Excel 至少包含：

- `02_CASES`：`case_id`、`paper_id`、`delta` 或 `delta_avg`。
- `03_PROFILES`：`profile_id`、`paper_id`、`case_id`、`variable`、`coord_name`、`y_unit_raw`、`data_origin`，以及可选的 `target_points_csv_relpath` 或 `points_file_relpath`。

CSV 文件名（不含 `.csv`）必须与 `profile_id` 完全一致。数据部分至少两列数值 `x,y`；表头可以存在。程序不会根据近似文件名、单位数值范围或图号猜测。

clean后单位：

- `Te`/`Ti`：keV`。
- `ne`：10^19 m^-3`。

## 3. 步骤详解

先整理训练集和测试集：

```powershell
.\.venv\Scripts\python.exe organize_data.py --split train --raw-source C:\path\train\raw
.\.venv\Scripts\python.exe organize_data.py --split test  --raw-source C:\path\test\raw
```

整理后固定为：

```text
data/
├── train/
│   ├── raw/{database_by_paper,data}
│   └── clean/
└── test/
    ├── raw/{database_by_paper,data}
    └── clean/
```

只执行清洗：

```powershell
.\.venv\Scripts\python.exe clean_data.py --split train
.\.venv\Scripts\python.exe clean_data.py --split test
```

分别审计 clean 数据：

```powershell
.\.venv\Scripts\python.exe audit_data.py --dataset data\train\clean\deeponet_dataset_Te.pt --variable Te --dataset-role train
.\.venv\Scripts\python.exe audit_data.py --dataset data\test\clean\deeponet_dataset_Te.pt  --variable Te --dataset-role test
```

把 `Te` 替换成 `ne` 或 `Ti` 可审计其他变量。审计失败时命令返回非零退出码，报告位于 `outputs/audit_<variable>/`。

把 clean PT 展开成人工查验 CSV：

```powershell
.\.venv\Scripts\python.exe export_pt_csv.py --dataset data\test\clean\deeponet_dataset_Te.pt
```

默认写入 `outputs/pt_csv/test/deeponet_dataset_Te.csv`；每行对应一个 profile
的一个 rho 网格点，并保留 ID、Branch 输入、目标值和 `valid_mask`。

逐剖面检查原始点、PCHIP 曲线、PT 网格值及重建残差：

```powershell
.\.venv\Scripts\python.exe visualize_pt.py --dataset data\train\clean\deeponet_dataset_Te.pt
```

默认输出到 `outputs/pt_visualizations/train/deeponet_dataset_Te/`。其中
`profiles/` 为每个剖面一张独立高清图，`overview_page_*.png` 为分页总览，
`visualization_manifest.csv` 记录每个剖面的最大绝对误差和 RMSE，
`inspection_data.csv` 是同批 PT 的长表数据。也可把 `--dataset` 换成
`--input <export_pt_csv生成的.csv>`；CSV 无法自动定位 raw 时需同时指定
`--raw-root` 和 `--conversion-log`。

## 4. 自检

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

预期全部通过。安全策略和已知边界见 `SECURITY_REVIEW.md`。

# 
