from typing import Optional
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import Plain, Image, Video
import asyncio
import aiohttp
from urllib.parse import urlparse, urlencode
import json


@register("cloudflare_imgbed_random", "", "从CloudFlare ImgBed图床中获取随机图片", "1.0.0")
class CloudflareImgbedRandomPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.config = {}

    async def initialize(self):
        """插件初始化"""
        await self._load_config()
        logger.info(f"[cloudflare_imgbed_random] 插件初始化完成")

    async def _load_config(self):
        '''加载插件配置'''
        try:
            config = self.context.get_config()

            imgbed_domain = config.get("imgbedDomain") if config else None
            api_endpoint = config.get("apiEndpoint") if config else None
            api_token = config.get("apiToken") if config else None
            default_dir = config.get("defaultDir") if config else None
            timeout = config.get("timeout") if config else None
            retry_count = config.get("retryCount") if config else None
            enable_llm = config.get("enableLLM") if config else None

            imgbed_domain = imgbed_domain or "https://example.com"
            api_endpoint = api_endpoint or "/random"
            api_token = api_token or ""
            default_dir = default_dir or ""
            timeout = timeout if timeout is not None and timeout > 0 else 10
            retry_count = retry_count if retry_count is not None and retry_count >= 0 else 3
            enable_llm = enable_llm if enable_llm is not None else True

            self.config = {
                "imgbedDomain": imgbed_domain,
                "apiEndpoint": api_endpoint,
                "apiToken": api_token,
                "defaultDir": default_dir,
                "timeout": timeout,
                "retryCount": retry_count,
                "enableLLM": enable_llm
            }

            logger.info(f"[cloudflare_imgbed_random] 配置加载成功")
        except Exception as e:
            logger.error(f"[cloudflare_imgbed_random] 加载配置失败: {str(e)}")
            self.config = {
                "imgbedDomain": "https://example.com",
                "apiEndpoint": "/random",
                "apiToken": "",
                "defaultDir": "",
                "timeout": 10,
                "retryCount": 3,
                "enableLLM": True
            }

    def _get_message_text(self, event: AstrMessageEvent):
        '''从事件中提取消息文本'''
        try:
            if hasattr(event, 'message_str') and event.message_str:
                return event.message_str
            elif hasattr(event, 'message') and event.message:
                if isinstance(event.message, str):
                    return event.message
                if hasattr(event.message, 'chain'):
                    texts = []
                    for comp in event.message.chain:
                        if hasattr(comp, 'text'):
                            texts.append(comp.text)
                    return ' '.join(texts)
            elif hasattr(event, 'get_message'):
                msg = event.get_message()
                if isinstance(msg, str):
                    return msg
            elif hasattr(event, 'raw_message'):
                if isinstance(event.raw_message, str):
                    return event.raw_message
            elif hasattr(event, 'content'):
                if isinstance(event.content, str):
                    return event.content
            elif hasattr(event, 'text'):
                if isinstance(event.text, str):
                    return event.text
        except Exception as e:
            logger.error(f"[cloudflare_imgbed_random] 提取消息文本失败: {str(e)}")
        return None

    async def _get_random_media(self, directory=None, content_type=None):
        '''获取随机媒体URL'''
        try:
            logger.info(f"[cloudflare_imgbed_random] 开始获取随机媒体 - directory: {directory}, content_type: {content_type}")

            if not self.config:
                await self._load_config()

            imgbed_domain = self.config.get('imgbedDomain')
            api_endpoint = self.config.get('apiEndpoint')
            api_token = self.config.get('apiToken')
            default_dir = self.config.get('defaultDir')

            if not imgbed_domain:
                logger.error("[cloudflare_imgbed_random] 图床域名为空，请检查配置")
                return None

            if imgbed_domain in ('https://example.com', 'http://example.com'):
                logger.warning("[cloudflare_imgbed_random] 检测到使用默认图床域名，请在插件配置中设置正确的CloudFlare ImgBed图床域名")
                return None

            if not api_endpoint:
                logger.error("[cloudflare_imgbed_random] API接口路径为空，请检查配置")
                return None

            if api_endpoint.startswith('/'):
                api_url = f"{imgbed_domain}{api_endpoint}"
            else:
                api_url = f"{imgbed_domain}/{api_endpoint}"

            target_dir = directory or default_dir

            params = {
                'type': 'url',
                'form': 'json'
            }
            if target_dir:
                params['dir'] = target_dir
            if content_type:
                params['content'] = content_type

            if params:
                separator = '&' if '?' in api_url else '?'
                api_url = f"{api_url}{separator}{urlencode(params)}"

            retry_count = self.config.get('retryCount', 3)
            timeout = self.config.get('timeout', 10)

            for i in range(retry_count):
                try:
                    headers = {}
                    if api_token:
                        headers['Authorization'] = api_token

                    async with aiohttp.ClientSession() as session:
                        async with session.get(
                            api_url,
                            allow_redirects=True,
                            headers=headers,
                            timeout=aiohttp.ClientTimeout(total=timeout)
                        ) as response:
                            if response.status == 200:
                                content_type_header = response.headers.get('Content-Type', '')

                                text = None
                                try:
                                    text = await response.text()
                                except Exception as e:
                                    logger.error(f"[cloudflare_imgbed_random] 读取响应文本失败: {str(e)}")
                                    continue

                                media_url = None
                                try:
                                    data = json.loads(text)

                                    if isinstance(data, dict):
                                        if 'url' in data:
                                            media_url = data.get('url', '')
                                        elif 'data' in data and isinstance(data['data'], dict):
                                            media_url = data['data'].get('url', '')

                                    if media_url and media_url.startswith('/'):
                                        parsed_url = urlparse(api_url)
                                        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
                                        media_url = base_url + media_url

                                    if not media_url:
                                        media_url = str(response.url)
                                except Exception as e:
                                    if 'image/' in content_type_header or 'video/' in content_type_header:
                                        media_url = str(response.url)
                                    else:
                                        media_url = text.strip() if text else str(response.url)

                                if media_url:
                                    try:
                                        parsed_url = urlparse(media_url)
                                        if not parsed_url.scheme or not parsed_url.netloc:
                                            logger.warning(f"[cloudflare_imgbed_random] URL格式无效: {media_url}")
                                            continue
                                        if parsed_url.scheme not in ['http', 'https']:
                                            logger.warning(f"[cloudflare_imgbed_random] URL协议无效: {media_url}")
                                            continue
                                    except Exception as e:
                                        logger.warning(f"[cloudflare_imgbed_random] URL解析失败: {str(e)}")
                                        continue

                                    logger.info(f"[cloudflare_imgbed_random] 成功获取媒体URL: {media_url}")
                                    return media_url
                            else:
                                logger.warning(f"[cloudflare_imgbed_random] 请求失败，状态码: {response.status}")

                except asyncio.TimeoutError:
                    logger.warning(f"[cloudflare_imgbed_random] 第{i+1}次请求超时")
                except Exception as e:
                    logger.error(f"[cloudflare_imgbed_random] 第{i+1}次请求失败: {str(e)}")

            logger.error(f"[cloudflare_imgbed_random] 所有{retry_count}次请求均失败")
            return None

        except Exception as e:
            logger.error(f"[cloudflare_imgbed_random] 获取随机媒体失败: {str(e)}")
            return None

    def _extract_directory(self, message: str):
        '''从消息中提取目录和内容类型'''
        if not message:
            return None, None

        message = message.strip()

        if message.startswith('/随机图'):
            dir_part = message[4:].strip() if len(message) > 4 else ''
            return dir_part, 'image'
        elif message.startswith('/随机视频'):
            dir_part = message[5:].strip() if len(message) > 5 else ''
            return dir_part, 'video'
        elif '随机图' in message or '随机图片' in message:
            return '', 'image'
        elif '随机视频' in message:
            return '', 'video'

        return None, None

    @filter.command("/随机图")
    async def random_image(self, event: AstrMessageEvent):
        '''发送随机图片'''
        logger.info("[cloudflare_imgbed_random] 命令处理器被触发: /随机图")
        try:
            async for result in self._handle_media(event, 'image'):
                yield result
        except Exception as e:
            logger.error(f"[cloudflare_imgbed_random] 处理/随机图命令失败: {str(e)}")
            yield event.plain_result(f"处理命令失败: {str(e)}")

    @filter.command("/随机视频")
    async def random_video(self, event: AstrMessageEvent):
        '''发送随机视频'''
        logger.info("[cloudflare_imgbed_random] 命令处理器被触发: /随机视频")
        try:
            async for result in self._handle_media(event, 'video'):
                yield result
        except Exception as e:
            logger.error(f"[cloudflare_imgbed_random] 处理/随机视频命令失败: {str(e)}")
            yield event.plain_result(f"处理命令失败: {str(e)}")

    async def _handle_media(self, event: AstrMessageEvent, content_type=None):
        '''处理媒体请求的统一方法'''
        try:
            logger.info(f"[cloudflare_imgbed_random] 开始处理媒体请求，content_type: {content_type}")

            directory = None
            message = self._get_message_text(event)
            logger.info(f"[cloudflare_imgbed_random] 获取到消息: {message}")

            if message:
                dir_part, type_part = self._extract_directory(message)
                if dir_part is not None:
                    directory = dir_part
                if type_part:
                    content_type = type_part

            media_url = await self._get_random_media(directory, content_type)

            if not media_url:
                yield event.plain_result("获取随机媒体失败，请检查配置或稍后重试")
                return

            logger.info(f"[cloudflare_imgbed_random] 获取到媒体URL: {media_url}")

            try:
                if media_url.endswith(('.jpg', '.jpeg', '.png', '.gif')):
                    yield event.chain_result([Plain("随机图片发送成功"), Image.fromURL(media_url)])
                elif media_url.endswith(('.mp4', '.avi', '.mov', '.wmv', '.flv', '.mkv')):
                    yield event.chain_result([Plain("随机视频发送成功"), Video.fromURL(media_url)])
                else:
                    yield event.plain_result(f"随机媒体发送成功: {media_url}")
            except Exception as e:
                logger.error(f"[cloudflare_imgbed_random] 发送媒体失败: {str(e)}")
                yield event.plain_result(f"发送媒体时出错: {str(e)}")

        except Exception as e:
            logger.error(f"[cloudflare_imgbed_random] 命令处理失败: {str(e)}")
            yield event.plain_result(f"命令处理失败: {str(e)}")

    @filter.llm_tool(name="sendRandomMedia")
    async def send_random_media(self, event: AstrMessageEvent, directory: str, content_type: str):
        '''发送随机图片或视频。

        当用户请求随机图片或视频时使用此工具，例如：
        - "随机图"
        - "随机图片"
        - "随机视频"
        - "给我一张随机图片"
        - "我想要一个随机视频"

        Args:
            directory(string): 目录路径，指定从哪个目录获取随机图片
            content_type(string): 内容类型，指定获取图片或视频，可选值：image, video
        '''
        try:
            if not self.config:
                await self._load_config()

            enable_llm = self.config.get("enableLLM", True)
            if not enable_llm:
                logger.warning("[cloudflare_imgbed_random] LLM调用已被禁用")
                yield event.plain_result("LLM调用已被禁用，请使用命令方式调用")
                return

            extracted_directory = directory
            extracted_content_type = content_type

            message = self._get_message_text(event)
            logger.debug(f"[cloudflare_imgbed_random] 消息内容: {message}")

            if message and not message.startswith('/'):
                dir_part, type_part = self._extract_directory(message)
                if dir_part:
                    extracted_directory = dir_part
                if type_part:
                    extracted_content_type = type_part

            if not extracted_content_type:
                extracted_content_type = 'image'

            logger.info(f"[cloudflare_imgbed_random] LLM工具调用参数: 目录={extracted_directory}, 内容类型={extracted_content_type}")

            async for result in self._handle_media(event, extracted_content_type):
                yield result

        except Exception as e:
            logger.error(f"[cloudflare_imgbed_random] LLM工具调用失败: {str(e)}")
            yield event.plain_result(f"LLM工具调用失败: {str(e)}")

    async def terminate(self):
        """插件销毁"""
        logger.info("[cloudflare_imgbed_random] 插件已卸载")
