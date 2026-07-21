# Clean 数据预处理代码原理与故障查阅字典

本文解释 `clean_test` 中除审查链路以外的代码文件，重点说明它们如何整理原始文件、构造 clean PT、加载数据以及提供公共安全能力。

本文覆盖：

- `organize_data.py`
- `clean_data.py`
- `src/data_layout.py`
- `src/raw_builder.py`
- `src/data.py`
- `src/split.py`
- `src/config.py`
- `src/utils.py`
- `src/__init__.py`

本文逐一覆盖非审查部分的所有 Python 代码。`audit_data.py`、`src/audit.py`、`export_pt_csv.py`、`visualize_pt.py` 和 `tests/` 仍列入全文件索引，但其实现原理不在这里重复，详见 `AUDIT_README.md`。

## 0. 如何把本文当作字典使用

遇到问题时可以按以下顺序查找：

1. 先在“故障现象反查字典”中搜索报错文字或现象；
2. 根据表中的负责文件跳到对应文件章节；
3. 在“函数级 API 字典”中确认函数输入、返回值、副作用和失败条件；
4. 在“数据结构字典”中核对目录、Excel、CSV、PT 和 manifest 字段；
5. 修改代码前查看“修改影响范围字典”，确认会影响哪些下游文件。

### 0.1 全部 Python 文件索引

| 文件 | 类型 | 主要职责 | 详细说明位置 |
|---|---|---|---|
| `organize_data.py` | 命令入口 | 归档外部 raw/legacy clean | 本文第 2 节、第 14.1 节 |
| `clean_data.py` | 命令入口 | 原子化生成 clean 数据 | 本文第 4 节、第 14.2 节 |
| `src/__init__.py` | 包入口 | 包标识与版本 | 本文第 10 节 |
| `src/data_layout.py` | 业务模块 | 目录、复制、哈希、manifest | 本文第 3 节、第 14.3 节 |
| `src/raw_builder.py` | 业务模块 | Excel/CSV 解析、单位、PCHIP、PT | 本文第 5 节、第 14.4 节 |
| `src/data.py` | 数据模块 | PT/NPZ 加载与 Dataset 适配 | 本文第 6 节、第 14.5 节 |
| `src/split.py` | 数据模块 | 人工 split 和论文分组 fold | 本文第 7 节、第 14.6 节 |
| `src/config.py` | 配置模块 | YAML 合并与参数约束 | 本文第 8 节、第 14.7 节 |
| `src/utils.py` | 公共模块 | 安全加载、路径、日志、JSON、设备 | 本文第 9 节、第 14.8 节 |
| `audit_data.py` | 审查入口 | 数据结构和 split 审查 | `AUDIT_README.md` |
| `src/audit.py` | 审查模块 | 审查规则与报告 | `AUDIT_README.md` |
| `export_pt_csv.py` | 审查入口 | PT 长表导出 | `AUDIT_README.md` |
| `visualize_pt.py` | 审查入口 | 原始点/PCHIP/PT 对照图 | `AUDIT_README.md` |
| `tests/test_clean_command.py` | 测试 | clean 提交一致性 | `AUDIT_README.md` |
| `tests/test_data_layout.py` | 测试 | 文件布局和覆盖冲突 | `AUDIT_README.md` |
| `tests/test_dataset_loading.py` | 测试 | PT/NPZ 加载 | `AUDIT_README.md` |
| `tests/test_export_pt_csv.py` | 测试 | CSV 展开 | `AUDIT_README.md` |
| `tests/test_pchip_interpolation.py` | 测试 | PCHIP 和边界规则 | `AUDIT_README.md` |
| `tests/test_security_guards.py` | 测试 | 路径、反序列化和关联安全 | `AUDIT_README.md` |
| `tests/test_split_leakage.py` | 测试 | case/论文级泄漏约束 | `AUDIT_README.md` |
| `tests/test_visualize_pt.py` | 测试 | 可视化产物和残差 | `AUDIT_README.md` |

## 1. 总体数据流

代码把文件处理分成两个明确阶段：

```text
人工指定的外部原始数据
        │
        ▼
organize_data.py + src/data_layout.py
        │  只复制、计算哈希、建立规范目录
        ▼
data/<train|test>/raw/
        │
        ▼
clean_data.py + src/raw_builder.py
        │  解析元数据、匹配 CSV、换算单位、PCHIP 重采样
        ▼
data/<train|test>/clean/
        ├── deeponet_dataset_Te.pt
        ├── deeponet_dataset_ne.pt
        ├── deeponet_dataset_Ti.pt
        ├── build_report.json
        ├── unit_conversion_log.csv
        └── <variable>_<role>_manifest.csv
```

核心边界是：

- `raw` 只保存来源数据的规范化副本，不在原文件上清洗；
- `clean` 只由 raw 构建，不被当作新的 raw；
- train/test 由目录和人工输入决定，程序不随机决定数据角色；
- 插值只在原始坐标覆盖范围内进行，不做径向外推；
- clean 构建采用暂存目录，只有请求的变量全部成功后才替换正式结果。

## 2. `organize_data.py`：入口层的数据归档

`organize_data.py` 是命令行入口，本身不解析 Excel 内容，也不生成 PT。它只负责把参数转换为规范目录操作：

- `--split train|test`：声明这批数据由人工分配到哪个角色；
- `--raw-source`：指定外部原始 Excel/CSV 所在目录；
- `--clean-source`：接收已有的 clean PT/NPZ，但不会把它们伪装成 raw；
- `--data-root`：指定规范数据根目录，默认是 `data/`；
- `--overwrite`：仅在人工明确允许时覆盖内容不同的目标文件；
- `--missing-raw-reason`：旧 clean 存在但 raw 缺失时，写出数据谱系缺口说明。

入口先构造 `DatasetLayout`，建立 `raw/database_by_paper`、`raw/data` 和 `clean`，然后分别调用 `organize_raw_data`、`adopt_clean_data` 或 `write_missing_raw_notice`。

这里的“整理”是复制和记录，不是移动、重命名源文件或修改内容。源目录应是外部 incoming 数据目录，而不是已经规范化完成的 `data/train` 或 `data/test` 角色目录。

## 3. `src/data_layout.py`：目录规范与可追溯复制

### 3.1 `DatasetLayout`

`DatasetLayout` 用 `root + role` 唯一推导目录：

```text
role_root     = <root>/<role>
raw           = <root>/<role>/raw
raw_workbooks = <root>/<role>/raw/database_by_paper
raw_profiles  = <root>/<role>/raw/data
clean         = <root>/<role>/clean
```

role 只允许 `train` 和 `test`。这个对象的目的不是自动划分样本，而是防止各入口自行拼接出不同目录。

### 3.2 raw 来源识别

`_source_files` 支持两类外部布局：

1. 已规范布局：来源中包含 `database_by_paper/` 和 `data/`；
2. 扁平/论文分组布局：工作簿在来源根目录，各论文/图号子目录中保存 CSV。

工作簿统一放入 `raw/database_by_paper`；profile 文件统一保留相对层级放入 `raw/data`。`raw`、`clean`、`train`、`test` 等保留目录不会被误当作论文数据目录递归复制。

### 3.3 内容冲突和 manifest

每个文件复制前都计算 SHA-256：

- 目标不存在：复制并记为 `copied`；
- 目标存在且哈希相同：不重复写入，记为 `unchanged`；
- 目标存在但内容不同：默认失败；只有显式 `--overwrite` 才覆盖。

