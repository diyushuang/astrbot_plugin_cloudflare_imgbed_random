# CloudFlare ImgBed 随机图

一个基于 AstrBot 的 CloudFlare ImgBed 随机图片/视频插件，支持服务端缩放、原图直传、本地压缩、会话级原图找回和 LLM 工具调用。

## 官方规范依据

- [AstrBot 插件配置规范](https://docs.astrbot.app/dev/star/guides/plugin-config.html)
- [AstrBot 消息发送规范](https://docs.astrbot.app/dev/star/guides/send-message.html)
- [AstrBot 平台适配器媒体处理规范](https://docs.astrbot.app/dev/plugin-platform-adapter.html)
- [NapCat `send_group_msg` / `send_private_msg` 接口文档](https://napcat.apifox.cn/226656598e0)
- [NapCat `OB11MessageImage` 消息段文档](https://napcat.apifox.cn/246111200d0)
- [CloudFlare ImgBed 随机图 API 文档](https://cfbed.sanyue.de/api/random.html)
- [CloudFlare ImgBed 读取 API 文档](https://cfbed.sanyue.de/api/file.html)
- [CloudFlare ImgBed 配置说明](https://cfbed.sanyue.de/deployment/configuration.html)

## 功能

- 从 CloudFlare ImgBed 随机获取图片或视频
- 三种图片发送模式：
  - `scaled-url`：QQ 与其他平台优先使用 ImgBed 官方缩放 URL；失败后回退原 URL
  - `original-url`：直传原 URL
  - `local-compress`：插件下载后经 Pillow 本地压缩
- 实际发送服务端缩放图或本地压缩图时自动标注「已压缩」，并附带 `/原图 文件名` 提示
- `/原图` 命令始终重发未修改的原 URL
- 支持会话级原图历史，最多保留最近 30 张
- 支持 AstrBot LLM 工具调用

## 前置要求

- AstrBot `>=4.16,<5`
- 已部署并可访问的 CloudFlare ImgBed
- 已在 ImgBed 后台开启随机图 API，并开放目标目录
- 若使用 `scaled-url`：
  - 在 ImgBed 后台开启「图片尺寸处理」
  - 将 `{maxSide}x{maxSide}`（默认 `1920x1920`）或等价的 `auto` 组合加入允许尺寸；允许尺寸留空时表示允许任意合法尺寸
  - Cloudflare Pages 部署需绑定已接入 Cloudflare 的自定义域名，`pages.dev` 域名不支持 URL 图片转换
- 若使用 `local-compress`：
  - 安装 `Pillow`

## 安装

1. 在 AstrBot 插件市场搜索并安装本插件
2. 打开插件配置面板
3. 按下文填写 `imgbed.domain` 与 `imgbed.apiEndpoint`
4. 如使用服务端缩放，先完成 ImgBed 后台的「图片尺寸处理」配置

## 配置

### `imgbed`

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `domain` | `string` | `""` | CloudFlare ImgBed 域名，例如 `https://your-domain` |
| `apiEndpoint` | `string` | `"/random"` | 随机图 API 路径 |
| `apiToken` | `string` | `""` | API Token，面板中已按敏感信息遮罩 |
| `defaultDir` | `string` | `""` | 默认目录，使用相对路径 |
| `timeout` | `float` | `10` | API 请求超时时间，单位秒 |
| `retryCount` | `int` | `3` | API 请求失败后的重试次数 |

### `message`

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `showFileInfo` | `bool` | `true` | 是否在消息中附带文件名 |
| `enableLLM` | `bool` | `true` | 是否允许 LLM 工具调用 |

### `image`

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `sendMode` | `string` | `"scaled-url"` | 图片发送模式 |
| `enableProcessing` | `bool` | `true` | 是否启用图片处理；关闭后 `scaled-url` 直传原 URL |
| `maxSide` | `int` | `1920` | 图片最长边，范围 `1`–`4096` |
| `quality` | `int` | `85` | 本地 JPEG 压缩质量，范围 `1`–`100` |

### 发送模式对比

| 模式 | 处理位置 | 说明 |
|------|----------|------|
| `scaled-url` | CloudFlare ImgBed 服务端 | 默认模式。优先使用 `?width={maxSide}&height={maxSide}&fallback=original`；QQ 失败后回退原 URL |
| `original-url` | 无 | 直接发送原图 URL，速度最快，但可能占用更多带宽 |
| `local-compress` | 插件本地 | 下载原图后经 Pillow 等比缩放并重编码为 JPEG |

`scaled-url` 不附加 `fit`：

- CloudFlare ImgBed 官方文档规定，同时设置 `width` 和 `height` 且不传 `fit` 时，二者是等比最大边界
- 因此 `width=1920&height=1920` 表示“最长边不超过 1920”，不会拉伸、不会裁剪、不会放大

`scaled-url` 也不附加 `quality`：

- CloudFlare ImgBed 读取 API 未提供 `quality` 参数
- `image.quality` 仅用于 `local-compress`

## 使用

### 获取随机图片

```text
/随机图
```

指定目录：

```text
/随机图 img/wallpaper
```

### 获取随机视频

```text
/随机视频
```

### 获取原图

```text
/原图
```

按文件名找回指定图片：

```text
/原图 Guerlain.jpg
/原图 Guerlain
```

`/原图` 始终发送未修改的原 URL，不受 `image.sendMode` 影响。

## 从 v1 升级到 v2

v2.0.0 对配置结构做了破坏性重构：

- 旧 `imgbedDomain` 等顶层配置会自动迁移为 `imgbed.*` 嵌套配置
- 旧 `showFileInfo`、`enableLLM` 迁移为 `message.*`
- 旧 `enableCompress`、`imageSendMode`、`compressMaxSide`、`compressQuality` 迁移为 `image.*`
- 旧 `imageSendMode=url` 且 `enableCompress=true` 迁移为 `image.sendMode=scaled-url`
- 旧 `imageSendMode=url` 且 `enableCompress=false` 迁移为 `image.sendMode=original-url`
- 旧 `imageSendMode=compress` 且 `enableCompress=true` 迁移为 `image.sendMode=local-compress`
- 旧 `imageSendMode=compress` 且 `enableCompress=false` 迁移为 `image.sendMode=original-url`

迁移会保留未识别的配置项，并写回 AstrBot 插件配置文件且输出 WARNING。写回失败时会恢复配置对象中的旧结构、本次运行继续使用内存中的迁移结果，下次启动会再次尝试迁移。建议升级后检查插件配置面板，确认旧键已被移除、新结构已生效。

## 故障排查

### `scaled-url` 返回 403

- 确认 ImgBed 后台已开启「图片尺寸处理」
- 确认允许尺寸包含当前 `image.maxSide` 对应组合，或保持留空以允许任意合法尺寸
- Cloudflare Pages 部署需绑定已接入 Cloudflare 的自定义域名

### `local-compress` 不生效

- 确认已安装 `Pillow`
- 检查 `image.enableProcessing` 是否开启
- 检查日志中是否有下载、解码或压缩失败信息

### QQ 聊天气泡显示 1:1

- 插件已按 NapCat `OB11MessageImage` 规范使用 URL 图片段
- `scaled-url` 会优先发送缩放 URL，失败后再尝试原 URL，最后进入本地字节回退
- AVIF/HEIC/SVG 等协议端无法解析宽高的格式会自动降级为本地压缩
- 若仍显示 1:1，检查日志是否出现两次「OneBot 直传图片失败」；这表示缩放 URL 与原 URL 均被协议端拒绝，消息已进入最后的字节回退
- 请升级 NapCat 到最新版本，或改用 `image.sendMode=original-url` 复测

### LLM 工具无法调用

- 确认 `message.enableLLM` 已开启
- 确认 AstrBot 已启用 LLM 工具调用能力

## 测试

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_main
```

质量检查：

```powershell
ruff format --check .
ruff check .
```

## 许可证

本项目基于 MIT 许可证发布，详见 [LICENSE](LICENSE)。
