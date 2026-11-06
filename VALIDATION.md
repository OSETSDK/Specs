# OSET Specs 验证记录

当前 M 渠道组合的 arm64 模拟器限制已通过 OSET 兼容规格 `AliyunLogProducer 4.3.3.1` 修复，见文末验收记录。下方 `4.3.3` 的失败记录保留为历史基线。

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

## 2026-11-06 Core 7.0.4.0 与 M Adapter 2.0.0.0

本轮完成后共收录 50 个 Pod、51 份规格。新增 Core `7.0.4.0`、M SDK `1.4.16`、M Adapter `2.0.0.0` 均保留公开交付 tag 中 JSON 的原始字节；原首批 48 份规格与已经登记的 M SDK 均通过不可变基线检查。Core `7.0.3.5` 继续保留。

| Pod | 版本 | 交付 tag commit | 规格 SHA1 / CocoaPods checksum |
|---|---|---|---|
| `OSETCoreAd` | `7.0.4.0` | `ccb1d199b84a1e036954c12fdbcb70ff42c41597` | `7461fb12831f9fbe7a99557eef71aeb2bd36ebb9` |
| `AdSetQDMAdSDK` | `1.4.16` | `f4fbcac79e18a0ec3c80b3085adf732051807d7a` | `50d025e53282a40af9d9c1be8178dea0a8f453a3` |
| `AdSetQDMAdapter` | `2.0.0.0` | `ada672524eea30c468ddda1fc89cdef678aa5fc1` | `f5db0a76b77fa5f6ef185ae0db0ad411b222d938` |

Core 使用当前源码快照，包含既有 SKT、环境机制、`jili` 配置类型容错与新增 `tuiyi` 注册。Release 真机 arm64、模拟器 arm64/x86_64 归档与打包验证通过；没有包含渠道 Adapter 或 Aliyun Producer 实现，继续使用外置 `AliyunLogProducer` 依赖。最终 36 份公开头与已发布 `7.0.3.5` 原字节相同，未把 Release 二进制没有实现的 Debug 环境切换声明放入交付头。独立 Release `jili` 配置类型检查 138/138 通过。

维护工具 57/57 回归通过。三个新版本在全新隔离 CocoaPods 目录中逐根依赖解析 3/3 通过，51 份输入规格在解析前后未变；Core、M SDK 和 M Adapter 均从 OSET Specs 解析，Aliyun `4.3.3` 来自公共 CDN。

发布前，本地路径组合消费者先验证了新 Core、M Adapter、M SDK 与实际外置 Aliyun `4.3.3` 的真机 arm64、模拟器 x86_64 链接。发布后，又在另一套全新 CP_HOME/CP_CACHE/TMPDIR 中，从真实公开 `https://github.com/OSETSDK/Specs.git` 安装，根声明只有 M Adapter `2.0.0.0` 与 Core `7.0.4.0`。完整锁文件见 [M 渠道消费者锁文件](.github/fixtures/m-2.0.0.0-Podfile.lock)。

| 最终真实远端消费者检查 | 结果 |
|---|---|
| 三个 OSET Pod 的 `SPEC REPOS` | 全部为 `https://github.com/OSETSDK/Specs.git`；Aliyun `4.3.3` 为 Trunk |
| 锁文件、下载缓存规格、索引规格 checksum | 三个 OSET Pod 全部相同；Podfile.lock 与 Manifest.lock 一致 |
| 下载后的 vendored 文件 | Core 105、Adapter 9、SDK 71，共 185 个文件与预检输入逐 SHA256 相同；SDK 同时与原厂 ZIP 一致 |
| `-ObjC` | 由 Podspec 自然传递；最终工程和构建命令没有手工补充该参数 |
| generic iOS device arm64 | BUILD SUCCEEDED；6 个 M Adapter 类及 Core 类符号保留 |
| generic iOS Simulator x86_64 | BUILD SUCCEEDED；6 个 M Adapter 类及 Core 类符号保留 |
| 动态 SDK 集成 | 两种成功配置均确认 M SDK 的 `@rpath`、正确薄架构、`Assets.car` 和 `PrivacyInfo.xcprivacy` 原始 SHA256 |
| generic iOS Simulator arm64 | 未通过；Aliyun `4.3.3` 官方配置排除该架构，见下方限制 |

最终 arm64 模拟器失败与首批代表性消费者相同：Aliyun `4.3.3` 官方规格在 Pod 和宿主配置中排除 `arm64 i386`，导致 `ARCHS` 为空，CocoaPods Embed 脚本报 `ARCHS[@]: unbound variable`。没有覆盖第三方规格或排除配置。Core、M Adapter 的 arm64 模拟器切片各自编译通过，M SDK 的 arm64 模拟器切片已在 SDK-only iOS 14.0 工程通过；这些结果不替代完整依赖链的 arm64 模拟器验收。