程序拒绝复制符号链接，并验证目标父目录仍位于允许的 raw/clean 根目录内。完成后写出：

- `raw_manifest.csv`：适合人工查看；
- `raw_manifest.json`：保存同一批文件记录的结构化版本。

每条记录包含源路径、目标路径、字节数、SHA-256 和处理状态。manifest 证明“哪一个源文件被复制成哪一个规范文件”，而不是证明文件内容在科学上正确。

### 3.4 接收旧 clean 数据

`adopt_clean_data` 只接收包含 `.pt` 或 `.npz` 的目录，并写出 `adopted_clean_manifest`。如果来源已经是规范 clean 目录，会直接拒绝，因为自我接收没有意义且可能混淆数据谱系。

当只有旧 clean、没有原始 Excel/CSV 时，`write_missing_raw_notice` 生成 `RAW_DATA_MISSING.md`。它明确记录缺口，而不是把 clean 反向宣称为 raw。

## 4. `clean_data.py`：原子化 clean 构建入口

`clean_data.py` 只处理已经整理好的一个 split。它不会复制来源、不会随机拆分，也不会训练模型。

### 4.1 前置条件

raw 根目录必须同时包含：

```text
database_by_paper/
data/
```

raw 和 clean 不能是同一目录，顶层也不能是符号链接。`--variables` 明确指定本次要生成的 Te、ne、Ti；`--min-valid-points` 控制一个剖面进入数据集所需的最少有效径向网格点。

### 4.2 暂存后替换

正式 clean 目录旁会建立临时 staging 目录。所有 PT、报告、单位日志和角色 manifest 先写入 staging。

只有当请求的所有变量都成功生成后，程序才使用 `os.replace` 把暂存文件逐个替换到正式 clean 目录。若缺少任一请求变量，程序直接失败，原 clean 文件保持不变。

如果本次只请求部分变量，例如只生成 Te，那么未请求变量对应的旧 PT 和旧角色 manifest 会在成功提交后删除，避免一个 clean 目录混有不同批次结果。

因此，这一入口保证的是“成功后得到完整一致的一批结果，失败时尽量保留上一批正式结果”。它不是数据库事务；进程或磁盘在逐文件替换的极端瞬间失效，仍可能需要通过报告和 manifest 检查文件批次。

## 5. `src/raw_builder.py`：从论文数据生成 PT

这是预处理的核心实现。它负责读取工作簿和原始剖面，构造 DeepONet 所需的 Branch、Trunk、target 和 mask。

### 5.1 `RawProfile`

每条原始剖面被表示为：

- `profile_id`、`paper_id`、`case_id`；
- `variable`：Te、ne 或 Ti；
- `coord_name` 和原始单位；
- 状态与 CSV 路径；
- 已排序、已转换到目标单位的 x/y 数组。

这个对象仍代表原始采样点，不代表 64 点 clean 网格。

### 5.2 Excel 元数据读取

每个 `database_by_paper/*.xlsx` 读取两个工作表：

- `02_CASES`：至少包含 `case_id`，并读取 `paper_id`、`delta` 或 `delta_avg`；
- `03_PROFILES`：至少包含 `profile_id`，并读取 case、论文、变量、坐标、单位、来源状态及可选 CSV 相对路径。

表头允许位于前 15 行内。工作簿文件大小、ZIP 解压后大小、成员数和工作表行数均有限制，防止异常文件造成过量内存消耗。

同一个 `case_id` 或 `profile_id` 在多个元数据行中重复时，不会猜测保留哪一条；相关实体被排除并写入报告。

### 5.3 profile CSV 关联

CSV 优先通过“文件名 stem 与 `profile_id` 完全一致”关联。若元数据提供 `target_points_csv_relpath` 或 `points_file_relpath`，路径必须仍位于 raw 根目录，而且目标文件名仍需与 `profile_id` 一致。

程序拒绝：

- 多个同名候选；
- 路径越出 raw 根目录；
- 文件名只近似相似；
- 根据论文号、图号或变量做模糊猜测。

这种严格关联牺牲了自动“修复”错名文件的便利，换取可追溯性。

### 5.4 数值 CSV 整理

CSV 至少需要两列可转换为浮点数的 x、y，允许数据开始前存在表头。数值数据开始后若再出现坏行，程序会失败，而不是静默跳过。

读入后：

1. 检查 NaN/Inf；
2. 按 x 稳定排序；
3. 同一 x 的多条 y 显式取平均并记录 warning；
4. 要求整理后的 x 严格递增；
5. 相邻 x 间距必须大于 `1e-8`，避免 PCHIP 产生病态斜率。

单个 CSV 的大小、行数和单行长度也设有上限。

### 5.5 单位转换

目标统一单位为：

- Te、Ti：keV；
- ne：`10^19 m^-3`。

转换只依据 `03_PROFILES.y_unit_raw` 的明确单位字符串：

- eV → keV：乘 `0.001`；
- keV → keV：乘 `1`；
- `m^-3` → `10^19 m^-3`：乘 `1e-19`；
- `10^19 m^-3`：乘 `1`；
- `10^20 m^-3`：乘 `10`。

未知单位会导致该 profile 被排除；程序不根据 y 数值范围猜测单位。所有实际转换写入 `unit_conversion_log.csv`。

### 5.6 样本筛选

只有满足下列条件的 profile 才可能进入 clean 数据集：

- 变量是 Te、ne 或 Ti；
- `data_origin == experimental`；
- profile 与 case 的 `paper_id` 不冲突；
- case 能在 `02_CASES` 中找到；
- `delta` 是明确数值且 `< 0`；
- 同一 case 至少具有 Te 和 ne，用于构造 Branch 输入；
- CSV 能被唯一关联、读取并完成单位转换。

`status=planned` 但实际 CSV 已存在时允许进入，同时保留 warning。非严格模式下，单个工作簿/profile 的问题进入 exclusions，其他数据继续处理；`--strict` 会在遇到此类异常时立即抛出。

### 5.7 Te/ne 参考剖面匹配

每个目标 profile 的 Branch 输入定义为：

```text
[delta, T0, n0]
```

其中：

- `delta` 来自 case 元数据；
- `T0` 是匹配 Te 剖面在 `rho=0.8` 的 PCHIP 值；
- `n0` 是匹配 ne 剖面在 `rho=0.8` 的 PCHIP 值。

同一 case 只有一个候选参考剖面时可直接使用；存在多个候选时，要求目标 profile 与候选在变量标记之后的 ID 后缀唯一一致。无法唯一匹配时拒绝启发式选择。

### 5.8 PCHIP 和有效 mask

共享 Trunk 网格为 float64 计算的：

```text
rho = linspace(0.8, 1.0, 64)
```

原始点使用 shape-preserving PCHIP 重采样。`extrapolate=False`，只有位于原始 x 覆盖范围内的网格点才计算 target 并令 `valid_mask=1`；范围外 target 仅作为张量填充值写为 0，同时 `valid_mask=0`。

距离原始端点不超过 `1e-7` 的网格点可贴到端点，用来吸收浮点表示误差；超过该容差仍视为外推并拒绝。PCHIP 结果还会检查是否越过相邻原始点的局部取值范围。

一个 profile 在 `[0.8,1.0]` 上的有效网格数少于 `min_valid_points` 时不会进入数据集。

### 5.9 PT 数据结构

每个变量生成独立的 `deeponet_dataset_<variable>.pt`：

