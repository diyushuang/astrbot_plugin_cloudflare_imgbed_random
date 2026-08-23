import asyncio
import json
import re
from typing import Optional
from urllib.parse import urljoin, urlparse, urlencode

import aiohttp
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import Image, Plain, Video
from astrbot.api.star import Context, Star, register


MAX_RESPONSE_BYTES = 1024 * 1024
ALLOWED_CONTENT_TYPES = {"image", "video"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".bmp", ".tif", ".tiff"}
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".wmv", ".flv", ".mkv", ".webm", ".m4v", ".3gp", ".ts"}


@register("cloudflare_imgbed_random", "", "从CloudFlare ImgBed图床中获取随机图片", "1.1.0")
class CloudflareImgbedRandomPlugin(Star):
    def __init__(self, context: Context, config=None):
        super().__init__(context)
        self.config = config if config is not None else {}
        self._plugin_config_supplied = config is not None
        self.settings = {}

    async def initialize(self):
        await self._load_config()
        logger.info("[cloudflare_imgbed_random] 插件初始化完成")

    async def _load_config(self):
        """加载并规范化插件配置。"""
        try:
            config = self.config
            if not self._plugin_config_supplied:
                config = self.context.get_config() or {}

            timeout = config.get("timeout", 10)
            retry_count = config.get("retryCount", 3)
            try:
                timeout = float(timeout)
            except (TypeError, ValueError):
                timeout = 10.0
            try:
                retry_count = int(retry_count)
            except (TypeError, ValueError):
                retry_count = 3

            enable_llm = config.get("enableLLM", True)
            if isinstance(enable_llm, str):
                enable_llm = enable_llm.strip().lower() not in {"false", "0", "no", "off"}

            self.settings = {
                "imgbedDomain": str(config.get("imgbedDomain") or "").strip(),
                "apiEndpoint": str(config.get("apiEndpoint") or "/random").strip(),
                "apiToken": str(config.get("apiToken") or "").strip(),
                "defaultDir": str(config.get("defaultDir") or "").strip(),
                "timeout": max(timeout, 0.1),
                "retryCount": max(retry_count, 0),
                "enableLLM": enable_llm,
            }
            self.config = config
            logger.info("[cloudflare_imgbed_random] 配置加载成功")
        except Exception as exc:
            logger.error(f"[cloudflare_imgbed_random] 加载配置失败: {exc}")
            self.settings = {
                "imgbedDomain": "",
                "apiEndpoint": "/random",
                "apiToken": "",
                "defaultDir": "",
                "timeout": 10.0,
                "retryCount": 3,
                "enableLLM": True,
            }

    @staticmethod
    def _get_message_text(event: AstrMessageEvent) -> Optional[str]:
        """从事件中提取纯文本。"""
        try:
            if getattr(event, "message_str", None):
                return event.message_str
            message = getattr(event, "message", None)
            if isinstance(message, str):
                return message
            if message is not None and hasattr(message, "chain"):
                return " ".join(comp.text for comp in message.chain if hasattr(comp, "text"))
            if hasattr(event, "get_message"):
                message = event.get_message()
                if isinstance(message, str):
                    return message
            for attr in ("raw_message", "content", "text"):
                value = getattr(event, attr, None)
                if isinstance(value, str):
                    return value
        except Exception as exc:
            logger.error(f"[cloudflare_imgbed_random] 提取消息文本失败: {exc}")
        return None

    @staticmethod
    def _extract_directory(message: str):
        """从命令或自然语言中提取目录和内容类型。"""
        if not message:
            return None, None
        message = re.sub(r"\s+", " ", message.strip())

        command_match = re.match(r"^/(随机图|随机图片|随机视频)(?:\s+(.*))?$", message)
        if command_match:
            keyword, directory = command_match.groups()
            return (directory or "").strip(), "video" if keyword == "随机视频" else "image"

        keyword_match = re.search(r"随机视频|随机图片?|随机影片", message)
        if not keyword_match:
            return None, None
        keyword = keyword_match.group(0)
        directory = message[keyword_match.end():].strip(" \t:：,，")
        return directory, "video" if keyword in {"随机视频", "随机影片"} else "image"

    def _build_api_url(self) -> Optional[str]:
        domain = self.settings.get("imgbedDomain", "").rstrip("/")
        endpoint = self.settings.get("apiEndpoint", "/random").strip()
        parsed_domain = urlparse(domain)
        if parsed_domain.scheme not in {"http", "https"} or not parsed_domain.netloc:
            logger.error("[cloudflare_imgbed_random] 图床域名必须是有效的 HTTP(S) URL")
            return None
        if parsed_domain.username or parsed_domain.password:
            logger.error("[cloudflare_imgbed_random] 图床域名不能包含账号或密码")
            return None
        if parsed_domain.query or parsed_domain.fragment:
            logger.error("[cloudflare_imgbed_random] 图床域名不能包含查询参数或片段")
            return None
        if not endpoint:
            logger.error("[cloudflare_imgbed_random] API接口路径为空")
            return None
        parsed_endpoint = urlparse(endpoint)
        if parsed_endpoint.scheme or parsed_endpoint.netloc:
            logger.error("[cloudflare_imgbed_random] API接口必须是相对路径")
            return None
        return f"{domain}/{endpoint.lstrip('/')}"

    @staticmethod
    def _resolve_media_url(value: str, response_url: str) -> Optional[str]:
        if not isinstance(value, str):
            return None
        value = value.strip()
        if not value:
            return None
        media_url = urljoin(response_url, value)
        parsed = urlparse(media_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return None
        if parsed.username or parsed.password:
            return None
        return media_url

    async def _get_random_media(self, directory=None, content_type=None):
        """获取并校验随机媒体 URL。"""
        if not self.settings:
            await self._load_config()

        content_type = content_type.lower().strip() if isinstance(content_type, str) else None
        if content_type and content_type not in ALLOWED_CONTENT_TYPES:
            logger.warning(f"[cloudflare_imgbed_random] 不支持的内容类型: {content_type}")
            return None

        api_url = self._build_api_url()
        if not api_url:
            return None

        target_dir = directory.strip() if isinstance(directory, str) else directory
        if not target_dir:
            target_dir = self.settings.get("defaultDir", "").strip()
        params = {"type": "url", "form": "json"}
        if target_dir:
            params["dir"] = target_dir
        if content_type:
            params["content"] = content_type
        api_url = f"{api_url}{'&' if '?' in api_url else '?'}{urlencode(params)}"

        retry_count = self.settings.get("retryCount", 3)
        timeout = self.settings.get("timeout", 10.0)
        headers = {}
        if self.settings.get("apiToken"):
            if urlparse(api_url).scheme != "https":
                logger.error("[cloudflare_imgbed_random] 配置 Token 时必须使用 HTTPS")
                return None
            headers["Authorization"] = self.settings["apiToken"]

        async with aiohttp.ClientSession() as session:
            for attempt in range(retry_count + 1):
                try:
                    async with session.get(
                        api_url,
                        allow_redirects=True,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=timeout),
                    ) as response:
                        if response.status != 200:
                            logger.warning(f"[cloudflare_imgbed_random] 请求失败，状态码: {response.status}")
                        else:
                            response_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
                            if response_type.startswith("image/") or response_type.startswith("video/"):
                                return str(response.url)

                            body = await response.content.read(MAX_RESPONSE_BYTES + 1)
                            if len(body) > MAX_RESPONSE_BYTES:
                                logger.warning("[cloudflare_imgbed_random] API 响应超过大小限制")
                            else:
                                text = body.decode(response.charset or "utf-8", errors="replace").strip()
                                media_value = None
                                try:
                                    data = json.loads(text)
                                    if isinstance(data, dict):
                                        media_value = data.get("url")
                                        if not media_value and isinstance(data.get("data"), dict):
                                            media_value = data["data"].get("url")
                                except json.JSONDecodeError:
                                    media_value = text

                                media_url = self._resolve_media_url(media_value, str(response.url))
                                if media_url:
                                    return media_url
                                logger.warning("[cloudflare_imgbed_random] API 未返回有效媒体 URL")
                except (asyncio.TimeoutError, aiohttp.ClientError) as exc:
                    logger.warning(f"[cloudflare_imgbed_random] 第{attempt + 1}次请求失败: {exc}")
                except Exception as exc:
                    logger.error(f"[cloudflare_imgbed_random] 第{attempt + 1}次请求发生未预期错误: {exc}")

                if attempt < retry_count:
                    await asyncio.sleep(min(2 ** attempt, 8))

        logger.error(f"[cloudflare_imgbed_random] 所有{retry_count + 1}次请求均失败")
        return None

    @filter.command("随机图")
    async def random_image(self, event: AstrMessageEvent):
        """发送随机图片。"""
        async for result in self._handle_media(event, "image"):
            yield result

    @filter.command("随机视频")
    async def random_video(self, event: AstrMessageEvent):
        """发送随机视频。"""
        async for result in self._handle_media(event, "video"):
            yield result

    async def _handle_media(self, event: AstrMessageEvent, content_type=None, directory=None):
        try:
            message = self._get_message_text(event)
            parsed_directory, parsed_type = self._extract_directory(message) if message else (None, None)
            if directory is None and parsed_directory is not None:
                directory = parsed_directory
            if parsed_type:
                content_type = parsed_type

            media_url = await self._get_random_media(directory, content_type)
            if not media_url:
                yield event.plain_result("获取随机媒体失败，请检查配置或稍后重试")
                return

            path = urlparse(media_url).path.lower()
            if content_type == "image" or any(path.endswith(ext) for ext in IMAGE_EXTENSIONS):
                yield event.chain_result([Plain("随机图片发送成功"), Image.fromURL(media_url)])
            elif content_type == "video" or any(path.endswith(ext) for ext in VIDEO_EXTENSIONS):
                yield event.chain_result([Plain("随机视频发送成功"), Video.fromURL(media_url)])
            else:
                yield event.plain_result(f"随机媒体发送成功: {media_url}")
        except Exception as exc:
            logger.error(f"[cloudflare_imgbed_random] 命令处理失败: {exc}")
            yield event.plain_result("处理随机媒体时出错，请稍后重试")

    @filter.llm_tool(name="sendRandomMedia")
    async def send_random_media(
        self,
        event: AstrMessageEvent,
        directory: Optional[str] = None,
        content_type: Optional[str] = None,
    ):
        """发送随机图片或视频。

        当用户请求随机图片或视频时使用此工具。

        Args:
            directory(string): 目录路径，指定从哪个目录获取随机媒体，可选。
            content_type(string): 内容类型，可选值为 image 或 video，可选。
        """
        try:
            if not self.settings:
                await self._load_config()
            if not self.settings.get("enableLLM", True):
                yield event.plain_result("LLM调用已被禁用，请使用命令方式调用")
                return

            message = self._get_message_text(event)
            parsed_directory, parsed_type = self._extract_directory(message) if message else (None, None)
            if directory is None and parsed_directory:
                directory = parsed_directory
            if parsed_type:
                content_type = parsed_type
            content_type = (content_type or "image").strip().lower()
            async for result in self._handle_media(event, content_type, directory):
                yield result
        except Exception as exc:
            logger.error(f"[cloudflare_imgbed_random] LLM工具调用失败: {exc}")
            yield event.plain_result("LLM工具调用失败，请稍后重试")

    async def terminate(self):
        logger.info("[cloudflare_imgbed_random] 插件已卸载")
