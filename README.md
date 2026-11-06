# OSET CocoaPods Specs

OSET SDK 的统一 CocoaPods 规格索引。SDK 源码、二进制和资源继续由各版本原有交付仓库提供，本仓库只保存 Podspec。

2026 年 11 月 5 日首批迁移范围为本地分发目录中各 Pod 在 CocoaPods 官方源已发布的最新版本，共 48 个 Pod。初始迁移不收录更早版本，也不首次发布尚未确认的本地版本。每份规格保留官方原始 JSON 字节与依赖声明。

## 客户接入

在项目原有 Podfile 中加入 OSET 源，并保留公共源及项目原有的其他厂商源。原有 platform、target、use_frameworks! 和 post_install 设置按项目需要保留。

```ruby
source 'https://github.com/OSETSDK/Specs.git'
source 'https://cdn.cocoapods.org/'

target 'YourApp' do
  pod 'OSETCoreSDK-BF', '7.0.3.3'
end
```

新工程执行 `pod install --repo-update`。已有工程保留并检查 `Podfile.lock`；版本升级使用定向 `pod update`，并核对整个依赖链的变化。全局源顺序、版本约束和锁文件共同影响解析，安装后检查 `SPEC REPOS`。主示例统一使用顶部 sources；在 CocoaPods 1.16.2 中，如果所有顶层 Pod 都显式绑定 `:source`，Analyzer 可能仅保留这些显式来源，导致公共间接依赖无法查找，因此不要仅为单个 BF 顶层声明添加 `:source`。

现有客户可继续使用原官方源接入方式。只切源而不升级时，先确认原锁定版本已收录；初始迁移没有收录的旧版本仍可继续从公共源获取。不要为了切源删除锁文件。

公共源仍然必需：第三方依赖、旧 Pod 名称和部分固定历史依赖不全部包含在本仓库。例如 `OSETCoreSDK-E 6.6.9.8` 依赖公共源中的 `OSETGDTAdapter 1.0.1`，`OSETCoreToGMAdapter-BF 6.6.3.3` 使用原依赖名 `OSETCodeSDK-BF`。

## 首批迁移清单

以下按迁移前本地仓库内受版本控制及未忽略文件的最近修改时间倒序排列，不使用顶层目录的修改时间。序号保留待确认项目的位置。时间使用 Asia/Shanghai；这个顺序是首次迁移清单，不代表后续 SDK 版本发布先后。下表为首批快照；后续最新收录版本以 specs-manifest.json 的 selected_version 为准。

| 顺序 | Pod | 本次收录版本 | 最近改动时间 |
|---:|---|---|---|
| 1 | `OSETCoreSDK-BF` | `7.0.3.3` | 2026-11-04 10:14:41 |
| 2 | `OSETCoreToCSJAdapter` | `7.0.3.0` | 2026-10-30 15:56:33 |
| 3 | `OSETCoreToGMAdapter` | `7.0.3.0` | 2026-10-30 15:56:33 |
| 4 | `OSETCoreAd` | `7.0.3.5` | 2026-10-27 13:24:30 |
| 5 | `AdSetQDEAdapter` | `2.0.2.1` | 2026-10-22 17:19:51 |
| 6 | `OSETQMAdapter` | `2.0.2.1` | 2026-10-22 17:06:27 |
| 7 | `AdSetQDAAdapter` | `2.0.2.0` | 2026-10-21 14:03:37 |
| 8 | `AdSetQDGAdapter` | `2.0.2.3` | 2026-10-21 13:44:37 |
| 9 | `AdSetQDAAdSDK` | `3.0.22` | 2026-10-21 11:57:19 |
| 10 | `OSETYDAdapter` | `2.0.1.0` | 2026-10-20 15:54:03 |
| 11 | `OSETCoreToBidRCAdapter` | `7.0.3.2` | 2026-10-20 09:22:26 |
| 12 | `OSETCoreToBidBetaAdapter` | `7.0.3.2` | 2026-10-20 09:22:14 |
| 13 | `OSETCoreToBidAdapter` | `7.0.3.2` | 2026-10-20 09:22:04 |
| 14 | `OSETCoreToTopOnAdapter` | `7.0.3.3` | 2026-10-19 15:05:36 |
| 15 | `OSETCoreToTakuAdapter` | `6.6.1.1` | 2026-10-19 14:35:13 |
| 16 | `OSETCoreToYQAdapter` | `7.0.0.0` | 2026-10-16 13:18:18 |
| 17 | `AdSetQDFAdapter` | `2.0.1.2` | 2026-10-14 18:04:49 |
| 18 | `OSETHXAdapter` | `2.0.2.2` | 2026-10-14 17:19:40 |
| 19 | `AdSetQDFAdSDK` | `1.1.32.0` | 2026-10-14 10:13:33 |
| 20 | `OSETGDTAdapter` | `2.0.2.1` | 2026-10-10 09:44:30 |
| 21 | `OSETKSAdapter` | `2.0.2.1` | 2026-10-10 09:44:15 |
| 22 | `AdSetQDDAdapter` | `2.0.2.0` | 2026-10-09 17:20:50 |
| 23 | `AdSetQDCAdapter` | `2.0.2.1` | 2026-10-09 17:16:06 |
| 24 | `OSETCoreSDK` | `7.0.3.2` | 2026-10-09 16:14:21 |
| 25 | `AdSetQDJAdapter` | `2.0.0.0` | 2026-09-22 09:29:32 |
| 26 | `AdSetQDIAdapter` | `2.0.1.0` | 2026-09-18 09:25:56 |
| 27 | `AdSetQDBAdapter` | `2.0.1.0` | 2026-09-17 15:42:53 |
| 28 | `AdSetQDJAdSDK` | `1.0.0.3` | 2026-09-09 12:05:37 |
| 29 | `OSETToAdScopeAdapter` | `1.0.0.1` | 2026-09-04 17:33:24 |
| 30 | `AdSetQDBAdSDK` | `7.9.4.37` | 2026-08-26 13:30:08 |
| 31 | `OSETCoreAdToYQAdapter` | `1.0.0.0` | 2026-08-12 15:16:23 |
| 32 | `AdSetQDIAdSDK` | `6.5.75.3` | 2026-08-06 17:06:12 |
| 34 | `OSETCoreSDK-E` | `6.6.9.8` | 2026-07-09 14:51:42 |
| 35 | `OSETSDK-H` | `6.6.8.6` | 2026-06-24 13:26:35 |
| 36 | `OSETCoreToGMAdapter-BF` | `6.6.3.3` | 2026-06-22 19:44:59 |
| 37 | `OSETSDK` | `6.6.7.6` | 2026-06-18 13:30:37 |
| 38 | `AdSetQDCAdSDK` | `7.7.4.32` | 2026-06-05 17:07:53 |
| 39 | `AdSetQDEAdSDK` | `1.0.0` | 2026-05-29 09:59:59 |
| 40 | `OSETToGMAdapter` | `6.6.3.6` | 2026-05-22 18:03:00 |
| 41 | `AdSetQDDAdSDK` | `1.3.0.0` | 2026-05-13 15:51:26 |
| 42 | `OSETToTakuLowAdapter` | `6.6.2.5` | 2026-03-16 15:58:34 |
| 43 | `OSETQMSDK` | `6.6.1.5` | 2026-02-25 16:58:56 |
| 44 | `OSETQMToBidRCAdapter` | `6.6.2.0` | 2026-01-29 18:07:46 |
| 46 | `OSETToTaku115Adapter` | `6.6.2.5` | 2026-01-04 11:09:52 |
| 47 | `OSETSDKNoCSJ` | `6.6.2.5` | 2026-01-04 11:03:33 |
| 48 | `OSETToTopOnAdapter` | `6.6.2.5` | 2025-12-31 15:43:53 |
| 49 | `OSETToTakuAdapter` | `6.6.2.4` | 2025-12-30 13:49:21 |
| 50 | `OSETQMToBidAdapter` | `6.6.0.2` | 2025-11-11 11:47:35 |