```text
case_ids      list[str], 长度 N
paper_ids     list[str], 长度 N
profile_ids   list[str], 长度 N
branch_input  float32 [N, 3]
trunk_x       float32 [64]
targets       float32 [N, 64]
valid_mask    float32 [N, 64]
variable      str
metadata      dict
```

metadata 记录 raw 根目录、数据角色、坐标名称、单位、PCHIP 方法、禁止外推、边界容差和最小原始 x 间距。

PT 故意不保存 `branch_scaled`、`scaler_mean`、`scaler_std`。缩放统计量应只在训练数据上拟合，不能在预处理阶段用 train+test 全体数据预计算。

### 5.10 构建报告

`build_report.json` 记录：

- 生成文件与各变量样本数；
- warnings 和 exclusions；
- 单位转换；
- 插值设置；
- 坐标混用等显式假设。

不同论文使用的 `rho_pol`、`rho_tor` 等归一化坐标会暂时映射到同一个数值网格，但程序会记录混用 warning，因为这些物理坐标并非严格等价。

## 6. `src/data.py`：统一的数据加载和 Dataset 适配

### 6.1 `ProfileData`

`ProfileData` 是 clean 数据在内存中的统一表示。`subset(indices)` 返回按样本索引切出的新对象；共享 `trunk_x` 和 metadata，不改变 profile 顺序。

### 6.2 PT/NPZ 加载

`load_profile_data` 支持：

- `.pt`：通过 `safe_torch_load(..., weights_only=True)` 加载；
- `.npz`：通过 `allow_pickle=False` 加载。

顶层必须包含 case、paper、Branch、Trunk、target 和 mask。旧文件缺少 `profile_ids` 时，会用 `case_id__row<index>` 生成兼容 ID。

所有数值张量被转换为独立的 float32 CPU Tensor。NPZ 中若存在需要 pickle 的 object array，会被拒绝。

### 6.3 `EdgeProfileDataset`

这个 PyTorch `Dataset` 适配器把一个 profile 作为一个样本，返回：

- case/paper/profile ID；
- 对应的 Branch 向量；
- 整条 target 和 mask；
- 原始数据中的 `source_index`。

`trunk_x` 是所有 profile 共享的网格，因此不在每个 item 中重复复制。构造时要求 indices、Branch 行数和 target 行数一致。

## 7. `src/split.py`：人工 split 的统一解析

这个模块不随机创建 train/test。它只把用户已有的角色声明解析成确定的行索引。

### 7.1 dedicated role

`resolve_dedicated_split` 把某个 `data/<role>/clean` 中的全部 profile 归入声明角色。它表示目录已经由用户人工分配，不表示统计意义上的随机划分。

### 7.2 manifest/ID 定义

`read_split_definition` 支持：

- 包含 `case_id,split` 的 CSV manifest；
- train/val/test 各自一行一个 case ID 的文本文件。

两种格式不能同时提供。同一 case 映射到不同 split 会失败，未知 split 名称也会失败。

`resolve_split` 按 case 把 profile 行分配到 train、val、test，并列出未分配 case。train 必须存在，val/test 可以为空。默认拒绝 train/test 共享论文；train/val 共享论文会产生提示。

`write_resolved_split` 把最终行索引、profile、case、paper 和 split 写成 CSV，使下游运行能够复现确切样本集合。

### 7.3 论文分组交叉验证

`grouped_paper_folds` 用 paper 为不可拆分单位构造确定性的折：

- 同一论文的 profile 始终位于同一验证折；
- 按论文样本数从多到少，贪心分配到当前样本量最小的折；
- 论文数量少于折数时拒绝执行。

这样做是为了避免同一论文同时出现在某一折的训练和验证部分。

## 8. `src/config.py`：共享配置解析

当前预处理入口不直接读取模型 YAML，但该文件保留了与完整项目兼容的配置能力。

`load_config` 先读取同目录 `default.yaml`，再递归合并变量专用 YAML。字典递归合并，标量和列表由变量配置整体覆盖。使用 `yaml.safe_load`，并拒绝超过 1 MiB 的配置文件。

`validate_config` 提前检查：

- 变量和 target scaling；
- Branch/Trunk 输入维度；
- 网络隐藏层、latent dim、dropout；
- loss 权重；
- epochs、batch size、学习率、优化器和 scheduler；
- standard target scaling 与非负输出约束不能同时启用。

最后一项是因为标准化后的合法物理正值可以为负，若在标准化空间强制非负，会改变目标定义。

`save_config` 保存合并后的完整配置，用于记录一次运行实际使用的参数，而不是只保存局部 override。

## 9. `src/utils.py`：公共安全和可复现工具

### 9.1 安全序列化

- `validate_archive_size`：在解析前限制文件大小、ZIP 成员数、解压后总大小，并拒绝加密成员；
- `safe_torch_load`：要求 PyTorch 至少为 2.6，使用 `weights_only=True`，并要求顶层是 dict；
- NPZ 的 `allow_pickle=False` 由 `src/data.py` 配合执行。

这些限制减少恶意 pickle、压缩炸弹和异常大文件带来的风险，但不等于可以信任任意外部文件内容。

### 9.2 输出路径和文本

- `safe_output_subdir`：只允许单层安全目录名，拒绝绝对路径、`..`、斜杠、冒号和控制字符；
- `csv_safe`：给可能被电子表格解释为公式的字符串增加前缀；
- `csv_restore`：读取项目自产 CSV 时恢复该前缀；
- `json_safe`：把 Path、Tensor、NumPy 数组和标量递归转换为 JSON 类型；
- `write_json`：以 UTF-8、缩进格式写 JSON，并禁止 NaN。

### 9.3 运行环境

- `setup_logging`：统一控制台和 UTF-8 文件日志格式；
- `set_seed`：同步设置 Python、NumPy、PyTorch 和 CUDA 随机种子，可启用确定性 cuDNN；
- `select_device`：解析 auto/cpu/cuda/mps，并在请求设备不可用时明确失败；
- `dtype_from_name`：只接受 float32 或 float64。

## 10. `src/__init__.py`

该文件把 `src` 标记为 Python 包，并记录包版本 `1.0.0`。它不执行数据处理，也不自动导入其他模块，从而避免仅导入 `src` 就触发昂贵计算或文件写入。

## 11. 文件职责边界总结

| 文件 | 负责 | 不负责 |
|---|---|---|
| `organize_data.py` | 解析整理命令并调度复制 | 解析物理数据、插值、随机 split |
| `src/data_layout.py` | 规范目录、复制、哈希 manifest | 修改源文件内容 |
| `clean_data.py` | 调度一次原子化 clean 构建 | 复制 raw、训练模型 |
| `src/raw_builder.py` | 元数据关联、单位转换、PCHIP、PT 构造 | 猜测错名文件或未知单位 |
| `src/data.py` | 安全加载和内存数据表示 | 拟合 scaler、改变 target |
| `src/split.py` | 解析人工 split、论文分组 fold | 随机决定 train/test |
| `src/config.py` | 合并并验证共享配置 | 执行训练或预处理 |
| `src/utils.py` | 安全加载、路径、日志、随机种子、序列化 | 定义具体数据业务规则 |

这些边界使原始数据归档、clean 构建、数据加载和角色解析可以分别复现，也使任何自动修复或猜测行为更容易被发现。

## 12. 调用关系字典

### 12.1 raw 整理调用链

