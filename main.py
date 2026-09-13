"""AstrBot CloudFlare ImgBed 随机图插件。

数据流：加载插件配置 → 请求图床随机接口
（GET {imgbed.domain}{imgbed.apiEndpoint}?type=url&form=json[&dir=][&content=]）
→ 校验并解析返回的媒体 URL → 以「文件名文案 + 图片/视频」的形式在同一条消息中发送。

图片默认使用 scaled-url 模式：在 aiocqhttp（QQ）平台把 CloudFlare ImgBed
官方 width/height/fallback 缩放 URL 交给协议端（NapCat 等）发送；其余平台与
失败情形回退为标准消息链。original-url 直传原图，local-compress 下载后经
Pillow 压缩。/原图 命令始终重发未修改的原 URL。
"""

import asyncio
import io
import json
import re
from collections import OrderedDict
from urllib.parse import (
    parse_qsl,
    unquote,
    urlencode,
    urljoin,
    urlparse,
    urlsplit,
    urlunsplit,
)

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
IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".avif",
    ".bmp",
    ".tif",
    ".tiff",
}
VIDEO_EXTENSIONS = {
    ".mp4",
    ".avi",
    ".mov",
    ".wmv",
    ".flv",
    ".mkv",
    ".webm",
    ".m4v",
    ".3gp",
    ".ts",
}
# QQ 协议端（NapCat 等）能从图片字节解析出宽高的格式集合；解析失败时协议端
# 会以固定 1024x1024 占位，QQ 聊天气泡里图片就显示成 1:1（点开查看才正常）
NAPCAT_PARSEABLE_FORMATS = frozenset({"JPEG", "PNG", "GIF", "WEBP", "BMP", "TIFF"})
# 与 NAPCAT_PARSEABLE_FORMATS 对应的扩展名；URL 直传时据此判断协议端能否解析宽高，
# 其余扩展名（.avif/.heic/.svg 等）降级为下载压缩转 JPEG 后发送
NAPCAT_PARSEABLE_EXTENSIONS = frozenset(
    {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tif", ".tiff"}
)
# 图片发送模式：
# scaled-url=通过 ImgBed 官方尺寸参数发送等比缩放图（默认）
# original-url=直接发送原图 URL
# local-compress=插件下载后本地压缩
IMAGE_SEND_MODES = {"scaled-url", "original-url", "local-compress"}
IMGBED_MANAGED_QUERY_KEYS = {"width", "height", "fit", "fallback"}
# 走 OneBot 原生接口直传的平台名，其余平台一律使用标准消息链发送
AIOCQHTTP_PLATFORM_NAME = "aiocqhttp"
LEGACY_CONFIG_KEYS = {
    "imgbedDomain",
    "apiEndpoint",
    "apiToken",
    "defaultDir",
    "timeout",
    "retryCount",
    "showFileInfo",
    "enableLLM",
    "enableCompress",
    "imageSendMode",
    "compressMaxSide",
    "compressQuality",
}


def _as_bool(value, default=True):
    if isinstance(value, str):
        return value.strip().lower() not in {"false", "0", "no", "off"}
    if isinstance(value, bool):
        return value
    return default


def _as_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _bounded_int(value, default, minimum, maximum):
    number = _as_int(value, default)
    return min(max(number, minimum), maximum)


def _default_settings():
    return {
        "imgbed": {
            "domain": "",
            "apiEndpoint": "/random",
            "apiToken": "",
            "defaultDir": "",
            "timeout": 10.0,
            "retryCount": 3,
        },
        "message": {
            "showFileInfo": True,
            "enableLLM": True,
        },
        "image": {
            "sendMode": "scaled-url",
            "enableProcessing": True,
            "maxSide": 1920,
            "quality": 85,
        },
    }


def _migrate_legacy_config(config):
    """把 v1 顶层配置迁移为 v2 嵌套配置；新键优先，旧键只补缺。"""
    if not isinstance(config, dict):
        return config, False
    if not any(key in config for key in LEGACY_CONFIG_KEYS):
        return config, False

    migrated = dict(config)
    for section in ("imgbed", "message", "image"):
        migrated[section] = dict(config.get(section) or {})
    simple_mappings = {
        "imgbed": {
            "imgbedDomain": "domain",
            "apiEndpoint": "apiEndpoint",
            "apiToken": "apiToken",
            "defaultDir": "defaultDir",
            "timeout": "timeout",
            "retryCount": "retryCount",
        },
        "message": {
            "showFileInfo": "showFileInfo",
            "enableLLM": "enableLLM",
        },
        "image": {
            "enableCompress": "enableProcessing",
            "compressMaxSide": "maxSide",
            "compressQuality": "quality",
        },
    }
    for section, mapping in simple_mappings.items():
        for old_key, new_key in mapping.items():
            if old_key in config and new_key not in migrated[section]:
                migrated[section][new_key] = config[old_key]

    if "imageSendMode" in config and "sendMode" not in migrated["image"]:
        old_mode = str(config.get("imageSendMode") or "").strip().lower()
        enable_processing = _as_bool(config.get("enableCompress", True), True)
        if old_mode == "compress":
            migrated["image"]["sendMode"] = (
                "local-compress" if enable_processing else "original-url"
            )
        elif old_mode == "url":
            migrated["image"]["sendMode"] = "scaled-url" if enable_processing else "original-url"
    for old_key in LEGACY_CONFIG_KEYS:
        migrated.pop(old_key, None)
    return migrated, True


@register(
    "astrbot_plugin_cloudflare_imgbed_random",
    "diyushuang",
    "从CloudFlare ImgBed图床中获取随机图片",
    "2.0.0",
)
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
        image_settings = self.settings.get("image", {})
        if image_settings.get("enableProcessing") and PILImage is None:
            logger.warning(
                "[astrbot_plugin_cloudflare_imgbed_random] 未安装 Pillow，"
                "local-compress 与 scaled-url 的本地降级压缩不可用（可 pip install Pillow 后重启）"
            )
        logger.info("[astrbot_plugin_cloudflare_imgbed_random] 插件初始化完成")

    @staticmethod
    def _persist_migrated_config(config, migrated_config):
        """把迁移结果写回传入的 AstrBot 配置对象，失败时恢复原内容。"""
        original_items = list(config.items())
        config.clear()
        config.update(migrated_config)
        save_config = getattr(config, "save_config", None)
        if callable(save_config):
            try:
                save_config()
            except Exception as exc:
                config.clear()
                config.update(original_items)
                logger.warning(
                    f"[astrbot_plugin_cloudflare_imgbed_random] v1 配置已迁移，但写回配置文件失败: {exc}"
                )

    async def _load_config(self):
        """加载并规范化插件配置。"""
        try:
            config = self.config
            if not self._plugin_config_supplied:
                config = self.context.get_config() or {}
            migrated_config, migrated = _migrate_legacy_config(config)
            if migrated:
                if self._plugin_config_supplied and isinstance(config, dict):
                    self._persist_migrated_config(config, migrated_config)
                config = migrated_config

            imgbed_config = config.get("imgbed") or {}
            message_config = config.get("message") or {}
            image_config = config.get("image") or {}

            timeout = _as_float(imgbed_config.get("timeout", 10), 10.0)
            retry_count = _as_int(imgbed_config.get("retryCount", 3), 3)
            image_send_mode = str(image_config.get("sendMode") or "scaled-url").strip().lower()
            if image_send_mode not in IMAGE_SEND_MODES:
                image_send_mode = "scaled-url"
            max_side = _bounded_int(image_config.get("maxSide", 1920), 1920, 1, 4096)
            quality = _bounded_int(image_config.get("quality", 85), 85, 1, 100)

            self.settings = {
                "imgbed": {
                    "domain": str(imgbed_config.get("domain") or "").strip(),
                    "apiEndpoint": str(imgbed_config.get("apiEndpoint") or "/random").strip(),
                    "apiToken": str(imgbed_config.get("apiToken") or "").strip(),
                    "defaultDir": str(imgbed_config.get("defaultDir") or "").strip(),
                    "timeout": max(timeout, 0.1),
                    "retryCount": max(retry_count, 0),
                },
                "message": {
                    "enableLLM": _as_bool(message_config.get("enableLLM", True), True),
                    "showFileInfo": _as_bool(message_config.get("showFileInfo", True), True),
                },
                "image": {
                    "sendMode": image_send_mode,
                    "enableProcessing": _as_bool(image_config.get("enableProcessing", True), True),
                    "maxSide": max_side,
                    "quality": quality,
                },
            }
            if migrated:
                logger.warning(
                    "[astrbot_plugin_cloudflare_imgbed_random] 检测到 v1 配置结构，已自动迁移为 v2 嵌套配置"
                )
            logger.info("[astrbot_plugin_cloudflare_imgbed_random] 配置加载成功")
        except Exception as exc:
            logger.error(f"[astrbot_plugin_cloudflare_imgbed_random] 加载配置失败: {exc}")
            self.settings = _default_settings()

    @staticmethod
    def _get_message_text(event: AstrMessageEvent) -> str | None:
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
        directory = message[keyword_match.end() :].strip(" \t:：,，")
        return directory, "video" if keyword in {"随机视频", "随机影片"} else "image"

    def _build_api_url(self) -> str | None:
        """拼接图床随机接口地址。

        校验域名必须是合法 HTTP(S)、不含账号密码/查询参数/片段，接口路径必须是
        相对路径；任一条件不满足时记录错误日志并返回 None。
        """
        imgbed_settings = self.settings.get("imgbed", {})
        domain = imgbed_settings.get("domain", "").rstrip("/")
        endpoint = imgbed_settings.get("apiEndpoint", "/random").strip()
        parsed_domain = urlparse(domain)
        if parsed_domain.scheme not in {"http", "https"} or not parsed_domain.netloc:
            logger.error(
                "[astrbot_plugin_cloudflare_imgbed_random] 图床域名必须是有效的 HTTP(S) URL"
            )
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
    def _resolve_media_url(value: str, response_url: str) -> str | None:
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

    def _build_scaled_media_url(self, media_url: str) -> str:
        """按 CloudFlare ImgBed 官方读取 API 生成等比缩放 URL。

        同时设置 width 和 height 且不传 fit 时，二者是等比最大边界；
        fallback=original 仅在处理失败或格式不支持时兜底返回原文件。
        """
        max_side = _bounded_int(self.settings.get("image", {}).get("maxSide", 1920), 1920, 1, 4096)
        parsed = urlsplit(media_url)
        query = [
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if key.lower() not in IMGBED_MANAGED_QUERY_KEYS
        ]
        query.extend(
            [
                ("width", str(max_side)),
                ("height", str(max_side)),
                ("fallback", "original"),
            ]
        )
        return urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                urlencode(query),
                parsed.fragment,
            )
        )

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
    def _sniff_image_format(data: bytes) -> str | None:
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
        if not self.settings.get("message", {}).get("showFileInfo", True):
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
        substring_matches = [
            (filename, url) for filename, url in history.items() if query in filename.lower()
        ]
        if len(substring_matches) == 1:
            return "found", substring_matches[0]
        if substring_matches:
            return "ambiguous", [name for name, _ in substring_matches]
        return "missing", None

    async def _download_image(self, media_url: str) -> bytes | None:
        """下载原图字节流，失败或超过大小上限时返回 None。"""
        headers = {}
        imgbed_settings = self.settings.get("imgbed", {})
        if imgbed_settings.get("apiToken"):
            # 仅当图片与图床同域时附带 Token，避免把鉴权信息发给第三方地址
            domain_host = urlparse(imgbed_settings.get("domain", "")).netloc
            if domain_host and urlparse(media_url).netloc == domain_host:
                headers["Authorization"] = imgbed_settings["apiToken"]
        timeout = aiohttp.ClientTimeout(total=imgbed_settings.get("timeout", 10.0))
        try:
            async with (
                aiohttp.ClientSession() as session,
                session.get(
                    media_url, allow_redirects=True, headers=headers, timeout=timeout
                ) as response,
            ):
                if response.status != 200:
                    logger.warning(
                        f"[astrbot_plugin_cloudflare_imgbed_random] 图片下载失败，状态码: {response.status}"
                    )
                    return None
                data = await response.content.read(MAX_IMAGE_BYTES + 1)
                if len(data) > MAX_IMAGE_BYTES:
                    logger.warning(
                        "[astrbot_plugin_cloudflare_imgbed_random] 原图超过大小上限，跳过压缩"
                    )
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
                image_settings = self.settings.get("image", {})
                max_side = _bounded_int(image_settings.get("maxSide", 1920), 1920, 1, 4096)
                width, height = img.size
                if max(width, height) > max_side:
                    scale = max_side / max(width, height)
                    img = img.resize(
                        (round(width * scale), round(height * scale)), PILImage.LANCZOS
                    )
                if img.mode in ("RGBA", "LA", "P"):
                    rgba = img.convert("RGBA")
                    background = PILImage.new("RGB", rgba.size, (255, 255, 255))
                    background.paste(rgba, mask=rgba.split()[-1])
                    img = background
                elif img.mode != "RGB":
                    img = img.convert("RGB")
                output = io.BytesIO()
                img.save(
                    output,
                    format="JPEG",
                    quality=_bounded_int(image_settings.get("quality", 85), 85, 1, 100),
                    optimize=True,
                )
                compressed = output.getvalue()
        except Exception as exc:
            logger.warning(f"[astrbot_plugin_cloudflare_imgbed_random] 图片压缩失败: {exc}")
            return None
        if len(compressed) >= len(data) and original_format in NAPCAT_PARSEABLE_FORMATS:
            return data, False
        return compressed, True

    async def _get_sendable_image(
        self,
        media_url: str,
        *,
        allow_processing: bool = True,
        raw_fallback: bool = False,
    ):
        """按配置下载并压缩图片，返回 (待发送字节, 是否压缩)。

        压缩关闭、Pillow 不可用或下载失败时返回 None，由调用方回退为
        Image.fromURL 直发；raw_fallback=True 时解码失败改为返回原字节。
        """
        if allow_processing and not self.settings.get("image", {}).get("enableProcessing", True):
            return None
        data = await self._download_image(media_url)
        if data is None:
            return None
        if not allow_processing:
            return data, False
        prepared = await asyncio.to_thread(self._prepare_image, data)
        if prepared is None:
            self._warn_qq_preview_risk(data)
            if raw_fallback:
                return data, False
        return prepared

    @staticmethod
    def _is_napcat_parseable_url(media_url: str) -> bool:
        """判断 URL 指向的图片格式能否被 QQ 协议端解析出宽高。

        扩展名不在白名单内（.avif/.heic/.svg 等）时返回 False，由调用方降级为
        下载压缩转 JPEG，避免协议端解析失败后以 1024x1024 占位显示成 1:1。
        """
        try:
            path = unquote(urlparse(media_url).path).lower()
        except Exception:
            return False
        return any(path.endswith(ext) for ext in NAPCAT_PARSEABLE_EXTENSIONS)

    def _can_send_via_onebot(self, event: AstrMessageEvent) -> bool:
        """仅 aiocqhttp 平台且拿得到 bot 实例时才能走 OneBot 原生直传。"""
        try:
            if event.get_platform_name() != AIOCQHTTP_PLATFORM_NAME:
                return False
        except Exception:
            return False
        return getattr(event, "bot", None) is not None

    def _normalize_onebot_media_url(self, media_url: str) -> str:
        """OneBot 直传前把同域 HTTP 地址升级为配置域名的 HTTPS 形式。

        部分 ImgBed API 会返回 HTTP 地址，NapCat 下载时需要跟随 301 到
        HTTPS；直接使用 HTTPS 可减少一次跳转，也避免个别协议端在跳转时
        丢失查询参数或被 CDN 拒绝。
        """
        try:
            domain = urlparse(self.settings.get("imgbed", {}).get("domain", ""))
            media = urlparse(media_url)
        except Exception:
            return media_url
        if (
            domain.scheme == "https"
            and media.scheme == "http"
            and media.netloc.lower() == domain.netloc.lower()
        ):
            return urlunsplit(("https", media.netloc, media.path, media.query, media.fragment))
        return media_url

    async def _send_via_onebot(self, event: AstrMessageEvent, caption: str, media_url: str) -> bool:
        """用 OneBot 原生接口直接发送带 URL 的图片段，成功返回 True。

        绕开 AstrBot 的 Image 组件：aiocqhttp 适配器会把所有 Image 段统一转成
        base64 再发给协议端，协议端只能从字节里嗅探宽高，失败就以 1024x1024
        占位、QQ 聊天气泡显示成 1:1。直接下发 http URL 可让协议端自行下载并
        解析出真实宽高，同时省去插件侧下载与 base64 膨胀的开销。
        """
        message = []
        if caption:
            message.append({"type": "text", "data": {"text": caption + "\n"}})
        message.append({"type": "image", "data": {"file": media_url}})

        params = {"message": message}
        group_id = event.get_group_id()
        if group_id:
            action = "send_group_msg"
            params["group_id"] = int(group_id) if str(group_id).isdigit() else group_id
        else:
            action = "send_private_msg"
            user_id = event.get_sender_id()
            params["user_id"] = int(user_id) if str(user_id).isdigit() else user_id
        # 与适配器保持一致：多号登录时透传 self_id，避免消息从错误的账号发出
        self_id = getattr(event.message_obj, "self_id", None)
        if self_id:
            params["self_id"] = self_id

        try:
            await event.bot.call_action(action, **params)
        except Exception as exc:
            logger.warning(
                f"[astrbot_plugin_cloudflare_imgbed_random] OneBot 直传图片失败，回退消息链发送: {exc}"
            )
            return False
        logger.info(f"[astrbot_plugin_cloudflare_imgbed_random] 已直传图片 URL 给协议端: {action}")
        return True

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

    async def _send_image(
        self,
        event: AstrMessageEvent,
        caption: str,
        media_url: str,
        force_url: bool = False,
    ):
        """统一的图片发送入口，/随机图 与 /原图 共用。

        scaled-url：使用 ImgBed 官方 width/height/fallback 参数发送等比缩放图。
        original-url：直传原 URL，不追加压缩提示。
        local-compress：下载后经 Pillow 压缩。
        force_url=True 供 /原图 使用，始终直传原 URL。
        """
        image_settings = self.settings.get("image", {})
        send_mode = image_settings.get("sendMode", "scaled-url")
        target_url = media_url
        base_caption = caption

        if (
            force_url
            or send_mode == "scaled-url"
            and not image_settings.get("enableProcessing", True)
        ):
            send_mode = "original-url"

        # AVIF/HEIC/SVG 等协议端解析不出宽高，scaled-url 下降级为本地压缩转 JPEG
        if send_mode == "scaled-url" and not self._is_napcat_parseable_url(media_url):
            logger.info(
                "[astrbot_plugin_cloudflare_imgbed_random] URL 格式协议端无法解析宽高，降级为压缩发送"
            )
            send_mode = "local-compress"

        if send_mode == "scaled-url":
            target_url = self._build_scaled_media_url(media_url)
            caption += self._build_original_hint(media_url)

        if send_mode in {"scaled-url", "original-url"}:
            onebot_attempted = False
            if self._can_send_via_onebot(event):
                onebot_attempted = True
                original_url = self._normalize_onebot_media_url(media_url)
                direct_candidates = [(base_caption, original_url)]
                if target_url != original_url:
                    direct_candidates.append((caption, target_url))
                for direct_caption, direct_url in direct_candidates:
                    if await self._send_via_onebot(event, direct_caption, direct_url):
                        event.stop_event()
                        return

            if onebot_attempted:
                prepared = await self._get_sendable_image(
                    media_url,
                    allow_processing=send_mode == "scaled-url",
                    raw_fallback=True,
                )
                if prepared is not None:
                    image_data, compressed = prepared
                    self._log_image_send(image_data, compressed)
                    if send_mode == "scaled-url" and compressed:
                        fallback_caption = base_caption + self._build_original_hint(media_url)
                    else:
                        fallback_caption = base_caption
                    yield event.chain_result([Plain(fallback_caption), Image.fromBytes(image_data)])
                    return
                logger.warning(
                    "[astrbot_plugin_cloudflare_imgbed_random] 本地字节回退失败，最后回退消息链 URL"
                )

            yield event.chain_result([Plain(caption), Image.fromURL(target_url)])
            return

        prepared = await self._get_sendable_image(media_url)
        if prepared is None:
            yield event.chain_result([Plain(caption), Image.fromURL(media_url)])
            return
        image_data, compressed = prepared
        self._log_image_send(image_data, compressed)
        if compressed:
            caption += self._build_original_hint(media_url)
        yield event.chain_result([Plain(caption), Image.fromBytes(image_data)])

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
            logger.warning(
                f"[astrbot_plugin_cloudflare_imgbed_random] 不支持的内容类型: {content_type}"
            )
            return None

        api_url = self._build_api_url()
        if not api_url:
            return None

        imgbed_settings = self.settings.get("imgbed", {})
        target_dir = directory.strip() if isinstance(directory, str) else directory
        if not target_dir:
            target_dir = imgbed_settings.get("defaultDir", "").strip()
        params = {"type": "url", "form": "json"}
        if target_dir:
            params["dir"] = target_dir
        if content_type:
            params["content"] = content_type
        api_url = f"{api_url}{'&' if '?' in api_url else '?'}{urlencode(params)}"

        retry_count = imgbed_settings.get("retryCount", 3)
        timeout = imgbed_settings.get("timeout", 10.0)
        headers = {}
        if imgbed_settings.get("apiToken"):
            if urlparse(api_url).scheme != "https":
                logger.error(
                    "[astrbot_plugin_cloudflare_imgbed_random] 配置 Token 时必须使用 HTTPS"
                )
                return None
            headers["Authorization"] = imgbed_settings["apiToken"]

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
                            logger.warning(
                                f"[astrbot_plugin_cloudflare_imgbed_random] 请求失败，状态码: {response.status}"
                            )
                        else:
                            response_type = (
                                response.headers.get("Content-Type", "").split(";", 1)[0].lower()
                            )
                            if response_type.startswith(("image/", "video/")):
                                return str(response.url)

                            body = await response.content.read(MAX_RESPONSE_BYTES + 1)
                            if len(body) > MAX_RESPONSE_BYTES:
                                logger.warning(
                                    "[astrbot_plugin_cloudflare_imgbed_random] API 响应超过大小限制"
                                )
                            else:
                                text = body.decode(
                                    response.charset or "utf-8", errors="replace"
                                ).strip()
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
                                logger.warning(
                                    "[astrbot_plugin_cloudflare_imgbed_random] API 未返回有效媒体 URL"
                                )
                except (asyncio.TimeoutError, aiohttp.ClientError) as exc:
                    logger.warning(
                        f"[astrbot_plugin_cloudflare_imgbed_random] 第{attempt + 1}次请求失败: {exc}"
                    )
                except Exception as exc:
                    logger.error(
                        f"[astrbot_plugin_cloudflare_imgbed_random] 第{attempt + 1}次请求发生未预期错误: {exc}"
                    )

                if attempt < retry_count:
                    await asyncio.sleep(min(2**attempt, 8))

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
            parsed_directory, parsed_type = (
                self._extract_directory(message) if message else (None, None)
            )
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
                async for result in self._send_image(event, caption, media_url):
                    yield result
            elif content_type == "video" or any(path.endswith(ext) for ext in VIDEO_EXTENSIONS):
                yield event.chain_result(
                    [
                        Plain(self._build_media_caption(media_url, "视频")),
                        Video.fromURL(media_url),
                    ]
                )
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
                    yield event.plain_result(
                        f"没有找到「{query}」，只能找回本会话最近发送过的随机图片"
                    )
                    return
                if status == "ambiguous":
                    candidates = "、".join(payload[:5])
                    yield event.plain_result(f"匹配到多张图片，请写出更完整的文件名：{candidates}")
                    return
                filename, url = payload
            else:
                filename = next(reversed(history))
                url = history[filename]

            caption = self._build_media_caption(url, "图片") + "（原图）"
            async for result in self._send_image(event, caption, url, force_url=True):
                yield result
        except Exception as exc:
            logger.error(f"[astrbot_plugin_cloudflare_imgbed_random] 原图命令处理失败: {exc}")
            yield event.plain_result("处理原图请求时出错，请稍后重试")

    @filter.llm_tool(name="sendRandomMedia")
    async def send_random_media(
        self,
        event: AstrMessageEvent,
        directory: str | None = None,
        content_type: str | None = None,
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
            if not self.settings.get("message", {}).get("enableLLM", True):
                yield event.plain_result("LLM调用已被禁用，请使用命令方式调用")
                return

            message = self._get_message_text(event)
            parsed_directory, parsed_type = (
                self._extract_directory(message) if message else (None, None)
            )
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
