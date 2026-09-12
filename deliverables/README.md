# 论文与交付统一入口

当前版本：**V5 四问同口径稿；不是最终提交包。**

## 最新交付（V5）

- [V5论文PDF（25页）](draft_v5/pdf/C_microgrid_draft_v5.pdf)
- [V5 LaTeX源文件](draft_v5/latex/main.tex)
- [第四问严格迁移报告](../docs/experiments/Q4_STRICT_TRANSFER.md) · [证据包](../analysis/strict_q4_transfer_v1/)

V5完成第四问严格迁移，四问自此处于同一因果口径。迁移唯一改动价格输入：执行器、结算规则与一月冻结的裕量参数全部不变。动态电价下裕量降幅8.5842%，与固定电价的8.7058%基本一致；新预报重规划仍更贵3.3546%，与固定电价的负结论一致。迁移中还得到一个结构性结果：固定承诺配B0控制器时，应急与富余轨迹完全不随电价改变，逐槽最大差2.2e-8 kWh，而充电量最大差达一个满槽功率。8个策略×334天共2672天、384768槽由独立脚本重算通过。

### 重建 V5

```sh
.venv/bin/python scripts/run_strict_q4.py
.venv/bin/python scripts/verify_strict_q4.py
.venv/bin/python scripts/paper/build_q4_tables.py
.venv/bin/python scripts/paper/build_pdf.py --version v5
```

## V4历史版本

- [V4论文PDF（23页）](draft_v4/pdf/C_microgrid_draft_v4.pdf) · [LaTeX源文件](draft_v4/latex/main.tex)
- [时间语义封版记录](../docs/data/TIME_SEMANTICS.md) · [证据包](../analysis/time_semantics_v1/)

V4把时间语义从待定项变为有证据的结论，新增定案推理与积分规则的解析上界。

## V3历史版本

- [V3论文PDF（22页）](draft_v3/pdf/C_microgrid_draft_v3.pdf) · [LaTeX源文件](draft_v3/latex/main.tex)
- [3D图件、网格与说明](candidate_figures/v3_3d/README.md) · [两页3D图册](candidate_figures/v3_3d/3D_candidate_atlas.pdf)

V3把两组三维图并入正文：参数—费用响应面与B2的日内—月份储电量曲面，各配解读与限制说明。

## V2历史版本

- [V2论文PDF（19页）](draft_v2/pdf/C_microgrid_draft_v2.pdf)
- [V2独立科研图册（5组、20个子图）](candidate_figures/v2/research_figures_v2.pdf)
- [V2图件、数据及说明](candidate_figures/v2/README.md)
- [V2 LaTeX源文件](draft_v2/latex/main.tex)
- [V2审阅包ZIP](C_microgrid_review_v2.zip)

本轮仅改图表、文字和排版，模型数值保持原版本。旧Excel仍未与新版主策略对齐。

### 重建 V2

```sh
rtk proxy .venv/bin/python scripts/paper/build_research_figures.py
rtk proxy .venv/bin/python scripts/paper/build_pdf.py --version v2
rtk proxy .venv/bin/python scripts/paper/verify_research_figures.py
```

## V1历史版本与原始交付证据

- [整套V1审阅包 ZIP](C_microgrid_review_v1.zip)：包含源码、图表、PDF及明确标注的旧Excel，非正式提交包。
- [第一版论文 PDF](draft_v1/pdf/C_microgrid_draft_v1.pdf)
- [LaTeX 主文件](draft_v1/latex/main.tex)：源文件与自动生成的表格一起保存。
- [候选图表目录](candidate_figures/v1/)：6组数据图，每组含矢量 PDF 与 PNG；系统结构和时序图使用正文中的 TikZ 源码。
- [候选图表来源及哈希](candidate_figures/v1/manifest.json)
- [四个指定日紧急区间 CSV](candidate_figures/v1/selected_emergency_intervals.csv)：Q2 B2及Q3裕量固定的内部物理区间。
- [旧五份 Excel](legacy_excel/)：仅供核对原模板与旧结果，**不与本稿构成同版本提交**。
- [证据摘录](review/)：当前Q2/Q3结果、独立验收、比较表及清理日志。

## 目录职责

| 目录 | 内容 | 当前状态 |
| --- | --- | --- |
| `draft_v5/latex/`、`draft_v5/pdf/` | **当前论文**源文件与PDF | V5，四问同口径 |
| `draft_v4/latex/`、`draft_v4/pdf/` | 论文源文件与PDF | V4，时间语义已封版 |
| `draft_v3/latex/`、`draft_v3/pdf/` | 论文源文件与PDF | V3，含两组三维图 |
| `candidate_figures/v3_3d/` | 三维图、网格CSV与哈希清单 | 已并入V3正文 |
| `draft_v1/latex/` | 论文主文件、生成表格 | 已可编译的V1 |
| `draft_v1/pdf/` | 供阅读的PDF | 草稿，有明确限制说明 |
| `candidate_figures/v1/` | 图表源数据索引、矢量图、预览图 | 候选，未作为最终批准图 |
| `legacy_excel/` | result1、2、3、4-2、4-3旧候选副本 | 未重算，未修正模板映射 |
| `review/` | 验收证据与版本整理记录 | 供内部复核 |
| `final_submission/` | 以后只放最终论文与五份正式Excel | 当前不放任何候选结果 |

`analysis/` 是可追溯的实验档案，`outputs/` 是旧模板写入与回读证据；二者保留原路径，避免移动后破坏源文件哈希、脚本及文档链接。无需再从这些目录寻找当前论文入口。数据、源码、测试和运行环境均保留。

## 本稿选用结果

Q1采用真实代表日优化；Q2采用B2（15,137,987.06元）；Q3采用裕量零点固定（15,129,676.16元）作为简单主候选，同时报告门控较低的实测费用15,122,320.83元。年度范围为2025-02-01至12-31，共334天。应急费已经包含5倍系数。

Q4已完成严格迁移：result4-2对应方案15,829,022.52元，result4-3裕量零点固定15,822,900.47元；旧执行器的历史数字不再引用。右端采样物理区间与官方Excel表头的一格差异已按 `interval-end-v1` 定案为按位置回填，但尚未用本稿新策略重导出Excel。文献库没有整库引入，正式综述与来源核验待补。

## 从项目根目录重建

```sh
rtk proxy .venv/bin/python scripts/paper/build_assets.py
rtk proxy .venv/bin/python scripts/paper/build_pdf.py
```

编译依赖现有 XeLaTeX、latexmk 和项目 Matplotlib、NumPy。图表/表格构建不运行优化，不改已有数值。编译中间产物进入 `tmp/paper_v1_build/`，不混入交付目录。根目录的生成脚本为源文件，不能当临时文件删除。

时间采样与日界映射已封版，第四问严格迁移已完成。下一版封版前：按封版口径同策略生成五份Excel；核验引用和竞赛格式；完成论文、表格与账本一致性验收。这里的 `final_submission/` 仅用于已通过上述检查的正式产物。
