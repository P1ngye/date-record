# NT 主表审阅台 + Overlay Studio 使用说明

## 1. 工具简介

这套工具由两个互相关联的本地 HTML 页面组成：

- **`profile_review_workbench.html`**：主表审阅台。用于导入主表数据，按 **paper → case → profile** 分层浏览，填写 QA 复审意见，导出 QA 检查表，并支持删除本地缓存。
- **`overlay_studio.html`**：Overlay 对齐工具。用于把图像与 CSV 曲线叠加显示，通过手动拾取坐标点完成校准，检查曲线与图中原始曲线是否对齐。

其中，主表审阅台提供了 **“打开 Overlay”** 按钮，可直接联动打开 Overlay 页面。因此，**建议把两个 HTML 文件放在同一个文件夹中使用**。

---

## 2. 适用场景

本工具适合以下工作流程：

1. 导入已经整理好的主表（论文、工况、剖面、QA）。
2. 在主表审阅台中快速定位某个 `paper_id / case_id / profile_id`。
3. 检查命名、变量、工况归属、坐标说明、CSV 路径等是否合理。
4. 必要时打开 Overlay，把提取的点数据和原图叠加，检查 digitize 结果。
5. 记录 QA 意见，并最终导出单独的 QA 检查表。

---

## 3. 主表审阅台

### 3.1 功能概览

主表审阅台用于：

- 导入主表
- 按 `paper / case / profile` 分层浏览
- 搜索与筛选条目
- 自动生成当前条目摘要
- 显示 ID 规则解释
- 填写和管理 QA 草稿
- 导出 QA 检查表 Excel
- 恢复或删除本地缓存

---

### 3.2 支持的导入格式

直接导入 `.xlsx` 文件。

工具会自动识别以下工作表：

- `01_PAPERS`
- `02_CASES`
- `03_PROFILES`
- `04_QA_LOG`

---

### 3.3 左侧区域说明

#### 1）导入主表

- **主表文件**：上传 `.xlsx / .json / .csv`
- **重新检查**：刷新当前视图
- **恢复缓存**：恢复本地缓存的工作区
- **删除缓存**：删除主表审阅台和 Overlay 的本地缓存
- **打开 Overlay**：打开叠图工具

#### 2）检索与筛选

支持：

- 关键字搜索：`paper_id / case_id / profile_id / fig_id / variable`
- 变量筛选：`Te / Ti / ne / ni / n_imp / T_imp`
- QA 结果筛选：`pass / warning / fail / info`

#### 3）检查与登记设置

- **默认检查者姓名**：自动填入 QA 表单
- **QA 表登记人姓名**：用于导出独立 QA 检查表
- **同步到当前 QA 表单**：把设置同步到当前记录

#### 4）当前状态

显示当前数据集中的：

- papers 数量
- cases 数量
- profiles 数量
- qa rows 数量

#### 5）三层列表

依次显示：

- Papers
- Cases
- Profiles

点击任意条目后，右侧会同步更新详情。

---

### 3.4 右侧区域说明

#### 1）当前条目概览

展示当前选中条目的：

- paper
- case
- profile
- figure

并生成适合人工复核的摘要。

#### 2）ID 规则与解释

页面会检查并解释：

- `paper_id`
- `case_id`
- `profile_id`
- 坐标 / 公式说明

其中页面内置的典型规则包括：

- `paper_id = 作者_设施_期刊_年份`
- `case_id` 以 `paper_id__NT__...` 的方式组织
- `profile_id` 以 `paper_id__FigX__变量__label` 的方式组织

#### 3）条目详情区

分为：

- Paper 详情
- Case 详情
- Profile 详情

并支持一键把当前条目预填到 QA 表单中。

#### 4）Figure / 坐标 / 关联条目

用于帮助你检查：

- 当前曲线属于哪张图
- 使用了什么变量
- 坐标与单位是否合理
- 同一 figure 下还有哪些 profile
- 当前最值得核查的高风险项

---

### 3.5 QA 记录编辑器

#### 快速记录

