"""astrbot_plugin_cloudflare_imgbed_random 插件单元测试。

先以 stub 替换 astrbot.* 模块（无需安装 AstrBot）再导入 main，
覆盖目录提取、URL 解析与校验、随机媒体请求、媒体文件名解析、
发送文案构建、图片压缩、图片格式嗅探、原图历史与 /原图 匹配。
"""

import asyncio
import importlib
import io
import sys
import types
import unittest
from urllib.parse import quote


def _install_astrbot_stubs():
    astrbot = types.ModuleType("astrbot")
    api = types.ModuleType("astrbot.api")
    event = types.ModuleType("astrbot.api.event")
    message_components = types.ModuleType("astrbot.api.message_components")
    star = types.ModuleType("astrbot.api.star")

    class Filters:
        @staticmethod
        def command(*_args, **_kwargs):
            return lambda function: function

        @staticmethod
        def llm_tool(*_args, **_kwargs):
            return lambda function: function

    class Star:
        def __init__(self, context):
            self.context = context

    event.filter = Filters()
    event.AstrMessageEvent = object
    api.logger = types.SimpleNamespace(info=lambda *_: None, warning=lambda *_: None, error=lambda *_: None)
    message_components.Image = types.SimpleNamespace(
        fromURL=lambda url: {"type": "url", "url": url},
        fromBytes=lambda data: {"type": "bytes", "data": data},
    )
    message_components.Plain = lambda value: value
    message_components.Video = types.SimpleNamespace(fromURL=lambda url: {"type": "video_url", "url": url})
    star.Context = object
    star.Star = Star
    star.register = lambda *_args, **_kwargs: lambda cls: cls

    sys.modules.update({
        "astrbot": astrbot,
        "astrbot.api": api,
        "astrbot.api.event": event,
        "astrbot.api.message_components": message_components,
        "astrbot.api.star": star,
    })


_install_astrbot_stubs()
main = importlib.import_module("main")


class PluginTests(unittest.TestCase):
    """配置加载、目录提取、API URL 构建与随机媒体请求等基础行为。"""

    def setUp(self):
        self.plugin = main.CloudflareImgbedRandomPlugin(
            types.SimpleNamespace(get_config=lambda: {"imgbedDomain": "https://fallback.invalid"}),
            config={
                "imgbedDomain": "https://img.example",
                "apiEndpoint": "/api/random",
                "retryCount": 0,
                "timeout": 5,
                "defaultDir": "default",
                "enableLLM": True,
            },
        )

    def test_plugin_config_is_used(self):
        self.assertEqual(self.plugin.config["imgbedDomain"], "https://img.example")

    def test_directory_parsing(self):
        self.assertEqual(main.CloudflareImgbedRandomPlugin._extract_directory("/随机图 img/wallpaper"), ("img/wallpaper", "image"))
        self.assertEqual(main.CloudflareImgbedRandomPlugin._extract_directory("随机视频 video/movies"), ("video/movies", "video"))
        self.assertEqual(main.CloudflareImgbedRandomPlugin._extract_directory("请发一张随机图片"), ("", "image"))

    def test_url_resolution(self):
        self.assertEqual(
            self.plugin._resolve_media_url("../file.jpg", "https://img.example/api/random"),
            "https://img.example/file.jpg",
        )
        self.assertIsNone(self.plugin._resolve_media_url("", "https://img.example/api/random"))
        self.assertIsNone(self.plugin._resolve_media_url("https://user:pass@img.example/file.jpg", "https://img.example/api/random"))
        self.assertIsNone(self.plugin._resolve_media_url("javascript:alert(1)", "https://img.example/api/random"))

    def test_api_url_rejects_absolute_endpoint(self):
        self.plugin.settings = {"imgbedDomain": "https://img.example", "apiEndpoint": "https://evil.example"}
        self.assertIsNone(self.plugin._build_api_url())

        self.plugin.settings = {"imgbedDomain": "https://img.example?token=secret", "apiEndpoint": "/random"}
        self.assertIsNone(self.plugin._build_api_url())

    def test_default_directory_is_used_when_no_directory_is_given(self):
        self.plugin.settings = {
            "imgbedDomain": "https://img.example",
            "apiEndpoint": "/random",
            "defaultDir": "configured/default",
            "retryCount": 0,
            "timeout": 5,
        }

        captured = {}

        class FakeResponse:
            status = 200
            url = "https://img.example/random"
            charset = "utf-8"
            headers = {"Content-Type": "application/json"}

            class Content:
                async def read(self, _limit):
                    return b'{"url":"/file.jpg"}'

            content = Content()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return False

        class FakeSession:
            def get(self, url, **_kwargs):
                captured["url"] = url
                return FakeResponse()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return False

        original_session = main.aiohttp.ClientSession
        main.aiohttp.ClientSession = FakeSession
        try:
            result = __import__("asyncio").run(self.plugin._get_random_media())
        finally:
            main.aiohttp.ClientSession = original_session

        self.assertEqual(result, "https://img.example/file.jpg")
        self.assertIn("dir=configured%2Fdefault", captured["url"])


