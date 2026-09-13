"""astrbot_plugin_cloudflare_imgbed_random 插件单元测试。

先以 stub 替换 astrbot.* 模块（无需安装 AstrBot）再导入 main，
覆盖目录提取、URL 解析与校验、随机媒体请求、媒体文件名解析、
发送文案构建、图片压缩、图片格式嗅探、原图历史与 /原图 匹配。
"""

import asyncio
import importlib
import io
import json
import sys
import types
import unittest
from pathlib import Path
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
    api.logger = types.SimpleNamespace(
        info=lambda *_: None, warning=lambda *_: None, error=lambda *_: None
    )
    message_components.Image = types.SimpleNamespace(
        fromURL=lambda url: {"type": "url", "url": url},
        fromBytes=lambda data: {"type": "bytes", "data": data},
    )
    message_components.Plain = lambda value: value
    message_components.Video = types.SimpleNamespace(
        fromURL=lambda url: {"type": "video_url", "url": url}
    )
    star.Context = object
    star.Star = Star
    star.register = lambda *_args, **_kwargs: lambda cls: cls

    sys.modules.update(
        {
            "astrbot": astrbot,
            "astrbot.api": api,
            "astrbot.api.event": event,
            "astrbot.api.message_components": message_components,
            "astrbot.api.star": star,
        }
    )


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
        asyncio.run(self.plugin._load_config())

    def test_plugin_config_is_used(self):
        self.assertEqual(self.plugin.config["imgbed"]["domain"], "https://img.example")

    def test_directory_parsing(self):
        self.assertEqual(
            main.CloudflareImgbedRandomPlugin._extract_directory("/随机图 img/wallpaper"),
            ("img/wallpaper", "image"),
        )
        self.assertEqual(
            main.CloudflareImgbedRandomPlugin._extract_directory("随机视频 video/movies"),
            ("video/movies", "video"),
        )
        self.assertEqual(
            main.CloudflareImgbedRandomPlugin._extract_directory("请发一张随机图片"),
            ("", "image"),
        )

    def test_url_resolution(self):
        self.assertEqual(
            self.plugin._resolve_media_url("../file.jpg", "https://img.example/api/random"),
            "https://img.example/file.jpg",
        )
        self.assertIsNone(self.plugin._resolve_media_url("", "https://img.example/api/random"))
        self.assertIsNone(
            self.plugin._resolve_media_url(
                "https://user:pass@img.example/file.jpg",
                "https://img.example/api/random",
            )
        )
        self.assertIsNone(
            self.plugin._resolve_media_url("javascript:alert(1)", "https://img.example/api/random")
        )

    def test_api_url_rejects_absolute_endpoint(self):
        self.plugin.settings = {
            "imgbed": {
                "domain": "https://img.example",
                "apiEndpoint": "https://evil.example",
            }
        }
        self.assertIsNone(self.plugin._build_api_url())

        self.plugin.settings = {
            "imgbed": {
                "domain": "https://img.example?token=secret",
                "apiEndpoint": "/random",
            }
        }
        self.assertIsNone(self.plugin._build_api_url())

    def test_default_directory_is_used_when_no_directory_is_given(self):
        self.plugin.settings = {
            "imgbed": {
                "domain": "https://img.example",
                "apiEndpoint": "/random",
                "defaultDir": "configured/default",
                "retryCount": 0,
                "timeout": 5,
            },
            "message": {"showFileInfo": True, "enableLLM": True},
            "image": {
                "sendMode": "original-url",
                "enableProcessing": True,
                "maxSide": 1920,
                "quality": 85,
            },
        }

        captured = {}

        class FakeResponse:
            status = 200
            url = "https://img.example/random"
            charset = "utf-8"

            def __init__(self):
                self.headers = {"Content-Type": "application/json"}

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
        filename = main.CloudflareImgbedRandomPlugin._extract_media_filename(
            "https://img.example/file/album/sub/pic.png"
        )
        self.assertEqual(filename, "pic.png")

    def test_filename_only_url(self):
        filename = main.CloudflareImgbedRandomPlugin._extract_media_filename(
            "https://img.example/file/abc123.jpg"
        )
        self.assertEqual(filename, "abc123.jpg")

    def test_path_without_extension_returns_none(self):
        self.assertIsNone(
            main.CloudflareImgbedRandomPlugin._extract_media_filename("https://img.example/random")
        )

    def test_empty_path_returns_none(self):
        self.assertIsNone(
            main.CloudflareImgbedRandomPlugin._extract_media_filename("https://img.example/")
        )


