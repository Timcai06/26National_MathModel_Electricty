# 交付统一入口

## 论文

论文只有一份：[PDF](../paper/pdf/C_microgrid.pdf) · [LaTeX源码](../paper/latex/main.tex)。
历史版本由 git 记录，工作区不再保留 `draft_v1`…`draft_v5` 并行目录。

```sh
.venv/bin/python scripts/paper/build_pdf.py
```

## 五份官方结果表

[final_submission/excel/](final_submission/excel/)：按当前已复核策略重导，每一格写入后立即回读比对，共352,466格。

| 文件 | 采用策略 | 334天总费/元 |
| --- | --- | ---: |
| result1.xlsx | 代表日优化调度 | 35,126.95（单日） |
| result2.xlsx | B2 安全裕量，零点固定合同 | 15,137,987.06 |
| result3.xlsx | 裕量零点固定 | 15,129,676.16 |
| result4-2.xlsx | 动态电价下的B2安全裕量 | 15,829,022.52 |
| result4-3.xlsx | 动态电价下的裕量零点固定 | 15,822,900.47 |

数值与论文正文逐项一致。填写按位置回填，某列的印刷标签比其物理区间晚一格，依据见[时间语义封版记录](../docs/data/TIME_SEMANTICS.md)。来源轨迹、模板与成品的哈希见 `final_submission/excel/manifest.json`。

```sh
.venv/bin/python scripts/deliver_strict_excel.py
```

## 图表

- [V2科研图册（5组、20个子图）](candidate_figures/v2/research_figures_v2.pdf) · [说明](candidate_figures/v2/README.md)
- [两页3D图册](candidate_figures/v3_3d/3D_candidate_atlas.pdf) · [说明](candidate_figures/v3_3d/README.md)
- [V1数据图](candidate_figures/v1/) · [来源哈希](candidate_figures/v1/manifest.json)

## 历史与证据

- [旧五份候选Excel](legacy_excel/)：09-11旧策略产物，**与当前论文不同版本，不得混作提交**。
- [审阅证据摘录](review/)：各轮结果、独立验收、比较表与整理日志。
- [V1审阅包](C_microgrid_review_v1.zip) · [V2审阅包](C_microgrid_review_v2.zip)：历史打包，非提交包。

## 目录职责

| 目录 | 内容 | 当前状态 |
| --- | --- | --- |
| `candidate_figures/v3_3d/` | 三维图、网格CSV与哈希清单 | 已并入V3正文 |
| `candidate_figures/v1/` | 图表源数据索引、矢量图、预览图 | 候选，未作为最终批准图 |
| `legacy_excel/` | result1、2、3、4-2、4-3旧候选副本 | 未重算，未修正模板映射 |
| `review/` | 验收证据与版本整理记录 | 供内部复核 |
| `final_submission/excel/` | 五份官方结果表 | 按当前策略重导，逐格回读通过 |

`analysis/` 是可追溯的实验档案，`outputs/` 是旧模板写入与回读证据；二者保留原路径，避免移动后破坏源文件哈希、脚本及文档链接。无需再从这些目录寻找当前论文入口。数据、源码、测试和运行环境均保留。

## 本稿选用结果

Q1采用真实代表日优化；Q2采用B2（15,137,987.06元）；Q3采用裕量零点固定（15,129,676.16元）作为简单主候选，同时报告门控较低的实测费用15,122,320.83元。年度范围为2025-02-01至12-31，共334天。应急费已经包含5倍系数。

Q4已完成严格迁移：result4-2对应方案15,829,022.52元，result4-3裕量零点固定15,822,900.47元；旧执行器的历史数字不再引用。右端采样物理区间与官方Excel表头的一格差异已按 `interval-end-v1` 定案为按位置回填，五份结果表已按该口径重导。文献库没有整库引入，正式综述与来源核验待补。

## 从项目根目录重建

```sh
.venv/bin/python -m unittest discover -s tests      # 130项回归
.venv/bin/python scripts/verify_time_semantics.py   # 时间契约34项断言
.venv/bin/python scripts/verify_strict_q4.py        # 第四问2672天复核
.venv/bin/python scripts/deliver_strict_excel.py    # 五份结果表
.venv/bin/python scripts/paper/build_pdf.py         # 论文
```

编译依赖 XeLaTeX、latexmk 与项目 Matplotlib、NumPy。中间产物进入 `tmp/`，不混入交付目录。

尚未完成：文献与竞赛格式验收；动态电价下的门控消融。