```text
organize_data.py
└── main()
    ├── DatasetLayout(data_root, split)
    ├── setup_logging(role_root/organize_data.log)
    ├── DatasetLayout.create()
    ├── organize_raw_data()
    │   ├── _source_files()
    │   ├── _copy_file()
    │   │   └── _sha256()
    │   └── _write_manifest()
    ├── adopt_clean_data()
    │   ├── _copy_file()
    │   └── _write_manifest()
    └── write_missing_raw_notice()
```

看到复制、覆盖、目录层级或 manifest 问题时，先查 `organize_data.py` 传参，再查 `src/data_layout.py`。

### 12.2 clean 构建调用链

```text
clean_data.py
└── main()
    ├── DatasetLayout(...)
    ├── TemporaryDirectory(staging)
    ├── build_clean_datasets()
    │   ├── _read_sheet_table()
    │   ├── _locate_csv()
    │   ├── _read_xy()
    │   ├── _convert_units()
    │   ├── _match_reference()
    │   ├── _interpolate_value()   # T0/n0 @ rho=0.8
    │   ├── _resample()            # target -> 64 点
    │   │   └── _evaluate_pchip()
    │   ├── torch.save()
    │   └── write_json()/CSV writer
    ├── write_role_manifest()
    │   └── safe_torch_load()
    ├── os.replace()               # staging -> 正式 clean
    └── stale_file.unlink()        # 删除未请求变量旧文件
```

看到 Excel、CSV、单位、profile 匹配、PCHIP、mask 或样本排除问题时查 `src/raw_builder.py`；看到“旧 clean 是否被替换”问题时查 `clean_data.py`。

### 12.3 数据加载调用链

```text
load_profile_data(path)
├── .pt  -> safe_torch_load() -> validate_archive_size() -> torch.load(weights_only=True)
├── .npz -> validate_archive_size() -> numpy.load(allow_pickle=False)
└── ProfileData(... float32 CPU clone ...)
    ├── subset(indices)
    └── EdgeProfileDataset(...)
```

看到 PT/NPZ 无法打开、缺字段、object array、PyTorch 版本或张量 dtype 问题时查 `src/data.py` 与 `src/utils.py`。

## 13. 常量字典

### 13.1 `src/raw_builder.py`

| 常量 | 当前值 | 控制内容 | 修改风险 |
|---|---:|---|---|
| `VARIABLES` | `("Te", "ne", "Ti")` | 允许构建的物理变量 | 新增变量还需同步单位、PT 文件名和下游代码 |
| `MAX_XLSX_BYTES` | 64 MiB | 单个工作簿压缩文件上限 | 过小会拒绝合法大表，过大会扩大资源风险 |
| `MAX_XLSX_UNCOMPRESSED_BYTES` | 256 MiB | 工作簿解压后总大小上限 | 防止 ZIP 解压膨胀 |
| `MAX_SHEET_ROWS` | 100000 | 单个工作表最大读取行数 | 防止异常表无限消耗内存 |
| `MAX_PROFILE_CSV_BYTES` | 64 MiB | 单个 profile CSV 大小上限 | 与真实数字化点规模有关 |
| `MAX_PROFILE_ROWS` | 1000000 | 单个 profile CSV 行数上限 | 防止极端输入耗尽内存 |
| `INTERPOLATION_METHOD` | `"pchip"` | 写入 metadata/report 的方法名 | 必须与实际 `_evaluate_pchip` 一致 |
| `BOUNDARY_ATOL` | `1e-7` | 端点浮点吸收容差 | 过大会把真实外推误判为端点误差 |
| `MIN_X_SPACING` | `1e-8` | 相邻原始 x 最小允许间距 | 过小可能产生病态斜率，过大可能排除合法高密度点 |

### 13.2 `src/data.py`

`REQUIRED_KEYS` 要求 PT/NPZ 至少包含：

```text
case_ids, paper_ids, branch_input, trunk_x, targets, valid_mask
```

`profile_ids`、`variable` 和 `metadata` 为兼容性可选字段，但新生成文件应包含它们。

### 13.3 `src/data_layout.py` 和 `src/split.py`

| 常量 | 值 | 含义 |
|---|---|---|
| `DATASET_ROLES` | `train, test` | 磁盘规范目录允许的角色 |
| `VALID_SPLITS` | `train, val, test` | 内存/manifest 允许的统计角色 |

磁盘布局没有单独的 `data/val` 强制入口，但 split manifest 可以包含 val。这两个集合用途不同，不应简单合并。

### 13.4 `src/utils.py`

| 常量 | 当前值 | 含义 |
|---|---:|---|
| `MIN_SAFE_TORCH_LOAD_VERSION` | 2.6.0 | 允许安全受限加载的最低 PyTorch 版本 |
| `MAX_SERIALIZED_FILE_BYTES` | 2 GiB | PT/NPZ 等序列化文件压缩大小上限 |
| `MAX_SERIALIZED_UNCOMPRESSED_BYTES` | 4 GiB | ZIP 格式序列化文件解压总大小上限 |

## 14. 函数级 API 字典

以下以“调用者需要知道什么”为主。以下划线开头的函数虽然是内部实现，仍列出以便定位问题。

### 14.1 `organize_data.py`

#### `parse_args() -> argparse.Namespace`

- 读取命令行，不访问数据文件；
- `split` 必填，只能是 train/test；
- raw-source 与 clean-source 至少要在 `main` 中存在一个；
- 相对 `data-root` 按当前工作目录解释。

#### `main() -> None`

- **读取**：命令行指定的来源目录；
- **写入**：规范 raw/clean、manifest、`organize_data.log` 或缺失说明；
- **重要副作用**：即使后续整理失败，`layout.create()` 和日志初始化也可能先建立空目录/日志；
- **常见失败**：未提供来源、来源不存在、来源结构中找不到 Excel/CSV、内容冲突、符号链接、路径越界。

### 14.2 `clean_data.py`

#### `parse_args() -> argparse.Namespace`

| 参数 | 默认 | 作用 |
|---|---|---|
| `--split` | 无 | train/test 角色，必填 |
| `--data-root` | `data` | 规范数据根目录 |
| `--raw-dir` | 推导 | 覆盖 `data/<split>/raw` |
| `--clean-dir` | 推导 | 覆盖 `data/<split>/clean` |
| `--variables` | Te ne Ti | 本次必须成功生成的变量集合 |
| `--min-valid-points` | 4 | profile 进入 PT 的最低有效网格数 |
| `--strict` | false | true 时单条坏数据立即终止；false 时记录 exclusion 后继续 |

#### `main() -> None`

- **读取**：一个 raw split；
- **暂存写入**：clean 同级临时目录；
- **正式写入**：PT、角色 manifest、build report、单位日志、clean log；
- **提交条件**：`report.generated_files` 必须覆盖用户请求的全部 variables；
- **提交方式**：`os.replace`，同一文件系统上通常是原子文件替换；
- **陈旧文件策略**：成功生成部分变量时，删除其他未请求变量的旧 PT/manifest；
- **失败保护**：变量未全部生成时不会提交 staging。

### 14.3 `src/data_layout.py`

#### `DatasetLayout(root, role)`

- frozen dataclass，创建后 root/role 不可重新赋值；
- `__post_init__` 拒绝 train/test 以外的磁盘角色；
- `role_root/raw/raw_workbooks/raw_profiles/clean` 都是计算属性；
- `create()` 只建立目录，不复制文件。

