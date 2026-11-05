# 首批 Specs 验证记录

验证日期为 2026 年 11 月 5 日。首批仅收录 48 个 Pod 各自官方源最新已发布版本，不迁入更早版本，不首次发布尚未确认的本地候选。所有 Podspec 均来自 CocoaPods 官方 Specs 的原始 JSON，原始字节保持不变。

## 已完成的验证

| 验证项 | 结果 | 覆盖范围 |
|---|---|---|
| 官方版本选择 | 48 / 48 | 通过 Ruby Gem::Version 从官方 Trunk 列表选择最大版本 |
| 交付 tag 可读性 | 48 / 48 | 匿名读取各规格声明的远端 tag，并核对 SHA |
| 原始字节与清单 | 48 / 48 | 路径、name、version、source、依赖、SHA1、SHA256 |
| CocoaPods repo lint | 48 / 48 | CocoaPods 1.16.2 规格结构与元数据检查 |
| 独立完整依赖解析 | 48 / 48 | 每个根 Pod 单独解析，使用候选 Specs 与公共 CDN，无旧锁文件 |
| 维护脚本回归测试 | 38 / 38 | 原字节保存、幂等同步、拒绝未发布版本、不可变版本、路径和清单检查 |
| 官方同步脚本网络预览 | 通过 | OSETCoreAd 7.0.3.5 确认为原字节一致，无写入 |

依赖解析基线为 iOS 12.0；若根规格要求更高则使用其最低版本。`OSETHXAdapter 2.0.2.2` 使用 iOS 13.0，其余根规格使用 iOS 12.0。这个检查验证元数据和递归依赖可解析，不会下载 SDK 产物或构建客户 App。

## 来源与既有兼容约束

所有根 Pod 均从候选 OSET Specs 解析。间接依赖可能继续来自公共 CDN；显式绑定根 Pod 的 `:source` 不会把其来源传递给依赖；CocoaPods 1.16.2 Analyzer 在所有顶层 Pod 都绑定来源时，还会改用仅包含这些绑定来源的列表。客户主示例保留两个全局 sources，并不给单一 BF 顶层声明添加 `:source`。初始范围仅最新版本，所以客户应继续保留公共源。

以下是本次解析中由公共 CDN 提供的、同名库也在新 Specs 清单中的依赖：

| 根 Pod | 公共源依赖 | 版本 |
|---|---|---|
| `OSETCoreSDK` | `OSETCoreAd` | `7.0.3.5` |
| `OSETCoreSDK-BF` | `OSETCoreAd` | `7.0.3.5` |
| `OSETCoreSDK-E` | `OSETGDTAdapter` | `1.0.1` |
| `OSETCoreToTakuAdapter` | `OSETCoreAd` | `7.0.3.5` |

前三项 CoreAd 在同版本多源、多条不同约束下选用了公共 CDN，属于本机 CocoaPods 1.16.2 / Molinillo 0.8.0 的候选去重行为，其规格 SHA1 与 OSET Specs 原始字节一致。这个结果不代表全部 OSET 间接依赖都已切换来源。

此外，`OSETCoreToGMAdapter-BF 6.6.3.3` 使用的 `OSETCodeSDK-BF` 是实际存在的旧 Pod 名称；`OSETCoreSDK-E 6.6.9.8` 固定要求 `OSETGDTAdapter 1.0.1`。本次保持官方依赖声明原样，不改名、不放宽或收紧版本约束，也不为它们额外迁入历史版本。

`OSETQMToBidRCAdapter 6.6.2.0` 的官方 JSON 指向同名交付 tag，但 tag 内根 Podspec 的 version/source.tag 仍为旧元数据。依赖和交付文件声明没有该差异；迁移保存官方 JSON，不重写已发布 tag。

## 安装与构建验收

48 个根 Pod 的完整 SDK 下载、模拟器构建、真机构建和广告功能验收没有由上述元数据检查替代。代表性 BF 工程的独立冷缓存安装与构建结果将在实际执行后追加；其余 Pod 的实际平台行为继续遵循既有 SDK 发版验证。

## 复核方式

```sh
python3 .github/scripts/validate_specs.py
python3 -m unittest discover -s .github/scripts -p 'test_*.py'
```

完整依赖解析工具为 `.github/scripts/validate_resolution.rb`，使用 CocoaPods 1.16.2。运行前把 CP_HOME_DIR、CP_CACHE_DIR、CP_REPOS_DIR 和 TMPDIR 指向工作区外专用临时目录，并把报告输出到 Specs 仓库之外；工具会拒绝常规全局 CocoaPods 目录。它不执行 SDK 下载、构建或发布。
