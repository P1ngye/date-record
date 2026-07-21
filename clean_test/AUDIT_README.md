# Clean 数据审查原理说明

本文只解释 `clean_test` 中与审查有关的文件及其判断原理：

- `audit_data.py` 与 `src/audit.py`
- `export_pt_csv.py`
- `visualize_pt.py`
- `tests/`

## 1. 审查链路解决什么问题

clean 数据审查不是单一检查，而是四层互补证据：

1. **结构审查**：`audit_data.py` 判断 PT 的张量形状、掩码、标识符和 split 是否满足约定。
2. **逐值展开**：`export_pt_csv.py` 把二进制 PT 无损展开成长表，使每个网格值都能被人工或其他工具读取。
3. **来源重建对照**：`visualize_pt.py` 回到原始 CSV，以同样的单位换算和 PCHIP 原理重建曲线，再与 PT 中保存的网格值比较。
4. **代码回归测试**：`tests/` 用人为构造的小数据验证上述规则没有被后续修改破坏。

## 2. `audit_data.py`：自动结构和数据划分审查

### 2.1 输入模型

`audit_data.py` 通过 `src.data.load_profile_data` 读取 PT/NPZ，并把数据统一表示为 `ProfileData`：

- `case_ids`、`paper_ids`、`profile_ids`：样本的来源标识；
- `branch_input`：每个样本的 `[delta, T0, n0]`；
- `trunk_x`：共享的径向网格；
- `targets`：各剖面在径向网格上的值；
- `valid_mask`：网格值是否处于原始数据覆盖范围；
- `variable` 和 `metadata`：变量及单位等附加信息。

### 2.2 严重错误

`src.audit.audit_dataset` 将下列情况记为 `errors`：

- `branch_input` 不是 `[样本数, 3]`；
- `targets` 不是 `[样本数, 64]`；
- `valid_mask` 与 `targets` 形状不一致；
- `trunk_x` 不是 64 点一维网格；
- ID 数量与张量第一维不一致；
- Branch 输入或有效 target 中含 NaN/Inf；
- `valid_mask` 出现 0、1 以外的值；
- `trunk_x` 不严格递增，或超出 `[0.8, 1.0]`；
- 任一剖面的有效点少于 `min_valid_points`；
- `profile_id` 重复。

审查完成后，即使报告文件已经写出，只要存在 `errors`，`raise_if_audit_failed` 仍会令进程以失败结束。程序不会为了通过审查而自动修补数据。

### 2.3 split 与泄漏审查

split 有两种来源：

- 没有传入 manifest/ID 文件时，目录角色被视为人工预先指定的角色；整个数据集全部属于 train、val 或 test，不进行随机拆分。
- 提供 split manifest 或 ID 文件时，按 `case_id` 映射到 train、val、test。

核心原则是 **按 case 锁定**。同一 case 的多条 profile 不允许跨 split。默认还禁止 train/test 共享论文，因为同一论文的数据处理方式和实验条件可能造成论文级泄漏；train/val 论文重叠会产生 warning。未分配 case 被显式列出，而不是随机补入某个 split。

当 train 和 test 同时存在时，程序计算 train 中 `delta`、`T0`、`n0` 三个 Branch 特征的逐维最小值和最大值。若 test 样本在任一维超出这个轴对齐范围，会写入 `test_extrapolation`。这表示模型将在该特征维度上外推，但不是完整的多维分布距离判断。

### 2.4 输出的含义

- `data_audit.json`：完整嵌套报告，是机器读取时的主要依据；
- `data_audit.csv`：状态、错误、警告和主要统计量的扁平摘要；
- `split_resolved.csv`：本次审查实际采用的每个 profile 所属 split；
- `audit.log`：运行日志。

报告中的 Branch 统计量是原始 `delta`、`T0`、`n0` 的 min、max、mean、std；`valid_point_ratio` 是 mask 中有效网格的比例。它们用于发现异常范围或覆盖不足，不构成物理阈值判定。

## 3. `export_pt_csv.py`：PT 的可读、逐值展开

