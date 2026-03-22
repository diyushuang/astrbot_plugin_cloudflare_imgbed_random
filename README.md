# AstrBot CloudFlare ImgBed 随机图插件

<div align="center">

![AstrBot](https://img.shields.io/badge/AstrBot-%3E%3D4.16-blue)
![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
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
- 🔐 **API Token 鉴权**：支持需要鉴权的 API 接口
- 📁 **目录选择**：支持从指定目录获取随机媒体
- 🤖 **LLM 工具集成**：支持 AI 模型调用插件功能
- 🔄 **智能重试**：自动重试失败的请求，提高成功率
- 🌐 **相对路径处理**：自动处理 API 返回的相对路径 URL
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
git clone https://github.com/diyushuang/suijitu.git /path/to/astrbot/data/plugins/cloudflare_imgbed_random

# 重启 AstrBot
```

---

## ⚙️ 配置说明

安装完成后，需要在插件配置中设置以下参数：

### 必填配置

| 配置项 | 说明 | 示例 | 默认值 |
|--------|------|------|--------|
| `apiUrl` | CloudFlare ImgBed API 地址 | `https://your-domain/random` | `https://example.com` |

### 可选配置

| 配置项 | 说明 | 示例 | 默认值 |
|--------|------|------|--------|
| `apiToken` | API Token（如需鉴权） | `Bearer YOUR_API_TOKEN` | 空字符串 |
| `defaultDir` | 默认目录（相对路径） | `img/wallpaper` | 空字符串 |
| `timeout` | API 请求超时时间（秒） | `10` | `10` |
| `retryCount` | API 请求重试次数 | `3` | `3` |

---

## 📚 使用方法

### 命令使用

#### 基本用法

发送以下命令从默认目录获取随机图片：

```
随机图
/随机图
```

#### 指定目录

发送以下命令从指定目录获取随机图片：

```
随机图 img/wallpaper
/随机图 img/wallpaper
```

#### 支持的命令别名

- `随机图`
- `/随机图`
- `imgbed`
- `random`
- `随机图片`
- `randomimg`

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
| `directory` | string | 否 | 目录路径，指定从哪个目录获取随机图片 |

#### 返回格式

```json
{
  "success": true,
  "media_url": "https://your-domain/file/example.jpg",
  "message": "随机媒体发送成功"
}
```

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
| `type` | string | 返回内容类型：`img` 直接返回图片 |
| `form` | string | 响应格式：`text` 直接返回文本 |
| `orientation` | string | 图片方向筛选：`landscape`、`portrait`、`square`、`auto` |

### 响应格式

- **JSON 格式**：`{"url": "/file/example.jpg"}`
- **直接返回图片**：当 `type=img` 时
- **直接返回文本**：当 `form=text` 时

---

## 🛠️ 开发说明

### 项目结构

```
suijitu/
├── main.py              # 主程序文件
├── metadata.yaml        # 插件元数据
├── _conf_schema.json    # 配置 Schema
├── requirements.txt     # 依赖列表
└── README.md           # 项目文档
```

### 核心功能

1. **配置加载**：从 AstrBot 配置系统加载插件配置
2. **媒体获取**：通过 HTTP 请求获取随机媒体 URL
3. **命令处理**：处理用户发送的命令并返回结果
4. **LLM 工具**：注册 LLM 工具供 AI 模型调用

### 技术栈

- **Python 3.8+**
- **aiohttp**：异步 HTTP 客户端
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

---

## 📝 更新日志

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

- **GitHub Issues**: [https://github.com/diyushuang/suijitu/issues](https://github.com/diyushuang/suijitu/issues)
- **项目地址**: [https://github.com/diyushuang/suijitu](https://github.com/diyushuang/suijitu)

---

## 🙏 致谢

- [AstrBot](https://github.com/Soulter/AstrBot) - 优秀的机器人框架
- [CloudFlare ImgBed](https://cfbed.sanyue.de/) - 稳定的图床服务
- 所有贡献者和用户

---

<div align="center">

**如果这个项目对你有帮助，请给一个 ⭐ Star 支持一下！**

</div>