页面提供三个快捷按钮：

- **快速记为通过**
- **快速记为待确认**
- **快速记为需修改**

#### 可填写字段

主要包括：

- `entity_type`
- `entity_id`
- `check_type`
- `result`
- `issue`
- `suggested_fix`
- `checked_by`
- `checked_date`
- `notes`

#### QA 草稿区

你可以先累计多条 QA，再决定何时导出。

支持操作：

- **写入当前数据集**
- **导出 QA 检查表 Excel**
- **清空 QA 草稿**

---

### 3.6 导出结果说明

#### 导出 QA 检查表 Excel

导出为单独的一张检查表：

```text
xxx_QA_check_table.xlsx
```

特点：

- 只包含一张 `QA_CHECK_TABLE`
- 不附带整本主表
- 会自动补齐上下文信息，如 `paper_id / case_id / profile_id / fig_id / variable / coord_desc` 等

---

### 3.7 缓存说明

主表审阅台和 Overlay 都会使用浏览器本地缓存（`localStorage`）保存工作区状态。

当前版本提供了 **删除缓存** 功能，可用于清除上一次使用留下的本地痕迹。该功能会删除以下缓存键：

- `nt-review-workbench-v3`
- `nt-review-workbench-v2`
- `overlay_studio_autosave_v1`

删除后，当前页面中已恢复的数据也会一起清空。

---

### 3.8 主表审阅建议流程

建议按下面顺序操作：

1. 导入 `.xlsx`
2. 在左侧搜索并选中目标 `paper / case / profile`
3. 查看右侧摘要、ID 规则、坐标解释和 figure 关联信息
4. 填写 QA 记录
5. 打开 Overlay
6. 在 Overlay 中核对后，回到主表审阅台继续登记 QA
7. 最后导出 QA 检查表 Excel

---

## 4. Overlay Studio

### 4.1 功能概览

Overlay Studio 用于：

- 导入一张图像
- 导入一个或多个 CSV 曲线层
- 通过 5 个点建立坐标映射
- 将 CSV 曲线投影到图像上
- 用 detail 放大区和 minimap 辅助微调
- 导出叠图 PNG
- 保存 / 恢复会话 JSON
- 自动本地缓存

---

### 4.2 适合什么数据

建议使用：

- **单张裁剪后的图 panel**
- 每条曲线一个 CSV，或多条曲线分别导入多个 CSV
- CSV 中至少有两列数值列

工具会自动尝试识别：

- 横坐标：`x / r / rho / radius / psi`
- 纵坐标：`y / Te / Ti / ne / density / temp`

如果自动识别不准确，也可以在图层卡片里手动切换 `xCol` 和 `yCol`。

---

### 4.3 基本操作流程

#### 第一步：导入图像

在左侧 **Files** 区域：

- 在 **Figure Image** 中上传图像文件

#### 第二步：导入 CSV 图层

在 **CSV Layers** 中上传一个或多个 CSV 文件。

每个 CSV 会变成一个独立图层，图层支持：

- 显示 / 隐藏
- 选为当前图层
- 删除
- 修改颜色
- 修改显示模式：
  - `Line + Points`
  - `Line`
  - `Points`
- 手动选择 x 列 / y 列

#### 第三步：建立坐标

在 **Align** 区域按顺序拾取 5 个点：

1. `O`：原点
2. `X1`
3. `X2`
4. `Y1`
5. `Y2`

然后在输入框中填入这些点对应的真实数值：

- `X1 Value`
- `X2 Value`
- `Y1 Value`
- `Y2 Value`

再点击 **Build Axis** 建立坐标映射。

#### 第四步：检查叠图效果

建立坐标后，CSV 曲线会投影到原图上。

你可以通过以下区域辅助检查：

- **主画布**：查看整体叠图
- **Detail**：局部放大
- **Mini Map**：查看当前视口位置
- **Inspector**：查看当前点、图层和状态

#### 第五步：微调点位

如果叠图不够准，可以：

