# CloudFlare ImgBed 随机图插件

## 项目介绍

CloudFlare ImgBed 随机图插件是一个为 AstrBot 设计的插件，用于从 CloudFlare ImgBed 图床中获取随机图片并发送到聊天平台。

### 主要功能

- 从 CloudFlare ImgBed 图床获取随机图片
- 支持 API Token 鉴权
- 支持从指定目录获取随机图片
- 支持自动处理相对路径 URL
- 支持图片和视频发送
- 支持 LLM 工具调用
- 完善的错误处理和日志记录

## 安装方法

### 方法一：通过 AstrBot 插件市场安装
1. 打开 AstrBot 管理面板
2. 进入「插件管理」页面
3. 搜索「CloudFlare ImgBed随机图」
4. 点击「安装」按钮

### 方法二：手动安装
1. 克隆本项目到 AstrBot 的插件目录
   ```bash
   git clone https://github.com/diyushuang/suijitu.git /path/to/astrbot/data/plugins/cloudflare_imgbed_random
   ```
2. 重启 AstrBot

## 配置说明

安装完成后，需要在插件配置中设置以下参数：

### 1. API 地址
- **配置项**：`apiUrl`
- **说明**：CloudFlare ImgBed 的随机图 API 端点地址
- **示例**：`https://your-domain/random`
- **默认值**：`https://example.com`

### 2. API Token（可选）
- **配置项**：`apiToken`
- **说明**：如果 API 需要鉴权，填写 API Token
- **格式**：`Bearer YOUR_API_TOKEN`
- **默认值**：空字符串

### 3. 默认目录（可选）
- **配置项**：`defaultDir`
- **说明**：设置默认获取图片的目录，使用相对路径
- **示例**：`img/wallpaper`
- **默认值**：空字符串

### 4. 超时时间
- **配置项**：`timeout`
- **说明**：API 请求超时时间（秒）
- **默认值**：`10`

### 5. 重试次数
- **配置项**：`retryCount`
- **说明**：API 请求失败后的重试次数
- **默认值**：`3`

## 使用方法

### 命令使用

#### 基本用法
发送 `随机图` 命令，从默认目录获取随机图片：
```
随机图
```

#### 指定目录
发送 `随机图 目录路径` 命令，从指定目录获取随机图片：
```
随机图 img/wallpaper
```

### LLM 工具调用

插件注册了 `sendRandomMedia` 工具，可以被 LLM 调用：

```python
# 调用示例
result = await sendRandomMedia(directory="img/wallpaper")

# 返回结果
{
  "success": true,
  "media_url": "https://your-domain/file/example.jpg",
  "message": "随机媒体发送成功"
}
```

## API 文档参考

本插件基于 CloudFlare ImgBed 的随机图 API 开发，参考文档：
- [随机图 API](https://cfbed.sanyue.de/api/random.html)
- [API 基本介绍](https://cfbed.sanyue.de/api/)

### API 端点
- 随机图 API：`/random`

### 请求参数
- `dir`：指定目录，使用相对路径
- `content`：文件类型过滤，可选值有 `image, video`
- `type`：返回内容类型，设为 `img` 时直接返回图片
- `form`：响应格式，设为 `text` 时直接返回文本
- `orientation`：图片方向筛选，可选值：`landscape`、`portrait`、`square`、`auto`

### 响应格式
- JSON 格式：`{"url": "/file/example.jpg"}`
- 直接返回图片：当 `type=img` 时
- 直接返回文本：当 `form=text` 时

## 常见问题

### 1. 无法获取图片
- 检查 API 地址是否正确
- 检查 API Token 是否有效（如果需要）
- 检查网络连接是否正常

### 2. 图片显示为文本
- 检查 API 响应格式是否为 JSON
- 检查 API 返回的 URL 是否为相对路径

### 3. 目录参数不生效
- 检查目录路径是否正确
- 检查 CloudFlare ImgBed 是否支持目录参数

## 日志说明

插件会在 AstrBot 的日志中输出以下格式的日志：
```
[cloudflare_imgbed_random] 插件初始化完成
[cloudflare_imgbed_random] 插件加载完成
[cloudflare_imgbed_random] 获取随机媒体成功: https://your-domain/file/example.jpg
```

## 版本历史

- **v1.0.0**：
  - 初始版本
  - 支持从 CloudFlare ImgBed 获取随机图片
  - 支持 API Token 鉴权
  - 支持指定目录获取图片
  - 支持 LLM 工具调用

## 许可证

本项目采用 MIT 许可证。

## 联系方式

如果有任何问题或建议，欢迎提交 Issue 或 Pull Request。