class MediaCaptionTests(unittest.TestCase):
    """_build_media_caption：发送文案生成与回退逻辑。"""

    def setUp(self):
        self.plugin = main.CloudflareImgbedRandomPlugin(
            types.SimpleNamespace(get_config=dict),
            config={},
        )
        self.plugin.settings = {"message": {"showFileInfo": True}}

    def test_caption_shows_filename_only(self):
        caption = self.plugin._build_media_caption(
            "https://img.example/file/10、商务宣传/Guerlain.jpg", "图片"
        )
        self.assertEqual(caption, "🖼️ Guerlain.jpg")

    def test_video_caption_uses_video_icon(self):
        caption = self.plugin._build_media_caption(
            "https://img.example/file/视频/movie.mp4", "视频"
        )
        self.assertEqual(caption, "🎬 movie.mp4")

    def test_caption_falls_back_when_info_missing(self):
        caption = self.plugin._build_media_caption("https://img.example/random", "图片")
        self.assertEqual(caption, "随机图片发送成功")

    def test_caption_falls_back_when_disabled(self):
        self.plugin.settings = {"message": {"showFileInfo": False}}
        caption = self.plugin._build_media_caption(
            "https://img.example/file/10、商务宣传/Guerlain.jpg", "图片"
        )
        self.assertEqual(caption, "随机图片发送成功")


