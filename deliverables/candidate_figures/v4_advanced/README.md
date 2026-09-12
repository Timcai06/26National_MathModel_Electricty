# v4 Advanced Candidate Figures

本目录是 2026 国赛 C 题“微网与外部电网电力调控”的候选图件包。它只服务于本轮可视化评审，当前**未进入 `paper/`、未修改论文主文件、未进入最终投稿包**。

## 生成与验证

从项目根目录运行：

```bash
.venv/bin/python scripts/paper/build_advanced_figures.py
.venv/bin/python scripts/paper/verify_advanced_figures.py
```

生成脚本只读取当前审计结果，写入本目录；固定随机种子为 `20260912`。源文件和输出文件的 SHA-256 记录在 `manifest.json`。

## 文件

- `fig01_prediction_consistency.{pdf,svg,png}`：多源预测误差分布、误差状态比例、候选输入 MAE/RMSE 与调度证据卡片。
- `fig02_rolling_mpc_feedback.{pdf,svg,png}`：2025-06-21 的四个滚动决策快照与反馈闭环。
- `fig03_economic_sensitivity.{pdf,svg,png}`：真实 9×9 参数网格的 3D 费用响应面、等高线投影与局部剖面。
- `fig01_prediction_consistency_data.json`、`fig02_rolling_mpc_feedback_data.json`、`fig03_economic_sensitivity_data.json`：对应数据摘要、口径和边界。
- `advanced_figures_montage.png`：便于快速预览的纵向 montage。
- `manifest.json`：源数据/脚本与输出 SHA-256 清单。

## 图 1：数据来源与结论

来源包括：

- `data/processed/team_delivery/annual_actual.csv`：365 天 × 144 槽的真实负荷、实际光伏与统一 `interval-end-v1` 端点标签；
- `analysis/team_delivery/pv_forecast_error.csv`：00:00、06:00、12:00、18:00 发布时刻的真实光伏预测误差；
- `analysis/real_q2_forecast_candidate/result.json`：当前候选口径下前一日/前七日的负荷与光伏 MAE/RMSE；
- `analysis/q2_margin_oracle_v1/result.json`：当前 Q2 B2 候选的 2025-02—12 调度费用与应急购电证据。

真实记录没有“预测状态 → 实际状态”的可回溯转移标签，因此没有绘制 Sankey / Alluvial。A 面改用真实残差分布，B 面使用真实误差的低估/近似/高估分箱；容差仅是“正值实际样本中位数的 2%”的可复现可视化规则，不是模型参数。

核心结论是：当前 Q2 候选选择负荷前七日、光伏前一日，且负荷 MAE 从 `108.3885` 降至 `29.0917 kWh/slot`；但这只证明输入误差统计与选择依据，不能单独证明整套执行策略已完成最终语义验收。

## 图 2：数据来源与结论

来源包括：

- `analysis/strict_q3_transfer_v1/selected_days.json`：真实日 `2025-06-21` 的 `margin_fresh` 严格 Q3 执行、06/12/18 更新、冻结历史承诺、实际 `C/D/G` 与物理诊断；
- `data/processed/team_delivery/annual_actual.csv`：样例日的真实观测；
- `data/processed/team_delivery/pv_forecast.csv` 与 `src/q3/pv.py`：发布式光伏预测及其 piecewise-linear 10 分钟能量转换；
- `analysis/strict_q3_transfer_v1/result.json`：Q3 各对照策略的全年候选汇总。

四个小图只把更新前的实际观测画在历史段，把当时可用的预测画在未来段。历史 `G` 取已执行锁定段；当前 `G` 取该时刻的滚动承诺。底部闭环使用 `FancyBboxPatch`、`FancyArrowPatch`、`annotate` 和 `PathPatch`。

图中使用 `margin_fresh` 是为了展示真实的滚动反馈过程；它明确标注为 Q3 对照，不是当前主候选。当前 Q3 主线仍是 `margin_zero`，不能把本图误读成已选主方案。

## 图 3：数据来源与结论

来源包括：

- `analysis/q2_january_surface_v1/result.json`：真实 9×9 参数网格，81 个节点、2025-01-15—01-31、1377 次日回放；
- `analysis/q2_january_surface_v1/protocol.json`、`validation.json`：参数可用时间、开发窗口、无平滑插值和物理回放验证；
- `analysis/q2_margin_oracle_v1/frozen_selection.json`：冻结候选 `(tau=0.8, scale=1.0)` 与 1 月选择结果；
- `analysis/q2_margin_oracle_v1/result.json`：Q2 B2 的 2025-02—12 当前候选费用。

3D 曲面只连接真实的 81 个节点，同时提供等高线投影；视角固定为 `elev=26, azim=50`，保持凹面朝向读者。观测网格最低点是 `(tau=0.90, scale=0.75)`、17 天总费 `¥929,199.21`；冻结候选 `(0.80, 1.00)` 为 `¥930,672.15`。这些是开发窗口的描述性结果，不是连续参数域的最优性证明。

C 面主动保留“数据不足/未实现”：当前没有同一 `(tau, scale)` 网格的逐月或全年重算，因此不制造“时间 × 参数”热力图，也不对节点做高密度插值。图 3 的 D 面只给出能被当前 CSV/JSON 回溯的局部敏感性与适用边界。

## 证据边界

- 当前主线：Q1 代表日优化、Q2 B2 安全裕量、Q3 裕量零点固定、Q4 严格动态电价迁移。
- 时间口径：`interval-end-v1`。
- `legacy_excel/` 和旧 `outputs/` 没有混入本候选包。
- Q4“价格提前可知”仍是候选假设；Oracle 只作下界/诊断，不是可执行主方案。
- 本目录保持候选状态；本轮不执行 commit、push、merge，也不把图放入论文。
