# Q1真实候选Excel交付

更新：2026-09-11。T2-7完成候选文件生成与技术检查，正式时间语义尚未验收。

## 文件与来源

- [候选Excel](../../outputs/q1_real_candidate_20260911/result1_candidate.xlsx)
- [144槽逐行映射](../../outputs/q1_real_candidate_20260911/slot_mapping.csv)
- [数值与模板回读证据](../../outputs/q1_real_candidate_20260911/readback.json)
- [写入载荷](../../outputs/q1_real_candidate_20260911/payload.json)
- [真实求解报告](../../analysis/real_q1_candidate/result.json)

输入使用队友交付的 `data/processed/team_delivery/day_base.csv`，生成前核对其SHA与求解记录一致，未重新整理原始数据。采用各方向效率0.9、母线侧功率限制、初末储能6000 kWh的主候选；优化费用35126.948589元，较无储能减少26.8981%。效率备选见[对照实验](../experiments/Q1_EFFICIENCY.md)。

## 写入与时间解释

仅填写原模板两个工作表中的158个数值：计划购电量B2:B145、充放电量B2:C7及E2:E3。保留原时间标签、样式、工作表名和其他内容；不添加工作表。

物理输入按区间终点解释，slot 0代表00:00–00:10，却按候选位置契约写入标签为00:10–00:20的B2；slot 60代表10:00–10:10，写入标签为10:10–10:20的B62；slot 143写入B145。CSV逐槽列出物理起止、模板标签和单元格，未暗中平移数据。映射日期2025-01-01仅是代表日锚点，不是附件1已确认的真实日期。

`scope=real-candidate-only`、`semantic_acceptance=false`。文件可供审阅，不能据此宣称官方时间解释已确认或最终提交完成。

## 验证

158个数值与模型结果回读一致，汇总及初末储能核对通过；模板未变、非目标值未变、样式差异为空、非工作表包内容保持一致。最终保存文件重新导入并渲染，已查看购电首段、末段与完整充放电汇总，未发现显示截断或错列。

新增3项测试覆盖真实输入默认拒绝、显式候选导出不升级语义验收、最终文件与模型/模板一致。全项目90项测试通过，命令 `rtk proxy .venv/bin/python -m unittest discover -s tests -q`，退出码0。此目录无Git仓库，验证针对当前工作目录。

复核命令：`rtk proxy .venv/bin/python scripts/run_q1_excel.py verify --real`。构建复用合成输出目录内的 `build_candidate.mjs --real`，随后运行Python的 `finalize --real` 保留原模板包；`--real --readback` 重新导入最终文件检查显示。

## 阶段状态

Q1真实候选已连通三策略、表格、图和Excel；1/4题有真实候选解，0/4题最终验收。Gate 2仍需时间映射及模型假设接收。下一项为Q2真实数据接入：明确数据可用时刻、年初热身和终端规则，再开展因果预测与回测；现有Q2成果仍限于合成验证。
