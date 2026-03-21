from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star
from astrbot.api import logger
from astrbot.api.message_components import Plain, Image, Video
from astrbot.core.utils.astrbot_path import get_astrbot_data_path
import os
import asyncio
import aiohttp

class SuijituPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.name = 'suijitu'
        self.description = '随机图床图片和视频发送插件'
        self.version = '1.0.0'
        self.config = self._load_config()
    
    def _load_config(self):
        try:
            config = self.context.get_config()
            return {
                "apiUrl": config.get("apiUrl", "https://example.com")
            }
        except Exception:
            return {
                "apiUrl": "https://example.com"
            }
    
    async def _get_random_media(self):
        if not self.config['apiUrl']:
            return None
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.config['apiUrl'], allow_redirects=True) as response:
                    if response.status == 200:
                        return str(response.url)
            return None
        except Exception as e:
            logger.error(f"获取随机媒体失败: {str(e)}")
            return None
    
    @filter.command("随机图", alias={"suijitu", "random"})
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
        '''
        media_url = await self._get_random_media()
        if media_url:
            return f"随机媒体发送成功: {media_url}"
        else:
            return "获取随机媒体失败"
    
    async def terminate(self):
        '''插件卸载时调用''' 
        logger.info("随机图床插件已卸载")
