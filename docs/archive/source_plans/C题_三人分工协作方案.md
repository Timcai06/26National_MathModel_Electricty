# 2026 数学建模国赛 C 题三人分工协作方案

> 题目：微网与外部电网电力调控策略  
> 团队规模：3 人  
> 核心原则：**主模型不拆散，数据工作并行推进，所有人从现在同时开工。**

---

# 1. 总体分工原则

本题四问存在明显递进关系：

- Q1：确定性计划购电与储能调度；
- Q2：加入实际负载 / 光伏偏差与紧急购电；
- Q3：加入 0:00、6:00、12:00、18:00 的光伏预测更新与购电调整；
- Q4：进一步加入波动电价。

因此不采用“每人负责一道题”的拆法。

否则容易出现：

- 四问符号体系不统一；
- SOC 状态转移定义不一致；
- 充放电效率处理不同；
- 费用函数重复或冲突；
- 最终 LaTeX 很难统一；
- Q2–Q4 无法顺畅复用 Q1 的优化内核。

本组采用：

> **1 名主建模者 + 1 名数据加工者 + 1 名数据审计 / 资料支持者**

其中核心模型、核心代码、官方 result 文件、图表和 LaTeX 全部由 Tim 统一掌握。

---

# 2. 三人角色

## 2.1 Tim —— 主建模 / 主开发 / 论文负责人

### 核心职责

Tim 负责所有会影响模型正确性和论文主线的工作：

1. 四问统一数学框架；
2. Q1–Q4 数学模型建立；
3. 储能状态方程；
4. 能量平衡约束；
5. 目标函数；
6. 充放电效率和 SOC 边界处理；
7. 是否使用 LP / MILP；
8. Q2 预测方法与风险模型；
9. Q2 紧急购电机制；
10. Q3 Rolling Horizon / MPC；
11. Q3 购电调整费用；
12. Q3 是否采用 6:00 / 12:00 / 18:00 预报的判断逻辑；
13. Q4 波动电价推广；
14. 全部核心 Python 代码；
15. 全部官方 `result*.xlsx`；
16. 全部论文图表；
17. LaTeX 主文档；
18. 最终结果解释；
19. 最终模型选择；
20. 最终论文封版。

### Tim 不等待组员数据完成

Tim 从比赛开始即进入主线开发：

```text
模型假设
  ↓
统一符号
  ↓
储能模型
  ↓
Q1
  ↓
Q2
  ↓
Q3
  ↓
Q4
```

组员处理的数据后续通过统一接口接入，不允许模型开发依赖某个 Excel 清洗工作完成后才能继续。

---

## 2.2 组员 A —— 数据加工负责人

### 定位

> 把官方附件中的原始 Excel 整理成稳定、统一、可直接被程序读取的数据。

组员 A **不负责建立模型，不决定算法，不修改目标函数**。

### 主要任务

#### A1. 原始附件结构梳理

整理附件 1–4：

- 文件包含哪些 sheet；
- 每行表示什么；
- 每列表示什么；
- 时间粒度；
- 单位；
- 日期范围；
- 数据行数；
- 是否存在特殊格式。

输出：

```text
docs/data_dictionary.md
```

---

#### A2. 时间轴标准化

统一将一天划分为：

\[
t=0,1,\ldots,143
\]

每个时间段长度：

\[
\Delta t=10\text{ min}=\frac{1}{6}\text{ h}
\]

统一建立：

```text
date
slot
start_time
end_time
```

例如：

```text
slot = 0   -> 00:00-00:10
slot = 1   -> 00:10-00:20
...
slot = 143 -> 23:50-24:00
```

---

#### A3. 单位统一

原始负载、光伏功率等若为 kW，则统一额外生成 kWh：

\[
E=P\Delta t=P/6
\]

标准字段：

```text
load_kw
load_kwh
pv_kw
pv_kwh
```

原则：

