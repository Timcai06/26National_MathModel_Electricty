# 候选图件总览

本目录管理图表候选包及其可追溯图源，不等同于正式提交材料。`v1`、`v2`、`v3_3d` 中的部分单图已经被当前论文引用，但整套图册仍不自动等于论文批准图件；每个版本目录保留自己的数据摘要、生成说明和 manifest，不互相覆盖。

## 版本状态

| 版本 | 内容 | 状态 | 入口 |
| --- | --- | --- | --- |
| `v1/` | 早期 Q1/Q2/Q3 数据图与来源清单 | `current-mainline` 图源与 `historical` 候选并存；整包 `not-for-submission` | [v1 manifest](v1/manifest.json) |
| `v2/` | 五组科研复合图和研究图册 | 部分单图为 `current-mainline` 图源；图册仍 `candidate-only`、`not-for-submission` | [v2说明](v2/README.md) · [图册](v2/research_figures_v2.pdf) |
| `v3_3d/` | 参数—费用、日内—月份储电量 3D 图与候选图册 | 论文当前引用的单图为 `current-mainline`；图册仍 `candidate-only`、`not-for-submission` | [v3说明](v3_3d/README.md) · [图册](v3_3d/3D_candidate_atlas.pdf) |
| `v4_advanced/` | 多源预测、滚动 MPC、经济敏感性高级复合图 | `candidate-only`、`not-for-submission` | [v4说明](v4_advanced/README.md) · [montage](v4_advanced/advanced_figures_montage.png) |

现有论文是否引用某张图，以 `paper/` 当前源文件和论文交付说明为准；候选目录中的“已出图”不自动获得论文采用资格。当前 `v4_advanced/` 明确不在 `paper/`，也不在 `final_submission/`。

## 使用规则

1. 候选图必须能回溯到同目录的 CSV、JSON、manifest 或其 README 中列出的真实结果来源。
2. 新版本使用新目录，不覆盖 `v1`、`v2`、`v3_3d` 或已审阅文件。
3. 图件进入论文前，必须经过独立审阅并在论文源文件中形成明确引用；仅生成 PDF、SVG 或 PNG 不代表已批准。
4. `legacy_excel/`、旧 `outputs/` 和 Oracle 证据不能被候选图包装成当前可执行主方案。

生成脚本位于 `scripts/paper/`，脚本物理路径保持稳定。高级候选图的生成与复核入口见 [v4_advanced/README.md](v4_advanced/README.md)。