## 官方源与 OSET Specs 并行维护

继续在现有 SDK 交付仓库和官方源按原流程发布。官方发布成功后，在本 Specs 仓库的独立克隆中同步对应版本：

```sh
# 默认只预览
python3 .github/scripts/sync_public_spec.py --pod OSETCoreAd --version 7.0.3.5

# 确认后写入原始官方 JSON 并更新规格清单
python3 .github/scripts/sync_public_spec.py --pod OSETCoreAd --version 7.0.3.5 --apply

python3 .github/scripts/validate_specs.py
python3 -m unittest discover -s .github/scripts -p 'test_*.py'
git diff --stat
```

同步脚本只读取已在官方源发布的版本，保留原始 JSON 字节；同版本内容一致时跳过，不一致时拒绝覆盖。脚本不会自动提交或推送。维护者审查差异和验证结果后，再按正常 Git 流程提交并推送本仓库。

首批不迁旧版；后续追加新版本时保留已经发布的目录，保障已切源客户的锁文件可重复安装。官方源暂时或永久停止接收新版本时，使用下方原生交付登记流程；官方同步脚本只处理已经在 Trunk 发布的版本。

## 直接向 OSET Specs 发布新版本

先在 `OSETSDK/<Pod>` 交付仓库提交 SDK 文件、Ruby Podspec 和与之语义一致的 `<Pod>.podspec.json`，再推送版本 tag。tag 及 JSON 必须公开可读，JSON 的 source.git/source.tag 必须指向同一交付仓库和版本。完成该版本的安装、构建与依赖检查后，在 Specs 独立克隆中执行：

```sh
# 默认预览，不查询 Trunk，也不写入
python3 .github/scripts/register_delivery_spec.py --pod AdSetQDMAdSDK --version 1.4.16

# 核对预览后登记原始 JSON 和交付 tag SHA
python3 .github/scripts/register_delivery_spec.py --pod AdSetQDMAdSDK --version 1.4.16 --apply

python3 .github/scripts/validate_specs.py
python3 -m unittest discover -s .github/scripts -p 'test_*.py'
```

以上 Pod/版本是命令示例，实际可用版本以规格清单为准。登记工具不会自动提交或推送。维护者核对新增文件与完整依赖可解析后，再提交本 Specs 仓库。新版本的未发布依赖应先完成交付和登记；不要为通过解析而降低真实所需依赖版本。

原生登记保留交付仓库 tag 中 JSON 的原始字节，记录 direct_delivery 来源；已有同版本内容或已登记 tag SHA 不一致时拒绝操作。后续向官方源发布同版本时，同样应保持规格和交付文件一致，不能覆盖已登记版本。

## 校验与版本稳定性

`specs-manifest.json` 记录每份规格的官方来源 URL、SHA1、SHA256、交付 tag SHA 和依赖。SHA1 对应原始规格字节，迁移不会格式化或重写这些 JSON。离线校验脚本检查清单、规格、路径和校验值的一致性；CI 会将更改或删除已发布规格的提交标记为检查失败。

完整依赖解析、实际下载安装、模拟器与真机构建、广告功能是不同的验收层级。验证范围和结果见 [VALIDATION.md](VALIDATION.md)。初始迁移不改交付文件、不改变最低系统版本或依赖约束。

`OSETQMToBidRCAdapter 6.6.2.0` 的官方规格与该 tag 内根 Podspec 存在既有的版本元数据差异；本仓库保留官方规格原文。对应依赖和文件路径未由本次迁移改写。
