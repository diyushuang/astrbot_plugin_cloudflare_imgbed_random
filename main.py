from astrbot.api.event import filter
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
            logger.info(f"[cloudflare_imgbed_random] 开始加载插件")
            await self._load_config()
            logger.info(f"[cloudflare_imgbed_random] 插件加载完成，配置: {self.config}")
            # 注册命令
            logger.info(f"[cloudflare_imgbed_random] 命令注册完成")
        except Exception as e:
            logger.error(f"[cloudflare_imgbed_random] 插件加载失败: {str(e)}")
            logger.error(f"[cloudflare_imgbed_random] 错误详情: {type(e).__name__}: {e}")
            import traceback
            logger.error(f"[cloudflare_imgbed_random] 堆栈信息: {traceback.format_exc()}")
            self.config = {
                "imgbedDomain": "https://example.com",
                "apiEndpoint": "/random",
                "apiToken": "",
                "defaultDir": "",
                "timeout": 10,
                "retryCount": 3,
                "enableLLM": True
            }
            logger.warning(f"[cloudflare_imgbed_random] 使用默认配置: {self.config}")
    
    async def _load_config(self):
        '''加载插件配置''' 
        try:
            config = self.astrbot_config
            logger.debug(f"[cloudflare_imgbed_random] 开始加载配置，配置对象: {config}")
            
            imgbed_domain = config.get("imgbedDomain") if config else None
            api_endpoint = config.get("apiEndpoint") if config else None
            api_token = config.get("apiToken") if config else None
            default_dir = config.get("defaultDir") if config else None
            timeout = config.get("timeout") if config else None
            retry_count = config.get("retryCount") if config else None
            enable_llm = config.get("enableLLM") if config else None
            
            logger.debug(f"[cloudflare_imgbed_random] 原始配置值 - imgbedDomain: {imgbed_domain}, apiEndpoint: {api_endpoint}, apiToken: {'***' if api_token else ''}, defaultDir: {default_dir}, timeout: {timeout}, retryCount: {retry_count}, enableLLM: {enable_llm}")
            
            imgbed_domain = imgbed_domain or "https://example.com"
            api_endpoint = api_endpoint or "/random"
            api_token = api_token or ""
            default_dir = default_dir or ""
            # timeout需要大于0，因为超时时间不能为0或负数
            timeout = timeout if timeout is not None and timeout > 0 else 10
            # retry_count可以为0，表示不重试
            retry_count = retry_count if retry_count is not None and retry_count >= 0 else 3
            # enable_llm默认为True
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
            
            logger.info(f"[cloudflare_imgbed_random] 配置加载成功: imgbedDomain={imgbed_domain}, apiEndpoint={api_endpoint}, defaultDir={default_dir}, timeout={timeout}, retryCount={retry_count}, enableLLM={enable_llm}")
        except Exception as e:
            logger.error(f"[cloudflare_imgbed_random] 加载配置失败: {str(e)}")
            logger.error(f"[cloudflare_imgbed_random] 错误详情: {type(e).__name__}: {e}")
            import traceback
            logger.error(f"[cloudflare_imgbed_random] 堆栈信息: {traceback.format_exc()}")
            self.config = {
                "imgbedDomain": "https://example.com",
                "apiEndpoint": "/random",
                "apiToken": "",
                "defaultDir": "",
                "timeout": 10,
                "retryCount": 3,
                "enableLLM": True
            }
            logger.warning(f"[cloudflare_imgbed_random] 使用默认配置: {self.config}")
    
    def _get_message_text(self, event):
        '''从事件中提取消息文本''' 
        try:
            # 尝试不同的方式获取消息文本
            if hasattr(event, 'message_str') and event.message_str:
                return event.message_str
            elif hasattr(event, 'message') and event.message:
                if isinstance(event.message, str):
                    return event.message
                # 如果是消息链，尝试提取文本
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
            # 尝试其他常见的消息属性
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
                logger.debug("[cloudflare_imgbed_random] 配置为空，重新加载配置")
                await self._load_config()
            
            imgbed_domain = self.config.get('imgbedDomain')
            api_endpoint = self.config.get('apiEndpoint')
            api_token = self.config.get('apiToken')
            default_dir = self.config.get('defaultDir')
            
            logger.debug(f"[cloudflare_imgbed_random] 配置值 - imgbedDomain: {imgbed_domain}, apiEndpoint: {api_endpoint}, defaultDir: {default_dir}")
            
            # 严格的配置验证
            if not imgbed_domain:
                logger.error("[cloudflare_imgbed_random] 图床域名为空，请检查配置")
                return None
            
            if imgbed_domain in ('https://example.com', 'http://example.com'):
                logger.warning("[cloudflare_imgbed_random] 检测到使用默认图床域名，请在插件配置中设置正确的CloudFlare ImgBed图床域名")
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
            
            # 构建参数
            params = {
                'type': 'url',  # 始终返回完整URL
                'form': 'json'  # 使用JSON格式响应
            }
            if target_dir:
                params['dir'] = target_dir
            if content_type:
                params['content'] = content_type
            
            # 添加参数到URL
            if params:
                separator = '&' if '?' in api_url else '?'
                api_url = f"{api_url}{separator}{urlencode(params)}"
            
            logger.debug(f"[cloudflare_imgbed_random] 构建的API URL: {api_url}")
            
            retry_count = self.config.get('retryCount', 3)
            timeout = self.config.get('timeout', 10)
            
            logger.debug(f"[cloudflare_imgbed_random] 重试次数: {retry_count}, 超时时间: {timeout}秒")
            
            for i in range(retry_count):
                try:
                    # 准备请求头
                    headers = {}
                    if api_token:
                        headers['Authorization'] = api_token
                        logger.debug(f"[cloudflare_imgbed_random] 使用API Token鉴权")
                    
                    logger.debug(f"[cloudflare_imgbed_random] 第{i+1}次请求，URL: {api_url}")
                    
                    # 发送请求
                    async with aiohttp.ClientSession() as session:
                        async with session.get(
                            api_url, 
                            allow_redirects=True,
                            headers=headers,
                            timeout=aiohttp.ClientTimeout(total=timeout)
                        ) as response:
                            logger.debug(f"[cloudflare_imgbed_random] 响应状态码: {response.status}, 响应头: {dict(response.headers)}")
                            
                            if response.status == 200:
                                content_type = response.headers.get('Content-Type', '')
                                logger.debug(f"[cloudflare_imgbed_random] 响应内容类型: {content_type}")
                                
                                # 读取响应文本
                                text = None
                                try:
                                    text = await response.text()
                                    logger.debug(f"[cloudflare_imgbed_random] 响应文本长度: {len(text) if text else 0}")
                                except Exception as e:
                                    logger.error(f"[cloudflare_imgbed_random] 读取响应文本失败: {str(e)}")
                                    continue
                                
                                media_url = None
                                try:
                                    # 尝试解析JSON响应
                                    logger.debug("[cloudflare_imgbed_random] 尝试解析JSON响应")
                                    data = json.loads(text)
                                    logger.debug(f"[cloudflare_imgbed_random] JSON解析成功，数据类型: {type(data)}")
                                    
                                    # 从JSON中提取URL
                                    if isinstance(data, dict):
                                        if 'url' in data:
                                            media_url = data.get('url', '')
                                            logger.debug(f"[cloudflare_imgbed_random] 从JSON字段'url'提取URL: {media_url}")
                                        elif 'data' in data and isinstance(data['data'], dict):
                                            media_url = data['data'].get('url', '')
                                            logger.debug(f"[cloudflare_imgbed_random] 从JSON字段'data.url'提取URL: {media_url}")
                                    
                                    # 处理相对路径
                                    if media_url and media_url.startswith('/'):
                                        parsed_url = urlparse(api_url)
                                        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
                                        media_url = base_url + media_url
                                        logger.debug(f"[cloudflare_imgbed_random] 处理相对路径，完整URL: {media_url}")
                                    
                                    # 如果未找到URL，使用响应URL
                                    if not media_url:
                                        media_url = str(response.url)
                                        logger.debug(f"[cloudflare_imgbed_random] 未找到URL，使用响应URL: {media_url}")
                                except Exception as e:
                                    # 非JSON响应处理
                                    logger.debug(f"[cloudflare_imgbed_random] JSON解析失败，尝试非JSON处理: {str(e)}")
                                    if 'image/' in content_type or 'video/' in content_type:
                                        media_url = str(response.url)
                                        logger.debug(f"[cloudflare_imgbed_random] 检测到图片/视频类型，使用响应URL: {media_url}")
                                    else:
                                        media_url = text.strip() if text else str(response.url)
                                        logger.debug(f"[cloudflare_imgbed_random] 使用文本响应作为URL: {media_url}")
                                
                                if media_url:
                                    # 验证URL格式
                                    try:
                                        parsed_url = urlparse(media_url)
                                        if not parsed_url.scheme or not parsed_url.netloc:
                                            logger.warning(f"[cloudflare_imgbed_random] URL格式无效: {media_url}")
                                            continue
                                        # 确保URL使用http或https协议
                                        if parsed_url.scheme not in ['http', 'https']:
                                            logger.warning(f"[cloudflare_imgbed_random] URL协议无效: {media_url}")
                                            continue
                                    except Exception as e:
                                        logger.warning(f"[cloudflare_imgbed_random] URL解析失败: {str(e)}")
                                        continue
                                    
                                    logger.info(f"[cloudflare_imgbed_random] 成功获取媒体URL: {media_url}")
                                    return media_url
                            else:
                                logger.warning(f"[cloudflare_imgbed_random] 获取随机媒体失败，状态码: {response.status}")
                                try:
                                    error_text = await response.text()
                                    logger.warning(f"[cloudflare_imgbed_random] 错误响应: {error_text[:200]}")
                                except:
                                    pass
                except asyncio.TimeoutError:
                    logger.warning(f"[cloudflare_imgbed_random] 获取随机媒体超时 (第{i+1}/{retry_count}次)")
                except Exception as e:
                    logger.error(f"[cloudflare_imgbed_random] 获取随机媒体失败: {str(e)}")
                
                if i < retry_count - 1:
                    logger.debug(f"[cloudflare_imgbed_random] 等待1秒后重试...")
                    await asyncio.sleep(1)
            
            logger.error(f"[cloudflare_imgbed_random] 所有{retry_count}次重试失败，无法获取随机媒体")
            return None
        except Exception as e:
            logger.error(f"[cloudflare_imgbed_random] _get_random_media方法执行失败: {str(e)}")
            return None
    
    def _extract_directory(self, message):
        '''从消息中提取目录参数和内容类型
        
        Args:
            message: 消息文本
            
        Returns:
            tuple: (目录路径, 内容类型) 如果没有目录则目录路径为None，如果没有匹配命令则返回(None, None)
        ''' 
        if not message or not isinstance(message, str):
            logger.debug(f"[cloudflare_imgbed_random] _extract_directory: 消息为空或不是字符串")
            return None, None
        
        original_message = message
        message = message.strip()
        logger.debug(f"[cloudflare_imgbed_random] _extract_directory: 原始消息长度={len(original_message)}, 清理后长度={len(message)}, 内容={repr(message)}")
        
        # 检查是否是视频命令
        if message.startswith('/随机视频'):
            dir_part = message[5:].strip() if len(message) > 5 else None
            logger.debug(f"[cloudflare_imgbed_random] 匹配到 /随机视频, 目录部分: {repr(dir_part)}")
            return dir_part, 'video'
        elif message.startswith('随机视频'):
            dir_part = message[4:].strip() if len(message) > 4 else None
            logger.debug(f"[cloudflare_imgbed_random] 匹配到 随机视频, 目录部分: {repr(dir_part)}")
            return dir_part, 'video'
        elif message.startswith('/随机图'):
            dir_part = message[4:].strip() if len(message) > 4 else None
            logger.debug(f"[cloudflare_imgbed_random] 匹配到 /随机图, 目录部分: {repr(dir_part)}")
            return dir_part, 'image'
        elif message.startswith('随机图'):
            dir_part = message[3:].strip() if len(message) > 3 else None
            logger.debug(f"[cloudflare_imgbed_random] 匹配到 随机图, 目录部分: {repr(dir_part)}")
            return dir_part, 'image'
        
        logger.debug(f"[cloudflare_imgbed_random] _extract_directory: 未匹配到任何命令")
        return None, None
    
    @filter.command("/随机图")
    async def random_image(self, event):
        '''发送随机图片'''
        logger.info("[cloudflare_imgbed_random] 命令处理器被触发: /随机图")
        try:
            # 直接调用处理方法，指定内容类型为图片
            async for result in self._handle_media(event, 'image'):
                yield result
        except Exception as e:
            logger.error(f"[cloudflare_imgbed_random] 处理/随机图命令失败: {str(e)}")
            yield event.plain_result(f"处理命令失败: {str(e)}")
    
    @filter.command("/随机视频")
    async def random_video(self, event):
        '''发送随机视频'''
        logger.info("[cloudflare_imgbed_random] 命令处理器被触发: /随机视频")
        try:
            # 直接调用处理方法，指定内容类型为视频
            async for result in self._handle_media(event, 'video'):
                yield result
        except Exception as e:
            logger.error(f"[cloudflare_imgbed_random] 处理/随机视频命令失败: {str(e)}")
            yield event.plain_result(f"处理命令失败: {str(e)}")
    
    async def _handle_media(self, event, content_type=None):
        '''处理媒体请求的统一方法'''
        try:
            logger.info(f"[cloudflare_imgbed_random] 开始处理媒体请求，content_type: {content_type}")
            
            # 提取目录参数
            directory = None
            message = self._get_message_text(event)
            logger.info(f"[cloudflare_imgbed_random] 获取到消息: {message}")
            
            if message:
                if message.startswith('/随机图') and len(message) > 4:
                    directory = message[4:].strip()
                    logger.debug(f"[cloudflare_imgbed_random] 从/随机图命令中提取目录: {directory}")
                elif message.startswith('/随机视频') and len(message) > 5:
                    directory = message[5:].strip()
                    logger.debug(f"[cloudflare_imgbed_random] 从/随机视频命令中提取目录: {directory}")
            
            if directory:
                logger.info(f"[cloudflare_imgbed_random] 指定目录: {directory}, 内容类型: {content_type}")
            
            # 获取随机媒体
            media_url = await self._get_random_media(directory, content_type)
            
            if not media_url:
                logger.warning("[cloudflare_imgbed_random] 未获取到媒体URL")
                yield event.plain_result("获取随机媒体失败，请检查配置或稍后重试")
                return
            
            logger.info(f"[cloudflare_imgbed_random] 获取到媒体URL: {media_url}")
            
            # 发送媒体
            try:
                if media_url.endswith(('.jpg', '.jpeg', '.png', '.gif')):
                    logger.debug("[cloudflare_imgbed_random] 检测到图片类型")
                    yield event.chain_result([Plain("随机图片发送成功"), Image.fromURL(media_url)])
                elif media_url.endswith(('.mp4', '.avi', '.mov', '.wmv', '.flv', '.mkv')):
                    logger.debug("[cloudflare_imgbed_random] 检测到视频类型")
                    yield event.chain_result([Plain("随机视频发送成功"), Video.fromURL(media_url)])
                else:
                    logger.debug(f"[cloudflare_imgbed_random] 其他类型: {media_url}")
                    yield event.plain_result(f"随机媒体发送成功: {media_url}")
            except Exception as e:
                logger.error(f"[cloudflare_imgbed_random] 发送媒体失败: {str(e)}")
                yield event.plain_result(f"发送媒体时出错: {str(e)}")
                
        except Exception as e:
            logger.error(f"[cloudflare_imgbed_random] 命令处理失败: {str(e)}")
            yield event.plain_result(f"命令处理失败: {str(e)}")
    
    @filter.llm_tool(name="sendRandomMedia")
    async def send_random_media(self, event, directory=None, content_type=None):
        '''发送随机图片或视频

        当用户请求随机图片或视频时使用此工具，例如：
        - "随机图"
        - "随机图片"
        - "随机视频"
        - "给我一张随机图片"
        - "我想要一个随机视频"

        Args:
            directory: 目录路径（可选），指定从哪个目录获取随机图片
            content_type: 内容类型（可选），指定获取图片或视频，可选值：image, video
        '''
        try:
            # 检查LLM开关是否开启
            if not self.config:
                await self._load_config()
            
            enable_llm = self.config.get("enableLLM", True)
            if not enable_llm:
                logger.warning("[cloudflare_imgbed_random] LLM调用已被禁用")
                yield event.plain_result("LLM调用已被禁用，请使用命令方式调用")
                return
            
            # 处理参数
            extracted_directory = directory
            extracted_content_type = content_type
            
            # 从消息中提取参数
            message = self._get_message_text(event)
            logger.debug(f"[cloudflare_imgbed_random] 消息内容: {message}")
            
            if message and not message.startswith('/'):
                dir_part, type_part = self._extract_directory(message)
                if dir_part:
                    extracted_directory = dir_part
                    logger.info(f"[cloudflare_imgbed_random] 从消息中提取目录: {extracted_directory}")
                if type_part:
                    extracted_content_type = type_part
                    logger.info(f"[cloudflare_imgbed_random] 从消息中提取内容类型: {extracted_content_type}")
            
            # 默认内容为图片
            if not extracted_content_type:
                extracted_content_type = 'image'
                logger.debug("[cloudflare_imgbed_random] 未指定内容类型，默认为图片")
            
            logger.info(f"[cloudflare_imgbed_random] LLM工具调用参数: 目录={extracted_directory}, 内容类型={extracted_content_type}")
            
            # 获取随机媒体URL
            media_url = await self._get_random_media(extracted_directory, extracted_content_type)
            
            if not media_url:
                logger.warning("[cloudflare_imgbed_random] 未获取到媒体URL")
                yield event.plain_result("获取随机媒体失败，请检查配置或稍后重试")
                return
            
            # 验证URL格式
            try:
                parsed_url = urlparse(media_url)
                if not parsed_url.scheme or not parsed_url.netloc:
                    logger.warning(f"[cloudflare_imgbed_random] URL格式无效: {media_url}")
                    yield event.plain_result("获取到的媒体URL格式无效")
                    return
                if parsed_url.scheme not in ['http', 'https']:
                    logger.warning(f"[cloudflare_imgbed_random] URL协议无效: {media_url}")
                    yield event.plain_result("获取到的媒体URL协议无效")
                    return
            except Exception as e:
                logger.error(f"[cloudflare_imgbed_random] URL解析失败: {str(e)}")
                yield event.plain_result("获取到的媒体URL解析失败")
                return
            
            # 发送媒体消息
            try:
                if media_url.endswith(('.jpg', '.jpeg', '.png', '.gif')):
                    logger.debug("[cloudflare_imgbed_random] 检测到图片类型")
                    yield event.chain_result([Plain("随机图片发送成功"), Image.fromURL(media_url)])
                elif media_url.endswith(('.mp4', '.avi', '.mov', '.wmv', '.flv', '.mkv')):
                    logger.debug("[cloudflare_imgbed_random] 检测到视频类型")
                    yield event.chain_result([Plain("随机视频发送成功"), Video.fromURL(media_url)])
                else:
                    logger.debug(f"[cloudflare_imgbed_random] 其他类型: {media_url}")
                    yield event.plain_result(f"随机媒体发送成功: {media_url}")
            except Exception as e:
                logger.error(f"[cloudflare_imgbed_random] 发送媒体失败: {str(e)}")
                yield event.plain_result(f"发送媒体时出错: {str(e)}")
                
        except Exception as e:
            logger.error(f"[cloudflare_imgbed_random] LLM工具调用失败: {str(e)}")
            yield event.plain_result(f"获取随机媒体时出错：{str(e)}")
    
    async def terminate(self):
        '''插件卸载时调用''' 
        logger.info("[cloudflare_imgbed_random] 插件已卸载")

# 导出插件
__plugin__ = CloudflareImgbedRandomPlugin