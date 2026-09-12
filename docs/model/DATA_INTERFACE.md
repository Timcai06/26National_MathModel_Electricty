# 数据适配层与优化内核接口草案

版本：v0.1，2026-09-11。属于 T0-2；整体字段为设计草案；[时间轴模块](../../src/time_axis.py)已实现并测试，公共内核和Q1优化器也已实现；尚无真实标准化数据接入。联读[符号与单位](SYMBOLS_AND_UNITS.md)、[模型假设](MODEL_ASSUMPTIONS.md)、[协作约定](../collaboration.md)。

## 模块职责

- 队友的数据加工：读取原始附件，负责清洗、日期重建、插值、单位/时间标准化，产出候选长表、来源定位和审计说明；tim的助手不承担这些加工任务。
- tim 的适配层：依冻结契约校验唯一键、时间、单位、信息可用性，构造内核输入；不静默修复不合格数据。
- tim 的优化内核：接收带单位的数值对象与明确的策略配置，不解析 Excel、不查询未来实际值。
- 因果执行器：拿已锁定购电承诺、当前可观测状态及当时允许的数据，记录实际动作与 SOC；与日前预测输入分离。
- writer：通过显式映射填候选模板副本。正式输出工作簿保留题目名称，内部运行日志另存，不写回官方空模板。

## 数据对象

| 对象 | 字段与类型 | 约束 |
| --- | --- | --- |
| SourceRef | `file_sha256: str`, `sheet: str`, `cell: str` | 可以追到真实输入单元格；文件变化则重新核验 |
| SlotMap | `date: date`, `slot_id: int`, `start_time/end_time: datetime`, `input_label/output_label: str`, `input_ref/output_ref: SourceRef`, `mapping_version: str` | 每日144条、槽号0..143；连续且跨日明确；标签原文保留；物理解释尚待冻结 |
| ActualSeries | `date`, `slot_id`, `load_kw/load_kwh`, `pv_actual_kw/pv_actual_kwh`, `observed_at`, `available_at` | 主键(date,slot_id)；kWh与kW/6一致；可用时刻规则显式，不把全年实际对象传进计划器 |
| ForecastSeries | `issue_time`, `target_time`, `horizon_hours`, `pv_forecast_kw`, `source_ref` | 主键(issue_time,target_time)；原始h为1..24；无日期的记录不能接收 |
| ForecastSlots | `issue_time`, `date`, `slot_id`, `pv_forecast_kwh`, `interpolation_method`, `boundary_policy`, `mapping_version` | 常数/线性保留方法标记；转换不引用未来实际值 |
| PriceSeries | `date`, `slot_id`, `price_yuan_per_kwh`, `available_at`, `knowledge_policy` | Q1–Q3静态轨迹与Q4动态轨迹分开；先核验数值正负，不默认所有价格正 |
| BatteryParams | `capacity_kwh=12000`, `min_energy_kwh=1200`, `max_energy_kwh=10800`, `max_charge_kw=5000`, `max_discharge_kw=5000`, `charge_efficiency`, `discharge_efficiency`, `power_reference_side` | 效率/测量侧来自假设配置，不隐藏在代码常量里 |
| PolicyConfig | `terminal_policy`, `initialization_policy`, `settlement_policy`, `adjustment_reference`, `price_knowledge_policy`, `recourse_policy` | 必填，无静默默认；记录假设文档版本 |

CSV的日期和时刻用明确格式；接口内用完整日期时间及统一本地时区约定，不只传“6:00”。未知值不填0；元/kWh与kWh分别传入，避免元/kW或重复乘Δt。

## Q1 纯计算接口

已实现于[solve.py](../../src/q1/solve.py)：

```python
solve_q1(
    *, load_kwh, pv_forecast_kwh, price_yuan_per_kwh,
    initial_energy_kwh, battery_params, slot_ids, input_metadata,
    mode="auto", time_limit_seconds=30,
)
```

前三个数组长度必须为144，值有限且非负；`slot_ids`必须为0..143原顺序，拒绝自动排序。`input_metadata`必须含非空的`input_kind`（synthetic/standardized）、`data_version`、`mapping_version`和`assumptions_version`。这些字段追踪上游契约，不能凭元数据宣称已核验时间语义；完整时间映射由队友交付并在接口接收时审查，不由优化器重建。

`BatteryParams`显式要求充/放电效率与功率侧（bus/battery），Q1固定10分钟槽和终端等于初始储电量，禁用紧急购电。初始储电量不能省略后每日默认为6000。

返回`SolveResult`包含状态、后端、消息、目标费用、G/C/D/U/W数组、145个E、独立物理诊断、LP/MILP尝试日志和版本元数据。只有状态optimal且验证通过时返回策略；limit/infeasible/unbounded/solver_error/validation_failed均不返回伪造零数组或未验收策略。有限时未最优的候选暂不暴露给交付流程。

无储能基线按输入直接计算，作为独立费用上界。规则基线与`compare_q1_strategies`已实现，比较用相同的输入参数和物理校验；Q1合成候选Excel与回读已实现，正式输出语义仍待接收。复现见[合成验证](../validation/CORE_Q1_SYNTHETIC.md)。

## Q2/Q3 承诺与执行日志

每条调整事件至少记录：`decision_time`、`target_date`、`slot_id`、`old_commitment_kwh`、`new_commitment_kwh`、`delta_plus_kwh`、`delta_minus_kwh`、定价/退费所用价格与依据、`incremental_cost_yuan`、`forecast_issue_time`、假设版本。

- 0点原计划不可被覆盖；`current_commitment` 随事件更新。
- 每个实际槽记录实际可用光伏、负载、最终承诺、实际C/D/U/W、起止储电量。
- 累计费用=初始计划费+逐次合法调整的净费用+紧急购电费；不能额外再收一次最终承诺全价。
- 执行日志与预测误差表隔离；按当前观测修正不等于用当天未来实测优化。
- 多次更新仅覆盖尚未执行且允许调整的合同槽位。跨日预测不自动扩大合同修改范围。

## A/B 交付接收条件

A 同时交数据、生成脚本、字段/单位说明和时间映射候选；B 独立比对源数据。必须证明：全年日期完整且无重复；负载/光伏/价格键一致；附件3每日4次×24步完整；两种转换有边界规则；结果日期334天；模板动态块展开规则明确。

上述是队友交付后的接收要求，不是当前已完成检查。我们仅校验交付对象与契约，不重做原始加工。当前模型设计见[公共内核](MICROGRID_CORE.md)与[Q1模型](Q1_MODEL.md)；Q1简单模型要求非负价格，负价格需退回模型适用性讨论，不静默改值。

## Q2 已实现的首版接口

见[Q2预测与回测接口](Q2_FORECAST.md)：ActualDay、history_as_of、predict_day、walk_forward及plan_from_forecast。当前按整日可用时间截断，严格拒绝未来数据、缺失历史不补零；调度仅生成预测下的计划，不计算实际执行成本。