class ExtractMediaFilenameTests(unittest.TestCase):
    """_extract_media_filename：从媒体 URL 提取文件名。"""

    def test_imgbed_url_returns_filename_only(self):
        filename = main.CloudflareImgbedRandomPlugin._extract_media_filename(
            "https://img.example/file/10、商务宣传/Guerlain.jpg"
        )
        self.assertEqual(filename, "Guerlain.jpg")

    def test_encoded_chinese_filename_is_decoded(self):
        url = "https://img.example/file/" + quote("10、商务宣传") + "/" + quote("照片（1）.jpg")
        filename = main.CloudflareImgbedRandomPlugin._extract_media_filename(url)
        self.assertEqual(filename, "照片（1）.jpg")

    def test_nested_directory_returns_last_segment(self):
        filename = main.CloudflareImgbedRandomPlugin._extract_media_filename("https://img.example/file/album/sub/pic.png")
        self.assertEqual(filename, "pic.png")

    def test_filename_only_url(self):
        filename = main.CloudflareImgbedRandomPlugin._extract_media_filename("https://img.example/file/abc123.jpg")
        self.assertEqual(filename, "abc123.jpg")

    def test_path_without_extension_returns_none(self):
        self.assertIsNone(main.CloudflareImgbedRandomPlugin._extract_media_filename("https://img.example/random"))

    def test_empty_path_returns_none(self):
        self.assertIsNone(main.CloudflareImgbedRandomPlugin._extract_media_filename("https://img.example/"))


class MediaCaptionTests(unittest.TestCase):
    """_build_media_caption：发送文案生成与回退逻辑。"""

    def setUp(self):
        self.plugin = main.CloudflareImgbedRandomPlugin(
            types.SimpleNamespace(get_config=lambda: {}),
            config={},
        )
        self.plugin.settings = {"showFileInfo": True}

    def test_caption_shows_filename_only(self):
        caption = self.plugin._build_media_caption(
            "https://img.example/file/10、商务宣传/Guerlain.jpg", "图片"
        )
        self.assertEqual(caption, "🖼️ Guerlain.jpg")

    def test_video_caption_uses_video_icon(self):
        caption = self.plugin._build_media_caption("https://img.example/file/视频/movie.mp4", "视频")
        self.assertEqual(caption, "🎬 movie.mp4")

    def test_caption_falls_back_when_info_missing(self):
        caption = self.plugin._build_media_caption("https://img.example/random", "图片")
        self.assertEqual(caption, "随机图片发送成功")

    def test_caption_falls_back_when_disabled(self):
        self.plugin.settings = {"showFileInfo": False}
        caption = self.plugin._build_media_caption(
            "https://img.example/file/10、商务宣传/Guerlain.jpg", "图片"
        )
        self.assertEqual(caption, "随机图片发送成功")