class ConfigMigrationTests(unittest.TestCase):
    """v1 顶层配置迁移与 v2 嵌套配置规范化。"""

    def _plugin_with(self, extra):
        config = {"imgbedDomain": "https://img.example", "retryCount": 0}
        config.update(extra)
        plugin = main.CloudflareImgbedRandomPlugin(
            types.SimpleNamespace(get_config=dict),
            config=config,
        )
        asyncio.run(plugin._load_config())
        return plugin

    def test_defaults(self):
        plugin = self._plugin_with({})
        self.assertEqual(plugin.settings["image"]["sendMode"], "scaled-url")
        self.assertTrue(plugin.settings["image"]["enableProcessing"])
        self.assertEqual(plugin.settings["image"]["maxSide"], 1920)
        self.assertEqual(plugin.settings["image"]["quality"], 85)

    def test_legacy_modes_map_to_new_modes(self):
        plugin = self._plugin_with({"imageSendMode": "url", "enableCompress": True})
        self.assertEqual(plugin.settings["image"]["sendMode"], "scaled-url")

        plugin = self._plugin_with({"imageSendMode": "url", "enableCompress": False})
        self.assertEqual(plugin.settings["image"]["sendMode"], "original-url")

        plugin = self._plugin_with({"imageSendMode": " COMPRESS "})
        self.assertEqual(plugin.settings["image"]["sendMode"], "local-compress")

        plugin = self._plugin_with({"imageSendMode": "compress", "enableCompress": False})
        self.assertEqual(plugin.settings["image"]["sendMode"], "original-url")

        plugin = self._plugin_with({"imageSendMode": "invalid"})
        self.assertEqual(plugin.settings["image"]["sendMode"], "scaled-url")

    def test_string_bool_and_invalid_numbers(self):
        plugin = self._plugin_with(
            {
                "enableCompress": "false",
                "compressMaxSide": "abc",
                "compressQuality": 500,
            }
        )
        self.assertFalse(plugin.settings["image"]["enableProcessing"])
        self.assertEqual(plugin.settings["image"]["maxSide"], 1920)
        self.assertEqual(plugin.settings["image"]["quality"], 100)

    def test_bounds_are_clamped(self):
        plugin = self._plugin_with({"compressQuality": 0, "compressMaxSide": -5})
        self.assertEqual(plugin.settings["image"]["quality"], 1)
        self.assertEqual(plugin.settings["image"]["maxSide"], 1)

    def test_imgbed_max_side_is_clamped_to_4096(self):
        plugin = self._plugin_with({"compressMaxSide": 5000})
        self.assertEqual(plugin.settings["image"]["maxSide"], 4096)

    def test_legacy_keys_migrate_to_nested_sections(self):
        plugin = self._plugin_with(
            {
                "imgbedDomain": "https://img.example",
                "apiEndpoint": "/api/random",
                "apiToken": "Bearer token",
                "defaultDir": "default",
                "timeout": "5",
                "retryCount": "2",
                "showFileInfo": "false",
                "enableLLM": "false",
                "enableCompress": "true",
                "imageSendMode": "url",
                "compressMaxSide": "2048",
                "compressQuality": "90",
            }
        )
        self.assertEqual(plugin.settings["imgbed"]["domain"], "https://img.example")
        self.assertEqual(plugin.settings["imgbed"]["apiEndpoint"], "/api/random")
        self.assertEqual(plugin.settings["imgbed"]["apiToken"], "Bearer token")
        self.assertEqual(plugin.settings["imgbed"]["defaultDir"], "default")
        self.assertEqual(plugin.settings["imgbed"]["timeout"], 5.0)
        self.assertEqual(plugin.settings["imgbed"]["retryCount"], 2)
        self.assertFalse(plugin.settings["message"]["showFileInfo"])
        self.assertFalse(plugin.settings["message"]["enableLLM"])
        self.assertEqual(plugin.settings["image"]["sendMode"], "scaled-url")
        self.assertTrue(plugin.settings["image"]["enableProcessing"])
        self.assertEqual(plugin.settings["image"]["maxSide"], 2048)
        self.assertEqual(plugin.settings["image"]["quality"], 90)

    def test_migration_is_persisted_to_config_object(self):
        class PersistedConfig(dict):
            saved_count = 0

            def save_config(self):
                self.saved_count += 1

        config = PersistedConfig(
            {
                "imgbedDomain": "https://img.example",
                "imageSendMode": "url",
                "enableCompress": True,
            }
        )
        plugin = main.CloudflareImgbedRandomPlugin(
            types.SimpleNamespace(get_config=dict),
            config=config,
        )
        asyncio.run(plugin._load_config())

        self.assertIs(plugin.config, config)
        self.assertEqual(config.saved_count, 1)
        self.assertNotIn("imgbedDomain", config)
        self.assertNotIn("imageSendMode", config)
        self.assertEqual(config["imgbed"]["domain"], "https://img.example")
        self.assertEqual(config["image"]["sendMode"], "scaled-url")

    def test_migration_failure_rolls_back_config_object(self):
        class FailingConfig(dict):
            saved_count = 0

            def save_config(self):
                self.saved_count += 1
                raise OSError("disk full")

        config = FailingConfig(
            {
                "imgbedDomain": "https://img.example",
                "imageSendMode": "url",
                "enableCompress": True,
            }
        )
        plugin = main.CloudflareImgbedRandomPlugin(
            types.SimpleNamespace(get_config=dict),
            config=config,
        )
        asyncio.run(plugin._load_config())

        self.assertEqual(config.saved_count, 1)
        self.assertIn("imgbedDomain", config)
        self.assertIn("imageSendMode", config)
        self.assertNotIn("imgbed", config)
        self.assertEqual(plugin.settings["imgbed"]["domain"], "https://img.example")

    def test_migration_preserves_unknown_config_values(self):
        config = {
            "imgbedDomain": "https://img.example",
            "futureOption": "keep-me",
            "image": {"sendMode": "original-url", "futureImageOption": 1},
        }
        migrated, changed = main._migrate_legacy_config(config)

        self.assertTrue(changed)
        self.assertNotIn("imgbedDomain", migrated)
        self.assertEqual(migrated["futureOption"], "keep-me")
        self.assertEqual(migrated["image"]["sendMode"], "original-url")
        self.assertEqual(migrated["image"]["futureImageOption"], 1)

    def test_api_token_is_marked_secret_in_schema(self):
        schema_path = Path(__file__).parents[1] / "_conf_schema.json"
        with schema_path.open(encoding="utf-8") as schema_file:
            schema = json.load(schema_file)
        self.assertTrue(schema["imgbed"]["items"]["apiToken"]["secret"])

    def test_schema_uses_only_documented_fields(self):
        schema_path = Path(__file__).parents[1] / "_conf_schema.json"
        with schema_path.open(encoding="utf-8") as schema_file:
            schema = json.load(schema_file)

        allowed_fields = {
            "type",
            "description",
            "hint",
            "obvious_hint",
            "default",
            "items",
            "invisible",
            "secret",
            "options",
            "editor_mode",
            "editor_language",
            "editor_theme",
            "_special",
        }

        def assert_fields_are_documented(value):
            for key, item in value.items():
                self.assertTrue(set(item) <= allowed_fields, f"未声明字段: {key}")
                if "items" in item:
                    assert_fields_are_documented(item["items"])

        assert_fields_are_documented(schema)


