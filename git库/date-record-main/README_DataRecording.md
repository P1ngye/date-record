# NT_profile_database 数据记录方案（v0.4，NT-only）

本版方案在原始数据记录方案基础上，**进一步收紧收录范围**，仅面向当前任务所需的数据，并对 **ID 命名规则** 进行了统一整理。

## 0. 当前收录范围

仅收录以下内容：

1. **NT 工况**  
   
   - 只记录 NT（Negative Triangularity）相关工况与剖面  
   - 不录入仅有 PT（Positive Triangularity）数据的剖面  
   - 如果一篇论文同时包含 NT 和 PT，记录在额外的登记表内，以便后续查找

2. **只收温度与密度量**
   
   - 温度：`Te`、`Ti`
   - 密度：`ne`、`ni`
   - 若论文明确给出其他**实验测得**的温度/密度量（如`n_imp`），可在备注说明后酌情纳入
   - **不再纳入**：`p`、`rotation`、`Er`、流速、热流等非温度/密度量

3. **只收实验数据图**
   
   - 只处理**实验测量结果对应的 figure / curve**
   - **排除**以下内容：
     - 模拟数据图
     - 数值计算结果图
     - 建模拟合单独生成的图
     - 纯理论图
     - synthetic diagnostic / post-processed simulation curves
   - 若一张图中同时含实验曲线与模拟曲线，只提取**实验曲线**，并在 `notes` 中说明“同图含模拟曲线，已排除”
   - 对于含有模拟数据图的论文，应记录在额外的登记表内，以便后续查找

---

## 1. 将使用的文件

- **`paper_registry_and_template.xlsx`**
  
  - `01_PAPERS`：论文登记
  - `02_CASES`：仅登记 NT 工况
  - `03_PROFILES`：仅登记 NT + 实验 + 温度/密度剖面
  - `04_QA_LOG`：质检记录（原为06）

- **data：`data/paper_id/*.csv`**
  
  - 每条剖面一份 CSV，至少两列：`x,y`

> 推荐继续采用“**Excel 记录元数据 + CSV 存点数据**”的方式，但当前数据库仅保留 NT 实验温度/密度剖面。

---

## 2. 工况记录

`02_CASES` 中：

- 每个 `case_id` 对应一个可区分、可追溯的 NT 工况
- `regime` 固定记录为 `NT`
- 若原论文同页同时比较 NT/PT，则该表仅登记 NT 对应 case
- `notes` 可注明：
  - `paper also contains PT comparison`
  - `figure also contains simulation curve, excluded from profile extraction`

---

## 3. 剖面元数据

`03_PROFILES` 中每条曲线仍为一行，但必须满足以下全部条件：

- 来自 NT 工况
- 来自实验数据图
- 变量属于温度/密度范围
- 曲线可追溯到 paper / case / figure / legend

### 允许的变量

优先只使用以下变量：

- `ne`
- `Te`
- `Ti`
- `ni`

如遇论文明确给出其他**实验测量**的温度/密度量，可暂用：

- `n_imp`
- `T_imp`

但必须在 `notes` 中说明来源和物理含义。

### 每条剖面必须填的字段

以下字段空缺则**不入库**：

- `profile_id`
- `paper_id`
- `case_id`
- `fig_id`
- `variable`
- `coord_name`
- `coord_desc`
- `y_unit_raw`
- `y_unit_SI`
- `data_origin`（必须是 `experimental`）
- `extraction_method`
- `status`

### 关键字段要求

- `data_origin`
  - 只能填：`experimental`
  - 若为 `simulation` 或 `mixed`，该曲线不得入当前库
- `variable`
  - 只允许温度/密度类变量
- `notes`
  - 若原图中混有模拟曲线，必须注明 `simulation curves excluded`

---

## 4. 点数据存储

文件：`data/paper_id/<profile_id>.csv`

最低两列：

- `x,y`

要求：

- x/y 单位必须与 `03_PROFILES` 一致
- 使用 WebPlotDigitizer

---

## 5. 常见排除情形

以下情况直接不入当前库：

- 只有 PT 剖面，没有 NT
- 只有压力、旋转或电场，没有温度或密度
- 图完全来自模拟结果
- 图中实验与模拟无法区分
- 坐标定义、变量定义或图例无法确认

---

## 6. 推荐 ID 规则

### 6.1 `paper_id`

`paper_id` 统一命名为：

`作者_设施_期刊_年份`

要求：

- 作者：使用**第一作者姓氏**
- 设施：使用**实验装置/设施缩写**，如 `AUG`、`TCV`、`DIII-D`、`JET`
- 期刊：使用**统一缩写**
- 年份：使用论文发表年份

示例：

- `Aucone_AUG_PPCF_2024`
- `Vanovac_TCV_NF_2023`
- `Smith_DIIID_PRL_2022`

### 6.2 `case_id`

`case_id` 统一命名为：

`paper_id__NT__简要标签`

说明：

- 固定保留 `NT`
- 简要标签用于区分同一篇论文中的不同 NT 工况
- 标签应尽量短且可读，如 `fav`、`unfav`、`ddt`、`ECRH`、`NBIECRH`

示例：

- `Aucone_AUG_PPCF_2024__NT__fav`
- `Aucone_AUG_PPCF_2024__NT__ddt`

### 6.3 `profile_id`

`profile_id` 统一命名为：

`paper_id__FigX__变量__label`

说明：

- `FigX`：写成适合 ID 的标准形式，如 `Fig3a`、`Fig16b`
- `变量`：仅使用本项目允许的温度/密度变量，如 `Te`、`Ti`、`ne`
- `label`：填写图例或曲线标签，便于唯一追溯

