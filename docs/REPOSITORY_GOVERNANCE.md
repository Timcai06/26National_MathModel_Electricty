# 仓库治理与目录边界

> 盘点日期：2026-09-12
> 目标：在不改变模型、论文和数据的前提下，让仓库的职责、状态和历史边界清晰可复核。

## 1. 范围与硬性边界

本文件记录仓库的目录契约和治理操作，不替代模型说明、实验结果或论文结论。治理变更只允许作用于文档、索引、只读检查器，以及已确认没有执行依赖的历史审阅包路径。

以下目录是本轮保护区：

| 路径 | 状态 | 本轮规则 |
| --- | --- | --- |
| `CUMCM2026Problems/` | `immutable-source` | 官方题面、附件和模板，只读，不移动、不改名 |
| `data/` | `canonical-data` | 当前规范化输入，只读保护，不重清洗、不替换 |
| `src/` | `current-mainline` | 模型实现和公共接口保持原路径、原内容 |
| `analysis/` | `supporting-evidence` | 实验目录、哈希路径和逐日证据保持原路径 |
| `outputs/` | `historical` / `supporting-evidence` | 旧模板写入与回读证据保持原路径，不与当前主线合并 |
| `paper/` | `current-mainline` | 唯一论文源文件和 PDF；本轮不修改、不重编译 |

同时不清理 `.workbuddy-ai/`、`.venv/`、`tmp/`、`.pytest_cache/`、`__pycache__/` 或任何被忽略的 JSONL/NDJSON 证据。`.workbuddy-ai/` 是已跟踪的工具元数据，但不属于项目事实来源。

## 2. 统一状态标签

目录 README、治理记录和候选图索引使用以下标签：

| 标签 | 含义 |
| --- | --- |
| `immutable-source` | 不可变的原始题面、附件或官方模板 |
| `canonical-data` | 当前规范化数据入口 |
| `current-mainline` | 当前论文和正式结果使用的主线 |
| `supporting-evidence` | 用于支撑主线判断的可追溯证据 |
| `candidate-only` | 候选图或候选结果，尚未获得正式采用资格 |
| `historical` | 历史版本或旧策略产物 |
| `not-for-submission` | 不得直接放入正式提交包 |
| `regenerable-cache` | 可由既有脚本重建的缓存或中间产物 |

状态来源优先级固定为：

1. `PROJECT_MAP.md`；
2. 根目录 `README.md`；
3. 对应子目录 README；
4. `analysis/` 中的 `result.json` 与独立验证文件；
5. `.workbuddy-ai/` 不作为事实来源。

## 3. 目录职责

| 类别 | 路径 | 职责与治理方式 |
| --- | --- | --- |
| 官方输入 | `CUMCM2026Problems/` | 原始题面、附件和官方模板，`immutable-source` |
| 规范化数据 | `data/` | 队友交付和处理后的当前输入，`canonical-data` |
| 模型实现 | `src/` | 四问共用内核、约束、执行器和算法，路径稳定 |
| 运行脚本 | `scripts/` | 运行、复核、交付和论文构建入口；只做逻辑分类，不物理搬迁 |
| 回归测试 | `tests/` | 现有测试文件保持原路径 |
| 实验证据 | `analysis/` | 当前与历史实验的结果、协议、独立验证和哈希链 |
| 历史导表证据 | `outputs/` | 旧模板写入与回读证据，`historical`，保持原路径 |
| 论文 | `paper/` | 唯一论文源文件和 PDF，`current-mainline` |
| 候选交付 | `deliverables/candidate_figures/` | 按 `v1`、`v2`、`v3_3d`、`v4_advanced` 管理，`candidate-only` |
| 正式交付 | `deliverables/final_submission/` | 当前策略的正式结果表和摘要；仅在完成相应验收后使用 |
| 审阅归档 | `deliverables/review/` | 审阅记录、历史结果和验证摘录；历史打包文件位于 `review/packages/` |
| 文档治理 | `docs/` | 数据、模型、实验、验证、交付和仓库边界说明 |
| 工具元数据 | `.workbuddy-ai/` | 工具自身记录，不作为项目状态来源，本轮不处理 |
| 缓存环境 | `.venv/`、`tmp/`、`.pytest_cache/`、`__pycache__/` | `regenerable-cache`，保持忽略，不纳入正式内容 |

## 4. 当前主线与候选边界

当前主线事实保持不变：

- Q1 是代表日确定性优化；
- Q2 是 B2 安全裕量；
- Q3 是裕量零点固定；
- Q4 是动态电价严格迁移；“价格提前可知”仍是候选假设；
- 技术时间口径是 `interval-end-v1`；
- 四问均已有真实候选基础闭环，但不等于最终竞赛验收完成；
- Oracle 只作为事后信息下界或诊断，不能包装成可执行主方案；
- `legacy_excel/` 和旧 `outputs/` 只作历史证据，不能混入当前主线。

候选图包仍然不等于论文图件。尤其 `deliverables/candidate_figures/v4_advanced/` 必须保持 `candidate-only` 和 `not-for-submission`，不能写入 `paper/` 或正式提交包。

## 5. 本轮唯一物理移动

在保留文件内容和 SHA-256 的前提下，只移动以下三个已确认无执行依赖的历史文件：

| 旧路径 | 新路径 | 基线 SHA-256 |
| --- | --- | --- |
| `deliverables/C_microgrid_review_v1.zip` | `deliverables/review/packages/C_microgrid_review_v1.zip` | `1898c3c6656f5aedf40670e8dff78eebcf9123c47d1fdaf26265a9290ed27a01` |
| `deliverables/C_microgrid_review_v2.zip` | `deliverables/review/packages/C_microgrid_review_v2.zip` | `7a43ed1c5845a314d3f6254910a41b8aae349716210af18d1629f7c81129b29b` |
| `deliverables/file_manifest.json` | `deliverables/review/packages/deliverables_snapshot_manifest.json` | `aedb536cc7cc22b17330f0810a4bec9ef982daa1a950cfd405ce6c3830c9dbb8` |

`deliverables_snapshot_manifest.json` 是历史快照：其中的内部路径仍按快照生成时的旧 `deliverables/` 根目录解释，不代表当前文件必须恢复到旧位置。

除此之外，本轮不移动、不重命名、不重写 `analysis/`、`outputs/`、`paper/`、`data/`、`src/` 或 `scripts/` 中的任何文件。

## 6. 检查、回滚与复现

治理前后应记录分支、HEAD、工作区状态、受保护目录指纹和三份历史包 SHA-256。布局检查器 [scripts/verify_repository_layout.py](../scripts/verify_repository_layout.py) 只读检查目录职责、关键路径、历史包位置、候选状态、论文隔离和 tracked 缓存，不导入模型、不运行优化、不写文件。

如果移动后的路径、哈希或引用校验失败，按上表逐项执行新路径到旧路径的反向 `git mv`，再重新检查；不使用 `git reset --hard`、`git checkout --` 或递归删除。文档更新只有在路径校验通过后才算完成。

本轮验收还要求：受保护目录内容 SHA-256 与基线一致、`paper/` 无 diff、旧路径不再作为有效交付链接、130 项回归测试及时间语义和高级候选图验证通过，并且 `git diff --check` 通过。

本治理记录本身不授权提交、推送、合并、重新求解、重导 Excel 或重编译论文。完成后工作区保持未提交、未推送，等待后续单独授权。