属性逐项对应：

| 属性/方法 | 返回或副作用 |
|---|---|
| `role_root` | `<root>/<role>` |
| `raw` | `<root>/<role>/raw` |
| `raw_workbooks` | `<root>/<role>/raw/database_by_paper` |
| `raw_profiles` | `<root>/<role>/raw/data` |
| `clean` | `<root>/<role>/clean` |
| `create()` | 建立 raw_workbooks、raw_profiles、clean 及所需父目录 |

#### `_sha256(path) -> str`

- 以 1 MiB block 流式读取文件；
- 返回小写/大写表现由 `hashlib.hexdigest()` 固定为小写十六进制；
- 文件在哈希过程中被修改时没有额外锁保护，因此来源目录应保持静止。

#### `_source_files(source) -> Iterable[(input_path, relative_destination)]`

- 只枚举候选，不执行复制；
- 规范来源优先读取 `database_by_paper/**/*.xlsx` 和 `data/**/*`；
- 非规范来源只读取根目录 `*.xlsx` 及非保留子目录中的文件；
- profile 子目录内不只限制 CSV，其他参考文件也可归档，但 `organize_raw_data` 最终要求至少存在 CSV。

#### `_copy_file(source, destination, allowed_root, overwrite) -> str`

- 返回 `copied` 或 `unchanged`；
- source/destination 符号链接被拒绝；
- 目标父目录必须解析到 allowed_root 内；
- 已存在且哈希不同、overwrite=false 时抛 `FileExistsError`；
- 使用 `shutil.copy2`，会尽量保留时间戳等元数据。

#### `_write_manifest(rows, csv_path, json_path) -> None`

- CSV 使用 UTF-8 BOM，并对字符串执行 `csv_safe`；
- JSON 顶层为 `{"files": rows, "count": len(rows)}`；
- 写 manifest 不是事务操作，磁盘故障可能导致 CSV/JSON 只写出一个。

#### `organize_raw_data(source, layout, overwrite=False) -> list[dict]`

- 验证 source 是目录；
- 防止两个源文件映射到同一相对目标；
- 要求最终至少一个 xlsx 和一个 csv；
- 成功后写 raw manifest，并返回与 manifest 相同的 rows；
- source 指向 `data/train` 而实际文件位于其 `raw/` 子目录时不会自动下钻，应传外部 incoming 根或明确的 raw 根。

#### `adopt_clean_data(source, layout, overwrite=False) -> list[dict]`

- 递归复制来源的全部文件；
- 至少要有一个 `.pt` 或 `.npz`；
- source 不得等于目标 clean；
- 不验证 PT 内部张量语义，只负责归档。

#### `write_missing_raw_notice(layout, reason) -> Path`

- 写出 `RAW_DATA_MISSING.md` 并返回路径；
- reason 会 `strip()`，调用方应传递清楚的数据谱系说明；
- 不会创建或伪造 raw Excel/CSV。

### 14.4 `src/raw_builder.py`

#### `RawProfile`

| 字段 | 类型 | 进入对象时的状态 |
|---|---|---|
| IDs/variable/coord/unit/status | str | 已清理首尾空白 |
| `csv_path` | Path | 已精确关联的来源 |
| `x` | float64 ndarray | 已排序、去重、严格递增 |
| `y` | float64 ndarray | 已与 x 对齐并转换到目标单位 |

#### `_clean_text(value) -> str`

- None 转空字符串；其他值转字符串并 strip；
- 不做大小写统一，调用者按字段需要再 `.lower()`。

#### `_read_sheet_table(path, sheet_name, required_column) -> list[dict]`

- 在前 15 行寻找包含 required_column 的表头；
- 使用 openpyxl read-only/data-only；公式单元格读取缓存值而不是公式文本；
- 忽略 required_column 为空的数据行；
- 无论成功失败都会关闭 workbook；
- 文件大小、ZIP 内容和行数先受限。

#### `_numeric(value) -> float | None`

- 接受有限 int/float 或可 `float(text)` 的字符串；
- 空值、坏字符串、NaN、Inf 返回 None，不直接抛错。

#### `_read_xy(path) -> (x, y, warnings)`

- 支持逗号、分号或空白分隔；只取前两列；
- 数据开始前的非数值行可作为表头跳过；
- 数据开始后的坏行立即失败；
- 同 x 多点取平均并写 warning；
- 输出 float64 x/y；
- 不做单位转换。

#### `_canonical_unit(unit) -> str`

- 转小写、去空格和 `^`；
- 兼容部分历史文本编码字符；
- 只是规范化字符串，不判断变量类型。

#### `_convert_units(variable, y, unit_raw) -> (converted_y, description)`

- 仅处理 Te/Ti/ne 已知单位组合；
- 返回新数值或原数组视情况，以及可写入日志的转换描述；
- 不依据数值范围猜测；未知单位抛 ValueError。

#### `_suffix(profile_id, variable) -> str`

- 用 `__` 切分 ID；
- 从变量 token 后取剩余后缀并转小写；
- 用于多参考剖面的精确配对，不用于 CSV 文件模糊匹配。

#### `_locate_csv(dataset_root, profile, all_csv) -> (Path|None, warnings)`

- 先寻找 stem 与 profile_id 完全一致的唯一文件；
- 多个同名文件直接返回 None；
- 再检查元数据显式相对路径，且目标仍必须同名、位于 root 内、后缀为 csv；
- 不抛出多数关联错误，而是通过 `None + warnings` 让 builder 写 exclusions。

#### `_match_reference(target, candidates) -> RawProfile`

- target 本身属于同变量候选时返回自身；
- 只有一个候选时返回该候选；
- 多候选时要求 `_suffix` 唯一一致；
- candidates 必须非空，调用者在进入前已保证 Te/ne 存在。

#### `_evaluate_pchip(profile, points) -> ndarray`

- 要求原始 x 至少两点、严格递增、间距大于阈值；
- `PchipInterpolator(..., extrapolate=False)`；
- 任何 NaN/Inf 均失败；
- 逐区间检查结果没有越过相邻原始 y 的 min/max，容忍量为 `1e-10 × max(1, max|y|)`。

#### `_interpolate_value(profile, rho) -> float`

- 用于获取单点 T0/n0；
- rho 在 `BOUNDARY_ATOL` 内可 clip 到原始端点；
- 真正超覆盖范围时失败。

#### `_resample(profile, grid) -> (target, mask)`

- mask 表示 grid 是否在原始 x 覆盖范围内；
- 只对 mask=true 的点调用 PCHIP；
- target 默认 float32 零，mask 返回 float32 0/1；
- 零填充值必须结合 mask 使用。

#### `build_clean_datasets(dataset_root, output_dir, variables, min_valid_points, strict, dataset_role) -> report`

- 这是核心批处理函数；
- **输入**：一个规范 raw 根；
- **输出文件**：变量 PT、build report、unit conversion log；
- **返回**：与 build report 主体一致的 dict；
- **非严格模式**：尽量继续构建，其余错误进入 exclusions；
- **严格模式**：工作簿读取、CSV 读取、单位、插值等异常立即传播；
- 如果一个变量无样本，该变量不生成文件并写 warning；
- 如果所有变量均无文件，写报告后抛 ValueError；
- 最终是否接受缺失变量由外层 `clean_data.main` 根据请求集合决定。

#### `write_role_manifest(dataset_path, output_path, role) -> None`

