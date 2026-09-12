# 运行入口索引

所有脚本从项目根目录执行，例如 `.venv/bin/python scripts/run_real_q1.py`。脚本对题面、附件和官方模板**全程只读**，读取前后校验哈希；结果写入 `analysis/` 或 `outputs/` 的独立目录，不覆盖既有证据。

按职责分五组。带"复核"的脚本独立重算，不复用被检查脚本的中间量。

## 一、时间语义与数据核验

| 脚本 | 作用 |
| --- | --- |
| `run_time_semantics.py` | 从官方文件重建时间证据链，跑积分规则敏感性与代表日四口径重解，产出 `analysis/time_semantics_v1/` |
| `verify_time_semantics.py` | 独立复核时间契约的34项断言，不读取上一脚本的数值 |
| `audit_time_axis.py` | 全量核对576个输入标签与1008个输出标签，导出144槽映射 |
| `compare_time_integration_conventions.py` | 早一轮的积分口径对照，含年度无储能费用差 |
| `audit_team_delivery.py` | 队友四份标准化CSV的接收审计与源值逐项比对 |
| `inspect_source_headers.py` | 九份原始工作簿的结构与表头记录 |

## 二、第一问

| 脚本 | 作用 |
| --- | --- |
| `run_real_q1.py` | 附件1代表日三策略求解、论文表格与图件（**主候选**） |
| `run_q1_comparison.py`、`run_q1_tables.py`、`run_q1_figures.py` | 策略比较、表格提取、图件的独立入口 |
| `run_q1_efficiency.py` | 两种效率解释的对照 |
| `run_q1_excel.py` | 第一问候选Excel的 prepare / finalize / verify 三段流程 |
| `run_synthetic_q1.py` | 合成闭环回归 |

## 三、第二、三问

| 脚本 | 作用 |
| --- | --- |
| `run_q2_margin_oracle.py` / `verify_q2_margin_oracle.py` | 安全裕量四方案与两种Oracle（**主候选**）及其独立复核 |
| `run_strict_q2.py` / `verify_strict_q2.py` | 第二问严格因果执行的全年回放与复核 |
| `run_strict_q3.py` / `verify_strict_q3.py` | 第三问六组严格迁移与复核（**主候选**） |
| `run_q3_voi.py` / `verify_q3_voi.py` | 预期净收益门控与其1257次决策复核 |
| `run_real_q2_forecast.py` | 预测基线与可用时刻敏感性 |
| `run_q2_execution.py`、`run_q2_multiday.py`、`run_synthetic_q2.py` | 执行器、多日协调与合成场景的开发期入口 |
| `run_real_q23.py` / `verify_real_q23.py` / `deliver_real_q23.py` / `plot_real_q23.py` | 早期真实Q2/Q3闭环、复核、Excel交付与绘图（历史口径） |

## 四、第四问

| 脚本 | 作用 |
| --- | --- |
| `run_strict_q4.py` / `verify_strict_q4.py` | 动态电价严格迁移与其2672天复核（**主候选**） |
| `run_real_q4.py` / `verify_real_q4.py` / `plot_real_q4.py` | 早期动态电价重算、复核与绘图（历史口径，已被严格迁移取代） |

## 五、论文与交付构建（`scripts/paper/`）

| 脚本 | 作用 |
| --- | --- |
| `build_assets.py` | 生成论文数值表与V1数据图；不运行优化，不改已有数值 |
| `build_research_figures.py` / `verify_research_figures.py` | V2五组科研组图及其数据绑定复核 |
| `build_3d_surface.py` / `build_soc_3d.py` | 参数—费用响应面与日内—月份储电量曲面 |
| `build_advanced_figures.py` / `verify_advanced_figures.py` | V4高级复合候选图的生成与数据边界复核；只写入 `deliverables/candidate_figures/v4_advanced/` |
| `build_q4_tables.py` | 由已复核的第四问结果生成论文表格；缺少有效复核时直接失败 |
| `build_pdf.py` | 编译 `paper/latex/main.tex`，中间产物进 `tmp/paper_build/`；论文只有一份，无版本参数 |
| `package_delivery.py` / `verify_delivery.py` | 审阅包打包与交付清单校验 |

`scripts/deliver_strict_excel.py`（在 `scripts/` 根下）由已复核的轨迹写出五份官方结果表，逐格回读；缺少有效复核时直接失败。

当前论文只使用 `paper/latex/main.tex` 和 `paper/pdf/C_microgrid.pdf`，图表原位更新，历史由 Git 保存。

- `reproduce_paper_q1.py`：读取已核验输入，直接复现代表日费用与物理约束。
- `paper/build_review_figures.py`：生成当前正文引用的五张图。
- `paper/verify_review_paper.py`：复核当前论文数据与排版日志，覆盖更新 `deliverables/review/paper_validation.json`。
- `paper/package_classmate.py`：将当前论文源码、引用图、建模代码和输入数据导出到固定临时路径 `tmp/export/C_microgrid_source_code.zip`；不复制 PDF，不生成版本编号文件，不将导出包纳入 Git。

## 六、仓库目录治理

| 脚本 | 作用 |
| --- | --- |
| `verify_repository_layout.py` | 只读检查根目录允许项、保护区路径、候选图状态、历史审阅包归档、论文隔离和 tracked 缓存；不导入模型、不运行优化、不写文件 |

该检查器用于确认目录治理没有改变模型、论文、数据和实验证据的物理路径。

## 常用序列

```sh
.venv/bin/python -m unittest discover -s tests    # 130项回归
.venv/bin/python scripts/verify_time_semantics.py # 时间契约34项断言
.venv/bin/python scripts/verify_strict_q4.py         # 第四问2672天复核
.venv/bin/python scripts/deliver_strict_excel.py     # 五份结果表
.venv/bin/python scripts/paper/build_pdf.py         # 论文
```