所有 App 构建均禁用签名，没有运行 SDK 初始化、真实广告、奖励、点击、关闭或生产后端请求。M 本轮开放初始化、开屏、插屏、激励视频和 Native 模板；NativeData、Banner、独立 FullscreenVideo、Draw 未开放。L/N 只有交付仓占位说明，没有发布 Podspec。

## 2026-11-06 Aliyun arm64 模拟器兼容修订

本次仅在 OSET Specs 新增官方 `AliyunLogProducer 4.3.3` 原始规格与 OSET 维护的 `4.3.3.1` 兼容修订。仓库现有 51 个 Pod、53 份规格，先前发布的 51 份规格逐字节不变；Core、M Adapter 和 M SDK 的版本、交付 tag 与文件均未更改。

兼容版本使用同一上游 `4.3.3` tag（commit `9f12d40a8bda23d0775963401e29d6a2954c7e51`）。原规格 SHA1 为 `889e71ee9e0fd0e49c03097dd806196549f8a873`，兼容规格 SHA1 为 `5a16cfb287cd555d5bab91fad5bb0204c7414cea`。只有版本号及两项模拟器架构排除值变化：`arm64 i386` 改为 `i386`，不改上游源码、下载地址、许可、系统版本、源文件和资源配置。

`register_aliyun_compat_spec.py --check` 离线核对固定基底双哈希、精确派生字节及 manifest 中的 upstream/transform 来源记录，CI 同样执行。全部 72 项工具测试通过，三个根 Pod（Aliyun、Core、M Adapter）独立解析均选择 OSET Specs 的 `4.3.3.1`。CocoaPods lint 的规格版本与上游 tag 不同提示为此兼容修订的预期警告；没有更改上游 tag 来消除提示。

| 全新真实远端消费者验证 | 结果 |
|---|---|
| 标准全局 OSET Specs + CDN，自然解析 | Aliyun `4.3.3.1`、Core `7.0.4.0`、Adapter `2.0.0.0`、SDK `1.4.16` 均来自 OSET Specs；锁文件与索引 checksum 一致 |
| 官方源代码完整性 | Aliyun 下载后 66 个文件与官方 `4.3.3` 逐 SHA256 相同；Core 105、Adapter 9、SDK 71 个文件均与原交付一致 |
| device arm64，iOS 12.0 | BUILD SUCCEEDED |
| Simulator x86_64，iOS 12.0 | BUILD SUCCEEDED |
| Simulator arm64，iOS 14.0 | BUILD SUCCEEDED；Aliyun 实际编译 18 个上游 C 和 10 个上游 ObjC 源文件，另有 CocoaPods 生成的 version.c / dummy.m，产物为 arm64 / iOS Simulator |
| 不使用 `use_frameworks!` 的默认静态 Pods 集成 | 全新真实远端工程 arm64 Simulator 构建通过；Aliyun 为 arm64 静态库，M 动态 SDK 与资源正常嵌入，无手工架构、链接或 post_install 覆盖 |
| 链接与嵌入 | 自然继承 `-ObjC`，无手工链接或排除架构覆盖；6 个 M Adapter 类与 Core 类符号保留；动态 M SDK 及 Assets/privacy 原始哈希正确 |
| 已有锁文件的实际定向更新 | `pod update AliyunLogProducer` 仅把 `4.3.3` 改为 `4.3.3.1`；另外三个 Pod 的版本和 checksum、根依赖、原 Podfile checksum 均保持不变 |

已保存 [兼容修订真实消费者锁文件](.github/fixtures/m-2.0.0.0-aliyun-4.3.3.1-Podfile.lock)。另有 26 个隔离 CocoaPods resolver 场景、70 条断言通过，覆盖原 Trunk 锁 `4.3.3` / `3.1.17`、显式来源及局部更新。普通 install 保留已锁版本；启用兼容修订时正常定向更新 Aliyun，无需删除锁文件、全量更新或添加架构 post_install。

主三架构消费者启用 `use_frameworks!`；默认静态 Pods 示例另建独立工程验证。两种集成方式都从真实 OSET Specs 安装同一兼容规格，未修改第三方下载源码。

本次验收覆盖安装、源码与产物完整性、三种架构编译、链接和资源嵌入。构建禁用签名，没有启动 App 或执行真实广告、日志上传、生产后端请求；不等同于这些运行时功能验收。
