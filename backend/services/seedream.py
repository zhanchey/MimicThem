"""
豆包 Seedream 图片大模型 API 封装类
火山引擎方舟平台 doubao-seedream 系列模型

支持功能:
- 文生图 (text_to_image)
- 图文生图 (image_to_image)
"""

import base64
import os
from pathlib import Path
from typing import Optional, Union, List, Literal
from dataclasses import dataclass
from openai import OpenAI


@dataclass
class SeedreamImage:
    """单张图片信息"""
    url: Optional[str] = None  # 图片URL
    b64_json: Optional[str] = None  # Base64编码的图片数据
    size: Optional[str] = None  # 图片尺寸


@dataclass
class SeedreamResponse:
    """Seedream API 响应结果"""
    success: bool
    images: List[SeedreamImage]  # 生成的图片列表
    error_message: Optional[str] = None
    raw_response: Optional[dict] = None


class Seedream:
    """
    火山引擎豆包 Seedream 图片大模型封装类
    
    使用方式:
        # 初始化
        seedream = Seedream(api_key="your_api_key")
        
        # 文生图
        response = seedream.text_to_image(
            prompt="一只可爱的猫咪在阳光下睡觉"
        )
        
        # 图文生图
        response = seedream.image_to_image(
            prompt="将背景改为海滩",
            image="path/to/image.jpg"
        )
    """
    
    # 可用模型列表
    MODELS = {
        "seedream-4.5": "doubao-seedream-4-5-251128",
        "seedream-4.0": "doubao-seedream-4-0-250828",
    }
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://ark.cn-beijing.volces.com/api/v3",
        model: str = "seedream-4.5",
        timeout: int = 120
    ):
        """
        初始化 Seedream 客户端
        
        Args:
            api_key: 火山引擎 API Key, 如果不提供则从环境变量 ARK_API_KEY 读取
            base_url: API 基础地址
            model: 使用的模型版本, 可选 "seedream-4.5" 或 "seedream-4.0"
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
    
    def _get_client(self) -> OpenAI:
        """获取或创建 OpenAI 客户端"""
        if self._client is None:
            self._client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout
            )
        return self._client
    
    def _encode_image(self, image_path: Union[str, Path]) -> str:
        """将图片文件编码为 base64 字符串并构建 data URL"""
        image_path = Path(image_path)
        if not image_path.exists():
            raise FileNotFoundError(f"图片文件不存在: {image_path}")
        
        with open(image_path, "rb") as f:
            image_data = f.read()
        
        base64_data = base64.b64encode(image_data).decode("utf-8")
        mime_type = self._get_mime_type(image_path)
        return f"data:{mime_type};base64,{base64_data}"
    
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
    
    def _process_image_input(self, image: Union[str, Path]) -> str:
        """
        处理图片输入，支持本地文件路径或URL
        
        Args:
            image: 图片路径或URL
            
        Returns:
            处理后的图片URL或data URL
        """
        if isinstance(image, str) and (image.startswith("http://") or image.startswith("https://")):
            return image
        else:
            return self._encode_image(image)
    
    def _parse_response(self, response) -> SeedreamResponse:
        """解析 API 响应"""
        try:
            images = []
            
            if hasattr(response, "data") and response.data:
                for item in response.data:
                    image = SeedreamImage(
                        url=getattr(item, "url", None),
                        b64_json=getattr(item, "b64_json", None),
                        size=getattr(item, "size", None)
                    )
                    images.append(image)
            
            return SeedreamResponse(
                success=True,
                images=images,
                raw_response=response.model_dump() if hasattr(response, "model_dump") else None
            )
            
        except Exception as e:
            return SeedreamResponse(
                success=False,
                images=[],
                error_message=f"解析响应失败: {str(e)}"
            )
    
    def text_to_image(
        self,
        prompt: str,
        size: str = "2K",
        response_format: Literal["url", "b64_json"] = "b64_json",
        watermark: bool = False,
        optimize_prompt_mode: Optional[Literal["auto", "fast", "disabled"]] = None,
        **kwargs
    ) -> SeedreamResponse:
        """
        文生图 - 根据文本提示生成图片
        
        Args:
            prompt: 图片生成的文本提示
            size: 输出图片尺寸, 可选 "1K", "2K", "4K" 或具体尺寸如 "3072x4096", 默认 "2K"
            response_format: 返回格式, "url" 返回链接, "b64_json" 返回 Base64 编码
            watermark: 是否添加水印, 默认 False
            optimize_prompt_mode: 提示词优化模式, 可选 "auto", "fast", "disabled"
            **kwargs: 其他 API 参数
            
        Returns:
            SeedreamResponse: 包含生成图片的响应对象
        """
        client = self._get_client()
        
        try:
            extra_body = {
                "watermark": watermark,
            }
            
            if optimize_prompt_mode:
                extra_body["optimize_prompt_options"] = {"mode": optimize_prompt_mode}
            
            response = client.images.generate(
                model=self.model,
                prompt=prompt,
                size=size,
                response_format=response_format,
                extra_body=extra_body,
                **kwargs
            )
            
            return self._parse_response(response)
            
        except Exception as e:
            return SeedreamResponse(
                success=False,
                images=[],
                error_message=str(e)
            )
    
    def image_to_image(
        self,
        prompt: str,
        image: Union[str, Path],
        size: str = "2K",
        response_format: Literal["url", "b64_json"] = "b64_json",
        watermark: bool = False,
        optimize_prompt_mode: Optional[Literal["auto", "fast", "disabled"]] = None,
        **kwargs
    ) -> SeedreamResponse:
        """
        图文生图 - 基于参考图片和文本提示生成新图片
        
        Args:
            prompt: 图片生成的文本提示
            image: 参考图片, 可以是本地文件路径或URL
            size: 输出图片尺寸, 可选 "1K", "2K", "4K" 或具体尺寸如 "3072x4096", 默认 "2K"
            response_format: 返回格式, "url" 返回链接, "b64_json" 返回 Base64 编码
            watermark: 是否添加水印, 默认 False
            optimize_prompt_mode: 提示词优化模式, 可选 "auto", "fast", "disabled"
            **kwargs: 其他 API 参数
            
        Returns:
            SeedreamResponse: 包含生成图片的响应对象
        """
        client = self._get_client()
        
        try:
            processed_image = self._process_image_input(image)
            
            extra_body = {
                "image": processed_image,
                "watermark": watermark,
            }
            
            if optimize_prompt_mode:
                extra_body["optimize_prompt_options"] = {"mode": optimize_prompt_mode}
            
            response = client.images.generate(
                model=self.model,
                prompt=prompt,
                size=size,
                response_format=response_format,
                extra_body=extra_body,
                **kwargs
            )
            
            return self._parse_response(response)
            
        except Exception as e:
            return SeedreamResponse(
                success=False,
                images=[],
                error_message=str(e)
            )
