from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star
from astrbot.api import logger, AstrBotConfig
from astrbot.api.message_components import Plain, Image, Video
import asyncio
import aiohttp
from urllib.parse import urlparse, urlencode
import json

class CloudflareImgbedRandomPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.name = 'cloudflare_imgbed_random'
        self.description = '从CloudFlare ImgBed图床中获取随机图片'
        self.version = '1.0.0'
        self.astrbot_config = config
        self.config = {}
        logger.info(f"[cloudflare_imgbed_random] 插件初始化完成")
    
    async def on_load(self):
        '''插件加载时调用''' 
        try:
            await self._load_config()
            logger.info(f"[cloudflare_imgbed_random] 插件加载完成")
        except Exception as e:
            logger.error(f"[cloudflare_imgbed_random] 插件加载失败: {str(e)}")
            self.config = {
                "imgbedDomain": "https://example.com",
                "apiEndpoint": "/random",
                "apiToken": "",
                "defaultDir": "",
                "timeout": 10,
                "retryCount": 3
            }
    
    async def _load_config(self):
        try:
            config = self.astrbot_config
            imgbed_domain = config.get("imgbedDomain") if config else None
            api_endpoint = config.get("apiEndpoint") if config else None
            api_token = config.get("apiToken") if config else None
            default_dir = config.get("defaultDir") if config else None
            timeout = config.get("timeout") if config else None
            retry_count = config.get("retryCount") if config else None
            
            imgbed_domain = imgbed_domain or "https://example.com"
            api_endpoint = api_endpoint or "/random"
            api_token = api_token or ""
            default_dir = default_dir or ""
            # timeout需要大于0，因为超时时间不能为0或负数
            timeout = timeout if timeout is not None and timeout > 0 else 10
            # retry_count可以为0，表示不重试
            retry_count = retry_count if retry_count is not None and retry_count >= 0 else 3
            
            self.config = {
                "imgbedDomain": imgbed_domain,
                "apiEndpoint": api_endpoint,
                "apiToken": api_token,
                "defaultDir": default_dir,
                "timeout": timeout,
                "retryCount": retry_count
            }
        except Exception as e:
            logger.error(f"[cloudflare_imgbed_random] 加载配置失败: {str(e)}")
            self.config = {
                "imgbedDomain": "https://example.com",
                "apiEndpoint": "/random",
                "apiToken": "",
                "defaultDir": "",
                "timeout": 10,
                "retryCount": 3
            }
    
    async def _get_random_media(self, directory=None, content_type=None):
        if not self.config:
            await self._load_config()
        
        imgbed_domain = self.config.get('imgbedDomain')
        api_endpoint = self.config.get('apiEndpoint')
        api_token = self.config.get('apiToken')
        default_dir = self.config.get('defaultDir')
        
        if imgbed_domain in ('https://example.com', 'http://example.com'):
            logger.warning("[cloudflare_imgbed_random] 检测到使用默认图床域名，请在插件配置中设置正确的CloudFlare ImgBed图床域名")
            return None
        
        if not imgbed_domain:
            logger.error("[cloudflare_imgbed_random] 图床域名为空，请检查配置")
            return None
        
        if not api_endpoint:
            logger.error("[cloudflare_imgbed_random] API接口路径为空，请检查配置")
            return None
        
        # 构建完整的API URL
        if api_endpoint.startswith('/'):
            api_url = f"{imgbed_domain}{api_endpoint}"
        else:
            api_url = f"{imgbed_domain}/{api_endpoint}"
        
        target_dir = directory or default_dir
        
        params = {}
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
                            content_type = response.headers.get('Content-Type', '')
                            
                            text = None
                            try:
                                text = await response.text()
                            except Exception as e:
                                logger.error(f"[cloudflare_imgbed_random] 读取响应文本失败: {str(e)}")
                                continue
                            
                            media_url = None
                            try:
                                # 尝试解析JSON响应
                                data = json.loads(text)
                                
                                # 从JSON中提取URL
                                if isinstance(data, dict):
                                    if 'url' in data:
                                        media_url = data.get('url', '')
                                    elif 'data' in data and isinstance(data['data'], dict):
                                        media_url = data['data'].get('url', '')
                                
                                # 处理相对路径
                                if media_url and media_url.startswith('/'):
                                    parsed_url = urlparse(api_url)
                                    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
                                    media_url = base_url + media_url
                                
                                # 如果未找到URL，使用响应URL
                                if not media_url:
                                    media_url = str(response.url)
                            except Exception:
                                # 非JSON响应处理
                                if 'image/' in content_type or 'video/' in content_type:
                                    media_url = str(response.url)
                                else:
                                    media_url = text.strip() if text else str(response.url)
                            
                            if media_url:
                                return media_url
                        else:
                            logger.warning(f"[cloudflare_imgbed_random] 获取随机媒体失败，状态码: {response.status}")
            except asyncio.TimeoutError:
                logger.warning("[cloudflare_imgbed_random] 获取随机媒体超时")
            except Exception as e:
                logger.error(f"[cloudflare_imgbed_random] 获取随机媒体失败: {str(e)}")
            
            if i < retry_count - 1:
                await asyncio.sleep(1)
        
        logger.error("[cloudflare_imgbed_random] 所有重试失败，无法获取随机媒体")
        return None
    
    def _extract_directory(self, message):
        '''从消息中提取目录参数''' 
        if not message:
            return None, None
        
        # 检查是否是视频命令
        if message.startswith('/随机视频') and len(message) > 5:
            return message[5:].strip(), 'video'
        elif message.startswith('随机视频') and len(message) > 4:
            return message[4:].strip(), 'video'
        elif message.startswith('/随机图') and len(message) > 4:
            return message[4:].strip(), 'image'
        elif message.startswith('随机图') and len(message) > 3:
            return message[3:].strip(), 'image'
        return None, None
    
    @filter.command("随机图", alias={"/随机图", "imgbed", "random", "随机图片", "randomimg"})
    @filter.command("随机视频", alias={"/随机视频", "randomvideo", "随机影片"})
    async def handle_random_media(self, event: AstrMessageEvent):
        '''发送随机图片或视频
        
        用法：
        随机图 - 从默认目录获取随机图片
        随机图 目录路径 - 从指定目录获取随机图片
        /随机图 - 从默认目录获取随机图片
        /随机图 目录路径 - 从指定目录获取随机图片
        随机视频 - 从默认目录获取随机视频
        随机视频 目录路径 - 从指定目录获取随机视频
        /随机视频 - 从默认目录获取随机视频
        /随机视频 目录路径 - 从指定目录获取随机视频
        ''' 
        try:
            message = None
            if hasattr(event, 'message'):
                message = event.message
            elif hasattr(event, 'get_message'):
                message = event.get_message()
            elif hasattr(event, 'raw_message'):
                message = event.raw_message
            
            directory, content_type = self._extract_directory(message)
            if directory:
                logger.info(f"[cloudflare_imgbed_random] 指定目录: {directory}, 内容类型: {content_type}")
            
            media_url = await self._get_random_media(directory, content_type)
            
            if not media_url:
                yield event.plain_result("获取随机媒体失败")
                return
            
            if media_url.endswith(('.jpg', '.jpeg', '.png', '.gif')):
                yield event.chain_result([Plain("随机图片发送成功"), Image.fromURL(media_url)])
            elif media_url.endswith(('.mp4', '.avi', '.mov', '.wmv', '.flv', '.mkv')):
                yield event.chain_result([Plain("随机视频发送成功"), Video.fromURL(media_url)])
            else:
                yield event.plain_result(f"随机媒体发送成功: {media_url}")
        except Exception as e:
            logger.error(f"[cloudflare_imgbed_random] 命令处理失败: {str(e)}")
            yield event.plain_result(f"命令处理失败: {str(e)}")
    
    @filter.llm_tool(name="sendRandomMedia")
    async def send_random_media(self, event, directory: str = None, content_type: str = None):
        '''发送随机图片或视频
        
        当用户请求随机图片或视频时使用此工具。
        适用于用户提到"随机图"、"随机图片"、"随机视频"等关键词的情况。
        
        参数：
        - directory: 目录路径（可选），指定从哪个目录获取随机图片
        - content_type: 内容类型（可选），指定获取图片或视频，可选值：image, video
        
        返回：
        - 成功时返回包含图片URL的结构化数据
        - 失败时返回错误信息
        '''
        try:
            if directory is None and event:
                message = None
                if hasattr(event, 'message'):
                    message = event.message
                elif hasattr(event, 'get_message'):
                    message = event.get_message()
                elif hasattr(event, 'raw_message'):
                    message = event.raw_message
                
                directory, extracted_content_type = self._extract_directory(message)
                if extracted_content_type:
                    content_type = extracted_content_type
                if directory:
                    logger.info(f"[cloudflare_imgbed_random] 从事件中提取目录: {directory}, 内容类型: {content_type}")
            
            media_url = await self._get_random_media(directory, content_type)
            
            if media_url:
                if media_url.endswith(('.jpg', '.jpeg', '.png', '.gif')):
                    yield event.chain_result([Plain("随机图片发送成功"), Image.fromURL(media_url)])
                elif media_url.endswith(('.mp4', '.avi', '.mov', '.wmv', '.flv', '.mkv')):
                    yield event.chain_result([Plain("随机视频发送成功"), Video.fromURL(media_url)])
                else:
                    yield event.plain_result(f"随机媒体发送成功: {media_url}")
                return {"success": True, "media_url": media_url, "message": "随机媒体发送成功"}
            else:
                yield event.plain_result("获取随机媒体失败")
                return {"success": False, "media_url": None, "message": "获取随机媒体失败"}
        except Exception as e:
            logger.error(f"[cloudflare_imgbed_random] LLM工具调用失败: {str(e)}")
            yield event.plain_result(f"LLM工具调用失败: {str(e)}")
            return {"success": False, "media_url": None, "message": f"LLM工具调用失败: {str(e)}"}
    
    async def terminate(self):
        '''插件卸载时调用''' 
        logger.info("[cloudflare_imgbed_random] 插件已卸载")
