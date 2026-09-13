# AstrBot CloudFlare ImgBed 随机图插件

<div align="center">

[![Test](https://github.com/diyushuang/astrbot_plugin_cloudflare_imgbed_random/actions/workflows/test.yml/badge.svg)](https://github.com/diyushuang/astrbot_plugin_cloudflare_imgbed_random/actions/workflows/test.yml)

![AstrBot](https://img.shields.io/badge/AstrBot-%3E%3D4.16-blue)
![Python](https://img.shields.io/badge/Python-3.9%2B-blue)
![License](https://img.shields.io/badge/License-MIT-green)

**AstrBot 的 CloudFlare ImgBed 随机图插件**

[功能特性](#功能特性) • [安装方法](#安装方法) • [配置说明](#配置说明) • [使用方法](#使用方法)

</div>

---

## 🤖 AI 编写说明

**本项目代码完全由 AI 编写生成**。这是一个实验性项目，旨在展示 AI 辅助编程的能力。虽然代码已经过测试和优化，但仍可能存在一些潜在的问题或改进空间。欢迎社区贡献者提出建议和改进。

---

## 📖 项目介绍

本项目是 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 的一个插件，用于从 [CloudFlare ImgBed](https://github.com/MarSeventh/CloudFlare-ImgBed) 图床中获取随机图片和视频，并支持通过命令或 LLM 工具调用的方式发送到聊天平台。

### ✨ 功能特性

- 🎲 **随机媒体获取**：从 CloudFlare ImgBed 图床获取随机图片或视频
- 🚀 **原图链接直传**：QQ（aiocqhttp）平台默认把原图链接直接交给协议端发送，聊天气泡显示真实比例，且免去下载与转码，发送最快
- 🗜️ **可选压缩发送**：`imageSendMode=compress` 时先压缩（等比缩放 + JPEG 重编码）再发送，适用于协议端无法访问图床的场景；失败自动回退原图直发
- 🖼️ **原图找回**：`/原图` 命令重发最近一张随机图片的原图，也可按文件名找回指定的某一张
- 🏷️ **文件名展示**：发送随机媒体时附带图片/视频文件名
- 🔐 **API Token 鉴权**：支持需要鉴权的 API 接口
- 📁 **目录选择**：支持从指定目录获取随机媒体
- 🤖 **LLM 工具集成**：支持 AI 模型调用插件功能
- 🔄 **智能重试**：自动重试失败的请求，提高成功率
- 🌐 **相对路径处理**：自动处理 API 返回的相对路径 URL
- 🛡️ **安全校验**：对 API 域名、返回 URL 和响应体大小做校验，拒绝异常响应
- 📝 **详细日志**：完善的日志记录，便于调试和问题定位
- ⚡ **异步处理**：使用异步编程，提高性能和响应速度

---

## 🚀 安装方法

### 方法一：通过 AstrBot 插件市场安装（推荐）

1. 打开 AstrBot 管理面板
2. 进入「插件管理」页面
3. 搜索「CloudFlare ImgBed随机图」
4. 点击「安装」按钮

### 方法二：手动安装

```bash
# 克隆项目到 AstrBot 插件目录
git clone https://github.com/diyushuang/astrbot_plugin_cloudflare_imgbed_random.git /path/to/astrbot/data/plugins/astrbot_plugin_cloudflare_imgbed_random

# 重启 AstrBot
```

---

## ⚙️ 配置说明

安装完成后，需要在插件配置中设置以下参数：

### API 接口说明

- **CloudFlare ImgBed 默认 API 端点**：`/random`
- **兼容其他图床**：只要能返回相同格式内容的图床都可以使用
- **支持的响应格式**：
  - JSON 格式：`{"url": "/path/to/image.jpg"}` 或 `{"data": {"url": "/path/to/image.jpg"}}`
  - 直接返回图片/视频（Content-Type 为 image/* 或 video/*）
  - 直接返回 URL 文本（纯文本格式）
- **示例配置**：
  - CloudFlare ImgBed：
    - 图床域名：`https://cfbed.sanyue.de`
    - API 接口：`/api/random`
  - 其他兼容图床：
    - 图床域名：`https://your-imgbed.com`
    - API 接口：`/api/random-image`
- **配置方式**：在插件配置中分别填写图床域名和 API 接口路径
- **自定义支持**：允许用户根据自己的图床服务自定义填写 API 接口路径

### 必填配置

| 配置项 | 说明 | 示例 | 默认值 |
|--------|------|------|--------|
| `imgbedDomain` | CloudFlare ImgBed 图床域名 | `https://your-domain` | 空字符串（必须配置） |
| `apiEndpoint` | API 接口路径 | `/random` 或 `/api/random.html` | `/random` |

### 可选配置

| 配置项 | 说明 | 示例 | 默认值 |
|--------|------|------|--------|
| `apiToken` | API Token（如需鉴权） | `Bearer YOUR_API_TOKEN` | 空字符串 |
| `defaultDir` | 默认目录（相对路径） | `img/wallpaper` | 空字符串 |
| `timeout` | API 请求超时时间（秒） | `10` | `10` |
| `retryCount` | API 请求重试次数 | `3` | `3` |
| `enableLLM` | 是否启用 LLM 工具调用 | `true` | `true` |
| `showFileInfo` | 发送时是否附带文件名 | `true` | `true` |
| `imageSendMode` | 图片发送方式：`url` 直传链接 / `compress` 压缩后发送 | `url` | `url` |
| `enableCompress` | `compress` 模式下是否启用图片压缩 | `true` | `true` |
| `compressMaxSide` | 压缩后图片最长边（像素，等比缩放） | `1920` | `1920` |
| `compressQuality` | JPEG 压缩质量（1-100） | `85` | `85` |

> 配置了 `apiToken` 时，`imgbedDomain` 必须使用 HTTPS。`retryCount` 表示失败后的重试次数，因此总请求次数为 `retryCount + 1`。
> 默认 `imageSendMode=url`，由 QQ 协议端自行下载图片，聊天气泡显示原始比例且发送最快。若协议端与图床网络不通（例如图床仅内网可达），请改为 `compress`。
>
> 图片压缩依赖 Pillow（安装插件时自动安装）；关闭 `enableCompress` 或压缩失败时自动回退为原图直发，不影响可用性。

---

## 📚 使用方法

### 命令使用

#### 基本用法

发送以下命令从默认目录获取随机图片：

```
/随机图
```

发送以下命令从默认目录获取随机视频：

```
/随机视频
```

#### 消息附带文件名

发送随机媒体时，消息会附带图片/视频的文件名，方便知道图片来源：

```
🖼️ Guerlain.jpg
```

视频使用 🎬 图标。该行为可通过配置项 `showFileInfo` 关闭。

#### 指定目录

发送以下命令从指定目录获取随机图片：

```
/随机图 img/wallpaper
```

发送以下命令从指定目录获取随机视频：

```
/随机视频 video/movies
```

#### 图片发送方式

插件提供两种发送方式，由 `imageSendMode` 配置控制。

**`url` 直传链接（默认，推荐）**

在 QQ（aiocqhttp）平台上，插件直接把原图链接交给协议端（NapCat 等），由协议端自行下载并解析出真实宽高。这样聊天气泡显示的就是图片的原始比例，同时省去插件下载、转码和 base64 编码的开销，发送延迟最低。

以下情况会自动回退为标准消息链发送，不影响使用：

- 非 aiocqhttp 平台（Telegram、Discord 等）
- 图片格式为 AVIF/HEIC/SVG 等协议端无法解析宽高的格式（自动改用 `compress` 转成 JPEG，见常见问题 8）
- 协议端接口调用失败

**`compress` 压缩后发送**

适用于协议端无法访问图床的场景（例如图床仅内网可达）。随机图片会先由插件下载原图并压缩（超过 `compressMaxSide` 的等比缩放到最长边限制，再按 `compressQuality` 质量重编码为 JPEG），然后以压缩后的字节发送，原图越大提速越明显。压缩图（非原图）会在文案中标注，并附带一条可直接复制的原图命令示范：

```
🖼️ Guerlain.jpg（已压缩，发送 /原图 Guerlain.jpg 可获取原图）
```

以下情况自动回退为原图直发，不影响使用：

- 配置中关闭了 `enableCompress` 或未安装 Pillow
- 原图是动图（GIF/动图 WebP，保留动画不重编码）
- 原图本身较小，且为 JPEG/PNG/GIF/WebP/BMP/TIFF 等协议端可解析宽高的格式（不超过 200KB，避免无谓的画质损失；AVIF/HEIC 等格式即使较小也会转成 JPEG，避免 QQ 气泡显示 1:1，见常见问题 8）
- 下载或压缩失败（含原图超过 30MB 上限）

重编码前会按 EXIF 方向信息把旋转烘进像素，竖拍照片的方向在压缩后保持正确。

#### 获取原图

发送以下命令重发**本会话最近一张**随机图片的原图（始终直传原图链接，不压缩，不受 `imageSendMode` 影响）：

```
/原图
```

也可以带上文件名（支持忽略大小写、省略扩展名、部分匹配）找回指定的某一张：

```
/原图 Guerlain.jpg
/原图 Guerlain
```

- 原图消息的文案会标注「（原图）」，与压缩图标注相区分
- 匹配到多张图片时，插件会列出候选文件名，请补充更完整的名称
- 只能找回本会话最近发送过的随机图片（每会话保留最近 30 张），且各会话互不干扰

#### LLM 智能识别

除了使用带斜杠的命令外，您还可以直接与AI对话：

- 发送"随机图"或"随机图片"，AI会自动识别并调用插件发送随机图片
- 发送"随机视频"或"随机影片"，AI会自动识别并调用插件发送随机视频
- 可以指定目录，如"随机图 img/wallpaper"或"随机视频 video/movies"

#### 命令说明

- **直接命令**：带斜杠的命令（`/随机图`、`/随机视频`、`/原图`）直接触发插件功能
- **LLM识别**：不带斜杠的命令由AI智能识别并调用插件工具
- **目录支持**：两种方式都支持指定目录参数

### LLM 工具调用

插件注册了 `sendRandomMedia` 工具，可以被 LLM 模型调用：

#### 工具描述

```
发送随机图片或视频

当用户请求随机图片或视频时使用此工具。
适用于用户提到"随机图"、"随机图片"、"随机视频"等关键词的情况。
```

#### 参数说明

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `directory` | string | 否 | 目录路径，指定从哪个目录获取随机媒体 |
| `content_type` | string | 否 | 内容类型，指定获取图片或视频，可选值：image, video |

#### 回复形式

工具调用后，插件以聊天消息形式回复：同一条消息中包含文案和媒体本身。开启 `showFileInfo` 时文案附带文件名（如 `🖼️ example.jpg`），关闭时为"随机图片发送成功"/"随机视频发送成功"；获取失败时回复失败提示。

---

## 🔌 API 文档参考

本插件基于 CloudFlare ImgBed 的随机图 API 开发。

### API 端点

- **随机图 API**：`/random`

### 请求参数

| 参数名 | 类型 | 说明 |
|--------|------|------|
| `dir` | string | 指定目录，使用相对路径 |
| `content` | string | 文件类型过滤：`image`、`video` |
| `type` | string | 返回内容类型：`url` 返回媒体地址（本插件使用）、`img` 直接返回图片 |
| `form` | string | 响应格式：`json` 返回 JSON（本插件使用）、`text` 直接返回文本 URL |
| `orientation` | string | 图片方向筛选：`landscape`、`portrait`、`square`、`auto`（上游支持，本插件未使用） |

本插件固定发送 `type=url&form=json`，并同时兼容直接返回媒体和纯文本 URL 两种响应形态。

### 响应格式

- **JSON 格式**：`{"url": "/file/example.jpg"}`
- **直接返回图片**：当 `type=img` 时
- **直接返回文本**：当 `form=text` 时

---

## 🛠️ 开发说明

### 项目结构

```
astrbot_plugin_cloudflare_imgbed_random/
├── main.py              # 主程序文件
├── metadata.yaml        # 插件元数据
├── _conf_schema.json    # 配置 Schema
├── requirements.txt     # 依赖列表
├── CHANGELOG.md         # 更新日志
├── .github/workflows/   # GitHub Actions 持续集成
├── tests/               # 单元测试
└── README.md            # 项目文档
```

### 核心功能

1. **配置加载**：从 AstrBot 配置系统加载并规范化插件配置（域名、超时、重试、开关等）
2. **媒体获取**：请求图床随机接口，带指数退避重试，兼容 JSON、直接返回媒体和纯文本 URL 三种响应
3. **URL 校验**：返回地址必须为合法 HTTP(S) 且不含凭据，相对路径自动拼接为绝对地址
4. **文案构建**：从媒体 URL 解析文件名，生成附带文件名的发送文案（可经 `showFileInfo` 关闭）
5. **图片发送**：`url` 模式（默认）在 aiocqhttp 平台经 OneBot `send_group_msg`/`send_private_msg` 直传原图链接，由协议端解析真实宽高；`compress` 模式下载原图字节流（同域才附带 Token、限 30MB），Pillow 等比缩放 + JPEG 重编码后在独立线程压缩，经 `Image.fromBytes` 发送；任一环节失败均回退标准消息链 URL 直发
6. **原图历史**：按会话记录最近发送的随机图片（文件名 → 原图 URL），`/原图` 命令支持最近一张与按文件名匹配找回
7. **命令与 LLM 双入口**：`/随机图`、`/随机视频` 命令与 `sendRandomMedia` LLM 工具共用同一处理流程

### 技术栈

- **Python 3.9+**
- **aiohttp**：异步 HTTP 客户端
- **Pillow**：图片压缩处理
- **AstrBot API**：插件开发框架

---

## ❓ 常见问题

### 1. 无法获取图片

**解决方案**：
- 检查 API 地址是否正确
- 检查 API Token 是否有效（如果需要）
- 检查网络连接是否正常
- 查看 AstrBot 日志获取详细错误信息

### 2. 图片显示为文本

**解决方案**：
- 检查 API 响应格式是否为 JSON
- 检查 API 返回的 URL 是否为相对路径
- 确认插件已正确处理相对路径转换

### 3. 目录参数不生效

**解决方案**：
- 检查目录路径是否正确
- 检查 CloudFlare ImgBed 是否支持目录参数
- 确认目录路径使用相对路径格式

### 4. LLM 工具调用失败

**解决方案**：
- 检查 AstrBot 版本是否支持 LLM 工具
- 确认插件已正确加载
- 查看 AstrBot 日志获取详细错误信息

### 5. 为什么有时只显示"随机图片发送成功"而没有文件名

**说明**：
- 媒体 URL 末段没有扩展名（如直链为随机 ID 形式）时，插件无法识别文件名，自动回退为默认文案
- 配置项 `showFileInfo` 关闭时同样只显示默认文案

### 6. 为什么收到的图片和图床里的原图不完全一致

**说明**：
- 默认 `imageSendMode=url` 直传原图链接，收到的就是原图；仅 `compress` 模式或 AVIF/HEIC 等格式降级时才是压缩图（等比缩放 + JPEG 重编码）
- 需要原图时发送 `/原图` 即可重发最近一张随机图片的原图，或用 `/原图 文件名` 找回指定图片
- 若不想压缩，保持 `imageSendMode=url`，或在插件配置中关闭 `enableCompress`

### 7. 压缩后画质不满意

**说明**：
- 调高 `compressQuality`（默认 85，最高 100）可提升画质、增大体积
- 调大 `compressMaxSide`（默认 1920）可保留更高的分辨率
- 原图不超过 200KB 且为 JPEG/PNG/GIF/WebP/BMP/TIFF 等格式、或为动图时插件不会重编码，直接按原图发送

### 8. 为什么 QQ 聊天里图片气泡显示为 1:1 正方形，点开才是原图比例

**说明**：
- QQ 聊天气泡的显示比例由消息元数据中声明的宽高决定，点开查看时才加载真实图片
- AstrBot 的 aiocqhttp 适配器会把**所有**图片消息段统一转成 base64 再发给协议端，因此 `fromURL`、`fromFileSystem`、`fromBytes` 三种写法最终效果相同，消息里都不带宽高信息
- 协议端（NapCat 等）只能从 base64 字节里嗅探宽高，遇到 AVIF/HEIC 等无法解析的格式时以固定的 1024×1024 占位，气泡就显示成 1:1

**解决方案**：
- 插件自 v1.4.0 起默认 `imageSendMode=url`，绕开图片消息段、经 OneBot 接口直接把原图链接交给协议端，由协议端自行下载并解析真实宽高，从根本上解决该问题
- 若仍显示 1:1，请确认协议端能访问图床链接（与 AstrBot 同网络环境），并将 NapCat 升级到最新版
- AVIF/HEIC/SVG 等格式会自动降级为下载转 JPEG 后发送（解码 AVIF/HEIC 需已安装 pillow-avif-plugin / pillow-heif）
- 也可让图床直接输出 JPEG/PNG 格式

---

## 📝 更新日志

## v1.4.0 (2026-09-13)

**修复**
- 🐛 修复 QQ 图片聊天气泡显示 1:1：AstrBot 的 aiocqhttp 适配器会把所有图片消息段统一转成 base64，协议端解析宽高失败后以 1024×1024 占位。插件改用 OneBot 原生 `send_group_msg` / `send_private_msg` 直传图片 URL，由协议端自行下载并解析真实宽高，并透传 `self_id` 支持多账号路由

**优化改进**
- ⚡ 默认 `imageSendMode=url`，跳过插件侧下载、压缩与 base64 编码开销，图片发送延迟更低；非 aiocqhttp 平台或协议端调用失败时自动回退标准消息链，不影响消息可达性
- 🛡️ AVIF/HEIC/SVG 等协议端无法解析宽高的格式自动降级为下载转 JPEG；`/原图` 命令始终直传原图 URL，且与 `/随机图` 共用统一发送链路
- ⚙️ 新增配置项 `imageSendMode`（`url` / `compress`），原有 `enableCompress`、`compressMaxSide`、`compressQuality` 在 `compress` 模式下继续生效
- 📖 README 更新图片发送方式说明与常见问题 8，说明根因、回退链路与适用场景
- ✅ 单元测试扩展至 58 个：覆盖 OneBot 直传群聊/私聊、平台探测、调用失败回退、非常见格式降级、模式切换与 `/原图` 直传

### v1.3.1 (2026-09-13)

**优化改进**
- 🛡️ QQ 聊天气泡 1:1 问题加固：发送前按文件头魔数识别图片格式并写入日志，AVIF/HEIC/SVG 等协议端无法解析宽高的格式即使较小也自动转成 JPEG，无法解码时回退原图直发并输出 WARNING 提示
- 🔄 重编码前按 EXIF Orientation 将旋转烘进像素，竖拍照片方向在压缩后保持正确
- 📖 新增常见问题「为什么 QQ 聊天里图片气泡显示为 1:1」：根因与处理建议（升级 NapCat 等）
- ✅ 单元测试扩展至 49 个：图片格式嗅探、非常见格式小图重编码、EXIF 方向保持

### v1.3.0 (2026-09-13)

**新增功能**
- 🗜️ 随机图片先压缩再发送：插件下载原图后经 Pillow 等比缩放（默认最长边 1920px）+ JPEG 重编码（默认质量 85），以字节流发送，明显缩短发送延迟
- 🖼️ 新增 `/原图` 命令：不带参数重发本会话最近一张随机图片的原图，支持 `/原图 文件名` 按文件名找回指定的某一张（忽略大小写、可省略扩展名、唯一子串匹配）
- ⚙️ 新增配置项 `enableCompress`（默认开启）、`compressMaxSide`、`compressQuality`

**优化改进**
- 🛡️ 压缩流程健壮性：动图不重编码保留动画、原图 ≤200KB 跳过重编码、下载限 30MB、鉴权 Token 仅在图片与图床同域时附带；任何环节失败自动回退原图 URL 直发
- ⚡ 压缩放入独立线程执行，不阻塞事件循环；Pillow 未安装时压缩自动禁用，其余功能不受影响

### v1.2.2 (2026-09-12)

**重大变更**
- 📛 按 AstrBot 官方插件命名规范，插件标识符由 `cloudflare_imgbed_random` 重命名为 `astrbot_plugin_cloudflare_imgbed_random`，GitHub 仓库同步更名
- ⚠️ 已安装用户需卸载后重新安装本插件，插件配置会按新插件名重新保存

**调整**
- 📋 `metadata.yaml` 规范化：`description` 字段改为 `desc`，新增 `repo` 字段，`astrbot_version` 按官方示例以双引号包裹版本约束
- ✍️ 补全 `@register` 注册装饰器中的作者信息

### v1.2.1 (2026-09-12)

**调整**
- 🔧 发送随机媒体时不再显示文件夹目录，只显示文件名

### v1.2.0 (2026-09-12)

**新增功能**
- 🏷️ 发送随机图片/视频时附带所在的文件夹目录和文件名（自动从媒体 URL 解析，兼容中文及 URL 编码路径）
- ⚙️ 新增配置项 `showFileInfo`，可关闭附带信息

### v1.1.0 (2026-08-23)

**修复与改进**
- 🔧 修复 AstrBot 插件配置注入和命令注册方式
- 🔧 修复 LLM 工具目录参数丢失、`retryCount=0` 不请求等问题
- 🌐 支持相对 URL、直接返回媒体响应和更多媒体后缀
- 🛡️ 增加 URL、Token、响应体大小和内容类型校验，避免暴露内部异常
- ⚡ 复用 HTTP 会话并加入指数退避，减少重复连接开销
- ✅ 增加单元测试和 GitHub Actions 持续集成

### v1.0.0 (2026-03-22)

**新增功能**
- ✨ 支持从 CloudFlare ImgBed 获取随机图片和视频
- ✨ 支持 API Token 鉴权
- ✨ 支持指定目录获取媒体
- ✨ 支持 LLM 工具调用
- ✨ 支持多种命令格式

**优化改进**
- ⚡ 使用异步编程提高性能
- 🔧 智能处理相对路径 URL
- 📝 完善的错误处理和日志记录
- 🔄 自动重试失败的请求

---

## 📄 许可证

本项目采用 [MIT 许可证](LICENSE)。

---

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request！

### 提交 Issue

- 描述问题的详细情况
- 提供复现步骤
- 附上相关日志

### 提交 Pull Request

- Fork 本仓库
- 创建新的分支
- 提交修改
- 创建 Pull Request

---

## 📞 联系方式

- **GitHub Issues**: [https://github.com/diyushuang/astrbot_plugin_cloudflare_imgbed_random/issues](https://github.com/diyushuang/astrbot_plugin_cloudflare_imgbed_random/issues)
- **项目地址**: [https://github.com/diyushuang/astrbot_plugin_cloudflare_imgbed_random](https://github.com/diyushuang/astrbot_plugin_cloudflare_imgbed_random)

---

## 🙏 致谢

- [AstrBot](https://github.com/Soulter/AstrBot) - 优秀的机器人框架
- [CloudFlare ImgBed](https://cfbed.sanyue.de/) - 稳定的图床服务
- 所有贡献者和用户

---

<div align="center">

**如果这个项目对你有帮助，请给一个 ⭐ Star 支持一下！**

</div>
