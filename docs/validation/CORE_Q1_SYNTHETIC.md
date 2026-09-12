# 公共内核与 Q1 合成验证

日期：2026-09-11。工作区：`/Users/tim/School/数模/数模26国赛`。本轮只实现模型与合成验证，未读取原始附件、清洗数据、运行年度回测或填写官方结果。

## 当前结论

- 公共约束构建器、独立物理校验器及 LP/MILP 求解路径已实现。
- Q1 的144槽求解接口已实现，并在合成数据上实际运行。
- **27项测试全部通过：19项模型/求解测试，加已有8项时间轴测试。** 其中一个测试包含4个固定种子的144槽日案例。
- Phase 1 的已列物理功能完成合成技术验证；Gate 0、真实数据接收和主假设冻结仍未完成，因此不宣称整个阶段链已放行。
- **真实竞赛题仍完成0/4问**；Q1尚缺队友标准化数据接入、真实策略比较、Excel输出与论文结果。

## 实现入口

| 文件 | 责任 |
| --- | --- |
| [model.py](../../src/core/model.py) | 构造稀疏能量平衡/SOC矩阵、动作/状态边界、终端与承诺约束、互斥变量 |
| [validation.py](../../src/core/validation.py) | 独立按物理方程重算残差与边界，不复用组装矩阵假装独立验证 |
| [solver.py](../../src/core/solver.py) | LP优先、必要时MILP重求解；验证状态、费用和结果，不事后修补动作 |
| [Q1接口](../../src/q1/solve.py) | 强制144槽、日中性、输入版本信息及无储能基线核对 |
| [模型测试](../../tests/test_microgrid.py) | 手算对照、边界、随机合成日、失败状态与回退路径 |
| [合成演示](../../scripts/run_synthetic_q1.py) | 自行构造数组，写出明确标记synthetic的证据 |

接口接受kWh数组，不自动转换功率、不排序、不补空值、不插值。Q1接收`slot_ids`与映射版本作为交接契约标识，不宣称凭槽号已证明实际时间含义。效率与功率侧显式传入；原始数据处理仍归队友。

## 运行环境与复现

本次环境：Python 3.12.13，NumPy 2.5.3，SciPy 1.18.1。依赖在项目`.venv`，版本固定于[requirements-core.txt](../../requirements-core.txt)。

```sh
rtk proxy uv venv --python 3.12 .venv
rtk proxy uv pip install --python .venv/bin/python -r requirements-core.txt
rtk proxy .venv/bin/python -m unittest discover -s tests -v
rtk proxy .venv/bin/python scripts/run_synthetic_q1.py
```

已有`.venv`无需重复创建。测试和演示最终退出码均为0。求解接口采用 SciPy 的 [linprog](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.linprog.html) 与 [milp](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.milp.html)，分别构造LP和含二元互斥变量的MILP；无求解状态成功证据时不返回可提交策略。

## 真实执行的合成案例

144槽，负载仅末槽81 kWh，光伏全部0；第0槽电价0.5元/kWh，其余槽1元/kWh；初始/终端6000 kWh，单向效率各0.9，母线侧功率上限5000 kW。

| 指标 | 实际结果 |
| --- | --- |
| 求解状态/后端 | optimal / highs_lp |
| 购电费用 | 50.000000元 |
| 无储能基线费用 | 81.000000元 |
| 费用差 | 31.000000元 |
| 最大母线残差 | 0 kWh |
| 最大SOC转移残差 | 0 kWh |
| 终端残差 | 0 kWh |
| 同时充放电槽 | 0 |

完整数组、输入、配置、求解日志及代码摘要在[合成结果JSON](../../analysis/synthetic_q1/result.json)。数值不得写入真实题目结果或论文实证表。

## 测试覆盖与边界

1. 两槽手算最优值50元、效率损耗和小价差不套利；144槽版本也求得50元。
2. 无光伏、光伏富余、不售电、SOC上下界、母线/电池侧功率界。
3. 固定与自由终端、不可达终端、固定购电承诺、紧急购电开关。
4. 真实MILP求解；另注入一个在零价格下合法且最优的同时充放电LP解，验证自动回退调用真实MILP。此项是确定性路径测试，不是声称实际LP总会产生该解。
5. 篡改状态/NaN被独立校验器拒绝；模拟时间限制返回明确limit，不输出未验证数组。
6. 4个固定种子的合成日均与独立无储能基线和整日守恒式核对。

首次测试中，对自由终端误设了唯一终值5900的断言；实际模型允许无价富余，多个终值可同价最优。已改为核验费用、可行性和状态守恒。没有改变模型以迎合测试。自由终端内核不是完整跨日经济策略，后续仍需末端价值/策略规则。

后续规则基线已实现，最新37项测试和三策略结果见[比较记录](../experiments/Q1_BASELINES.md)；本文27项为初次内核验证记录。年度预测/MPC、Excel writer与论文图表尚未实现。合成结果也不证明队友时间映射正确、原始数据无泄漏或实际Q1已有收益。
