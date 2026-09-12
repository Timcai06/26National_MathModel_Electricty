# 第4题候选Excel交付

2026-09-11。模型与费用见[真实结果报告](../experiments/Q4_REAL_RESULTS.md)。

- [Q4-2候选文件](../../outputs/q4_candidate_20260911/result4-2_candidate.xlsx)
- [Q4-3候选文件](../../outputs/q4_candidate_20260911/result4-3_candidate.xlsx)
- [全量回读记录](../../outputs/q4_candidate_20260911/readback.json)
- [Q4-2槽映射](../../outputs/q4_candidate_20260911/slot_mapping4-2.csv)
- [Q4-3槽映射](../../outputs/q4_candidate_20260911/slot_mapping4-3.csv)

两份文件覆盖2025-02-01至12-31共334天，每天144槽。通过 `DeliverySpec` 复用Q2/Q3写入与验证器，新增 `--q4` 选择原result4-2/result4-3模板及独立输出目录；没有覆盖第2、3题已生成文件。

## 字段含义

沿用[Q2/Q3输出契约](Q23_EXCEL.md)：Q4-2计划页为0点承诺，EP为承诺量合计，EQ为含应急购电的实际日总费用；Q4-3计划页保存0点原承诺及原费用，调整页保存各槽最终适用承诺和实际日总费用。两页费用不可相加。充放电页为实际执行的六个4小时合计及初末储能；应急页按同日连续非零槽合并，无应急日填“无”、0。

完整费用分项见 [Q4-2逐日费用](../../analysis/real_q4_candidate/q4_2_daily_fees.csv)和[Q4-3逐日费用](../../analysis/real_q4_candidate/q4_3_daily_fees.csv)。所有价格按对应目标物理槽取值。购电表原标签与物理槽的10分钟差异保留在映射CSV中，未隐式平移输入或改动原模板标签。

## 核验

Q4-2核对54404个数值，Q4-3核对102959个数值，合计157363个；全日期、表头、文本、矩阵尺寸及模板样式回读通过。使用artifact-tool写入；为保留其不能完整导出的模板元数据，沿用已验证的包保真步骤。原始模板和其他题候选文件保持不变。

最终文件重新导入，查看各工作表及年末区域；调整页使用单独区间渲染检查，以绕过渲染器偶发空白预览。图件另生成PNG/SVG并查看。所有数值以全量回读为准，不以局部预览替代。

```sh
rtk proxy .venv/bin/python scripts/deliver_real_q23.py prepare --q4
rtk proxy /Users/tim/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node outputs/q23_candidate_20260911/build.mjs --q4
rtk proxy .venv/bin/python scripts/deliver_real_q23.py finalize --q4
rtk proxy /Users/tim/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node outputs/q23_candidate_20260911/build.mjs --q4 --readback
rtk proxy .venv/bin/python scripts/deliver_real_q23.py verify --q4
```

这些是当日价格提前可知、当前槽可反馈等显式假设下的候选输出，`semantic_acceptance=false`。最终时间、观测、价格和计费语义尚未接收，不等于最终提交验收。
