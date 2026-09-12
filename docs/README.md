# C 题项目文档

本目录归档 C 题的执行、建模、实验、验证与交付文档。四题均有真实候选，130 项测试通过。**技术时间口径已封版**为 `interval-end-v1`，见[封版记录](data/TIME_SEMANTICS.md)；官方表头、观测与计费语义的最终接收仍待完成。

全项目目录分类见[项目地图](../PROJECT_MAP.md)，实验档案见[实验索引](../analysis/README.md)，运行入口见[脚本索引](../scripts/README.md)。

## 导航

- [当前任务板](current_tasks.md)：tim、A、B 第一轮任务、依赖和真实状态。
- [三人协作与交接](collaboration.md)：职责、接口、归档和源方案冲突处理。
- [分阶段执行计划](plan.md)：Phase 0–10 的目标、任务、阶段产物、依赖与 Gate。
- [数据与时间契约](data/README.md)：数据审计、时间轴、单位和输入输出映射。
- [模型定义](model/README.md)：题意假设、符号、约束和各问题模型。
- [实验记录](experiments/README.md)：基线、回测、敏感性、消融与图表数据。
- [验证证据](validation/README.md)：Gate、测试、数据泄漏和物理一致性检查。
- [交付说明](delivery/README.md)：官方 Excel、论文、图表和最终复核。
- [论文提纲](delivery/PAPER_OUTLINE.md)：正文结构与结果索引（原 `paper/OUTLINE.md`）。

## 归档约定

1. 原始题目、附件和官方模板保持只读，不移入 `docs/`。
2. 审计结果与模型假设分开记录；计划中的陈述不自动视为已验证事实。
3. 每份结论文档应注明数据范围、运行入口、验证方式和未核验边界。
4. 阶段只有在对应 Gate 的证据齐全后才能标记完成。
5. 执行范围随 tim 授权更新，当前已推进到 Q4 严格迁移和五份官方结果表技术交付；技术完成与正式语义验收分别记录。
6. 总路线见 `plan.md`，协作约定见 `collaboration.md`，当前任务状态见 `current_tasks.md`；源方案保留作为依据。

计划来源：[C题_分阶段建模执行计划.md](archive/source_plans/C题_分阶段建模执行计划.md)。

协作来源：[C题_三人分工协作方案.md](archive/source_plans/C题_三人分工协作方案.md)。

已交付：[Q1论文表格提取](delivery/Q1_TABLES.md)，仅合成技术验证，真实结果待队友标准化数据与时间契约。

已交付：[Q1合成结果图](delivery/Q1_FIGURES.md)，4张图及PNG/SVG版本，48项测试通过。

已交付：[Q1合成候选Excel与回读](delivery/Q1_EXCEL.md)，158个单元格通过，55项测试通过。时间语义仍待验收。

已提前开发：[Q2因果预测与回测](model/Q2_FORECAST.md)，合成验证通过，项目67项测试通过；真实Q2与Gate 3未验收。

已提前开发：[Q2因果执行与结算](model/Q2_EXECUTION.md)，4组合成场景与76项测试通过；真实Q2和Gate 4未验收。

已提前开发：[Q2连续多日协调比较](model/Q2_MULTIDAY.md)，热身24天、评价14天，项目84项测试通过。

最新：[队友交付接收与质量评价](validation/TEAM_DELIVERY_REVIEW.md)；核心CSV已到并核对通过，缺陷和阶段接收范围见报告。

最新：[真实Q1候选结果](experiments/Q1_REAL_CANDIDATE.md)：三策略、表格与图已出，早期 87 项测试通过；最终验收待完成。该记录保留当时阶段状态。

已完成：[Q1效率解释比较及输出口径](experiments/Q1_EFFICIENCY.md)，保留主候选与敏感性对照，不以低费用反推题意。

## 当前交付

[Q2/Q3真实模型与费用结果](experiments/Q23_REAL_RESULTS.md)；[两题候选Excel及字段口径](delivery/Q23_EXCEL.md)。上方早期交付记录保留为历史，当前状态见任务板。

[Q4真实动态电价结果](experiments/Q4_REAL_RESULTS.md)与[两份候选 Excel](delivery/Q4_EXCEL.md)已完成；当前 4/4 题有真实候选、五份官方结果表已按当前策略重导，0/4 最终语义验收。

## 当前文档口径

- `current_tasks.md` 是当前进度快照；其下的旧轮次文字只作为历史证据保存。
- `validation/GATE_STATUS.md` 区分技术候选闭环与最终人工/竞赛验收，不因文件生成而自动通过 Gate。
- `deliverables/README.md` 与 `deliverables/final_submission/README.md` 是当前结果表、论文和历史产物的交付入口。
