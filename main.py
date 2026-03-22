from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star
from astrbot.api import logger
from astrbot.api.message_components import Plain, Image, Video
import asyncio
import aiohttp

class SuijituPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.name = 'suijitu'
        self.description = '随机图床图片和视频发送插件'
        self.version = '1.0.0'
        self.config = {}
    
    async def onLoad(self):
        '''插件加载时调用''' 
        await self._load_config()
        logger.info("随机图床插件已加载")
    
    async def _load_config(self):
        try:
            # 首先从AstrBot配置中获取
            config = self.context.get_config() or {}
            
            # 检查AstrBot配置是否存在
            if config:
                # 如果AstrBot配置存在，使用AstrBot配置
                api_url = config.get("apiUrl", "https://example.com")
                timeout = config.get("timeout", 10)
                retry_count = config.get("retryCount", 3)
                
                # 将AstrBot配置保存到KV存储
                await self.put_kv_data("apiUrl", api_url)
                await self.put_kv_data("timeout", timeout)
                await self.put_kv_data("retryCount", retry_count)
            else:
                # 如果AstrBot配置不存在，从KV存储中获取
                api_url = await self.get_kv_data("apiUrl", "https://example.com")
                timeout = await self.get_kv_data("timeout", 10)
                retry_count = await self.get_kv_data("retryCount", 3)
            
            # 确保配置值有效
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
            return self.config
        except Exception as e:
            logger.error(f"加载配置失败: {str(e)}")
            # 回退到默认配置
            self.config = {
                "apiUrl": "https://example.com",
                "timeout": 10,
                "retryCount": 3
            }
            return self.config
    
    async def _get_random_media(self):
        if not self.config.get('apiUrl'):
            return None
        
        retry_count = self.config.get('retryCount', 3)
        timeout = self.config.get('timeout', 10)
        
        for i in range(retry_count):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        self.config.get('apiUrl'), 
                        allow_redirects=True,
                        timeout=aiohttp.ClientTimeout(total=timeout)
                    ) as response:
                        if response.status == 200:
                            media_url = str(response.url)
                            logger.info(f"获取随机媒体成功: {media_url}")
                            return media_url
                        else:
                            logger.warning(f"获取随机媒体失败，状态码: {response.status}, 尝试 {i+1}/{retry_count}")
            except asyncio.TimeoutError:
                logger.warning(f"获取随机媒体超时，尝试 {i+1}/{retry_count}")
            except Exception as e:
                logger.error(f"获取随机媒体失败: {str(e)}, 尝试 {i+1}/{retry_count}")
            
            # 重试间隔
            if i < retry_count - 1:
                await asyncio.sleep(1)
        
        return None
    
    @filter.command("随机图", alias={"suijitu", "random", "随机图片", "randomimg"})
    async def handle_random_media(self, event: AstrMessageEvent):
        '''发送随机图片或视频''' 
        media_url = await self._get_random_media()
        if not media_url:
            yield event.plain_result("获取随机媒体失败")
            return
        
        # 直接使用AstrBot的消息发送API发送消息
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
    
    @filter.llm_tool(name="sendRandomMedia")
    async def send_random_media(self, event: AstrMessageEvent):
        '''发送随机图片或视频
        
        无参数
        
        返回结构化数据：
        - success: 是否成功
        - media_url: 媒体URL（成功时）
        - message: 结果消息
        '''
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
    
    async def terminate(self):
        '''插件卸载时调用''' 
        logger.info("随机图床插件已卸载")