> 后续优化程序内部尽量直接使用 kWh，不允许在不同模块重复做单位换算。

---

#### A4. 数据清洗

检查并整理：

- 缺失值；
- 重复日期；
- 重复时间点；
- 一天是否完整包含 144 个点；
- 非法负数；
- 时间断点；
- 日期排序；
- 数值格式；
- Excel 合并单元格或特殊格式。

输出：

```text
docs/data_quality_report.md
```

---

#### A5. 附件 3 光伏预测数据重建

附件 3 需要整理为标准长表：

```text
date
issue_time
target_time
forecast_horizon
pv_forecast_kw
```

其中：

```text
issue_time ∈ {00:00, 06:00, 12:00, 18:00}
```

要求：

- 每条预测必须对应明确的发布时间；
- 每条预测必须对应明确的目标时间；
- 不依赖原 Excel 中可能存在歧义的合并格式；
- 能够被代码直接通过日期 + 发布时间调用。

---

#### A6. 生成标准化数据文件

最终整理成：

```text
data/processed/
├── day_base.csv
├── annual_actual.csv
├── pv_forecast.csv
└── dynamic_price.csv
```

推荐字段如下。

### day_base

```text
slot
start_time
end_time
price
load_kw
load_kwh
pv_forecast_kw
pv_forecast_kwh
```

### annual_actual

```text
date
slot
start_time
load_kw
load_kwh
pv_actual_kw
pv_actual_kwh
```

### pv_forecast

```text
date
issue_time
target_time
forecast_horizon
pv_forecast_kw
```

### dynamic_price

```text
date
slot
price
```

---

# 3. 组员 B —— 数据审计 / 简单统计 / 资料支持

## 定位

> 不建模，不写复杂算法，不画最终论文图，只做简单、机械但能节省主建模者时间的工作。

---

## 3.1 独立检查组员 A 的数据

组员 B 不直接相信 A 的清洗结果。

独立检查：

- 是否 365 天；
- 每天是否 144 个时段；
- 是否存在缺失日期；
- 是否有重复记录；
- 是否有异常空值；
- 是否存在明显不合理负值；
- 光伏夜间值是否异常；
- 附件 3 每日是否包含 0/6/12/18 四次预报；
- 每次预报是否能正确对应未来目标时刻。

输出：

```text
docs/data_crosscheck.md
```

---

## 3.2 基础统计

不需要建模，只统计原始数据。

例如：

### 负载

- 每日平均负载；
- 每日最大负载；
- 每日最小负载；
- 每月平均负载；
- 每月最大负载。

### 光伏

- 每日光伏总量；
- 每日最大光伏功率；
- 每月光伏总量；
- 每月最大光伏功率。

### 电价

- 每日平均价格；
- 每日最高价格；
- 每日最低价格；
- 月度平均价格；
- 峰谷价差。

输出：

```text
analysis/basic_statistics.csv
```

Tim 后续自行决定哪些统计量用于论文、哪些需要画图。

---

## 3.3 光伏预测误差原始表

将附件 3 中预测值与附件 2 中实际光伏值对齐。

生成：

```text
date
issue_time
target_time
forecast_horizon
forecast_kw
actual_kw
error
abs_error
squared_error
```

其中：

\[
error=\hat P-P
\]

\[
abs\_error=|\hat P-P|
\]

\[
squared\_error=(\hat P-P)^2
\]

输出：

```text
analysis/pv_forecast_error.csv
```

不要求 B 自己研究复杂预测模型。

---

## 3.4 简单周期比较

只做机械比较，不作最终模型决定。

例如负载：

\[
|L_{d,t}-L_{d-1,t}|
\]

以及：

\[
|L_{d,t}-L_{d-7,t}|
\]

输出：

```text
analysis/load_lag_comparison.csv
```

用于后续判断：

- 前一天同期是否有参考价值；
- 上周同期是否更稳定；
- 是否值得加入 lag-1 / lag-7 特征。

最终是否使用由 Tim 决定。

