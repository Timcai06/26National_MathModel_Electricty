# Q1 候选 Excel 与回读

2026-09-11：合成候选文件已生成，158个数值单元格回读通过，项目55项测试通过。真实Q1和Gate 2未完成。

## 文件与口径

最终候选为 `outputs/q1_candidate_20260911/result1_synthetic_candidate.xlsx`，使用此前 `seeded_variable_day` 的优化结果。它与论文表格、运行图共享 `analysis/q1_tables/tables.json`，没有重新求解、读取或清洗原始数值附件。

工作簿保留官方两个工作表、所有原标签、格式和列宽。只填入以下单元格，单位均为kWh：

| 工作表 | 区域 | 含义 |
| --- | --- | --- |
| 计划购电量 | B2:B145 | 144槽母线侧购电量 |
| 充放电量 | B2:C7 | 六个四小时段母线侧充放电量 |
| 充放电量 | E2:E3 | 起始、结束储电量 |

全天费用仍在论文表格证据中，模板没有该字段，未增设列。购电量沿用模板四位小数显示格式，底层保留未舍入数值；储能页沿用General格式。

## 未解决的时间语义

本次必须显式传入 `endpoint-positional-v0.1-candidate`，且只接受synthetic输入。例：物理10:00–10:10对应slot 60，按原位置写B62，原模板标签为10:10–10:20。未重命名或移动标签，未把两者宣称为同一物理区间。

文件名明确标记synthetic候选；[payload.json](../../outputs/q1_candidate_20260911/payload.json)保存144行物理时间、模板标签、目标单元格和10分钟偏移。`semantic_acceptance`始终为false。**本文件不能作为竞赛结果提交。** 正式输出需要接收独立时间映射与真实数据，并另外落实真实数据输出接口。

## 实现与验证

[Python接口](../../src/q1/excel.py)负责物理复核、版本/表格一致性、单元格映射和只读回读；[运行入口](../../scripts/run_q1_excel.py)负责准备和记录证据。JS构建器用随附的artifact-tool导入官方模板并填写数值，随后导出。

实际导出检查发现artifact-tool丢失字体族、字符集及主题字体属性。为保留模板，补充封装步骤将库实际导出的数值节点移入原模板包。该步骤不重新计算数值、不改变其他文件部件；原工作表XML仅更新目标数值，缺省单元格按列顺序插入。openpyxl只用于读取和校验，不用于写入。

[回读报告](../../outputs/q1_candidate_20260911/readback.json)确认：158个目标值逐格差异小于1e-6，全天购电与分段充放电汇总一致；工作表名称、顺序、维度、标签、非目标值和单元格样式保持；模板SHA-256不变，工作表以外的ZIP部件字节完全一致。结果文件、数据源和实现代码均记录哈希。

新增7项测试覆盖完整映射、最终文件、拒绝真实输入/未明确策略、过期表格/版本、空白输出、数值/标签篡改和模板哈希变化。全部55项测试通过。最终文件重新导入后查看两张表的渲染，包含购电首尾及非零值区域，数字可读。未在桌面Excel中人工验收。

## 复现

项目Python环境安装 `requirements-excel.txt`。JS使用运行时自带node及artifact-tool；输出目录下的node_modules是运行时依赖的软链接，不是新增项目依赖。以下命令按顺序执行，`node`应指向该运行时的node可执行文件：

```sh
rtk proxy .venv/bin/python scripts/run_q1_excel.py prepare
rtk proxy node outputs/q1_candidate_20260911/build_candidate.mjs
rtk proxy .venv/bin/python scripts/run_q1_excel.py finalize
rtk proxy node outputs/q1_candidate_20260911/build_candidate.mjs --readback
rtk proxy .venv/bin/python scripts/run_q1_excel.py verify
rtk proxy .venv/bin/python -m unittest discover -s tests -q
```

本轮最终finalize、verify、绘制和测试命令均退出0。保真封装前的格式检查曾失败，已修复后重新校验。

下一步：接收队友的标准化数据、单位说明和独立时间契约，复核Gate 0与模型假设后，完成真实Q1闭环。不代队友整理原始数据。

## 真实候选Excel更新（2026-09-11）

[真实Q1候选Excel及映射说明](Q1_REAL_EXCEL.md)已交付：158个数值回读通过，原模板标签及格式保留，最终保存文件渲染已查看，全项目90项测试通过。此前“真实Excel待生成”由本记录更新；时间语义与假设仍待验收。当前1/4题有真实候选解、0/4题最终验收，Gate 2未正式通过。下一项是Q2真实数据接入与因果预测回测准备。