class CompressConfigTests(unittest.TestCase):
    """enableCompress / compressMaxSide / compressQuality 配置加载与规范化。"""

    def _plugin_with(self, extra):
        config = {"imgbedDomain": "https://img.example", "retryCount": 0}
        config.update(extra)
        plugin = main.CloudflareImgbedRandomPlugin(
            types.SimpleNamespace(get_config=lambda: {}),
            config=config,
        )
        asyncio.run(plugin._load_config())
        return plugin

    def test_defaults(self):
        plugin = self._plugin_with({})
        self.assertTrue(plugin.settings["enableCompress"])
        self.assertEqual(plugin.settings["compressMaxSide"], 1920)
        self.assertEqual(plugin.settings["compressQuality"], 85)

    def test_string_bool_and_invalid_numbers(self):
        plugin = self._plugin_with({"enableCompress": "false", "compressMaxSide": "abc", "compressQuality": 500})
        self.assertFalse(plugin.settings["enableCompress"])
        self.assertEqual(plugin.settings["compressMaxSide"], 1920)
        self.assertEqual(plugin.settings["compressQuality"], 100)

    def test_bounds_are_clamped(self):
        plugin = self._plugin_with({"compressQuality": 0, "compressMaxSide": -5})
        self.assertEqual(plugin.settings["compressQuality"], 1)
        self.assertEqual(plugin.settings["compressMaxSide"], 1)


@unittest.skipUnless(main.PILImage, "需要 Pillow")
class PrepareImageTests(unittest.TestCase):
    """_prepare_image：缩放重编码、动图与小图跳过、透明铺白底、损坏回退。"""

    def setUp(self):
        self.plugin = main.CloudflareImgbedRandomPlugin(types.SimpleNamespace(get_config=lambda: {}), config={})
        self.plugin.settings = {"compressMaxSide": 1920, "compressQuality": 85}

    @staticmethod
    def _jpeg(size, quality, noise=False):
        if noise:
            img = main.PILImage.effect_noise(size, 64)
        else:
            img = main.PILImage.new("RGB", size, (120, 130, 140))
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=quality)
        return buf.getvalue()

    def test_large_image_is_resized_and_reencoded(self):
        data = self._jpeg((3000, 1500), 95, noise=True)
        out, compressed = self.plugin._prepare_image(data)
        self.assertTrue(compressed)
        with main.PILImage.open(io.BytesIO(out)) as img:
            self.assertEqual(img.size, (1920, 960))
            self.assertEqual(img.format, "JPEG")

    def test_small_image_is_left_untouched(self):
        data = self._jpeg((50, 40), 95)
        out, compressed = self.plugin._prepare_image(data)
        self.assertFalse(compressed)
        self.assertEqual(out, data)

    def test_animated_gif_is_not_reencoded(self):
        frames = [main.PILImage.new("RGB", (60, 60), (i * 80, 10, 10)) for i in range(3)]
        buf = io.BytesIO()
        frames[0].save(buf, format="GIF", save_all=True, append_images=frames[1:], duration=100, loop=0)
        data = buf.getvalue()
        out, compressed = self.plugin._prepare_image(data)
        self.assertFalse(compressed)
        self.assertEqual(out, data)

    def test_transparent_png_gets_white_background(self):
        img = main.PILImage.effect_noise((1000, 1000), 64).convert("RGBA")
        alpha = main.PILImage.new("L", img.size, 255)
        alpha.paste(main.PILImage.new("L", (1000, 500), 0), (0, 500))
        img.putalpha(alpha)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        out, compressed = self.plugin._prepare_image(buf.getvalue())
        self.assertTrue(compressed)
        with main.PILImage.open(io.BytesIO(out)) as result:
            self.assertEqual(result.format, "JPEG")
            self.assertEqual(result.getpixel((500, 750)), (255, 255, 255))

    def test_corrupt_data_returns_none(self):
        junk = b"\x00" * (main.COMPRESS_MIN_BYTES + 1024)
        self.assertIsNone(self.plugin._prepare_image(junk))

    def test_not_smaller_result_keeps_original(self):
        data = self._jpeg((3500, 2500), 15, noise=True)
        self.plugin.settings["compressMaxSide"] = 4000  # 不缩放，仅重编码
        out, compressed = self.plugin._prepare_image(data)
        self.assertFalse(compressed)
        self.assertEqual(out, data)

    def test_unparseable_small_image_is_reencoded(self):
        # ICO 不在协议端可解析宽高的格式集合内，即使很小也要转成 JPEG，
        # 否则 QQ 协议端解析失败、聊天气泡显示为 1:1
        img = main.PILImage.new("RGB", (64, 64), (10, 200, 30))
        buf = io.BytesIO()
        img.save(buf, format="ICO")
        out, compressed = self.plugin._prepare_image(buf.getvalue())
        self.assertTrue(compressed)
        with main.PILImage.open(io.BytesIO(out)) as result:
            self.assertEqual(result.format, "JPEG")

    def test_exif_orientation_is_baked_in(self):
        # 用噪声纹理保证重编码后体积变小，命中压缩分支
        noise = main.PILImage.effect_noise((2000, 1000), 64).convert("RGB")
        green = main.PILImage.blend(noise.crop((0, 0, 1000, 1000)), main.PILImage.new("RGB", (1000, 1000), (0, 255, 0)), 0.6)
        red = main.PILImage.blend(noise.crop((1000, 0, 2000, 1000)), main.PILImage.new("RGB", (1000, 1000), (255, 0, 0)), 0.6)
        img = main.PILImage.new("RGB", (2000, 1000))
        img.paste(green, (0, 0))
        img.paste(red, (1000, 0))
        exif = main.PILImage.Exif()
        exif[274] = 6  # Orientation: 展示时旋转 90° CW
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95, exif=exif)
        out, compressed = self.plugin._prepare_image(buf.getvalue())
        self.assertTrue(compressed)
        with main.PILImage.open(io.BytesIO(out)) as result:
            # 存储尺寸 2000x1000 按 EXIF 展示为 1000x2000，重编码后最长边 1920
            self.assertEqual(result.size, (960, 1920))
            top = result.getpixel((480, 100))
            bottom = result.getpixel((480, 1800))
            self.assertGreater(top[1], top[0])  # 顶部为绿色
            self.assertGreater(bottom[0], bottom[1])  # 底部为红色