PT 是便于 PyTorch 使用的张量容器，但不适合直接逐行查看。导出器把每个样本的每个径向网格点写成一行，因此理论行数为：

```text
CSV 数据行数 = profile 数量 × trunk_x 网格点数
```

当前 clean 约定为 64 点，所以一个包含 N 个 profile 的 PT 应导出 `N × 64` 行。

每一行同时保留：

- `sample_index`、`grid_index`；
- `variable`、`case_id`、`paper_id`、`profile_id`；
- `delta`、`T0_keV`、`n0_1e19m3`；
- `rho`、`target_value`、`target_unit`；
- `valid_mask`。

导出前会检查 ID 数量、Branch 形状、target/mask 形状和 trunk 长度。导出过程只做张量到文本的展开，不重新插值、不改变 target，也不会丢弃 `valid_mask == 0` 的填充值。保留无效行是为了让审查者看到完整的张量布局，同时依靠 mask 区分真实有效值和补零。

字符串通过 `csv_safe` 处理，以防以 `=、+、-、@` 等字符开头的 ID 被电子表格软件解释成公式。文件使用 UTF-8 BOM，便于常见表格软件正确识别中文。

导出成功只证明 PT 内容被一致地展开，不能单独证明 PT 内的数值正确。

## 4. `visualize_pt.py`：原始点与插值结果重建对照

### 4.1 为什么要回到原始 CSV

可视化程序同时读取：

- clean PT，或由 `export_pt_csv.py` 生成的长表 CSV；
- raw 目录中的原始 profile CSV；
- `unit_conversion_log.csv` 中记录的换算倍率。

原始 CSV 必须通过 `profile_id` 与文件名精确匹配，而且只能有一个匹配项。程序不采用模糊文件名匹配，也不根据数值大小猜测单位。这样可以防止“图看起来合理，但实际取错曲线”的情况。

### 4.2 重建计算

原始点先排序；重复 x 会显式取同一 x 下 y 的平均值。单位按 `unit_conversion_log.csv` 的 `factor` 转到 PT 使用的目标单位。随后用 `PchipInterpolator(..., extrapolate=False)` 构造 shape-preserving PCHIP。

对每个 `valid_mask == 1` 的 PT 网格点，程序计算：

```text
expected_i = PCHIP(raw_x, converted_raw_y)(rho_i)
residual_i = stored_target_i - expected_i
```

并汇总：

```text
max_abs_error = max(|residual_i|)
RMSE = sqrt(mean(residual_i²))
```

无效网格点不参与误差计算。若有效网格超出原始点覆盖范围，PCHIP 会产生非有限值并触发失败，而不是外推。

### 4.3 每张审查图表达什么

每个 profile 单独生成一张三联图：

1. **Full raw-profile coverage**：显示完整原始点范围，并标出 clean 网格所在区间；
2. **Clean-grid inspection window**：放大 `[0.8, 1.0]` 附近，同时显示原始点、PCHIP 曲线和 PT/CSV 网格值；
3. **Interpolation reconstruction residual**：显示 `PT - PCHIP` 随半径的变化。

图中的角色是：

- 空心点：单位换算后的原始采样点；
- 蓝线：由原始点重新构造的连续 PCHIP；
- 红色叉号：PT 或导出 CSV 中实际保存的网格值；
- 紫线：保存值相对重建值的残差。

此外还生成分页总览、`inspection_data.csv` 和 `visualization_manifest.csv`。manifest 把每个 profile 的原始点数、有效网格点数、最大绝对误差和 RMSE 与具体图片路径关联起来，便于先按误差排序，再逐图检查。

### 4.4 误差如何理解

理想情况下，若 PT 正是由当前 raw 文件、当前单位转换记录和当前 PCHIP 实现生成，误差应主要来自 float32 序列化，通常很小。

较大的局部残差表示“当前保存值无法由当前审查链路精确重建”。可能原因包括：

- PT 来自旧版插值算法；
- raw CSV 或单位转换记录在 PT 生成后发生变化；
- profile 关联错误；
- 重复点处理、边界处理或有效 mask 规则不同；
- PT 文件被其他流程修改。

