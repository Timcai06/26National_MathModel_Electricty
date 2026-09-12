# 正式提交区

## excel/

五份官方结果表，按当前已复核策略重导，由 `scripts/deliver_strict_excel.py` 生成。每一格写入后立即从保存的工作簿读回比对，共352,466格通过。官方模板文件本身只读，未做任何修改。

来源轨迹、模板与成品的 SHA-256 见 `excel/manifest.json`，逐文件摘要见 `excel/summary.csv`。

填写方式为**按位置回填**：槽 $t$ 写入第 $t$ 个购电列，该列的印刷标签比其物理区间晚一格。依据见[时间语义封版记录](../../docs/data/TIME_SEMANTICS.md)。

## 论文

论文只有一份，在 [`paper/`](../../paper/pdf/C_microgrid.pdf)，不在本目录重复存放。

## 尚未完成

文献与竞赛格式验收未完成，因此本目录仍不等于最终封版包。旧五份候选在 `../legacy_excel/`，与当前策略不同版本，不得混用。
