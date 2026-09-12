# 第2、3题候选Excel交付

2026-09-11。来源与完整模型见[真实结果报告](../experiments/Q23_REAL_RESULTS.md)。

## 文件及范围

- [第2题候选文件](../../outputs/q23_candidate_20260911/result2_candidate.xlsx)
- [第3题候选文件](../../outputs/q23_candidate_20260911/result3_candidate.xlsx)
- [全量回读报告](../../outputs/q23_candidate_20260911/readback.json)
- [第2题144槽映射](../../outputs/q23_candidate_20260911/slot_mapping2.csv)
- [第3题144槽映射](../../outputs/q23_candidate_20260911/slot_mapping3.csv)

两份文件均覆盖2025-02-01至12-31共334天，每天144槽。保留原工作表名、购电表全部日期和时间标签；将充放电表的省略示例展开为334个六行日块，将紧急购电表展开为全部连续非零区间。原模板文件未改动。

## 字段口径

| 工作表/字段 | 第2题 | 第3题 |
| --- | --- | --- |
| 计划购电量 B:EO | 零点计划承诺 | 零点初始承诺 |
| 计划购电量 EP | 零点计划量合计，不含紧急购电 | 零点初始承诺合计 |
| 计划购电量 EQ | 含紧急购电的实际日总费用 | 零点原计划费用 |
| 调整购电量 B:EO | 无此页 | 每槽最终适用的承诺量，不是增减差额 |
| 调整购电量 EP | 无此页 | 最终承诺量合计，不含紧急购电 |
| 调整购电量 EQ | 无此页 | 原计划费+逐次调整净费用+紧急费，即实际日总费用 |
| 充放电量 | 实际执行的六个4小时合计，以及初末储能 | 同左 |
| 紧急购电量 | 同日连续非零槽合并，无紧急购电日填写“无”、0 | 同左 |

上述EQ及“调整购电量”的口径是候选输出解释，写在旁置说明中以保持模板原表头。第3题原计划页和调整页费用不能相加。完整分项见 [Q2逐日费用](../../analysis/real_q23_candidate/q2_daily_fees.csv)、[Q3逐日费用](../../analysis/real_q23_candidate/q3_daily_fees.csv)；每次更新的增减差额及账本保存在逐日日志中。

购电表保持模板的原列位置：B对应物理00:00—00:10，但原表头为00:10—00:20；映射CSV逐列披露这一差异。充放电汇总、紧急购电和论文指定时间表均按物理区间。没有平移实际数据，也没有宣称此输出语义已被最终确认。

## 构建与核验

使用官方result2/result3模板由artifact-tool写入数值。导出器不能完整保留字体、边框元数据和扩展日块的格式，因此在所有引擎写入值核验通过后，将引擎生成的sheetData装回原模板包，并按原位置或六行日块继承样式；其余包内容保持原样。未用openpyxl写Excel，openpyxl仅用于读取和独立核验。

第2题54314个、第3题102919个数值全部回读通过；所有日期、文本、表头、矩阵尺寸和模板样式检查通过。最终文件已重新导入，逐页查看首段及年末购电/充放电区域；调整表另单独导入渲染，避免渲染器连续输出时偶发空白图。图像预览不替代上述全量数值校验。

```sh
rtk proxy .venv/bin/python scripts/deliver_real_q23.py prepare
rtk proxy /Users/tim/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node outputs/q23_candidate_20260911/build.mjs
rtk proxy .venv/bin/python scripts/deliver_real_q23.py finalize
rtk proxy /Users/tim/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node outputs/q23_candidate_20260911/build.mjs --readback
rtk proxy .venv/bin/python scripts/deliver_real_q23.py verify
```

`semantic_acceptance=false`。文件是可复查的真实候选结果，不是最终提交授权或题意无歧义的声明。