- 安全加载 PT，只取唯一 case_id；
- 每个 case 写一行固定 role；
- 不随机拆分；role 可为 train/val/test。

#### `write_train_only_manifest(...)`

- 旧接口兼容包装；
- 等价于 `write_role_manifest(..., "train")`。

### 14.5 `src/data.py`

#### `ProfileData`

- 纯内存 dataclass；
- `subset(indices)` 同步切 ID、Branch、target、mask；
- trunk_x/metadata 被共享引用，调用者不应原地修改它们；
- 空 indices 会产生空样本 Tensor，具体形状由 PyTorch 高级索引保持。

#### `_safe_torch_load(path)`

- 对 `utils.safe_torch_load` 的 CPU 固定包装；
- 便于本模块统一调用和测试替换。

#### `load_profile_data(path) -> ProfileData`

- 路径不存在：FileNotFoundError；
- 后缀不是 pt/npz：ValueError；
- 缺 REQUIRED_KEYS：KeyError；
- PT/NPZ 字符串 ID 全部转换为 Python str；
- 数值全部 `torch.as_tensor(..., float32).clone()`；
- 此函数只完成安全加载和类型统一，不检查 `[N,64]` 等完整业务形状。

#### `EdgeProfileDataset(data, indices, branch_values, target_values)`

- 初始化时验证三者样本数一致；
- `__len__` 返回 indices 长度；
- `__getitem__` 返回 ID、已传入的 Branch/target、原始 mask 和 source_index；
- branch_values/target_values 可以是经过训练集 scaler 处理后的版本；data 中仍保留原始值。

`EdgeProfileDataset.__init__`（即 `__init__`）不检查每个 target 的网格长度，也不重新缩放数值；这些应由上游数据准备保证。`__getitem__(item)` 中的 `item` 是当前 subset 内的位置，而返回的 `source_index` 是它在原始 `ProfileData` 中的行号。

### 14.6 `src/split.py`

#### `ResolvedSplit`

| 字段 | 含义 |
|---|---|
| `indices` | train/val/test 到 profile 行索引列表 |
| `case_to_split` | 人工 case 映射 |
| `unassigned_case_ids` | 数据集中存在但未映射的 case |
| `warnings` | 非致命 split 风险 |

#### `resolve_dedicated_split(data, role)`

- 把所有行放入一个指定角色；
- case_to_split 对唯一 case 排序后构建；
- warnings 明确说明没有随机拆分。

#### `_read_id_file(path) -> list[str]`

- UTF-8 BOM 兼容；
- 忽略空行；
- 不在此处去重，冲突由后续映射逻辑处理。

#### `read_split_definition(...) -> dict[str,str]`

- manifest 与 legacy ID 文件互斥；
- manifest 必须含 `case_id,split`；
- 用 `csv_restore` 恢复项目写出的安全前缀；
- 同一 case 多角色立即失败；
- 最终没有任何映射时失败。

#### `resolve_split(data, case_to_split, allow_paper_overlap=False)`

- 映射中出现数据集未知 case 时失败；
- 人工映射至少要包含一个 train case；
- 未映射 case 不进入任何 indices，并写 warning；
- train/test 论文交叉默认失败；train/val 论文交叉只 warning。

#### `write_resolved_split(data, split, path)`

- 只写已分配行；
- 行按原数据 index 排序；
- ID 使用 CSV 公式保护。

#### `grouped_paper_folds(data, train_indices, n_folds)`

- n_folds 至少 2；论文数至少等于折数；
- 以 paper 为整体，按样本量贪心平衡；
- 返回多个 `(train_indices, val_indices)`；
- 排序规则固定，因此同一输入可重复。

### 14.7 `src/config.py`

#### `_positive_int(value, name) -> int`

- 先 `int(value)` 再要求 >0；
- `1.5` 会被 `int` 截断为 1，因此配置来源应使用整数类型，不应依靠本函数识别小数输入。

#### `validate_config(config) -> None`

- 成功无返回值；失败抛 ValueError；
- 验证变量、scaler、输入维度、网络、loss、训练超参数；
- 不补默认值，缺字段通常通过 `.get(..., invalid_default)` 触发失败。

#### `deep_merge(base, override) -> dict`

- 对 base 深拷贝，不修改调用方原对象；
- dict 对 dict 递归合并；
- 列表、标量及类型不同的值整体覆盖。

#### `load_config(path) -> dict`

- 同目录必须存在 `default.yaml`；
- path 为 default 本身时只加载一次；
- 使用 YAML safe_load；空 YAML 视为空 dict；
- 合并后调用 validate_config。

#### `save_config(config, path) -> None`

- UTF-8、允许 Unicode、不排序 key；
- 创建父目录；
- 不在保存前再次 validate，调用者应保存已验证配置。

### 14.8 `src/utils.py`

#### `_torch_version_tuple() -> tuple[int,int,int]`

- 只解析版本开头的 `major.minor.patch`；
- `2.13.0+cpu` 可正常解析；无法解析则 RuntimeError。

#### `validate_archive_size(path, ...) -> None`

- 普通非 ZIP 文件只检查压缩文件本身大小；
- ZIP 还检查成员数、成员解压总大小和加密标记；
- 不逐个验证 ZIP 内部路径，因为函数不负责解压到磁盘。

#### `safe_torch_load(path, map_location="cpu") -> dict`

- 先查 PyTorch 版本和文件大小；
- 使用 `weights_only=True`；
- 顶层非 dict 时失败；
- 只降低反序列化风险，不验证 dict 的业务字段。

#### `safe_output_subdir(root, name, prefix="") -> Path`

- name 最长 128、不能空、不能含控制字符；
- 禁止绝对路径、点目录、路径分隔符和冒号；
- 返回 resolve 后的安全子目录，但不创建目录。

#### `csv_safe(value)` / `csv_restore(value)`

- 只处理字符串；
- 对公式触发前缀加单引号；
- restore 只撤销本项目约定格式，不应对任意第三方 CSV 无条件调用。

#### `setup_logging(log_file=None, level=INFO)`

- `force=True` 会替换进程已有 root logging 配置；
- 同时输出控制台和可选 UTF-8 日志；
- 多次调用会重新配置而不是叠加 handler。

#### `set_seed(seed, deterministic=True)`

- 设置 Python/NumPy/PyTorch/CUDA；
- deterministic=true 关闭 cuDNN benchmark；
- 不能保证所有第三方 GPU 算子绝对确定。

#### `select_device(requested) -> torch.device`

- auto 优先 CUDA，再 MPS，最后 CPU；
- 显式请求不可用设备时失败，不静默回退；
- 未专门限制其他 torch device 字符串，由 `torch.device` 解析。

#### `dtype_from_name(name) -> torch.dtype`

- 只支持 float32/float64；
- 不接受别名 `fp32`、`double`。

#### `json_safe(value)` / `write_json(data, path)`

- Tensor 自动 detach、移到 CPU、转 list；
- NumPy scalar 转 Python scalar；
- dict key 强制转 str；
- `allow_nan=False`，仍含 NaN/Inf 时写入会失败；
- write_json 直接写目标文件，不使用临时原子替换。

## 15. 数据结构字典

### 15.1 外部 raw 来源

推荐结构：

```text
incoming_train/
├── database_by_paper/
│   └── <paper>_profile_database.xlsx
└── data/
    └── <paper>/<figure>/<profile_id>.csv
```

扁平兼容结构允许工作簿在根目录、论文目录与工作簿并列，但建议尽早整理为规范结构。