示例：

- `Aucone_AUG_PPCF_2024__Fig3a__Te__fav`
- `Aucone_AUG_PPCF_2024__Fig16b__ne__ddt`

### 6.4 分隔符规则

- 单下划线 `_`：用于单个字段内部组合，如 `Aucone_AUG_PPCF_2024`
- 双下划线 `__`：用于不同层级之间分隔，如 `paper_id__NT__fav`

### 6.5 期刊缩写建议

为避免命名不统一，建议优先使用以下标准缩写：

- `PPCF` = *Plasma Physics and Controlled Fusion*
- `NF` = *Nuclear Fusion*
- `PRL` = *Physical Review Letters*
- `PoP` = *Physics of Plasmas*

---

## 7. 本版与原版相比的核心变化

- 删除压力、旋转、Er 等非目标变量
- 明确排除 simulation-only 图
- 删除Excel 主表中的00、04、05部分，其中DICTIONARIES移至Readme文件Appendix中
- **统一修订 ID 命名规则：`paper_id` 改为 `作者_设施_期刊_年份`**
- 新增一个登记表：
  * `论文处理信息登记表.xlsx`

---

## Appendix A. 数据字典

本附录由原 Excel 中的 `05_DICTIONARIES` 整理而来，仅保留**当前 NT-only 数据库实际需要**的字典项

### A.0 整理原则

- 只保留与 **NT + experimental + temperature/density profiles** 相关的字典内容
- 删除与当前方案无关的变量、单位和冗余项
- 若后续遇到本附录未覆盖、但**确属实验测得的温度/密度量**，可临时补充；但必须在 `notes` 中说明来源与物理含义

### A.1 `variable` 允许值

| `variable` | 含义                   | 是否纳入当前库 | 说明                   |
| ---------- | -------------------- | -------:| -------------------- |
| `ne`       | electron density     | 是       | 优先纳入                 |
| `Te`       | electron temperature | 是       | 优先纳入                 |
| `Ti`       | ion temperature      | 是       | 优先纳入                 |
| `ni`       | ion density          | 是       | 优先纳入                 |
| `n_imp`    | impurity density     | 有条件     | 必须在 `notes` 中说明物种与来源 |
| `T_imp`    | impurity temperature | 有条件     | 必须在 `notes` 中说明物种与来源 |

> 已从原 dictionary 中删除的非目标变量包括：`pe`、`p`、`v_tor`、`omega_tor`、`Er`、`nC`、`TC`、`Zeff`、`q`、`iota`、`phi`、`Prad` 等。

### A.2 `coord_name` 推荐取值

| `coord_name`        | 含义 / 使用说明                     |
| ------------------- | ----------------------------- |
| `rho_pol`           | 归一化 poloidal flux 坐标          |
| `rho_tor`           | 归一化 toroidal flux 坐标          |
| `sqrt_psi_tor_norm` | 归一化 toroidal flux 的平方根形式      |
| `psi_N`             | 归一化 poloidal flux             |
| `r_a`               | 以小半径 `a` 归一化的径向坐标             |
| `R-Rsep`            | 相对 separatrix 的径向坐标           |
| `R`                 | 大半径坐标                         |
| `r`                 | 径向坐标；必须在 `coord_desc` 中写清具体定义 |
| `other`             | 非标准坐标；必须在 `coord_desc` 中完整说明  |

### A.3 `extraction_method` 允许值

| `extraction_method` | 含义             | 使用建议                 |
| ------------------- | -------------- | -------------------- |
| `manual_digitize`   | 人工从图中 digitize | **推荐默认方式**           |
| `ai_digitize`       | AI 辅助 digitize | 原则上不可使用              |
| `manual_table`      | 人工从正文/附录表格录入   | 若论文直接给表，优先于 digitize |
| `ai_table`          | AI 辅助表格提取      | 仅可在人工复核后使用           |
| `direct_numeric`    | 论文已直接提供数值      | 适用于补充材料或正文可复制数值      |
| `hybrid`            | 多种方式混合         | 必须在 `notes` 中说明具体流程  |

> 当前点数据提取工具仍推荐统一使用 **WebPlotDigitizer**

### A.4 `status` 允许值

| `status`    | 含义          |
| ----------- | ----------- |
| `planned`   | 已登记，待提取     |
| `digitized` | 已完成曲线提取，待复核 |
| `imported`  | 已从表格/数值源导入  |
| `qa_passed` | 已完成质检并通过    |
| `rejected`  | 不纳入当前库      |

### A.5 `y_unit_SI` 规范写法

| 适用变量                | `y_unit_SI` | 说明                                          |
| ------------------- | ----------- | ------------------------------------------- |
| `ne`, `ni`, `n_imp` | `m^-3`      | `y_unit_raw` 可保留论文原写法，如 `10^19 m^-3`        |
| `Te`, `Ti`, `T_imp` | `eV`        | `y_unit_raw` 可为 `eV` 或 `keV`，但需在元数据中如实记录原单位 |

### A.6 清理说明

原 `05_DICTIONARIES` 中与当前 NT-only 方案无关的部分已删除，主要包括：

- 非温度/密度变量项
- 与上述变量对应、但已不再使用的单位项（如 `Pa`、`kPa`、`m/s`、`km/s`、`rad/s`、`krad/s`、`V/m`、`kV/m` 等）
- 对当前 README 规则没有实际约束作用的冗余占位内容

后续若数据库范围再次扩展，应优先修改 README 中本附录，而不是恢复旧版混合式 dictionary 表。