---

## 3.5 题目输出要求 Checklist

把题目所有必须提交的内容整理成检查清单。

例如：

```text
Q1
[ ] 表 1
[ ] 表 2
[ ] result1.xlsx

Q2
[ ] 指定日期结果
[ ] 紧急购电结果
[ ] result2.xlsx

Q3
[ ] 计划购电
[ ] 调整购电
[ ] 紧急购电
[ ] 储能结果
[ ] 是否需要其他时刻预报的分析
[ ] result3.xlsx

Q4
[ ] 波动电价下 Q2
[ ] 波动电价下 Q3
[ ] result4-2.xlsx
[ ] result4-3.xlsx
```

输出：

```text
docs/submission_checklist.md
```

---

## 3.6 文献资料整理

搜索和整理以下主题相关文献：

- 微网经济调度；
- 储能优化；
- 日前调度；
- 光伏预测；
- 滚动优化；
- Model Predictive Control；
- stochastic optimization。

每篇只需要记录：

```text
论文题目
作者
年份
来源
DOI / 链接
一句话内容
```

如果方便，额外整理 BibTeX。

输出：

```text
literature/references.md
literature/references.bib
```

最终是否引用、放在哪，由 Tim 决定。

---

# 4. 三人不允许做的事情

## 4.1 组员 A / B 不自行修改模型

禁止未经确认自行决定：

- SOC 方程；
- 电池效率；
- 终端 SOC；
- 目标函数；
- 是否允许同时充放电；
- 紧急购电成本；
- Q3 调整费用；
- Q3 预测更新时间；
- Q4 电价模型；
- 优化器结构。

发现问题时：

> 记录问题 → 发给 Tim → Tim 拍板。

---

## 4.2 不按题号拆模型

禁止：

```text
Tim：Q1
A：Q2
B：Q3/Q4
```

四问必须复用同一套公共模型。

---

## 4.3 不等待

禁止工作流程：

```text
A 数据清洗完成
   ↓
Tim 才开始模型
```

正确流程：

```text
Tim：模型开发
A：数据处理
B：数据审计 / 简单统计
```

三条线从一开始并行。

---

# 5. Tim 当前立即开始的任务

Tim 现在不需要等待任何数据加工任务完成。

立即推进：

## Phase T0：统一符号与假设

确定：

- 时间离散；
- 功率 / 电量单位；
- 储能状态变量；
- 充电量；
- 放电量；
- 外网购电量；
- 紧急购电量；
- 光伏；
- 负载；
- 电价；
- SOC 上下界；
- 充放电效率。

---

## Phase T1：储能公共模型

建立：

\[
E_{t+1}
=
E_t+\eta_c C_t-\frac{D_t}{\eta_d}
\]

并定义：

\[
1200\le E_t\le10800
\]

最大充放电功率：

\[
5000\text{ kW}
\]

转换到 10 min：

\[
5000\times\frac16
=
833.3333\text{ kWh}
\]

---

## Phase T2：Q1 优化器

建立：

\[
\min\sum_t p_tG_t
\]

以及能量平衡、SOC 和充放电约束。

Q1 跑通后形成四问共用 optimization core。

---

## Phase T3：LaTeX 框架

立即建立：

```text
paper/
├── main.tex
├── sections/
│   ├── 01_problem.tex
│   ├── 02_analysis.tex
│   ├── 03_assumptions.tex
│   ├── 04_symbols.tex
│   ├── 05_q1.tex
│   ├── 06_q2.tex
│   ├── 07_q3.tex
│   ├── 08_q4.tex
│   ├── 09_evaluation.tex
│   └── 10_conclusion.tex
└── figures/
```

结果未出来也可以先写：

- 问题分析；
- 模型假设；
- 符号说明；
- Q1 数学模型。

---

# 6. 推荐项目目录

