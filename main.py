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
        logger.info("========== 插件初始化 ==========")
        logger.info(f"插件名称: {self.name}")
        logger.info(f"插件版本: {self.version}")
        logger.info(f"插件描述: {self.description}")
        logger.info("========== 插件初始化完成 ==========")
    
    async def on_load(self):
        '''插件加载时调用''' 
        logger.info("========== 开始加载随机图床插件 ==========")
        logger.info(f"插件名称: {self.name}")
        logger.info(f"插件版本: {self.version}")
        logger.info(f"插件描述: {self.description}")
        logger.info(f"插件上下文: {self.context}")
        logger.info(f"插件上下文类型: {type(self.context)}")
        
        try:
            logger.info("开始加载配置...")
            await self._load_config()
            logger.info("配置加载完成")
            logger.info("随机图床插件已加载")
            logger.info("========== 随机图床插件加载完成 ==========")
        except Exception as e:
            logger.error("========== 插件加载失败 ==========")
            logger.error(f"on_load方法执行失败: {str(e)}")
            logger.error(f"异常类型: {type(e)}")
            logger.error(f"异常详细信息: {repr(e)}")
            logger.error(f"异常堆栈信息:", exc_info=True)
            # 设置默认配置
            logger.info("设置默认配置...")
            self.config = {
                "apiUrl": "https://example.com",
                "timeout": 10,
                "retryCount": 3
            }
            logger.info(f"默认配置: {self.config}")
            logger.info("========== 使用默认配置继续运行 ==========")
    
    async def _load_config(self):
        logger.info("========== 开始加载配置 ==========")
        try:
            # 首先从AstrBot配置中获取
            logger.info("尝试从AstrBot获取配置...")
            logger.info(f"self.context类型: {type(self.context)}")
            logger.info(f"self.context: {self.context}")
            
            config = self.context.get_config() or {}
            
            logger.info(f"从AstrBot获取的配置: {config}")
            logger.info(f"配置类型: {type(config)}")
            logger.info(f"配置是否为空: {not config}")
            logger.info(f"配置键: {list(config.keys()) if config else []}")
            
            # 初始化配置值
            api_url = None
            timeout = None
            retry_count = None
            
            # 检查AstrBot配置是否存在
            if config:
                logger.info("AstrBot配置存在，开始解析配置...")
                # 如果AstrBot配置存在，使用AstrBot配置
                api_url = config.get("apiUrl")
                timeout = config.get("timeout")
                retry_count = config.get("retryCount")
                
                logger.info(f"AstrBot配置值 - api_url: {api_url}, timeout: {timeout}, retry_count: {retry_count}")
                logger.info(f"api_url类型: {type(api_url)}, timeout类型: {type(timeout)}, retry_count类型: {type(retry_count)}")
                
                # 将AstrBot配置保存到KV存储（只有当值不为None时）
                logger.info("开始保存配置到KV存储...")
                if api_url is not None:
                    logger.info(f"保存apiUrl到KV存储: {api_url}")
                    await self.put_kv_data("apiUrl", api_url)
                if timeout is not None:
                    logger.info(f"保存timeout到KV存储: {timeout}")
                    await self.put_kv_data("timeout", timeout)
                if retry_count is not None:
                    logger.info(f"保存retryCount到KV存储: {retry_count}")
                    await self.put_kv_data("retryCount", retry_count)
                logger.info("配置保存到KV存储完成")
            else:
                logger.info("AstrBot配置为空，将从KV存储获取配置")
            
            # 从KV存储中获取缺失的配置值
            logger.info("开始从KV存储获取缺失的配置值...")
            if api_url is None:
                logger.info("apiUrl为None，从KV存储获取...")
                api_url = await self.get_kv_data("apiUrl", "https://example.com")
                logger.info(f"从KV存储获取apiUrl: {api_url}")
            if timeout is None:
                logger.info("timeout为None，从KV存储获取...")
                timeout = await self.get_kv_data("timeout", 10)
                logger.info(f"从KV存储获取timeout: {timeout}")
            if retry_count is None:
                logger.info("retryCount为None，从KV存储获取...")
                retry_count = await self.get_kv_data("retryCount", 3)
                logger.info(f"从KV存储获取retryCount: {retry_count}")
            
            logger.info(f"从KV存储获取配置完成 - api_url: {api_url}, timeout: {timeout}, retry_count: {retry_count}")
            
            # 确保配置值有效
            logger.info("开始验证配置值...")
            if not api_url:
                logger.warning("api_url为空，使用默认值")
                api_url = "https://example.com"
            if timeout is None or timeout <= 0:
                logger.warning(f"timeout无效: {timeout}，使用默认值")
                timeout = 10
            if retry_count is None or retry_count < 0:
                logger.warning(f"retry_count无效: {retry_count}，使用默认值")
                retry_count = 3
            
            logger.info(f"配置值验证完成 - api_url: {api_url}, timeout: {timeout}, retry_count: {retry_count}")
            
            self.config = {
                "apiUrl": api_url,
                "timeout": timeout,
                "retryCount": retry_count
            }
            
            logger.info(f"最终配置: {self.config}")
            logger.info("========== 配置加载完成 ==========")
            return self.config
        except Exception as e:
            logger.error("========== 配置加载失败 ==========")
            logger.error(f"加载配置失败: {str(e)}")
            logger.error(f"异常类型: {type(e)}")
            logger.error(f"异常详细信息: {repr(e)}")
            logger.error(f"异常堆栈信息:", exc_info=True)
            # 回退到默认配置
            logger.info("设置默认配置...")
            self.config = {
                "apiUrl": "https://example.com",
                "timeout": 10,
                "retryCount": 3
            }
            logger.info(f"默认配置: {self.config}")
            logger.info("========== 使用默认配置继续运行 ==========")
            return self.config
    
    async def _get_random_media(self):
        logger.info("========== 开始获取随机媒体 ==========")
        logger.info(f"当前配置对象: {self.config}")
        logger.info(f"配置类型: {type(self.config)}")
        
        # 如果配置为空，尝试加载配置
        if not self.config:
            logger.warning("配置为空，尝试加载配置...")
            try:
                await self._load_config()
                logger.info(f"配置加载后的self.config: {self.config}")
            except Exception as e:
                logger.error(f"加载配置失败: {str(e)}")
                logger.error(f"异常类型: {type(e)}")
                logger.error(f"异常详细信息: {repr(e)}")
                logger.error(f"异常堆栈信息:", exc_info=True)
        
        api_url = self.config.get('apiUrl')
        logger.info(f"获取到的api_url: {api_url}")
        logger.info(f"api_url类型: {type(api_url)}")
        
        # 检查是否使用默认API地址
        if api_url == 'https://example.com' or api_url == 'http://example.com':
            logger.warning("检测到使用默认API地址，这可能不是有效的随机图API")
            logger.warning("请在插件配置中设置正确的随机图床API地址")
            logger.error("========== API地址为默认值 ==========")
            logger.error("API地址为默认值，请在插件配置中设置正确的随机图床API地址")
            logger.error("配置路径：AstrBot -> 插件管理 -> 随机图床 -> 配置")
            logger.error("========== 获取随机媒体失败 ==========")
            return None
        
        if not api_url:
            logger.error("========== API地址为空 ==========")
            logger.error("API地址为空，请检查配置")
            logger.error(f"完整的self.config内容: {self.config}")
            logger.error("========== 获取随机媒体失败 ==========")
            return None
        
        retry_count = self.config.get('retryCount', 3)
        timeout = self.config.get('timeout', 10)
        
        logger.info(f"开始获取随机媒体，API地址: {api_url}, 重试次数: {retry_count}, 超时时间: {timeout}")
        
        for i in range(retry_count):
            logger.info(f"========== 开始第 {i+1}/{retry_count} 次尝试 ==========")
            try:
                logger.info(f"创建aiohttp会话...")
                async with aiohttp.ClientSession() as session:
                    logger.info(f"发送GET请求到: {api_url}")
                    async with session.get(
                        api_url, 
                        allow_redirects=True,
                        timeout=aiohttp.ClientTimeout(total=timeout)
                    ) as response:
                        logger.info(f"收到响应，状态码: {response.status}")
                        logger.info(f"响应头: {dict(response.headers)}")
                        
                        if response.status == 200:
                            content_type = response.headers.get('Content-Type', '')
                            logger.info(f"响应内容类型: {content_type}")
                            
                            # 检查响应类型并处理
                            if 'application/json' in content_type:
                                logger.info("检测到JSON格式响应")
                                # JSON格式响应，解析获取url
                                try:
                                    logger.info("开始解析JSON...")
                                    data = await response.json()
                                    logger.info(f"JSON数据: {data}")
                                    media_url = data.get('url', '')
                                    logger.info(f"从JSON获取的url: {media_url}")
                                    if not media_url:
                                        logger.warning("JSON中的url为空，使用响应URL")
                                        media_url = str(response.url)
                                    logger.info(f"从JSON解析获取URL: {media_url}")
                                except Exception as e:
                                    logger.error(f"解析JSON失败: {str(e)}")
                                    logger.error(f"异常类型: {type(e)}")
                                    logger.error(f"异常详细信息: {repr(e)}")
                                    logger.error(f"异常堆栈信息:", exc_info=True)
                                    logger.info("使用响应URL作为回退")
                                    media_url = str(response.url)
                            elif 'image/' in content_type or 'video/' in content_type:
                                logger.info(f"检测到媒体文件响应: {content_type}")
                                # 直接返回图片或视频
                                media_url = str(response.url)
                                logger.info(f"直接使用响应URL: {media_url}")
                            else:
                                logger.info(f"检测到其他格式响应: {content_type}")
                                # 其他格式，尝试解析文本
                                try:
                                    logger.info("开始解析文本...")
                                    text = await response.text()
                                    logger.info(f"响应文本: {text}")
                                    media_url = text.strip()
                                    logger.info(f"从文本解析的URL: {media_url}")
                                    if not media_url:
                                        logger.warning("文本为空，使用响应URL")
                                        media_url = str(response.url)
                                    logger.info(f"从文本解析获取URL: {media_url}")
                                except Exception as e:
                                    logger.error(f"解析文本失败: {str(e)}")
                                    logger.error(f"异常类型: {type(e)}")
                                    logger.error(f"异常详细信息: {repr(e)}")
                                    logger.error(f"异常堆栈信息:", exc_info=True)
                                    logger.info("使用响应URL作为回退")
                                    media_url = str(response.url)
                            
                            logger.info(f"========== 获取随机媒体成功 ==========")
                            logger.info(f"媒体URL: {media_url}")
                            logger.info(f"媒体URL类型: {type(media_url)}")
                            return media_url
                        else:
                            logger.warning(f"========== 获取随机媒体失败 ==========")
                            logger.warning(f"获取随机媒体失败，状态码: {response.status}, 尝试 {i+1}/{retry_count}")
                            logger.warning(f"响应内容: {await response.text()}")
            except asyncio.TimeoutError:
                logger.warning(f"========== 获取随机媒体超时 ==========")
                logger.warning(f"获取随机媒体超时，尝试 {i+1}/{retry_count}")
            except Exception as e:
                logger.error(f"========== 获取随机媒体异常 ==========")
                logger.error(f"获取随机媒体失败: {str(e)}, 尝试 {i+1}/{retry_count}")
                logger.error(f"异常类型: {type(e)}")
                logger.error(f"异常详细信息: {repr(e)}")
                logger.error(f"异常堆栈信息:", exc_info=True)
            
            # 重试间隔
            if i < retry_count - 1:
                logger.info(f"等待1秒后重试...")
                await asyncio.sleep(1)
        
        logger.error("========== 所有重试失败 ==========")
        logger.error(f"所有重试失败，无法获取随机媒体")
        logger.error(f"API地址: {api_url}")
        logger.error(f"重试次数: {retry_count}")
        logger.error(f"超时时间: {timeout}")
        return None
    
    @filter.command("随机图", alias={"suijitu", "random", "随机图片", "randomimg"})
    async def handle_random_media(self, event: AstrMessageEvent):
        '''发送随机图片或视频''' 
        logger.info("========== 命令处理开始 ==========")
        logger.info(f"命令: 随机图")
        logger.info(f"事件类型: {type(event)}")
        logger.info(f"事件内容: {event}")
        
        try:
            logger.info("开始获取随机媒体...")
            media_url = await self._get_random_media()
            
            if not media_url:
                logger.error("获取随机媒体失败")
                logger.info("发送失败消息...")
                yield event.plain_result("获取随机媒体失败")
                logger.info("========== 命令处理结束 ==========")
                return
            
            logger.info(f"获取到媒体URL: {media_url}")
            logger.info("开始构建消息链...")
            
            # 直接使用AstrBot的消息发送API发送消息
            if media_url.endswith(('.jpg', '.jpeg', '.png', '.gif')):
                logger.info("检测到图片文件")
                chain = [
                    Plain("随机图片发送成功"),
                    Image.fromURL(media_url)
                ]
                logger.info(f"消息链: {chain}")
                logger.info("发送图片消息...")
                yield event.chain_result(chain)
            elif media_url.endswith(('.mp4', '.avi', '.mov', '.wmv')):
                logger.info("检测到视频文件")
                chain = [
                    Plain("随机视频发送成功"),
                    Video.fromURL(media_url)
                ]
                logger.info(f"消息链: {chain}")
                logger.info("发送视频消息...")
                yield event.chain_result(chain)
            else:
                logger.info("检测到其他格式文件")
                logger.info("发送纯文本消息...")
                yield event.plain_result(f"随机媒体发送成功: {media_url}")
            
            logger.info("========== 命令处理成功 ==========")
        except Exception as e:
            logger.error("========== 命令处理失败 ==========")
            logger.error(f"命令处理失败: {str(e)}")
            logger.error(f"异常类型: {type(e)}")
            logger.error(f"异常详细信息: {repr(e)}")
            logger.error(f"异常堆栈信息:", exc_info=True)
            logger.info("发送错误消息...")
            yield event.plain_result(f"命令处理失败: {str(e)}")
            logger.info("========== 命令处理结束 ==========")
    
    @filter.llm_tool(name="sendRandomMedia")
    async def send_random_media(self, event: AstrMessageEvent):
        '''发送随机图片或视频
        
        无参数
        
        返回结构化数据：
        - success: 是否成功
        - media_url: 媒体URL（成功时）
        - message: 结果消息
        '''
        logger.info("========== LLM工具调用开始 ==========")
        logger.info(f"工具名称: sendRandomMedia")
        logger.info(f"事件类型: {type(event)}")
        logger.info(f"事件内容: {event}")
        
        try:
            logger.info("开始获取随机媒体...")
            media_url = await self._get_random_media()
            
            if media_url:
                logger.info(f"获取随机媒体成功: {media_url}")
                result = {
                    "success": True,
                    "media_url": media_url,
                    "message": "随机媒体发送成功"
                }
                logger.info(f"返回结果: {result}")
                logger.info("========== LLM工具调用成功 ==========")
                return result
            else:
                logger.error("获取随机媒体失败")
                result = {
                    "success": False,
                    "media_url": None,
                    "message": "获取随机媒体失败"
                }
                logger.info(f"返回结果: {result}")
                logger.info("========== LLM工具调用结束 ==========")
                return result
        except Exception as e:
            logger.error("========== LLM工具调用失败 ==========")
            logger.error(f"LLM工具调用失败: {str(e)}")
            logger.error(f"异常类型: {type(e)}")
            logger.error(f"异常详细信息: {repr(e)}")
            logger.error(f"异常堆栈信息:", exc_info=True)
            result = {
                "success": False,
                "media_url": None,
                "message": f"LLM工具调用失败: {str(e)}"
            }
            logger.info(f"返回结果: {result}")
            logger.info("========== LLM工具调用结束 ==========")
            return result
    
    async def terminate(self):
        '''插件卸载时调用''' 
        logger.info("========== 开始卸载随机图床插件 ==========")
        logger.info("随机图床插件已卸载")
        logger.info("========== 随机图床插件卸载完成 ==========")
