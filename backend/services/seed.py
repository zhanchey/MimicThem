"""
豆包 Seed 大模型 API 封装类
火山引擎方舟平台 doubao-seed 系列模型

支持功能:
- 文本生成 (generate)
- 多模态理解 (understand) - 支持图片输入
"""

import base64
import os
from pathlib import Path
from typing import Optional, Union, List
from dataclasses import dataclass
from openai import OpenAI


@dataclass
class SeedResponse:
    """Seed API 响应结果"""
    success: bool
    content: str  # 模型输出的文本内容
    thinking: Optional[str] = None  # 深度思考内容(如果启用)
    error_message: Optional[str] = None
    raw_response: Optional[dict] = None
    usage: Optional[dict] = None  # token 使用情况


class Seed:
    """
    火山引擎豆包 Seed 大模型封装类
    
    使用方式:
        # 初始化
        seed = Seed(api_key="your_api_key")
        
        # 文本生成
        response = seed.generate(
            prompt="你好，请介绍一下你自己"
        )
        
        # 多模态理解 - 图片理解
        response = seed.understand(
            prompt="描述这张图片的内容",
            image_path="path/to/image.jpg"
        )
    """
    
    # 可用模型列表
    MODELS = {
        "seed-1.6": "doubao-seed-1-6-251015",
        "seed-2.0": "doubao-seed-2-0-pro-260215"
    }
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://ark.cn-beijing.volces.com/api/v3",
        model: str = "seed-2.0",
        timeout: int = 120
    ):
        """
        初始化 Seed 客户端
        
        Args:
            api_key: 火山引擎 API Key, 如果不提供则从环境变量 ARK_API_KEY 读取
            base_url: API 基础地址
            model: 使用的模型版本
            timeout: 请求超时时间(秒)
        """
        self.api_key = api_key or os.getenv("ARK_API_KEY")
        if not self.api_key:
            raise ValueError("API Key 未提供, 请通过参数传入或设置环境变量 ARK_API_KEY")
        
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        
        # 设置模型
        if model in self.MODELS:
            self.model = self.MODELS[model]
        else:
            self.model = model  # 直接使用完整模型名
        
        self._client = None
    
    def _get_client(self):
        """获取或创建 OpenAI 客户端"""
        if self._client is None:
            self._client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout
            )
        return self._client
    
    def _encode_image(self, image_path: Union[str, Path]) -> str:
        """将图片文件编码为 base64 字符串"""
        image_path = Path(image_path)
        if not image_path.exists():
            raise FileNotFoundError(f"图片文件不存在: {image_path}")
        
        with open(image_path, "rb") as f:
            image_data = f.read()
        
        return base64.b64encode(image_data).decode("utf-8")
    
    def _get_mime_type(self, image_path: Union[str, Path]) -> str:
        """根据文件扩展名获取 MIME 类型"""
        suffix = Path(image_path).suffix.lower()
        mime_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".bmp": "image/bmp",
        }
        return mime_types.get(suffix, "image/jpeg")
    
    def _parse_response(self, response) -> SeedResponse:
        """解析 API 响应"""
        try:
            content = ""
            thinking = None
            
            # 解析输出内容
            if hasattr(response, "output"):
                for item in response.output:
                    item_type = getattr(item, "type", None)
                    
                    # 解析推理/思考过程 (type: "reasoning")
                    if item_type == "reasoning":
                        if hasattr(item, "summary") and item.summary:
                            thinking_parts = []
                            for summary_item in item.summary:
                                if hasattr(summary_item, "text") and summary_item.text:
                                    thinking_parts.append(summary_item.text)
                            if thinking_parts:
                                thinking = "\n".join(thinking_parts)
                    
                    # 解析消息内容 (type: "message")
                    elif item_type == "message":
                        if hasattr(item, "content") and item.content:
                            content_parts = []
                            for content_item in item.content:
                                if hasattr(content_item, "text") and content_item.text:
                                    content_parts.append(content_item.text)
                            if content_parts:
                                content = "\n".join(content_parts)
                    
                    # 兼容旧格式
                    elif item_type == "thinking" and hasattr(item, "thinking"):
                        thinking = item.thinking
                    elif item_type == "text" and hasattr(item, "text"):
                        content = item.text
            
            # 解析 usage
            usage = None
            if hasattr(response, "usage"):
                usage = {
                    "input_tokens": getattr(response.usage, "input_tokens", 0),
                    "output_tokens": getattr(response.usage, "output_tokens", 0),
                    "total_tokens": getattr(response.usage, "total_tokens", 0),
                }
            
            return SeedResponse(
                success=True,
                content=content,
                thinking=thinking,
                usage=usage,
                raw_response=response.model_dump() if hasattr(response, "model_dump") else None
            )
            
        except Exception as e:
            return SeedResponse(
                success=False,
                content="",
                error_message=f"解析响应失败: {str(e)}"
            )
    
    def generate(
        self,
        prompt: str,
        enable_thinking: bool = True,
        **kwargs
    ) -> SeedResponse:
        """
        文本生成
        
        Args:
            prompt: 用户输入的提示词
            enable_thinking: 是否启用深度思考, 默认启用
            **kwargs: 其他 API 参数
            
        Returns:
            SeedResponse: 包含生成文本的响应对象
        """
        client = self._get_client()
        
        try:
            request_params = {
                "model": self.model,
                "input": prompt,
                **kwargs
            }
            
            if not enable_thinking:
                request_params["extra_body"] = {
                    "thinking": {"type": "disabled"}
                }
            
            response = client.responses.create(**request_params)
            return self._parse_response(response)
            
        except Exception as e:
            return SeedResponse(
                success=False,
                content="",
                error_message=str(e)
            )
    
    def understand(
        self,
        prompt: str,
        image_path: Optional[Union[str, Path]] = None,
        image_url: Optional[str] = None,
        image_base64: Optional[str] = None,
        enable_thinking: bool = True,
        **kwargs
    ) -> SeedResponse:
        """
        多模态理解 - 支持图片输入
        
        Args:
            prompt: 用户输入的提示词/问题
            image_path: 本地图片文件路径
            image_url: 网络图片 URL
            image_base64: 图片的 base64 编码
            enable_thinking: 是否启用深度思考, 默认启用
            **kwargs: 其他 API 参数
            
        Returns:
            SeedResponse: 包含理解结果的响应对象
        """
        client = self._get_client()
        
        # 构建内容列表
        content_list = []
        
        # 添加图片
        if image_path:
            base64_data = self._encode_image(image_path)
            mime_type = self._get_mime_type(image_path)
            content_list.append({
                "type": "input_image",
                "image_url": f"data:{mime_type};base64,{base64_data}"
            })
        elif image_url:
            content_list.append({
                "type": "input_image",
                "image_url": image_url
            })
        elif image_base64:
            content_list.append({
                "type": "input_image",
                "image_url": f"data:image/jpeg;base64,{image_base64}"
            })
        
        # 添加文本
        content_list.append({
            "type": "input_text",
            "text": prompt
        })
        
        try:
            request_params = {
                "model": self.model,
                "input": [
                    {
                        "role": "user",
                        "content": content_list
                    }
                ],
                **kwargs
            }
            
            if not enable_thinking:
                request_params["extra_body"] = {
                    "thinking": {"type": "disabled"}
                }
            
            response = client.responses.create(**request_params)
            return self._parse_response(response)
            
        except Exception as e:
            return SeedResponse(
                success=False,
                content="",
                error_message=str(e)
            )
    
    def chat(
        self,
        messages: List[dict],
        enable_thinking: bool = True,
        **kwargs
    ) -> SeedResponse:
        """
        多轮对话
        
        Args:
            messages: 消息列表, 格式为 [{"role": "user", "content": "..."}]
            enable_thinking: 是否启用深度思考, 默认启用
            **kwargs: 其他 API 参数
            
        Returns:
            SeedResponse: 包含回复的响应对象
        """
        client = self._get_client()
        
        try:
            request_params = {
                "model": self.model,
                "input": messages,
                **kwargs
            }
            
            if not enable_thinking:
                request_params["extra_body"] = {
                    "thinking": {"type": "disabled"}
                }
            
            response = client.responses.create(**request_params)
            return self._parse_response(response)
            
        except Exception as e:
            return SeedResponse(
                success=False,
                content="",
                error_message=str(e)
            )