```text
project/
│
├── data/
│   ├── raw/
│   └── processed/
│
├── docs/
│   ├── data_dictionary.md
│   ├── data_quality_report.md
│   ├── data_crosscheck.md
│   └── submission_checklist.md
│
├── analysis/
│   ├── basic_statistics.csv
│   ├── pv_forecast_error.csv
│   └── load_lag_comparison.csv
│
├── literature/
│   ├── references.md
│   └── references.bib
│
├── src/
│   ├── data/
│   ├── core/
│   ├── q1/
│   ├── q2/
│   ├── q3/
│   └── q4/
│
├── outputs/
│
├── result/
│   ├── result1.xlsx
│   ├── result2.xlsx
│   ├── result3.xlsx
│   ├── result4-2.xlsx
│   └── result4-3.xlsx
│
└── paper/
```

---

# 7. 数据接口原则

核心优化代码不得直接依赖官方 Excel 格式。

禁止：

```python
pd.read_excel("附件2.xlsx")
```

散落在优化程序内部。

统一结构：

```text
官方 Excel
   ↓
Data Adapter
   ↓
标准 DataFrame / ndarray
   ↓
Optimization Core
```

因此优化器接口应类似：

```python
solve_q1(
    load,
    pv,
    price,
    initial_soc,
    battery_params,
)
```

而不是让优化器自己解析 Excel。

这样即使组员的数据加工暂时没有完成，Tim 也可以使用测试数组先完成模型。

---

# 8. 工作交接规则

## 8.1 不通过聊天消息交数字

禁止：

> “我算出来平均负载大概是 xxx。”

必须提交文件。

A：

```text
data/processed/
docs/data_dictionary.md
docs/data_quality_report.md
```

B：

```text
analysis/
docs/data_crosscheck.md
docs/submission_checklist.md
literature/
```

Tim：

```text
src/
result/
paper/
```

---

## 8.2 所有中间结果必须可复现

数据处理脚本、统计脚本不要只保存结果。

推荐：

```text
scripts/
├── preprocess_data.py
├── validate_data.py
└── build_statistics.py
```

保证后续发现错误时可以重新生成，而不是人工重新修改 Excel。

---

# 9. 当前三人立即开工任务

## Tim

立即开始：

1. 统一符号；
2. 建立储能状态模型；
3. 建 Q1 优化模型；
4. 建项目代码架构；
5. 建 LaTeX；
6. 先用附件 1 或测试数组跑通 Q1；
7. Q1 完成后直接推进 Q2。

---

## 组员 A

立即开始：

1. 阅读附件 1–4；
2. 写数据字典；
3. 检查日期 / 时间；
4. 检查缺失值与重复值；
5. 建立 `slot=0...143`；
6. 转换 kW / kWh；
7. 重构附件 3；
8. 输出标准化 CSV。

---

## 组员 B

立即开始：

1. 独立检查附件数据完整性；
2. 检查 A 的处理是否正确；
3. 做基础统计；
4. 生成光伏预测误差原始表；
5. 做简单 lag-1 / lag-7 比较；
6. 整理题目提交 Checklist；
7. 搜集基础参考文献。

---

# 10. 最终团队关系

三个人的关系可以概括为：

> **Tim 决定模型为什么这样做。**

> **A 保证模型吃进去的数据是正确的。**

> **B 保证数据处理没有遗漏，并提供基础统计、误差数据和资料支持。**

核心模型不拆分。

核心代码不拆分。

官方 result 不拆分。

最终图表不拆分。

LaTeX 不拆分。

通过这种方式，两位组员承担大量耗时间但低决策风险的工作，同时 Tim 可以从比赛开始立即推进主线，不形成任何等待关系。

---

# 11. 一句话执行原则

\[
\boxed{
\text{模型领先半个阶段，数据并行供给，审计同步跟进}
}
\]

不要等待数据清洗完成再建模。

不要为了平均工作量而拆核心模型。

目标不是三个人“平均做题”，而是三个人共同最大化最终论文质量和完成速度。
