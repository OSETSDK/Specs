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
| 匿名远端克隆 | 48 / 48 | 从公开 HTTPS 仓库重新克隆，清单和全部原字节校验通过 |
| GitHub Actions | 通过 | [首次云端运行](https://github.com/OSETSDK/Specs/actions/runs/41984503569)，包含 38 项回归和规格清单检查 |
| 后续版本选择 | 通过 | 同一 Pod 保留多个版本的独立 fixture 只验证 selected_version |

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

代表性工程使用真实公开源 `https://github.com/OSETSDK/Specs.git` 与公共 CDN，唯一顶层声明为 `OSETCoreSDK-BF 7.0.3.3`，不使用逐 Pod 的 `:source` 或额外顶层 SDK。实际安装完成，共 9 个根 Pod。已保存[本次锁文件](.github/fixtures/bf-7.0.3.3-Podfile.lock)。

最终锁文件中，BF、B/F Adapter 和 B/F SDK 来自 OSET Specs；Core 7.0.3.5、Ads-CN 7.8.1.1、AliyunLogProducer 4.3.3、BUTTSDKFramework 1.48.2.3-premium 来自公共源。Core 的 SHA1 为 `913be90e79a0f5c6061eab38be089abd5658c672`，与新 Specs 中的原始规格一致。

实际构建使用 Xcode 26.4、独立 workspace 和 DerivedData、Debug 配置，禁用签名。

| BF 代表性构建 | 结果 |
|---|---|
| generic iOS device arm64 | BUILD SUCCEEDED |
| generic iOS Simulator x86_64 | BUILD SUCCEEDED |
| generic iOS Simulator arm64 | 未通过，受下述既有第三方架构排除配置限制 |

AliyunLogProducer 4.3.3 的官方规格在 pod_target_xcconfig 和 user_target_xcconfig 中设置 `EXCLUDED_ARCHS[sdk=iphonesimulator*] = arm64 i386`。指定 arm64 模拟器构建时，ARCHS 为空，生成的 Embed Frameworks 脚本报 `ARCHS[@]: unbound variable`。本次没有修改该第三方规格，也没有据此改动 OSET 同版本规格或二进制。

这些结果不等于全部 48 个 Pod 已完成实际构建或广告功能验证。其余 Pod 的实际平台行为继续遵循既有 SDK 发版验证；本次没有运行广告初始化、曝光、点击或收益相关功能。

## 复核方式

```sh
python3 .github/scripts/validate_specs.py
python3 -m unittest discover -s .github/scripts -p 'test_*.py'
```

完整依赖解析工具为 `.github/scripts/validate_resolution.rb`，使用 CocoaPods 1.16.2。运行前把 CP_HOME_DIR、CP_CACHE_DIR、CP_REPOS_DIR 和 TMPDIR 指向工作区外专用临时目录，并把报告输出到 Specs 仓库之外；工具会拒绝常规全局 CocoaPods 目录，并按清单顺序验证各 Pod 的 selected_version；后续追加版本时仍可保留已发布目录。它不执行 SDK 下载、构建或发布。

## 2026-11-06 直接发布 M SDK

新增 `AdSetQDMAdSDK 1.4.16` 的直接交付规格。原有 48 份官方来源 JSON 保持原始字节，新增规格与公开交付 tag 中的 JSON 原字节一致。

| 检查 | 结果 |
|---|---|
| 公开交付 tag | `f4fbcac79e18a0ec3c80b3085adf732051807d7a` |
| 全新隔离 CocoaPods 从真实 Git tag 安装 | 通过；下载后的 71 个 XCFramework 文件与原厂 ZIP 提取件逐文件 SHA256 相同 |
| Podspec SHA1 / CocoaPods checksum | `50d025e53282a40af9d9c1be8178dea0a8f453a3` |
| 本地路径 SDK-only：arm64 真机架构 | 编译、链接、动态框架嵌入通过 |
| 本地路径 SDK-only：x86_64 模拟器 | 编译、链接、动态框架嵌入通过 |
| 本地路径 SDK-only：arm64 模拟器，iOS 14.0 | 编译、链接、动态框架嵌入通过 |
| 原厂资源 | 三种配置均保留框架内 `Assets.car` 与 `PrivacyInfo.xcprivacy` |
| 直接交付登记工具 | 57 项回归通过；[工具提交的云端验证](https://github.com/OSETSDK/Specs/actions/runs/42155174362)通过 |

SDK 是动态 XCFramework，原包内容未改动。以上构建禁用签名，没有运行广告初始化、真实广告、奖励或点击流程；远端 tag 安装完整性与本地路径构建分别记录，不等同于广告功能验收。M Adapter 及其 Core 依赖在各自版本完成登记和联验后单独记录。