class ScaledUrlTests(unittest.TestCase):
    """_build_scaled_media_url：CloudFlare ImgBed 官方尺寸参数构造。"""

    def setUp(self):
        self.plugin = main.CloudflareImgbedRandomPlugin(
            types.SimpleNamespace(get_config=dict),
            config={
                "image": {
                    "sendMode": "scaled-url",
                    "enableProcessing": True,
                    "maxSide": 1920,
                    "quality": 85,
                }
            },
        )
        self.plugin.settings = {
            "imgbed": {
                "domain": "",
                "apiEndpoint": "/random",
                "apiToken": "",
                "defaultDir": "",
                "timeout": 10,
                "retryCount": 3,
            },
            "message": {"showFileInfo": True, "enableLLM": True},
            "image": {
                "sendMode": "scaled-url",
                "enableProcessing": True,
                "maxSide": 1920,
                "quality": 85,
            },
        }

    def test_plain_url_gets_managed_parameters(self):
        url = self.plugin._build_scaled_media_url("https://img.example/file/pic.jpg")
        self.assertEqual(
            url,
            "https://img.example/file/pic.jpg?width=1920&height=1920&fallback=original",
        )

    def test_existing_query_is_preserved_and_managed_keys_are_replaced(self):
        url = self.plugin._build_scaled_media_url(
            "https://img.example/file/pic.jpg?token=secret&width=100&fit=cover&fallback=none"
        )
        self.assertEqual(
            url,
            "https://img.example/file/pic.jpg?token=secret&width=1920&height=1920&fallback=original",
        )
        self.assertNotIn("fit=", url)
        self.assertNotIn("quality=", url)

    def test_managed_query_keys_are_replaced_case_insensitively(self):
        url = self.plugin._build_scaled_media_url(
            "https://img.example/file/pic.jpg?token=secret&Width=100&Fit=cover&FALLBACK=none"
        )
        self.assertEqual(
            url,
            "https://img.example/file/pic.jpg?token=secret&width=1920&height=1920&fallback=original",
        )
        self.assertNotIn("Fit=", url)

    def test_runtime_max_side_is_clamped(self):
        self.plugin.settings["image"]["maxSide"] = 999999
        url = self.plugin._build_scaled_media_url("https://img.example/file/pic.jpg")
        self.assertIn("width=4096", url)
        self.assertIn("height=4096", url)

    def test_fragment_is_preserved(self):
        url = self.plugin._build_scaled_media_url("https://img.example/file/pic.jpg#section")
        self.assertEqual(
            url,
            "https://img.example/file/pic.jpg?width=1920&height=1920&fallback=original#section",
        )

    def test_encoded_chinese_path_is_preserved(self):
        encoded_path = quote("10、商务宣传/照片（1）.jpg")
        url = self.plugin._build_scaled_media_url(f"https://img.example/file/{encoded_path}")
        self.assertTrue(url.startswith(f"https://img.example/file/{encoded_path}?"))
        self.assertIn("width=1920", url)
        self.assertIn("height=1920", url)
        self.assertIn("fallback=original", url)


