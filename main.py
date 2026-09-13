"""AstrBot CloudFlare ImgBed 随机图插件。

数据流：加载插件配置 → 请求图床随机接口
（GET {imgbedDomain}{apiEndpoint}?type=url&form=json[&dir=][&content=]）
→ 校验并解析返回的媒体 URL → 以「文件名文案 + 图片/视频」的形式在同一条消息中发送。

图片默认先由插件下载原图并经 Pillow 压缩（缩放 + JPEG 重编码）后以字节发送，
失败自动回退为 URL 直发；/原图 命令可找回本会话最近发送图片的原图。
"""

import asyncio
import io
import json
import re
from collections import OrderedDict
from typing import Optional
from urllib.parse import urljoin, urlparse, urlencode, unquote

import aiohttp
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import Image, Plain, Video
from astrbot.api.star import Context, Star, register

try:
    from PIL import Image as PILImage
    from PIL import ImageOps as PILImageOps
except ImportError:  # Pillow 未安装时压缩自动禁用，其余功能不受影响
    PILImage = None
    PILImageOps = None


# API 响应体大小上限，超过则视为异常响应并丢弃
MAX_RESPONSE_BYTES = 1024 * 1024
# 压缩模式下下载原图的大小上限，防止占满内存
MAX_IMAGE_BYTES = 30 * 1024 * 1024
# 原图字节数不超过该值时不重编码，避免小图画质受损
COMPRESS_MIN_BYTES = 200 * 1024
# 每个会话最多记录的图片历史条数 / 最多记录的会话数
MAX_HISTORY_PER_SESSION = 30
MAX_HISTORY_SESSIONS = 200
# 命令/LLM 工具允许的内容类型，以及用于从 URL 识别媒体类型的扩展名集合
ALLOWED_CONTENT_TYPES = {"image", "video"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".bmp", ".tif", ".tiff"}
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".wmv", ".flv", ".mkv", ".webm", ".m4v", ".3gp", ".ts"}
# QQ 协议端（NapCat 等）能从图片字节解析出宽高的格式集合；解析失败时协议端
# 会以固定 1024x1024 占位，QQ 聊天气泡里图片就显示成 1:1（点开查看才正常）
NAPCAT_PARSEABLE_FORMATS = frozenset({"JPEG", "PNG", "GIF", "WEBP", "BMP", "TIFF"})