### 15.2 Excel 字段

#### `02_CASES`

| 字段 | 必需性 | 用途 | 缺失结果 |
|---|---|---|---|
| `case_id` | 必需 | profile 归组和 Branch 样本单位 | 行不进入表 |
| `paper_id` | 业务必需 | 来源与冲突检查 | 可回退 profile paper，但不推荐 |
| `delta` 或 `delta_avg` | 必需数值 | Branch 第 1 维和负三角筛选 | case 排除 |

#### `03_PROFILES`

| 字段 | 必需性 | 用途 | 缺失/异常结果 |
|---|---|---|---|
| `profile_id` | 必需 | 唯一 ID、CSV 精确匹配 | 行不进入表 |
| `case_id` | 必需 | 关联 02_CASES | profile/case 排除 |
| `paper_id` | 强烈建议 | 与 case 来源核对 | 冲突时排除 |
| `variable` | 必需 | Te/ne/Ti 路由 | 其他变量忽略 |
| `coord_name` | 建议 | 记录 rho 类型 | 混用时 warning |
| `y_unit_raw` | 必需 | 明确单位转换 | 未知/空单位排除 |
| `data_origin` | 必需 | 只纳入 experimental | 非 experimental 排除 |
| `status` | 可选 | planned 情况提示 | planned+CSV 可纳入并 warning |
| `target_points_csv_relpath` / `points_file_relpath` | 可选 | 显式 CSV 路径 | 越界或错名拒绝 |

### 15.3 原始 profile CSV

最小语义是两列 x,y。允许：

- `x,y` 表头；
- 逗号、分号或空白分隔；
- x 无序；
- 完全重复 x（会平均 y 并告警）。

不允许：

- 少于两个数值点；
- 数据开始后的坏行；
- NaN/Inf；
- 整理后 x 不严格递增；
- 近重复 x 间距不大于阈值。

### 15.4 PT 字段

| 字段 | 维度/类型 | 语义 | 使用注意 |
|---|---|---|---|
| `case_ids` | list[str], N | 实验工况 | split 按它锁定 |
| `paper_ids` | list[str], N | 论文来源 | 分组和泄漏控制 |
| `profile_ids` | list[str], N | 剖面唯一 ID | 对应原始 CSV stem |
| `branch_input` | float32 `[N,3]` | delta/T0/n0 | 未缩放物理量 |
| `trunk_x` | float32 `[64]` | 0.8 到 1.0 的共享 rho | 所有 profile 共用 |
| `targets` | float32 `[N,64]` | 重采样剖面 | mask=false 处为填充值 |
| `valid_mask` | float32 `[N,64]` | 原始覆盖范围 | 必须参与 loss/指标 |
| `variable` | str | Te/ne/Ti | 一个 PT 一个变量 |
| `metadata` | dict | 来源、单位、插值参数 | 用于追踪，不代替 manifest |

### 15.5 `build_report.json`

| key | 解释 |
|---|---|
| `status` | 是否至少生成一个变量文件 |
| `dataset_role` | 调用者声明的 train/test |
| `raw_source` | raw 根的绝对路径 |
| `clean_output` | 构建函数写入位置；外层提交前会改为正式位置 |
| `generated_files` | 实际生成的变量到 PT 路径 |
| `sample_counts` | 每个请求变量的样本数，可能为 0 |
| `warnings` | 非致命风险，去重排序 |
| `exclusions` | 被排除实体及原因，可能同一实体多条 |
| `unit_conversions` | profile 到换算描述 |
| `interpolation` | PCHIP、外推和容差设置 |
| `assumptions` | 坐标映射等仍需人工理解的假设 |

### 15.6 raw manifest

| 字段 | 解释 |
|---|---|
| `source` | 原始绝对/解析路径 |
| `destination` | 规范副本绝对路径 |
| `bytes` | 来源文件字节数 |
| `sha256` | 复制时来源哈希 |
| `status` | copied 或 unchanged |

## 16. 故障现象反查字典

| 现象/关键词 | 最可能原因 | 先检查 | 处理方向 |
|---|---|---|---|
| `拒绝访问`，执行 `.venv\Scripts\python.exe` | python.exe 损坏、0 字节或 ACL/安全软件阻止 | 文件长度、ACL、`pyvenv.cfg` | 修复虚拟环境解释器，再检查依赖；不是业务脚本报错 |
| `ModuleNotFoundError: scipy` | 环境未完整安装 requirements | `python -m pip show scipy` | 用同一个 `.venv` 安装 `requirements_preprocessing.txt` |
| `No .xlsx metadata or profile files found` | raw-source 层级错误或来源缺文件 | source 下是否直接有 `database_by_paper/data` | 指向 incoming 根或规范 raw 根，不要指向其父级角色目录 |
| `Raw source directory does not exist` | 相对路径工作目录不对或路径拼错 | `Path.resolve()` 后位置 | 使用正确绝对路径或从项目根运行 |
| `Destination exists with different content` | 同名目标哈希与来源不同 | raw manifest、两边 SHA-256 | 人工确认后才使用 overwrite；不要盲目覆盖 |
| `Multiple source files map to the same destination` | 扁平整理后两个文件目标相同 | 来源目录中的重名文件 | 修正来源布局或名称 |
| `raw and clean directories must be different` | raw-dir/clean-dir 指向同一路径 | 两参数 resolve 结果 | 分离 raw 与 clean |
| `must contain database_by_paper/ and data/` | clean 输入不是规范 raw 根 | 目录树 | 先 organize 或修正 raw-dir |
| `请求的变量没有全部生成` | 某变量样本数为 0 | staging/build report 的 exclusions | 修 raw/元数据，或明确缩小 `--variables`；旧 clean 未提交 |
| `当前原始数据没有构建出任何可训练样本` | 所有 case/profile 均被排除 | build_report exclusions | 从最早的 workbook/CSV/单位问题开始排查 |
| `缺少工作表` | Excel 无 `02_CASES` 或 `03_PROFILES` | workbook sheet names | 按模板补齐工作表 |
| `前 15 行找不到字段` | 表头过晚、字段拼写错 | 前 15 行、required column | 移动/更正表头 |
| `case_id 在多个元数据行中重复` | 多工作簿或同表重复定义 case | 全部 02_CASES | 保留唯一权威定义 |
| `profile_id 在多个元数据行中重复` | 同 profile 被重复登记 | 全部 03_PROFILES | 修正 ID 或删除重复元数据 |
| `data_origin 不是 experimental` | 理论/模拟/其他来源 | 03_PROFILES | 这是设计筛选；不要为了纳入而随意改来源 |
| `不是明确的负三角形变` | delta 缺失、非数值或 >=0 | 02_CASES delta | 核对实验定义和字段 |
| `缺少 Te 或 ne` | 无法构造 T0/n0 | 同 case 的 profiles | 补齐实验剖面或排除该 case |
| `找不到唯一 CSV` | 文件名不等于 profile_id、重复同名或路径错误 | all CSV stem、元数据相对路径 | 精确改名/改路径，不做模糊匹配 |
| `元数据 CSV 路径越出 raw 根目录` | `../` 或绝对路径逃逸 | relpath 字段 | 把来源文件置于 raw/data 内 |
| `与 profile_id 不一致` | relpath 指向别的 profile 文件 | 文件 stem | 修正 profile_id 或目标文件名 |
| `不是有效的 x,y 数据` | 数据开始后有文本/坏列 | 报错行号 | 修正 CSV，不静默删除未知行 |
| `至少需要两行数值` | 表内有效点不足 | CSV 内容/分隔符 | 提供至少两个合法坐标点 |
| `包含 NaN 或 Inf` | 数字化或计算导出异常 | CSV 数值 | 回到来源修正 |
| `病态斜率` / 最小间距 | x 近重复 | 排序后 `diff(x)` | 核对数字化精度；不可随意降低阈值 |
| `单位无法识别` | y_unit_raw 不在明确映射中 | Excel 单位原文 | 增加经过确认的单位映射或修正元数据 |
| `多条参考剖面中没有唯一匹配` | 同 case 多个 Te/ne，ID 后缀无法配对 | profile_id 后缀 | 建立唯一、明确的命名对应 |
| `原始坐标范围不覆盖 rho=0.8` | Te/ne 未覆盖 Branch 基准点 | 原始 x min/max | 补数据或排除，不能外推 T0/n0 |
| `PCHIP 产生 NaN/Inf` | 求值越界或数值病态 | x 覆盖、间距、y 有限性 | 修原始点/边界，不开启外推 |
| `PCHIP 结果越过相邻原始点范围` | 数值异常或实现行为不符约束 | 对应区间原始点 | 保留失败证据，检查输入和 SciPy 版本 |
| `有效网格点少于` | 原始 x 在 0.8–1.0 覆盖太窄 | mask 和 x 范围 | 调整数据或经科学确认后调整 min-valid-points |
| `混合使用归一化坐标` | rho_pol/rho_tor 等被共用数值网格 | metadata coord_names | 作为物理风险处理，不是简单代码错误 |
| `数据集缺少字段` | PT/NPZ schema 不完整 | REQUIRED_KEYS | 从正规构建流程重新生成或补兼容转换 |
| `需要 pickle 的 object 数组` | NPZ 用 dtype=object 保存字符串 | NumPy dtype | 改存 Unicode dtype `<U...` |
| `PyTorch < 2.6` | 安全加载策略拒绝旧版本 | torch.__version__ | 升级环境，不关闭 weights_only |
| `文件过大` / `解压后过大` | 输入超过安全资源限制 | 文件大小/ZIP 成员 | 核实来源；必要时经评估调整专用上限 |
| `输出目录越出根目录` | 名称含路径分隔符、绝对路径或 `..` | 输出 name | 只传单层安全名称 |
| `配置 variable 必须是` | YAML 变量不受支持或缺失 | resolved config | 修正 default/override |
| `nonnegative_output 不能与 standard` | 物理空间约束误用于标准化空间 | data/model 配置 | 二选一，按建模目标决定 |
| `配置要求 CUDA，但检测不到` | 环境无可用 CUDA build/device | torch.cuda.is_available | 改 cpu/auto 或安装匹配 CUDA 环境 |