- 重新点击 O / X1 / X2 / Y1 / Y2 重新拾取
- 用方向键微调选中的点
- 用 Shift + 方向键进行快速微调
- 清除某个点后重新设置
- 必要时重新 Build Axis

---

### 4.4 工具栏说明

#### 视图工具

- **Select**：选择模式
- **Box Zoom**：框选放大
- **Hand**：手动平移

#### 视图控制

- **Fit**：适配画布
- **100%**：按实际像素比例查看
- **Reset View**：重置视图

---

### 4.5 Style 区域说明

可以实时调节叠图外观：

- **Detail Zoom**：局部放大倍率
- **Image**：底图透明度
- **Line**：曲线透明度
- **Points**：点透明度
- **Stroke**：曲线线宽
- **Radius**：点半径

还可开关：

- **Marks**：标记点
- **Guides**：辅助线
- **Grid**：网格
- **Loupe**：放大镜
- **Mini Map**：小地图
- **Guided Tooltips**：提示文字

---

### 4.6 Session 区域说明

支持以下操作：

- **Export PNG**：导出当前叠图结果
- **Save JSON**：保存会话
- **Restore Autosave**：恢复自动保存内容
- **Clear All**：清空当前工作区
- **Open Session**：打开之前保存的 JSON 会话

会话 JSON 中会保存：

- 图像
- 图层
- x/y 列设置
- 颜色
- 显示模式
- 标记点
- 校准结果
- 当前视图
- 界面参数

---

### 4.7 快捷键

Overlay 内置了以下快捷操作：

- **滚轮**：缩放
- **Space + Drag**：平移
- **双击**：适配视图
- **方向键**：微调当前选中点
- **Shift + 方向键**：快速微调
- **Ctrl / Cmd + Z**：撤销
- **Ctrl / Cmd + Shift + Z** 或 **Ctrl / Cmd + Y**：重做
- **Esc**：退出当前拾点模式
- **V**：切换到 Select
- **H**：切换到 Hand
- **Z**：切换到 Box Zoom

---

## 5. 常见问题

### Q1：为什么导入 Excel 失败？

可能原因：

- 浏览器没有成功加载 `xlsx` 库
- 当前离线，无法访问 CDN
- 工作表名称与预期不一致
- 文件内容不是标准 xlsx

建议：

- 先联网重试
- 检查工作表名是否包含 `01_PAPERS / 02_CASES / 03_PROFILES / 04_QA_LOG`

### Q2：为什么导入 CSV 后没有曲线？

可能原因：

- 选错了 x/y 列
- CSV 中存在非数值内容
- 尚未完成轴校准
- 图层被隐藏

建议：

- 在图层卡片中手动切换 `xCol` 和 `yCol`
- 检查 CSV 是否至少包含两列数值
- 确认已经完成 O/X1/X2/Y1/Y2 并点击 **Build Axis**

### Q3：为什么改了点以后曲线又不对了？

因为校准点变化后，旧的轴映射会失效。此时需要重新点击 **Build Axis**。

### Q4：缓存保存在哪里？

两个页面都使用浏览器本地缓存（`localStorage`）保存工作区状态。清浏览器缓存后，本地自动保存内容可能丢失。

当前主表审阅台版本额外提供了 **删除缓存** 按钮，可直接清除常用缓存键。

### Q5：为什么“打开 Overlay”没有反应？

通常是因为：

- `overlay_studio_bundle.html` 不在同一目录
- 浏览器阻止了新窗口
- 文件名被改动

建议：

- 保持两个 HTML 文件名不变
- 放在同一文件夹中
- 允许浏览器弹出新标签页

---

## 6. 注意事项

- 本工具是**本地前端工具**，不依赖后端数据库。
- 主表审阅台更适合做**结构化 QA 管理**。
- Overlay 更适合做**图像-曲线对齐核查**。
- 主表和 Overlay 是联动关系，不是互相替代。
- 如果你主要做登记和复审，请以 **主表审阅台** 为主入口。
- 如果你主要做曲线点位核查，请使用 **Overlay Studio**。
