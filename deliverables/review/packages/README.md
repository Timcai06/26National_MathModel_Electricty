# 历史审阅包归档

本目录只存放已经生成、仅供内部审阅或历史追溯的打包文件。它们属于 `historical`、`supporting-evidence` 和 `not-for-submission`，不是当前正式提交包，也不是当前论文入口。

## 归档清单

| 文件 | 来源 | SHA-256 | 说明 |
| --- | --- | --- | --- |
| [`C_microgrid_review_v1.zip`](C_microgrid_review_v1.zip) | 原 `deliverables/` 根目录 | `1898c3c6656f5aedf40670e8dff78eebcf9123c47d1fdaf26265a9290ed27a01` | V1 历史审阅包 |
| [`C_microgrid_review_v2.zip`](C_microgrid_review_v2.zip) | 原 `deliverables/` 根目录 | `7a43ed1c5845a314d3f6254910a41b8aae349716210af18d1629f7c81129b29b` | V2 历史审阅包 |
| [`deliverables_snapshot_manifest.json`](deliverables_snapshot_manifest.json) | 原 `deliverables/file_manifest.json` | `aedb536cc7cc22b17330f0810a4bec9ef982daa1a950cfd405ce6c3830c9dbb8` | 历史交付目录快照 |

`deliverables_snapshot_manifest.json` 的内部路径按生成时的旧 `deliverables/` 根目录解释。文件本身只做历史记录，不是当前目录的动态 manifest；当前正式结果清单见 [`deliverables/final_submission/excel/manifest.json`](../../final_submission/excel/manifest.json)。

## 路径和回滚

本轮只执行三项 `git mv`：

```text
deliverables/C_microgrid_review_v1.zip
  -> deliverables/review/packages/C_microgrid_review_v1.zip
deliverables/C_microgrid_review_v2.zip
  -> deliverables/review/packages/C_microgrid_review_v2.zip
deliverables/file_manifest.json
  -> deliverables/review/packages/deliverables_snapshot_manifest.json
```

移动前后的 SHA-256 必须一致，旧路径不得保留第二份副本。若校验失败，按上述映射反向移动即可恢复；不删除、不重打包、不修改压缩包内部内容。
