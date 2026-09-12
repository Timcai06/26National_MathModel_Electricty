# 模型派生输入

本目录保存由已接收标准化数据生成的模型输入，不覆盖队友原CSV。

`pv_10min_candidate.csv`：2026-09-11经tim明确授权由我们完成。1460个发布批次×144个未来10分钟槽=210240行，保留跨年目标，含线性积分与分段常数两版kWh。首小时只使用当次第1小时预报，不引用未来实测。

转换规则及验证见[真实Q2/Q3报告](../../docs/experiments/Q23_REAL_RESULTS.md)，来源与输出SHA见[运行清单](../../analysis/real_q23_candidate/result.json)。由 `scripts/run_real_q23.py` 生成。
