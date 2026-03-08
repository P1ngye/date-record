# NT_profile_database 数据记录方案（v0.1）

本方案的目标：先把 **NT 实验中公开可获得的剖面点数据**（ne/Te/Ti/p/rotation/Er…）做成一个**结构化数据库**，并保证每条剖面都能追溯到：

- 论文（paper_id / DOI / 本地PDF路径）
- Figure 编号（fig_id）
- 工况信息（shot / time_window / regime，缺失时需说明原因）
- 坐标定义（coord_name + coord_desc，必须写清楚“归一化到什么、如何映射”）
- 单位（图上原单位 y_unit_raw + 规范单位 y_unit_SI）

---

## 1. 将使用的文件

- **`NT_profile_database_template.xlsx`**
  
  - `01_PAPERS_论文`：论文清单（paper_id 入口）
  - `02_CASES_工况`：每篇论文里的“实验工况/放电段”清单（case_id 入口）
  - `03_PROFILES_剖面`：每条剖面曲线的元数据（profile_id 入口）
  - `04_POINTS_MANUAL`：少量点数据可手工填（不推荐大规模）
  - `05_DICTIONARIES`：下拉选项词典（变量、坐标、提取方式、状态、单位等）
  - `06_QA_LOG`：质检记录（谁查的、问题是什么、怎么修）

- **可选：`data/digitized/*.csv`**（推荐的点数据存储方式）
  
  - 每条剖面一份CSV，至少两列：`x,y`
  - 如果有误差棒，可加：`x_err,y_err`（单位与剖面元数据保持一致）

> 推荐采用“**Excel记录元数据 + CSV存点数据**”的混合方式：前期人工最方便，后期也最容易自动化合并。

---

## 2. 记录方式

### Excel + CSV

- 元数据：填 `01/02/03`
- 点数据：每条剖面导出一个CSV放到 `data/digitized/`
- 在 `03_PROFILES_剖面` 里用 `points_source=csv` + `points_file_relpath=...` 指向CSV

---

## 3. 强制规范

### 3.1 ID 规则

- `paper_id`：建议 `设备_作者年份`（例：`AUG_Vanovac2024`）
- `case_id`：建议 `paper_id__简要工况标签`（例：`AUG_Vanovac2024__case_fav_unfav`）
- `profile_id`：建议 `paper_id__fig__variable__label`（例：`AUG_Vanovac2024__Fig3a__Te__fav`）

### 3.2 每条剖面必须填的字段（`03_PROFILES_剖面`）

以下字段空缺视为 **不入库**：

- `profile_id`
- `paper_id`
- `case_id`（拿不到shot/time也行，但必须有case_id）
- `fig_id`
- `variable`
- `coord_name`
- `coord_desc`（必须写清楚坐标定义，不能只写“rho”）
- `y_unit_raw`（图上原单位）
- `extraction_method`（手工/AI/混合，见第5节）
- `status`（planned/digitized/qa_passed/imported）

> shot/time 缺失允许，但必须在 `notes` 写明：论文未给出 / 图注无信息 / 无法确认。

---

## 4. 操作流程

### Step 1：登记论文（`01_PAPERS_论文`）

每新增一篇论文，填一行：

- `paper_id`
- `title/year/journal/doi`
- `device`
- `local_pdf_relpath`
- `notes`

### Step 2：登记工况（`02_CASES_工况`）

每篇论文里通常有多个放电/阶段/三角形度扫描：

- 一种“可区分、可追溯”的工况 = 一行 `case_id`
- 优先填：shot、time_window、regime（NT/PT、L/H、ECRH/NBI…）
- 全局量（Bt/Ip/Paux/n̄e/q95…）能填尽量填；缺失写 N/A

### Step 3：登记剖面元数据（`03_PROFILES_剖面`）

每条曲线（一个变量、一条颜色/图例） = 一行 `profile_id`

关键字段怎么填：

- `fig_id`：如 `Fig.3a` / `FIG.1`
- `variable`：从下拉选（ne/Te/Ti/pe/v_tor/Er…）
- `species`：e/i/C/impurity 等
- `coord_name`：从下拉选（rho_pol / rho_tor / sqrt_psi_tor_norm / R-Rsep…）
- `coord_desc`：用一句话写清楚坐标定义与映射方式（例：“mapped to normalized poloidal flux ρ_pol; profiles shown across pedestal and SOL”）
- `y_unit_raw`：图上单位（keV、10^19 m^-3、kPa…）
- `y_unit_SI`：规范单位（eV、m^-3、Pa…；拿不准可先填 other 并在notes说明）
- `points_source`：`csv` 或 `manual_sheet`
- `points_file_relpath`：如果是csv，填 `data/digitized/<profile_id>.csv`
- `curve_label/curve_color`：写图例/颜色，方便复核
- `extraction_confidence(1-5)`：1=不确定，5=非常确定（用于后续筛选）

### Step 4：录入点数据

文件：`data/digitized/<profile_id>.csv`
最低两列：

- `x,y`

可选列：

- `x_err,y_err`

注意：

- x 与 y 的单位必须与 `03_PROFILES_剖面` 里一致
- 建议使用WebPlotDigitizer

---

## 5. 人工还是AI辅助

在 `03_PROFILES_剖面` 里用两个字段锁死：

- `extraction_method`（下拉）
  
  - `manual_digitize`：人工用数字化工具抠点
  - `ai_digitize`：AI从图像/矢量提取点（仍需人工复核）
  - `manual_table`：人工从论文表格抄录
  - `ai_table`：AI从表格/补充材料抽取（仍需人工复核）
  - `direct_numeric`：作者直接给出数值文件/数据表（最可靠）
  - `hybrid`：混合（必须在notes说明哪部分AI）

- `digitizer_tool`
  
  - 例：WebPlotDigitizer / Engauge / Origin / “AI+manual check”

强烈建议：任何 `ai_*` 都必须：

- `extraction_confidence ≤ 4`（除非有第二人复核）
- 在 `06_QA_LOG` 留一条复核记录

---

## 6. 质检（QA）怎么做才不拖慢

最小质检规则（建议每条剖面都做）：

1) **追溯检查**：paper_id / fig_id / coord_desc / y_unit_raw 是否完整
2) **单调性检查**：x 是否大致单调（非单调通常是导出点顺序乱）
3) **范围检查**：x 是否落在图轴范围；y 是否出现明显离谱值（例如 Te=300 keV）
4) **单位检查**：10^19 m^-3 是否被当成 m^-3（最常见错误）

质检记录写到 `06_QA_LOG`：

- `result(pass/fail)` + `issue` + `suggested_fix`
- 修完后将 `03_PROFILES_剖面.status` 改为 `qa_passed`

---

## 7. 常见坑（提前规避）

- 坐标没写清楚：只写“rho” → 后面无法比较不同设备/不同映射
- 单位不统一：10^19 m^-3、keV、kPa 未换算 → 拟合/AI会学到假规律
- 没有曲线标签：同一figure多条曲线无法追溯
- AI提取但没复核：点偏了还以为是物理差异
