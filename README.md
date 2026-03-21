# 随机图床插件

## 功能
- 调用随机图床API获取图片和视频
- 直接通过AstrBot发送到QQ群或好友
- 支持多种消息平台
- 支持LLM调用

## 安装
1. 将插件目录复制到AstrBot的 `data/plugins/` 目录
2. 运行 `pip install -r requirements.txt` 安装依赖
3. 重启AstrBot

## 配置
在AstrBot的插件管理界面中设置以下参数：

- `apiUrl`：随机图床API地址（默认：https://example.com）

## 使用
### 命令方式
在QQ群或私聊中发送：
```
/随机图
```

支持的命令别名：
- `/suijitu`
- `/random`

### LLM调用
LLM可以通过 `sendRandomMedia` 工具调用插件功能。

## 注意事项
- 确保网络连接正常，能够访问图床API
- 注意文件大小限制，避免发送过大的文件
- 支持的平台：QQ、Telegram、Discord等