残差本身只定位不一致，不自动判定哪一侧正确，也不应被当成实验误差或模型预测误差。

## 5. `tests/`：审查规则的回归保护

测试全部使用临时目录和小型合成数据，目标是验证程序规则，而不是复现真实实验结论。

### `test_dataset_loading.py`

- 验证加载器忽略 PT 中预计算的缩放字段，只读取原始 Branch 输入；
- 验证安全的 NPZ 数据也能加载。

这保护“审查原始数据，不盲信预存 scaler”的原则。

### `test_split_leakage.py`

- 允许只有 train、暂时没有 val/test 的明确划分；
- 验证 dedicated test 数据集全部进入 test，不随机拆分；
- 验证 train/test 索引不会因 case 映射发生交叉；
- 默认拒绝 train/test 的论文级重叠。

这保护 split 的人工可追溯性和 case/论文泄漏边界。

### `test_pchip_interpolation.py`

- 证明实际使用 PCHIP，而不是线性插值；
- 检查端点保持和相邻点范围内不 overshoot；
- 仅容忍 `BOUNDARY_ATOL` 内的浮点端点误差，真实外推仍被拒绝；
- 原始数据覆盖不到的网格必须 mask 并补零；
- 近重复 x 在进入 PCHIP 前被拒绝，避免病态斜率。

这保护可视化重建和 clean 数据生成共同依赖的插值约束。

### `test_export_pt_csv.py`

- 验证 `N × 64` 行展开关系；
- 验证字段顺序、ID、浮点 target 和 mask 被保留；
- 验证可能触发电子表格公式的字符串被安全转义。

### `test_visualize_pt.py`

- 验证 PT 输入会生成逐 profile 图片、分页总览、长表 CSV 和审查 manifest；
- 验证 manifest 中的原始点数与重建误差；
- 验证导出的长表 CSV 也能重新关联原始点并绘图。

合成数据使用可被 PCHIP 精确重建的线性剖面，因此最大误差应低于 `1e-6`。

### `test_security_guards.py`

- 阻止输出路径逃逸指定根目录；
- 禁止通过 NPZ object array 触发 pickle；
- 验证受限 Torch loader 可读取普通安全状态；
- 阻止元数据中的 CSV 路径越出 raw 根目录；
- 禁止 profile CSV 模糊匹配；
- 数值数据开始后的坏行不能被静默跳过；
- 多个候选参考剖面不能靠启发式猜测；
- 验证 CSV 公式转义可往返恢复；
- 禁止在标准化空间错误使用非负输出约束。

这些测试保护审查证据的来源边界，避免“程序能运行”掩盖取错文件、路径越界或不安全反序列化。

### `test_data_layout.py`

- 验证外部 raw 文件会被复制到规范布局并产生哈希 manifest；
- 目标中已有不同内容时，若未显式允许覆盖则拒绝替换。

它不直接检查 PT，但保护审查所依赖的 raw 来源完整性。

### `test_clean_command.py`

- 只请求部分变量时，最终 clean 目录不保留未请求变量的陈旧 PT/manifest；
- 请求多个变量但未全部成功生成时，原有 clean 数据保持不变。

它保护审查对象的一致性：审查目录不应混入旧批次残留，也不能在失败构建后留下半套新结果。

## 6. 如何组合判断

建议把审查结论分成三种状态理解：

| 证据                 | 通过时可以说明                       | 仍不能说明            |
| ------------------ | ----------------------------- | ---------------- |
| `audit_data.py`    | PT 结构、mask、ID、split 满足程序约定    | PT 是否忠实来自原始点     |
| `export_pt_csv.py` | PT 每个值可追踪、可人工逐行查看             | 数值来源是否正确         |
| `visualize_pt.py`  | 当前 PT 与当前 raw/PCHIP/单位记录的一致程度 | raw 数字化和物理解释是否正确 |
| `tests/`           | 审查规则在受控样例上按预期工作               | 真实数据一定正确         |

只有结构审查无错误、重建残差可接受、来源对应关系可追踪，并且关键剖面经过人工查看后，才能形成较完整的 clean 数据审查证据链。