## 17. 按阶段排查字典

### 17.1 程序根本无法启动

依次确认：

1. `.venv/Scripts/python.exe` 存在且非 0 字节；
2. `python.exe -c "import sys; print(sys.executable, sys.version)"` 能运行；
3. `python.exe -m pip check`；
4. torch、numpy、scipy、openpyxl、yaml 能导入；
5. 入口脚本 `--help` 能运行。

此阶段不要先修改数据文件，因为 Python 尚未进入业务逻辑。

### 17.2 organize 失败

依次确认：

1. `raw-source` 是外部 incoming 根或明确 raw 根；
2. 其下能找到至少一个 xlsx 和一个 csv；
3. 没有符号链接；
4. 同名目标是否已存在且哈希冲突；
5. 查看 `organize_data.log` 和已有 raw manifest。

### 17.3 clean 没有生成某个变量

按 `build_report.json.exclusions` 的顺序分类：

1. 工作簿层：缺 sheet/表头；
2. case 层：重复 ID、delta、负三角条件；
3. profile 层：origin、paper 冲突、CSV 关联；
4. CSV 层：坏行、NaN、坐标间距；
5. 单位层：未知单位；
6. case 完整性：缺 Te/ne；
7. 参考匹配：多候选不唯一；
8. 插值层：rho=0.8 或 target 覆盖不足；
9. 有效点层：mask 点数不足。

排查时优先修最上游问题，因为一个 workbook 失败会引起其下多个 case/profile 同时消失。

### 17.4 PT 能生成但样本数不符合预期

比较：

- Excel 中 experimental 且变量匹配的 profile 数；
- `unit_conversion_log.csv` 行数；
- `build_report.json.sample_counts`；
- exclusions 按 reason 分组计数；
- PT 的 `len(profile_ids)`。

不要只看 CSV 文件总数，因为有些 CSV 可能属于非目标变量、非 experimental、正三角 case 或无法构造 Branch 的 case。

### 17.5 结果不可复现

确认以下证据来自同一批次：

- raw manifest 中的 SHA-256；
- PT metadata.source_root；
- build report 的 interpolation 常量；
- unit conversion log；
- 变量角色 manifest；
- 使用的软件版本，尤其 NumPy/SciPy/PyTorch；
- 是否在 PT 生成后修改过 raw CSV 或 Excel。

## 18. 修改影响范围字典

| 修改位置 | 直接影响 | 必须同步关注 |
|---|---|---|
| `DatasetLayout` 属性 | 所有规范路径 | README、已有数据迁移、入口默认值 |
| `_source_files` | raw 文件发现 | manifest 内容、重名映射、安全测试 |
| `_copy_file` | 覆盖与哈希行为 | 数据谱系和恢复策略 |
| Excel 字段读取 | case/profile 纳入 | 数据库模板、build report exclusions |
| `_convert_units` | target、T0、n0 数值 | unit log、历史 PT 兼容、可视化重建 |
| `_match_reference` | T0/n0 配对 | profile_id 命名规范 |
| `BOUNDARY_ATOL` | 边界 mask/T0/n0 | PCHIP 测试、历史 PT 重建误差 |
| `MIN_X_SPACING` | profile 是否被拒绝 | 高密度数字化数据和 PCHIP 稳定性 |
| `_resample` | target/mask | loss、指标、PT schema、可视化 |
| Trunk 64 点网格 | PT 第二维 | audit、模型、导出、可视化和所有 shape 测试 |
| PT key/schema | 加载器和下游 | REQUIRED_KEYS、兼容逻辑、文档 |
| split 论文规则 | 训练/验证集合 | 泄漏风险、交叉验证结果 |
| `safe_torch_load` | 所有 PT 读取 | PyTorch 最低版本和安全策略 |
| `csv_safe` | 所有人工 CSV | `csv_restore` 和外部工具读取方式 |
| clean staging/replace | 正式结果提交 | 失败恢复、陈旧文件删除测试 |

## 19. 维护时的最小原则

- 不用数值范围猜单位；
- 不用模糊文件名猜 profile；
- 不在原始覆盖范围外插值；
- 不把 mask=false 的零当作真实测量值；
- 不用全数据预计算训练 scaler；
- 不让同一 case 在不同 split；
- 不在未检查哈希冲突时覆盖 raw；
- 不在请求变量未全部成功时提交半套 clean；
- 不通过关闭安全加载来迁就旧环境；
- 所有自动排除都要在报告中留下原因。

这些原则比某个函数的当前写法更稳定。若未来重构模块，只要仍保留这些数据边界、失败语义和可追溯输出，整体行为才算兼容。