class SniffImageFormatTests(unittest.TestCase):
    """_sniff_image_format：按文件头魔数识别图片格式。"""

    @staticmethod
    def _sniff(data):
        return main.CloudflareImgbedRandomPlugin._sniff_image_format(data)

    def test_common_formats(self):
        self.assertEqual(self._sniff(b"\xff\xd8\xff\xe0" + b"\x00" * 16), "JPEG")
        self.assertEqual(self._sniff(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16), "PNG")
        self.assertEqual(self._sniff(b"GIF89a" + b"\x00" * 16), "GIF")
        self.assertEqual(self._sniff(b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 8), "WEBP")
        self.assertEqual(self._sniff(b"BM\x36\x00\x00\x00" + b"\x00" * 16), "BMP")
        self.assertEqual(self._sniff(b"II*\x00\x08\x00\x00\x00" + b"\x00" * 8), "TIFF")
        self.assertEqual(self._sniff(b"MM\x00*\x00\x00\x00\x08" + b"\x00" * 8), "TIFF")

    def test_isobmff_brands(self):
        self.assertEqual(self._sniff(b"\x00\x00\x00\x18ftypavif\x00\x00\x00\x00"), "AVIF")
        self.assertEqual(self._sniff(b"\x00\x00\x00\x18ftypavis\x00\x00\x00\x00"), "AVIF")
        self.assertEqual(self._sniff(b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00"), "HEIF")
        self.assertEqual(self._sniff(b"\x00\x00\x00\x18ftypmif1\x00\x00\x00\x00"), "HEIF")

    def test_svg_xml_and_unknown(self):
        self.assertEqual(self._sniff(b'  <?xml version="1.0"?><svg xmlns="urn:x"/>'), "SVG")
        self.assertEqual(self._sniff(b'<svg xmlns="http://www.w3.org/2000/svg"></svg>'), "SVG")
        self.assertIsNone(self._sniff(b"\x00" * 32))
        self.assertIsNone(self._sniff(b"tiny"))
        self.assertIsNone(self._sniff(b""))


class DownloadImageTests(unittest.TestCase):
    """_download_image：成功下载、大小上限、鉴权头同域限制与异常回退。"""

    def setUp(self):
        self.plugin = main.CloudflareImgbedRandomPlugin(types.SimpleNamespace(get_config=lambda: {}), config={})
        self.plugin.settings = {
            "imgbedDomain": "https://img.example",
            "apiToken": "Bearer tok",
            "timeout": 5,
        }

    def _run_download(self, url, status, body):
        captured = {}

        class FakeSession:
            def get(self, got_url, **kwargs):
                captured["url"] = got_url
                captured["headers"] = kwargs.get("headers")

                class Content:
                    async def read(self, _limit):
                        return body

                class FakeResponse:
                    def __init__(self):
                        self.status = status
                        self.headers = {}
                        self.content = Content()

                    async def __aenter__(self):
                        return self

                    async def __aexit__(self, *_args):
                        return False

                return FakeResponse()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return False

        original_session = main.aiohttp.ClientSession
        main.aiohttp.ClientSession = FakeSession
        try:
            result = asyncio.run(self.plugin._download_image(url))
        finally:
            main.aiohttp.ClientSession = original_session
        return result, captured

    def test_success_returns_bytes(self):
        result, _ = self._run_download("https://img.example/file/a.jpg", 200, b"img")
        self.assertEqual(result, b"img")

    def test_non_200_returns_none(self):
        result, _ = self._run_download("https://img.example/file/a.jpg", 404, b"")
        self.assertIsNone(result)

    def test_oversize_returns_none(self):
        body = b"x" * (main.MAX_IMAGE_BYTES + 1)
        result, _ = self._run_download("https://img.example/file/a.jpg", 200, body)
        self.assertIsNone(result)

    def test_auth_header_only_for_same_domain(self):
        _, captured = self._run_download("https://img.example/file/a.jpg", 200, b"x")
        self.assertEqual(captured["headers"], {"Authorization": "Bearer tok"})
        _, captured = self._run_download("https://cdn.other/file/a.jpg", 200, b"x")
        self.assertEqual(captured["headers"], {})

    def test_network_error_returns_none(self):
        import aiohttp

        class FailingSession:
            def get(self, *_args, **_kwargs):
                raise aiohttp.ClientError("boom")

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return False

        original_session = main.aiohttp.ClientSession
        main.aiohttp.ClientSession = FailingSession
        try:
            result = asyncio.run(self.plugin._download_image("https://img.example/file/a.jpg"))
        finally:
            main.aiohttp.ClientSession = original_session
        self.assertIsNone(result)


class ImageHistoryTests(unittest.TestCase):
    """_remember_image 历史记录与 /原图 的文件名匹配逻辑。"""

    def setUp(self):
        self.plugin = main.CloudflareImgbedRandomPlugin(types.SimpleNamespace(get_config=lambda: {}), config={})

    @staticmethod
    def _event(uo="session:A"):
        return types.SimpleNamespace(unified_msg_origin=uo)

    def test_remember_and_cap_history(self):
        for i in range(main.MAX_HISTORY_PER_SESSION + 2):
            self.plugin._remember_image(self._event(), f"https://img.example/file/pic{i}.jpg")
        history = self.plugin._image_history["session:A"]
        self.assertEqual(len(history), main.MAX_HISTORY_PER_SESSION)
        self.assertNotIn("pic0.jpg", history)
        self.assertEqual(next(reversed(history)), "pic31.jpg")

    def test_remember_without_filename_is_ignored(self):
        self.plugin._remember_image(self._event(), "https://img.example/random")
        self.assertEqual(self.plugin._image_history, {})

    def test_match_exact_case_insensitive(self):
        self.plugin._remember_image(self._event(), "https://img.example/file/dir/Guerlain.jpg")
        history = self.plugin._image_history["session:A"]
        status, payload = main.CloudflareImgbedRandomPlugin._match_image_history(history, "guerlain.jpg")
        self.assertEqual(status, "found")
        self.assertEqual(payload[1], "https://img.example/file/dir/Guerlain.jpg")

    def test_match_stem_and_substring(self):
        self.plugin._remember_image(self._event(), "https://img.example/file/photo.png")
        history = self.plugin._image_history["session:A"]
        status, _ = main.CloudflareImgbedRandomPlugin._match_image_history(history, "photo")
        self.assertEqual(status, "found")
        status, _ = main.CloudflareImgbedRandomPlugin._match_image_history(history, "hot")
        self.assertEqual(status, "found")

    def test_match_ambiguous_and_missing(self):
        self.plugin._remember_image(self._event(), "https://img.example/file/Guerlain.jpg")
        self.plugin._remember_image(self._event(), "https://img.example/file/Guerlain.png")
        history = self.plugin._image_history["session:A"]
        status, candidates = main.CloudflareImgbedRandomPlugin._match_image_history(history, "guerlain")
        self.assertEqual(status, "ambiguous")
        self.assertEqual(len(candidates), 2)
        status, _ = main.CloudflareImgbedRandomPlugin._match_image_history(history, "不存在.jpg")
        self.assertEqual(status, "missing")
        status, _ = main.CloudflareImgbedRandomPlugin._match_image_history(history, "")
        self.assertEqual(status, "missing")


class HandlerTests(unittest.TestCase):
    """/原图 命令与 _handle_media 压缩发送/回退路径。"""

    class FakeEvent:
        def __init__(self, message_str="", uo="session:A"):
            self.message_str = message_str
            self.unified_msg_origin = uo
            self.results = []

        def plain_result(self, text):
            self.results.append(("plain", text))
            return ("plain", text)

        def chain_result(self, chain):
            self.results.append(("chain", chain))
            return ("chain", chain)

    def setUp(self):
        self.plugin = main.CloudflareImgbedRandomPlugin(types.SimpleNamespace(get_config=lambda: {}), config={})
        self.plugin.settings = {
            "showFileInfo": True,
            "enableCompress": True,
            "compressMaxSide": 1920,
            "compressQuality": 85,
        }

    @staticmethod
    def _run(agen, event):
        async def runner():
            async for item in agen:
                event.results.append(item)

        asyncio.run(runner())

    def _fake_media_source(self, url):
        async def fake_get(directory, content_type):
            return url

        self.plugin._get_random_media = fake_get

    def test_handle_media_uses_compressed_bytes(self):
        event = self.FakeEvent("/随机图")
        self._fake_media_source("https://img.example/file/dir/pic.jpg")

        async def fake_download(_url):
            return b"original-bytes"

        self.plugin._download_image = fake_download
        self.plugin._prepare_image = lambda _data: (b"small-bytes", True)
        self._run(self.plugin._handle_media(event, "image"), event)

        kind, chain = event.results[0]
        caption, image = chain
        self.assertEqual(kind, "chain")
        self.assertIn("已压缩", caption)
        self.assertIn("/原图 pic.jpg", caption)
        self.assertEqual(image, {"type": "bytes", "data": b"small-bytes"})
        self.assertEqual(self.plugin._image_history["session:A"]["pic.jpg"], "https://img.example/file/dir/pic.jpg")

    def test_original_hint_falls_back_without_filename(self):
        event = self.FakeEvent("/随机图")
        self._fake_media_source("https://img.example/t/abc123")

        async def fake_download(_url):
            return b"original-bytes"

        self.plugin._download_image = fake_download
        self.plugin._prepare_image = lambda _data: (b"small-bytes", True)
        self._run(self.plugin._handle_media(event, "image"), event)

        caption, image = event.results[0][1]
        self.assertEqual(caption, "随机图片发送成功（已压缩，发送 /原图 可获取原图）")
        self.assertEqual(image, {"type": "bytes", "data": b"small-bytes"})

    def test_handle_media_falls_back_when_download_fails(self):
        event = self.FakeEvent("/随机图")
        self._fake_media_source("https://img.example/file/pic.jpg")

        async def fake_download(_url):
            return None

        self.plugin._download_image = fake_download
        self._run(self.plugin._handle_media(event, "image"), event)

        caption, image = event.results[0][1]
        self.assertNotIn("已压缩", caption)
        self.assertEqual(image, {"type": "url", "url": "https://img.example/file/pic.jpg"})

    def test_handle_media_skips_compression_when_disabled(self):
        self.plugin.settings["enableCompress"] = False
        event = self.FakeEvent("/随机图")
        self._fake_media_source("https://img.example/file/pic.jpg")

        async def fail_download(_url):
            raise AssertionError("关闭压缩时不应下载图片")

        self.plugin._download_image = fail_download
        self._run(self.plugin._handle_media(event, "image"), event)

        _, image = event.results[0][1]
        self.assertEqual(image, {"type": "url", "url": "https://img.example/file/pic.jpg"})

    def test_original_image_without_history(self):
        event = self.FakeEvent("/原图")
        self._run(self.plugin.original_image(event), event)
        kind, text = event.results[0]
        self.assertEqual(kind, "plain")
        self.assertIn("还没有发送过随机图片", text)

    def test_original_image_returns_latest(self):
        self.plugin._remember_image(self.FakeEvent(), "https://img.example/file/first.jpg")
        self.plugin._remember_image(self.FakeEvent(), "https://img.example/file/second.jpg")
        event = self.FakeEvent("/原图")
        self._run(self.plugin.original_image(event), event)

        caption, image = event.results[0][1]
        self.assertIn("（原图）", caption)
        self.assertEqual(image, {"type": "url", "url": "https://img.example/file/second.jpg"})

    def test_original_image_by_filename(self):
        self.plugin._remember_image(self.FakeEvent(), "https://img.example/file/first.jpg")
        event = self.FakeEvent("/原图 first.jpg")
        self._run(self.plugin.original_image(event), event)

        caption, image = event.results[0][1]
        self.assertIn("（原图）", caption)
        self.assertEqual(image, {"type": "url", "url": "https://img.example/file/first.jpg"})

    def test_original_image_ambiguous(self):
        self.plugin._remember_image(self.FakeEvent(), "https://img.example/file/Guerlain.jpg")
        self.plugin._remember_image(self.FakeEvent(), "https://img.example/file/Guerlain.png")
        event = self.FakeEvent("/原图 guerlain")
        self._run(self.plugin.original_image(event), event)

        kind, text = event.results[0]
        self.assertEqual(kind, "plain")
        self.assertIn("匹配到多张图片", text)

    def test_original_image_missing(self):
        self.plugin._remember_image(self.FakeEvent(), "https://img.example/file/first.jpg")
        event = self.FakeEvent("/原图 nope.jpg")
        self._run(self.plugin.original_image(event), event)

        kind, text = event.results[0]
        self.assertEqual(kind, "plain")
        self.assertIn("没有找到", text)

    def test_original_image_isolated_by_session(self):
        self.plugin._remember_image(self.FakeEvent(uo="session:A"), "https://img.example/file/a.jpg")
        event = self.FakeEvent("/原图", uo="session:B")
        self._run(self.plugin.original_image(event), event)
        self.assertIn("还没有发送过随机图片", event.results[0][1])


if __name__ == "__main__":
    unittest.main()