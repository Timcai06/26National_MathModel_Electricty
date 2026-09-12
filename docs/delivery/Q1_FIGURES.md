# Q1 合成结果图

2026-09-11：完成三张全天运行图和一张三策略费用比较图，每张同时保存 PNG 与 SVG。全部来自合成数据，真实 Q1 和 Gate 2 仍未完成。

## 图件

- [手算套利场景](../../analysis/q1_figures/hand_arbitrage.png)：首槽购电100 kWh，末槽放电81 kWh，优化费用50元，对照81元。
- [恒价无光伏场景](../../analysis/q1_figures/flat_no_pv.png)：三策略费用均为1440元，曲线重合属预期。
- [随机变化场景](../../analysis/q1_figures/seeded_variable_day.png)：用于覆盖调度边界的合成输入，不代表真实日负荷或光伏形态。
- [费用对比](../../analysis/q1_figures/strategy_costs.png)：每个场景使用独立、从零开始的纵轴，柱顶标明费用。

SVG 与对应 PNG 同名，位于 `analysis/q1_figures/`。尚未纳入正式论文目录。

## 数据和绘制口径

[绘图脚本](../../scripts/run_q1_figures.py)直接读取[上一轮完整表格证据](../../analysis/q1_tables/tables.json)，不重新求解。逐策略复核物理约束、费用、时间轴及全部表格值，一致后才生成图。此演示入口仅接受 synthetic 数据。

五联图依次展示负载与光伏、三策略购电、优化策略充放电、三策略储电量与上下界、电价。能量序列是每十分钟 kWh，不是 kW；充电画正值，放电画负值，仅改变展示符号。144槽使用阶梯线，145个储电状态画在时段边界上，连接线只辅助阅读。横轴为上海物理时间00:00至次日00:00。

非填充阶梯线不连接零基线，避免午夜出现虚假骤降；充放电轴至少保留正负1.25 kWh范围，不将浮点残差放大成可见调度。保留全部原始结果，不截断或归零。

## 验证

工作目录为项目根目录，绘图和测试命令均退出0；依赖文件安装命令供复现：

```sh
rtk proxy uv pip install --python .venv/bin/python -r requirements-figures.txt
rtk proxy .venv/bin/python scripts/run_q1_figures.py
rtk proxy .venv/bin/python -m unittest discover -s tests -q
```

运行环境已安装 matplotlib 3.11.1，固定在[绘图依赖](../../requirements-figures.txt)。新增4项证据一致性测试，总计48项通过；3场景、9套策略均重新校验。已逐张查看四张PNG，并修正午夜竖线和近零坐标尺度；SVG由同一图对象导出，未独立渲染验收。

[产物清单](../../analysis/q1_figures/manifest.json)记录输入证据哈希、绘图与验证代码哈希、运行环境和8个输出文件哈希。

后续已完成[Q1合成候选Excel与回读](Q1_EXCEL.md)。下一步接收队友标准化数据及时间契约。真实时间映射仍待接收，不能擅自平移官方标签；原始数据整理归队友负责。
