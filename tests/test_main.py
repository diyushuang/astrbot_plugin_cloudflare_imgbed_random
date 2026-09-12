"""suijitu 插件单元测试。

先以 stub 替换 astrbot.* 模块（无需安装 AstrBot）再导入 main，
覆盖目录提取、URL 解析与校验、随机媒体请求、媒体文件名解析
及发送文案构建。
"""

import importlib
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
    message_components.Image = types.SimpleNamespace(fromURL=lambda url: url)
    message_components.Plain = lambda value: value
    message_components.Video = types.SimpleNamespace(fromURL=lambda url: url)
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


if __name__ == "__main__":
    unittest.main()