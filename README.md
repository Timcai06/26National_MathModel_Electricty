# 2026国赛C题：微网与外部电网电力调控策略

## 入口

- **论文** — [V5 PDF](deliverables/draft_v5/pdf/C_microgrid_draft_v5.pdf) · [LaTeX源码](deliverables/draft_v5/latex/main.tex)
- **图表** — [V2科研图册](deliverables/candidate_figures/v2/research_figures_v2.pdf) · [3D图册](deliverables/candidate_figures/v3_3d/3D_candidate_atlas.pdf)
- **目录总览** — [项目地图](PROJECT_MAP.md)：每个目录装什么、能不能动
- **进度** — [当前任务板](docs/current_tasks.md) · [分阶段计划](docs/plan.md)

## 分类索引

| 索引 | 内容 |
| --- | --- |
| [项目地图](PROJECT_MAP.md) | 全项目五类目录与当前状态 |
| [实验档案](analysis/README.md) | 21个实验目录，按时间核验与四问分类 |
| [运行入口](scripts/README.md) | 30个脚本，按职责分五组 |
| [交付总览](deliverables/README.md) | 论文各版本、候选图、旧Excel与审阅证据 |
| [文档导航](docs/README.md) | 52篇文档，按数据、模型、实验、交付、验收分类 |

## 当前结论

时间语义已封版为 `interval-end-v1`：输入标签是区间终点，模型日为00:00–24:00，功率按右端保持转电量，模板按位置回填。决定性证据是五份官方模板的充放电量页一律铺满00:00–24:00，而购电页整体晚一格，同一文件的两张表不可能都按字面成立。完整推导、积分规则的解析上界与34项独立断言见[封版记录](docs/data/TIME_SEMANTICS.md)。

四问均有真实候选。第一问优化费35,126.95元，较无储能降26.90%；第二问安全裕量方案334天总费15,137,987.06元，较严格基线降8.71%；第三问裕量零点固定15,129,676.16元，门控消融15,122,320.83元，额外收益仅0.0486%；第四问已完成严格迁移：唯一改动价格输入，裕量降幅8.5842%，与固定电价的8.7058%基本一致；新预报重规划仍更贵3.3546%。迁移中发现固定承诺下应急电量与电价无关，裕量因此可零成本迁移。应急费均已含5倍系数。

未完成项：五份Excel同版本重导、文献与竞赛格式验收。五份旧Excel与本稿策略不同版本，**不得混作提交**。

## 环境与回归

```sh
.venv/bin/python -m unittest discover -s tests
```

130项测试通过。依赖见 `requirements-core.txt`、`requirements-excel.txt`、`requirements-figures.txt`；论文编译依赖 XeLaTeX 与 latexmk。