@register("astrbot_plugin_cloudflare_imgbed_random", "diyushuang", "从CloudFlare ImgBed图床中获取随机图片", "1.3.1")
class CloudflareImgbedRandomPlugin(Star):
    def __init__(self, context: Context, config=None):
        super().__init__(context)
        self.config = config if config is not None else {}
        self._plugin_config_supplied = config is not None
        self.settings = {}
        # 会话图片历史：{unified_msg_origin: OrderedDict{文件名: 原图URL}}，供 /原图 命令找回
        self._image_history = {}

    async def initialize(self):
        await self._load_config()
        if self.settings.get("enableCompress") and PILImage is None:
            logger.warning("[astrbot_plugin_cloudflare_imgbed_random] 未安装 Pillow，图片压缩已禁用（可 pip install Pillow 后重启）")
        logger.info("[astrbot_plugin_cloudflare_imgbed_random] 插件初始化完成")

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

            show_file_info = config.get("showFileInfo", True)
            if isinstance(show_file_info, str):
                show_file_info = show_file_info.strip().lower() not in {"false", "0", "no", "off"}

            enable_compress = config.get("enableCompress", True)
            if isinstance(enable_compress, str):
                enable_compress = enable_compress.strip().lower() not in {"false", "0", "no", "off"}

            compress_max_side = config.get("compressMaxSide", 1920)
            try:
                compress_max_side = int(compress_max_side)
            except (TypeError, ValueError):
                compress_max_side = 1920
            compress_max_side = max(compress_max_side, 1)

            compress_quality = config.get("compressQuality", 85)
            try:
                compress_quality = int(compress_quality)
            except (TypeError, ValueError):
                compress_quality = 85
            compress_quality = min(max(compress_quality, 1), 100)

            self.settings = {
                "imgbedDomain": str(config.get("imgbedDomain") or "").strip(),
                "apiEndpoint": str(config.get("apiEndpoint") or "/random").strip(),
                "apiToken": str(config.get("apiToken") or "").strip(),
                "defaultDir": str(config.get("defaultDir") or "").strip(),
                "timeout": max(timeout, 0.1),
                "retryCount": max(retry_count, 0),
                "enableLLM": enable_llm,
                "showFileInfo": show_file_info,
                "enableCompress": enable_compress,
                "compressMaxSide": compress_max_side,
                "compressQuality": compress_quality,
            }
            self.config = config
            logger.info("[astrbot_plugin_cloudflare_imgbed_random] 配置加载成功")
        except Exception as exc:
            logger.error(f"[astrbot_plugin_cloudflare_imgbed_random] 加载配置失败: {exc}")
            self.settings = {
                "imgbedDomain": "",
                "apiEndpoint": "/random",
                "apiToken": "",
                "defaultDir": "",
                "timeout": 10.0,
                "retryCount": 3,
                "enableLLM": True,
                "showFileInfo": True,
                "enableCompress": True,
                "compressMaxSide": 1920,
                "compressQuality": 85,
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
            logger.error(f"[astrbot_plugin_cloudflare_imgbed_random] 提取消息文本失败: {exc}")
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
        """拼接图床随机接口地址。

        校验域名必须是合法 HTTP(S)、不含账号密码/查询参数/片段，接口路径必须是
        相对路径；任一条件不满足时记录错误日志并返回 None。
        """
        domain = self.settings.get("imgbedDomain", "").rstrip("/")
        endpoint = self.settings.get("apiEndpoint", "/random").strip()
        parsed_domain = urlparse(domain)
        if parsed_domain.scheme not in {"http", "https"} or not parsed_domain.netloc:
            logger.error("[astrbot_plugin_cloudflare_imgbed_random] 图床域名必须是有效的 HTTP(S) URL")
            return None
        if parsed_domain.username or parsed_domain.password:
            logger.error("[astrbot_plugin_cloudflare_imgbed_random] 图床域名不能包含账号或密码")
            return None
        if parsed_domain.query or parsed_domain.fragment:
            logger.error("[astrbot_plugin_cloudflare_imgbed_random] 图床域名不能包含查询参数或片段")
            return None
        if not endpoint:
            logger.error("[astrbot_plugin_cloudflare_imgbed_random] API接口路径为空")
            return None
        parsed_endpoint = urlparse(endpoint)
        if parsed_endpoint.scheme or parsed_endpoint.netloc:
            logger.error("[astrbot_plugin_cloudflare_imgbed_random] API接口必须是相对路径")
            return None
        return f"{domain}/{endpoint.lstrip('/')}"

    @staticmethod
    def _resolve_media_url(value: str, response_url: str) -> Optional[str]:
        """把 API 返回的媒体地址解析为绝对 URL。

        相对路径会以响应地址为基准拼接；仅接受合法 HTTP(S) 且不含账号密码的
        地址，其余一律返回 None。
        """
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

    @staticmethod
    def _extract_media_filename(media_url: str):
        """从媒体 URL 中提取文件名，无法识别时返回 None。"""
        try:
            path = unquote(urlparse(media_url).path)
            segments = [seg for seg in path.split("/") if seg]
            if segments and "." in segments[-1]:
                return segments[-1]
            return None
        except Exception:
            return None

    @staticmethod
    def _sniff_image_format(data: bytes) -> Optional[str]:
        """按文件头魔数识别图片格式，返回与 Pillow 一致的格式名（如 JPEG/PNG/AVIF）。

        不依赖 Pillow，用于在发送前判断字节能否被 QQ 协议端解析宽高；
        无法识别时返回 None。
        """
        if len(data) < 12:
            return None
        if data.startswith(b"\xff\xd8\xff"):
            return "JPEG"
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            return "PNG"
        if data.startswith((b"GIF87a", b"GIF89a")):
            return "GIF"
        if data.startswith(b"BM"):
            return "BMP"
        if data[:4] in (b"II*\x00", b"MM\x00*"):
            return "TIFF"
        if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return "WEBP"
        if data[4:8] == b"ftyp":
            brand = data[8:12]
            if brand.startswith(b"av"):
                return "AVIF"
            if brand in (b"heic", b"heix", b"hevc", b"mif1", b"msf1"):
                return "HEIF"
        stripped = data.lstrip(b" \t\r\n")
        if stripped.startswith((b"<svg", b"<?xml")):
            return "SVG"
        return None

    def _build_media_caption(self, media_url: str, kind: str) -> str:
        """构建随媒体一起发送的文案，附带文件名。"""
        default_caption = f"随机{kind}发送成功"
        if not self.settings.get("showFileInfo", True):
            return default_caption
        filename = self._extract_media_filename(media_url)
        if not filename:
            return default_caption
        icon = "🖼️" if kind == "图片" else "🎬"
        return f"{icon} {filename}"

    def _build_original_hint(self, media_url: str) -> str:
        """构建压缩图的原图提示，能识别文件名时给出可直接复制的命令示范。"""
        filename = self._extract_media_filename(media_url)
        if filename:
            return f"（已压缩，发送 /原图 {filename} 可获取原图）"
        return "（已压缩，发送 /原图 可获取原图）"

    @staticmethod
    def _get_session_key(event: AstrMessageEvent) -> str:
        """获取会话唯一标识，用于隔离 /原图 的图片历史。"""
        return str(getattr(event, "unified_msg_origin", None) or "default")

    def _remember_image(self, event: AstrMessageEvent, media_url: str):
        """把发送过的随机图片记入会话历史，供 /原图 命令找回。"""
        filename = self._extract_media_filename(media_url)
        if not filename:
            return
        history = self._image_history.setdefault(self._get_session_key(event), OrderedDict())
        history.pop(filename, None)
        history[filename] = media_url
        while len(history) > MAX_HISTORY_PER_SESSION:
            history.popitem(last=False)
        while len(self._image_history) > MAX_HISTORY_SESSIONS:
            self._image_history.pop(next(iter(self._image_history)))

    @staticmethod
    def _match_image_history(history, query: str):
        """按文件名在会话历史中查找图片。

        依次尝试精确文件名（忽略大小写）、不带扩展名的名字、唯一子串匹配；
        返回 (状态, 数据)：状态为 "found"（数据为 (文件名, URL)）、
        "ambiguous"（数据为候选文件名列表，需用户精确化）或 "missing"。
        """
        query = query.strip().lower()
        if not query:
            return "missing", None
        for filename, url in history.items():
            if filename.lower() == query:
                return "found", (filename, url)
        stem_matches = [
            (filename, url)
            for filename, url in history.items()
            if filename.rsplit(".", 1)[0].lower() == query.rsplit(".", 1)[0]
        ]
        if len(stem_matches) == 1:
            return "found", stem_matches[0]
        if stem_matches:
            return "ambiguous", [name for name, _ in stem_matches]
        substring_matches = [(filename, url) for filename, url in history.items() if query in filename.lower()]
        if len(substring_matches) == 1:
            return "found", substring_matches[0]
        if substring_matches:
            return "ambiguous", [name for name, _ in substring_matches]
        return "missing", None

    async def _download_image(self, media_url: str) -> Optional[bytes]:
        """下载原图字节流，失败或超过大小上限时返回 None。"""
        headers = {}
        if self.settings.get("apiToken"):
            # 仅当图片与图床同域时附带 Token，避免把鉴权信息发给第三方地址
            domain_host = urlparse(self.settings.get("imgbedDomain", "")).netloc
            if domain_host and urlparse(media_url).netloc == domain_host:
                headers["Authorization"] = self.settings["apiToken"]
        timeout = aiohttp.ClientTimeout(total=self.settings.get("timeout", 10.0))
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(media_url, allow_redirects=True, headers=headers, timeout=timeout) as response:
                    if response.status != 200:
                        logger.warning(f"[astrbot_plugin_cloudflare_imgbed_random] 图片下载失败，状态码: {response.status}")
                        return None
                    data = await response.content.read(MAX_IMAGE_BYTES + 1)
                    if len(data) > MAX_IMAGE_BYTES:
                        logger.warning("[astrbot_plugin_cloudflare_imgbed_random] 原图超过大小上限，跳过压缩")
                        return None
                    return data
        except (asyncio.TimeoutError, aiohttp.ClientError) as exc:
            logger.warning(f"[astrbot_plugin_cloudflare_imgbed_random] 图片下载失败: {exc}")
        except Exception as exc:
            logger.error(f"[astrbot_plugin_cloudflare_imgbed_random] 图片下载发生未预期错误: {exc}")
        return None

    def _prepare_image(self, data: bytes):
        """压缩图片字节流，返回 (待发送字节, 是否实际压缩)。

        动图不重编码（保留动画）；小图仅在协议端能解析宽高的格式下才沿用
        原字节；解码失败返回 None，由调用方回退为 URL 直发。
        """
        if not PILImage:
            return None
        try:
            with PILImage.open(io.BytesIO(data)) as img:
                if getattr(img, "is_animated", False):
                    return data, False
                original_format = (img.format or "").upper()
                if len(data) <= COMPRESS_MIN_BYTES and original_format in NAPCAT_PARSEABLE_FORMATS:
                    # 小图不值得重编码，避免无谓的画质损失；AVIF/HEIC 等协议端
                    # 解析不出宽高的格式例外，必须转成 JPEG，否则 QQ 聊天气泡
                    # 会以 1024x1024 占位显示成 1:1
                    return data, False
                # 依 EXIF Orientation 把旋转烘进像素，避免重编码丢元数据后方向错乱
                img = PILImageOps.exif_transpose(img)
                max_side = self.settings.get("compressMaxSide", 1920)
                width, height = img.size
                if max(width, height) > max_side:
                    scale = max_side / max(width, height)
                    img = img.resize((round(width * scale), round(height * scale)), PILImage.LANCZOS)
                if img.mode in ("RGBA", "LA", "P"):
                    rgba = img.convert("RGBA")
                    background = PILImage.new("RGB", rgba.size, (255, 255, 255))
                    background.paste(rgba, mask=rgba.split()[-1])
                    img = background
                elif img.mode != "RGB":
                    img = img.convert("RGB")
                output = io.BytesIO()
                img.save(output, format="JPEG", quality=self.settings.get("compressQuality", 85), optimize=True)
                compressed = output.getvalue()
        except Exception as exc:
            logger.warning(f"[astrbot_plugin_cloudflare_imgbed_random] 图片压缩失败: {exc}")
            return None
        if len(compressed) >= len(data) and original_format in NAPCAT_PARSEABLE_FORMATS:
            return data, False
        return compressed, True

    async def _get_sendable_image(self, media_url: str):
        """按配置下载并压缩图片，返回 (待发送字节, 是否压缩)。

        压缩关闭、Pillow 不可用或任一环节失败时返回 None，
        由调用方回退为 Image.fromURL 直发。
        """
        if not self.settings.get("enableCompress", True):
            return None
        data = await self._download_image(media_url)
        if data is None:
            return None
        prepared = await asyncio.to_thread(self._prepare_image, data)
        if prepared is None:
            # 解码失败回退 URL 直发，同样提示协议端宽高解析风险
            self._warn_qq_preview_risk(data)
        return prepared

    def _log_image_send(self, image_data: bytes, compressed: bool):
        """记录发送图片的格式与大小，便于排查 QQ 聊天气泡显示问题。"""
        logger.info(
            "[astrbot_plugin_cloudflare_imgbed_random] 发送图片: 格式=%s, %s, 大小=%.0fKB",
            self._sniff_image_format(image_data) or "未知",
            "已压缩" if compressed else "原样字节",
            len(image_data) / 1024,
        )
        self._warn_qq_preview_risk(image_data)

    def _warn_qq_preview_risk(self, image_data: bytes):
        """图片格式超出协议端（NapCat 等）宽高解析能力时，提示聊天气泡 1:1 风险。"""
        image_format = self._sniff_image_format(image_data)
        if image_format in NAPCAT_PARSEABLE_FORMATS:
            return
        logger.warning(
            "[astrbot_plugin_cloudflare_imgbed_random] 图片格式为 %s，QQ 协议端解析不出宽高，"
            "聊天气泡可能显示为 1:1 占位（点开查看正常）。建议升级 NapCat 到最新版，"
            "或让图床输出 JPEG/PNG 格式",
            image_format or "未知",
        )

    async def _get_random_media(self, directory=None, content_type=None):
        """获取并校验随机媒体 URL。

        带指数退避的重试机制；兼容三种响应形态：直接返回图片/视频
        （Content-Type 为 image/* 或 video/*）、JSON（顶层 url 或 data.url）、
        纯文本 URL。全部尝试失败时返回 None。
        """
        if not self.settings:
            await self._load_config()

        content_type = content_type.lower().strip() if isinstance(content_type, str) else None
        if content_type and content_type not in ALLOWED_CONTENT_TYPES:
            logger.warning(f"[astrbot_plugin_cloudflare_imgbed_random] 不支持的内容类型: {content_type}")
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
                logger.error("[astrbot_plugin_cloudflare_imgbed_random] 配置 Token 时必须使用 HTTPS")
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
                            logger.warning(f"[astrbot_plugin_cloudflare_imgbed_random] 请求失败，状态码: {response.status}")
                        else:
                            response_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
                            if response_type.startswith("image/") or response_type.startswith("video/"):
                                return str(response.url)

                            body = await response.content.read(MAX_RESPONSE_BYTES + 1)
                            if len(body) > MAX_RESPONSE_BYTES:
                                logger.warning("[astrbot_plugin_cloudflare_imgbed_random] API 响应超过大小限制")
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
                                logger.warning("[astrbot_plugin_cloudflare_imgbed_random] API 未返回有效媒体 URL")
                except (asyncio.TimeoutError, aiohttp.ClientError) as exc:
                    logger.warning(f"[astrbot_plugin_cloudflare_imgbed_random] 第{attempt + 1}次请求失败: {exc}")
                except Exception as exc:
                    logger.error(f"[astrbot_plugin_cloudflare_imgbed_random] 第{attempt + 1}次请求发生未预期错误: {exc}")

                if attempt < retry_count:
                    await asyncio.sleep(min(2 ** attempt, 8))

        logger.error(f"[astrbot_plugin_cloudflare_imgbed_random] 所有{retry_count + 1}次请求均失败")
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
        """处理随机媒体请求：解析消息中的目录/类型，获取媒体后按类型发送。

        文案由 _build_media_caption 生成（附带文件名），与图片/视频在
        同一条消息中发送；无法识别媒体类型时以纯文本回退。
        """
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
                self._remember_image(event, media_url)
                caption = self._build_media_caption(media_url, "图片")
                prepared = await self._get_sendable_image(media_url)
                if prepared is not None:
                    image_data, compressed = prepared
                    self._log_image_send(image_data, compressed)
                    if compressed:
                        caption += self._build_original_hint(media_url)
                    yield event.chain_result([Plain(caption), Image.fromBytes(image_data)])
                else:
                    yield event.chain_result([Plain(caption), Image.fromURL(media_url)])
            elif content_type == "video" or any(path.endswith(ext) for ext in VIDEO_EXTENSIONS):
                yield event.chain_result([Plain(self._build_media_caption(media_url, "视频")), Video.fromURL(media_url)])
            else:
                yield event.plain_result(f"随机媒体发送成功: {media_url}")
        except Exception as exc:
            logger.error(f"[astrbot_plugin_cloudflare_imgbed_random] 命令处理失败: {exc}")
            yield event.plain_result("处理随机媒体时出错，请稍后重试")

    @filter.command("原图")
    async def original_image(self, event: AstrMessageEvent):
        """重发随机图片的原图：不带参数取最近一张，可带文件名指定某一张。"""
        try:
            message = self._get_message_text(event) or ""
            match = re.search(r"原图\s*(.*)", message)
            query = (match.group(1) if match else "").strip(" \t:：,，")

            history = self._image_history.get(self._get_session_key(event))
            if not history:
                yield event.plain_result("本会话还没有发送过随机图片，请先使用 /随机图")
                return

            if query:
                status, payload = self._match_image_history(history, query)
                if status == "missing":
                    yield event.plain_result(f"没有找到「{query}」，只能找回本会话最近发送过的随机图片")
                    return
                if status == "ambiguous":
                    candidates = "、".join(payload[:5])
                    yield event.plain_result(f"匹配到多张图片，请写出更完整的文件名：{candidates}")
                    return
                filename, url = payload
            else:
                filename = next(reversed(history))
                url = history[filename]

            yield event.chain_result([Plain(self._build_media_caption(url, "图片") + "（原图）"), Image.fromURL(url)])
        except Exception as exc:
            logger.error(f"[astrbot_plugin_cloudflare_imgbed_random] 原图命令处理失败: {exc}")
            yield event.plain_result("处理原图请求时出错，请稍后重试")

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
            logger.error(f"[astrbot_plugin_cloudflare_imgbed_random] LLM工具调用失败: {exc}")
            yield event.plain_result("LLM工具调用失败，请稍后重试")

    async def terminate(self):
        logger.info("[astrbot_plugin_cloudflare_imgbed_random] 插件已卸载")