@unittest.skipUnless(main.PILImage, "需要 Pillow")
class PrepareImageTests(unittest.TestCase):
    """_prepare_image：缩放重编码、动图与小图跳过、透明铺白底、损坏回退。"""

    def setUp(self):
        self.plugin = main.CloudflareImgbedRandomPlugin(
            types.SimpleNamespace(get_config=dict), config={}
        )
        self.plugin.settings = {"image": {"maxSide": 1920, "quality": 85}}

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

    def test_runtime_max_side_is_clamped_during_local_compression(self):
        self.plugin.settings["image"]["maxSide"] = 999999
        data = self._jpeg((5000, 2500), 95, noise=True)
        out, compressed = self.plugin._prepare_image(data)
        self.assertTrue(compressed)
        with main.PILImage.open(io.BytesIO(out)) as img:
            self.assertEqual(img.size, (4096, 2048))

    def test_small_image_is_left_untouched(self):
        data = self._jpeg((50, 40), 95)
        out, compressed = self.plugin._prepare_image(data)
        self.assertFalse(compressed)
        self.assertEqual(out, data)

    def test_animated_gif_is_not_reencoded(self):
        frames = [main.PILImage.new("RGB", (60, 60), (i * 80, 10, 10)) for i in range(3)]
        buf = io.BytesIO()
        frames[0].save(
            buf,
            format="GIF",
            save_all=True,
            append_images=frames[1:],
            duration=100,
            loop=0,
        )
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
        self.plugin.settings["image"]["maxSide"] = 4000  # 不缩放，仅重编码
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
        green = main.PILImage.blend(
            noise.crop((0, 0, 1000, 1000)),
            main.PILImage.new("RGB", (1000, 1000), (0, 255, 0)),
            0.6,
        )
        red = main.PILImage.blend(
            noise.crop((1000, 0, 2000, 1000)),
            main.PILImage.new("RGB", (1000, 1000), (255, 0, 0)),
            0.6,
        )
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
        self.plugin = main.CloudflareImgbedRandomPlugin(
            types.SimpleNamespace(get_config=dict), config={}
        )
        self.plugin.settings = {
            "imgbed": {
                "domain": "https://img.example",
                "apiToken": "Bearer tok",
                "timeout": 5,
            },
            "message": {"showFileInfo": True, "enableLLM": True},
            "image": {
                "sendMode": "scaled-url",
                "enableProcessing": True,
                "maxSide": 1920,
                "quality": 85,
            },
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
        self.plugin = main.CloudflareImgbedRandomPlugin(
            types.SimpleNamespace(get_config=dict), config={}
        )

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

    def test_session_history_is_capped(self):
        for i in range(main.MAX_HISTORY_SESSIONS + 1):
            event = self._event(f"session:{i}")
            self.plugin._remember_image(event, f"https://img.example/file/pic{i}.jpg")

        self.assertEqual(len(self.plugin._image_history), main.MAX_HISTORY_SESSIONS)
        self.assertNotIn("session:0", self.plugin._image_history)
        self.assertIn("session:200", self.plugin._image_history)

    def test_remember_without_filename_is_ignored(self):
        self.plugin._remember_image(self._event(), "https://img.example/random")
        self.assertEqual(self.plugin._image_history, {})

    def test_match_exact_case_insensitive(self):
        self.plugin._remember_image(self._event(), "https://img.example/file/dir/Guerlain.jpg")
        history = self.plugin._image_history["session:A"]
        status, payload = main.CloudflareImgbedRandomPlugin._match_image_history(
            history, "guerlain.jpg"
        )
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
        status, candidates = main.CloudflareImgbedRandomPlugin._match_image_history(
            history, "guerlain"
        )
        self.assertEqual(status, "ambiguous")
        self.assertEqual(len(candidates), 2)
        status, _ = main.CloudflareImgbedRandomPlugin._match_image_history(history, "不存在.jpg")
        self.assertEqual(status, "missing")
        status, _ = main.CloudflareImgbedRandomPlugin._match_image_history(history, "")
        self.assertEqual(status, "missing")


class HandlerTests(unittest.TestCase):
    """/原图 命令与 _handle_media 压缩发送/回退路径。"""

    class FakeBot:
        def __init__(self, fail=False):
            self.calls = []
            self.fail = fail

        async def call_action(self, action, **params):
            if self.fail:
                raise RuntimeError("protocol side error")
            self.calls.append((action, params))
            return {}

    class FakeEvent:
        def __init__(
            self,
            message_str="",
            uo="session:A",
            platform="aiocqhttp",
            bot=None,
            group_id="",
            sender_id="10001",
            self_id=None,
        ):
            self.message_str = message_str
            self.unified_msg_origin = uo
            self.results = []
            self.bot = bot
            self.stopped = False
            self._platform = platform
            self._group_id = group_id
            self._sender_id = sender_id
            self.message_obj = types.SimpleNamespace(self_id=self_id)

        def get_platform_name(self):
            return self._platform

        def get_group_id(self):
            return self._group_id

        def get_sender_id(self):
            return self._sender_id

        def stop_event(self):
            self.stopped = True

        def plain_result(self, text):
            self.results.append(("plain", text))
            return ("plain", text)

        def chain_result(self, chain):
            self.results.append(("chain", chain))
            return ("chain", chain)

    def setUp(self):
        self.plugin = main.CloudflareImgbedRandomPlugin(
            types.SimpleNamespace(get_config=dict), config={}
        )
        self.plugin.settings = {
            "imgbed": {
                "domain": "",
                "apiEndpoint": "/random",
                "apiToken": "",
                "defaultDir": "",
                "timeout": 10,
                "retryCount": 3,
            },
            "message": {"showFileInfo": True, "enableLLM": True},
            "image": {
                # 既有用例覆盖本地压缩链路，URL 直传链路由 OneBotSendTests 专门覆盖
                "sendMode": "local-compress",
                "enableProcessing": True,
                "maxSide": 1920,
                "quality": 85,
            },
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
        self.assertEqual(
            self.plugin._image_history["session:A"]["pic.jpg"],
            "https://img.example/file/dir/pic.jpg",
        )

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
        self.plugin.settings["image"]["enableProcessing"] = False
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
        self.plugin._remember_image(
            self.FakeEvent(uo="session:A"), "https://img.example/file/a.jpg"
        )
        event = self.FakeEvent("/原图", uo="session:B")
        self._run(self.plugin.original_image(event), event)
        self.assertIn("还没有发送过随机图片", event.results[0][1])


class OneBotSendTests(unittest.TestCase):
    """URL 直传链路：平台探测、群/私聊参数、失败回退、格式降级与模式切换。"""

    FakeBot = HandlerTests.FakeBot
    FakeEvent = HandlerTests.FakeEvent

    def setUp(self):
        self.plugin = main.CloudflareImgbedRandomPlugin(
            types.SimpleNamespace(get_config=dict), config={}
        )
        self.plugin.settings = {
            "imgbed": {
                "domain": "",
                "apiEndpoint": "/random",
                "apiToken": "",
                "defaultDir": "",
                "timeout": 10,
                "retryCount": 3,
            },
            "message": {"showFileInfo": True, "enableLLM": True},
            "image": {
                "sendMode": "scaled-url",
                "enableProcessing": True,
                "maxSide": 1920,
                "quality": 85,
            },
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

    def _forbid_download(self):
        async def fail_download(_url):
            raise AssertionError("URL 直传模式不应下载图片")

        self.plugin._download_image = fail_download

    def test_group_message_uses_send_group_msg(self):
        bot = self.FakeBot()
        event = self.FakeEvent("/随机图", bot=bot, group_id="12345", self_id="99")
        self._fake_media_source("https://img.example/file/pic.jpg")
        self._forbid_download()
        self._run(self.plugin._handle_media(event, "image"), event)
        scaled_url = "https://img.example/file/pic.jpg?width=1920&height=1920&fallback=original"

        self.assertEqual(len(bot.calls), 1)
        action, params = bot.calls[0]
        self.assertEqual(action, "send_group_msg")
        self.assertEqual(params["group_id"], 12345)
        self.assertEqual(params["self_id"], "99")
        self.assertNotIn("user_id", params)
        text_seg, image_seg = params["message"]
        self.assertEqual(text_seg["type"], "text")
        self.assertIn("pic.jpg", text_seg["data"]["text"])
        self.assertIn("已压缩", text_seg["data"]["text"])
        self.assertEqual(image_seg, {"type": "image", "data": {"file": scaled_url}})
        # 直传成功后不再产生消息链结果，并终止事件避免重复发送
        self.assertEqual(event.results, [])
        self.assertTrue(event.stopped)

    def test_private_message_uses_send_private_msg(self):
        bot = self.FakeBot()
        event = self.FakeEvent("/随机图", bot=bot, group_id="", sender_id="10001")
        self._fake_media_source("https://img.example/file/pic.png")
        self._forbid_download()
        self._run(self.plugin._handle_media(event, "image"), event)

        action, params = bot.calls[0]
        self.assertEqual(action, "send_private_msg")
        self.assertEqual(params["user_id"], 10001)
        self.assertNotIn("group_id", params)
        self.assertNotIn("self_id", params)

    def test_non_aiocqhttp_platform_uses_chain_result(self):
        bot = self.FakeBot()
        event = self.FakeEvent("/随机图", platform="telegram", bot=bot)
        self._fake_media_source("https://img.example/file/pic.jpg")
        self._forbid_download()
        self._run(self.plugin._handle_media(event, "image"), event)
        scaled_url = "https://img.example/file/pic.jpg?width=1920&height=1920&fallback=original"

        self.assertEqual(bot.calls, [])
        kind, chain = event.results[0]
        self.assertEqual(kind, "chain")
        self.assertEqual(chain[1], {"type": "url", "url": scaled_url})
        self.assertFalse(event.stopped)

    def test_missing_bot_uses_chain_result(self):
        event = self.FakeEvent("/随机图", bot=None)
        self._fake_media_source("https://img.example/file/pic.jpg")
        self._forbid_download()
        self._run(self.plugin._handle_media(event, "image"), event)
        scaled_url = "https://img.example/file/pic.jpg?width=1920&height=1920&fallback=original"

        kind, chain = event.results[0]
        self.assertEqual(kind, "chain")
        self.assertEqual(chain[1], {"type": "url", "url": scaled_url})

    def test_call_action_failure_falls_back_to_chain_result(self):
        bot = self.FakeBot(fail=True)
        event = self.FakeEvent("/随机图", bot=bot, group_id="12345")
        self._fake_media_source("https://img.example/file/pic.jpg")
        self._forbid_download()
        self._run(self.plugin._handle_media(event, "image"), event)
        scaled_url = "https://img.example/file/pic.jpg?width=1920&height=1920&fallback=original"

        kind, chain = event.results[0]
        self.assertEqual(kind, "chain")
        self.assertEqual(chain[1], {"type": "url", "url": scaled_url})
        self.assertFalse(event.stopped)

    def test_unparseable_extension_falls_back_to_compression(self):
        for url in (
            "https://img.example/file/pic.avif",
            "https://img.example/file/pic.heic",
            "https://img.example/file/pic.heif",
            "https://img.example/file/pic.svg",
            "https://img.example/file/pic.jxl",
            "https://img.example/file/pic",
        ):
            with self.subTest(url=url):
                bot = self.FakeBot()
                event = self.FakeEvent("/随机图", bot=bot, group_id="12345")
                self._fake_media_source(url)

                async def fake_download(_url):
                    return b"original-bytes"

                self.plugin._download_image = fake_download
                self.plugin._prepare_image = lambda _data: (b"jpeg-bytes", True)
                self._run(self.plugin._handle_media(event, "image"), event)

                # 协议端解析不出宽高的格式必须降级压缩，不能直传
                self.assertEqual(bot.calls, [])
                caption, image = event.results[0][1]
                self.assertEqual(image, {"type": "bytes", "data": b"jpeg-bytes"})
                self.assertIn("已压缩", caption)

    def test_compress_mode_skips_direct_send(self):
        self.plugin.settings["image"]["sendMode"] = "local-compress"
        bot = self.FakeBot()
        event = self.FakeEvent("/随机图", bot=bot, group_id="12345")
        self._fake_media_source("https://img.example/file/pic.jpg")

        async def fake_download(_url):
            return b"original-bytes"

        self.plugin._download_image = fake_download
        self.plugin._prepare_image = lambda _data: (b"jpeg-bytes", True)
        self._run(self.plugin._handle_media(event, "image"), event)

        self.assertEqual(bot.calls, [])
        _, image = event.results[0][1]
        self.assertEqual(image, {"type": "bytes", "data": b"jpeg-bytes"})

    def test_original_url_mode_does_not_append_scaling_or_hint(self):
        self.plugin.settings["image"]["sendMode"] = "original-url"
        bot = self.FakeBot()
        event = self.FakeEvent("/随机图", bot=bot, group_id="12345")
        self._fake_media_source("https://img.example/file/pic.jpg?width=100&fit=cover")
        self._forbid_download()
        self._run(self.plugin._handle_media(event, "image"), event)

        text_seg, image_seg = bot.calls[0][1]["message"]
        self.assertNotIn("已压缩", text_seg["data"]["text"])
        self.assertEqual(
            image_seg["data"]["file"],
            "https://img.example/file/pic.jpg?width=100&fit=cover",
        )

    def test_scaled_url_mode_without_processing_sends_original_url(self):
        self.plugin.settings["image"]["enableProcessing"] = False
        bot = self.FakeBot()
        event = self.FakeEvent("/随机图", bot=bot, group_id="12345")
        self._fake_media_source("https://img.example/file/pic.jpg")
        self._forbid_download()
        self._run(self.plugin._handle_media(event, "image"), event)

        text_seg, image_seg = bot.calls[0][1]["message"]
        self.assertNotIn("已压缩", text_seg["data"]["text"])
        self.assertEqual(image_seg["data"]["file"], "https://img.example/file/pic.jpg")

    def test_original_image_always_sends_url(self):
        self.plugin.settings["image"]["sendMode"] = "local-compress"
        bot = self.FakeBot()
        self.plugin._remember_image(self.FakeEvent(), "https://img.example/file/pic.jpg")
        event = self.FakeEvent("/原图", bot=bot, group_id="12345")
        self._forbid_download()
        self._run(self.plugin.original_image(event), event)

        # /原图 始终直传原图 URL，不受 compress 模式影响
        action, params = bot.calls[0]
        self.assertEqual(action, "send_group_msg")
        self.assertEqual(params["message"][1]["data"]["file"], "https://img.example/file/pic.jpg")
        self.assertIn("（原图）", params["message"][0]["data"]["text"])


if __name__ == "__main__":
    unittest.main()
