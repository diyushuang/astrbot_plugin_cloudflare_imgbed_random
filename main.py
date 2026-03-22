from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star
from astrbot.api import logger, AstrBotConfig
from astrbot.api.message_components import Plain, Image, Video
import asyncio
import aiohttp
from urllib.parse import urlparse
import json

class SuijituPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.name = 'suijitu'
        self.description = '随机图床图片和视频发送插件'
        self.version = '1.0.0'
        self.astrbot_config = config
        self.config = {}
        logger.info(f"[suijitu] 插件初始化完成")
    
    async def on_load(self):
        '''插件加载时调用''' 
        try:
            await self._load_config()
            logger.info(f"[suijitu] 插件加载完成")
        except Exception as e:
            logger.error(f"[suijitu] 插件加载失败: {str(e)}")
            self.config = {
                "apiUrl": "https://example.com",
                "timeout": 10,
                "retryCount": 3
            }
    
    async def _load_config(self):
        try:
            config = self.astrbot_config
            api_url = config.get("apiUrl") if config else None
            timeout = config.get("timeout") if config else None
            retry_count = config.get("retryCount") if config else None
            
            if not api_url:
                api_url = "https://example.com"
            if timeout is None or timeout <= 0:
                timeout = 10
            if retry_count is None or retry_count < 0:
                retry_count = 3
            
            self.config = {
                "apiUrl": api_url,
                "timeout": timeout,
                "retryCount": retry_count
            }
        except Exception as e:
            logger.error(f"[suijitu] 加载配置失败: {str(e)}")
            self.config = {
                "apiUrl": "https://example.com",
                "timeout": 10,
                "retryCount": 3
            }
    
    async def _get_random_media(self):
        if not self.config:
            await self._load_config()
        
        api_url = self.config.get('apiUrl')
        
        if api_url == 'https://example.com' or api_url == 'http://example.com':
            logger.warning("[suijitu] 检测到使用默认API地址，请在插件配置中设置正确的随机图床API地址")
            return None
        
        if not api_url:
            logger.error("[suijitu] API地址为空，请检查配置")
            return None
        
        retry_count = self.config.get('retryCount', 3)
        timeout = self.config.get('timeout', 10)
        
        for i in range(retry_count):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        api_url, 
                        allow_redirects=True,
                        timeout=aiohttp.ClientTimeout(total=timeout)
                    ) as response:
                        if response.status == 200:
                            content_type = response.headers.get('Content-Type', '')
                            
                            # 读取响应文本
                            text = None
                            try:
                                text = await response.text()
                            except Exception as e:
                                logger.error(f"[suijitu] 读取响应文本失败: {str(e)}")
                                continue
                            
                            # 尝试解析JSON
                            media_url = None
                            is_json = False
                            try:
                                data = json.loads(text)
                                is_json = True
                            except Exception:
                                pass
                            
                            if is_json:
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
                            elif 'image/' in content_type or 'video/' in content_type:
                                media_url = str(response.url)
                            else:
                                media_url = text.strip() if text else str(response.url)
                            
                            if media_url:
                                return media_url
                        else:
                            logger.warning(f"[suijitu] 获取随机媒体失败，状态码: {response.status}")
            except asyncio.TimeoutError:
                logger.warning(f"[suijitu] 获取随机媒体超时")
            except Exception as e:
                logger.error(f"[suijitu] 获取随机媒体失败: {str(e)}")
            
            if i < retry_count - 1:
                await asyncio.sleep(1)
        
        logger.error("[suijitu] 所有重试失败，无法获取随机媒体")
        return None
    
    @filter.command("随机图", alias={"suijitu", "random", "随机图片", "randomimg"})
    async def handle_random_media(self, event: AstrMessageEvent):
        '''发送随机图片或视频''' 
        try:
            media_url = await self._get_random_media()
            
            if not media_url:
                yield event.plain_result("获取随机媒体失败")
                return
            
            if media_url.endswith(('.jpg', '.jpeg', '.png', '.gif')):
                chain = [
                    Plain("随机图片发送成功"),
                    Image.fromURL(media_url)
                ]
                yield event.chain_result(chain)
            elif media_url.endswith(('.mp4', '.avi', '.mov', '.wmv')):
                chain = [
                    Plain("随机视频发送成功"),
                    Video.fromURL(media_url)
                ]
                yield event.chain_result(chain)
            else:
                yield event.plain_result(f"随机媒体发送成功: {media_url}")
        except Exception as e:
            logger.error(f"[suijitu] 命令处理失败: {str(e)}")
            yield event.plain_result(f"命令处理失败: {str(e)}")
    
    @filter.llm_tool(name="sendRandomMedia")
    async def send_random_media(self, event: AstrMessageEvent):
        '''发送随机图片或视频
        
        无参数
        
        返回结构化数据：
        - success: 是否成功
        - media_url: 媒体URL（成功时）
        - message: 结果消息
        '''
        try:
            media_url = await self._get_random_media()
            
            if media_url:
                return {
                    "success": True,
                    "media_url": media_url,
                    "message": "随机媒体发送成功"
                }
            else:
                return {
                    "success": False,
                    "media_url": None,
                    "message": "获取随机媒体失败"
                }
        except Exception as e:
            logger.error(f"[suijitu] LLM工具调用失败: {str(e)}")
            return {
                "success": False,
                "media_url": None,
                "message": f"LLM工具调用失败: {str(e)}"
            }
    
    async def terminate(self):
        '''插件卸载时调用''' 
        logger.info("[suijitu] 插件已卸载")
