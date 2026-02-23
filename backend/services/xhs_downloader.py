"""
精简版小红书图文下载器
从原 xhs_downloader 项目提取核心功能

功能：
- URL解析（短链接转长链接）
- HTML数据获取和解析
- 图片链接提取
- 并行图片下载
"""

import asyncio
import re
import json
import logging
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlparse

import httpx
from lxml import etree

logger = logging.getLogger(__name__)


@dataclass
class DownloadResult:
    """下载结果"""
    success: bool
    note_id: str = ""
    title: str = ""
    description: str = ""
    author: str = ""
    author_id: str = ""
    images: list[Path] = field(default_factory=list)
    image_urls: list[str] = field(default_factory=list)
    error_message: str = ""


class XHSDownloader:
    """小红书图文下载器"""
    
    # URL 正则模式
    LINK_PATTERN = re.compile(r"(?:https?://)?www\.xiaohongshu\.com/explore/\S+")
    SHARE_PATTERN = re.compile(r"(?:https?://)?www\.xiaohongshu\.com/discovery/item/\S+")
    SHORT_PATTERN = re.compile(r"(?:https?://)?xhslink\.com/[^\s\"<>\\^`{|}，。；！？、【】《》]+")
    
    # 默认 User-Agent
    DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    
    def __init__(
        self,
        user_agent: str = None,
        cookie: str = "",
        proxy: str = None,
        timeout: int = 30,
    ):
        self.user_agent = user_agent or self.DEFAULT_UA
        self.cookie = cookie
        self.proxy = proxy
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
    
    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            headers=self._get_headers(),
            proxy=self.proxy,
            timeout=self.timeout,
            follow_redirects=True,
            verify=False,
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client:
            await self._client.aclose()
    
    def _get_headers(self) -> dict:
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        if self.cookie:
            headers["Cookie"] = self.cookie
        return headers
    
    async def download_from_url(self, url: str, save_dir: Path) -> DownloadResult:
        """
        从小红书链接下载图片
        
        Args:
            url: 小红书链接（支持短链接和长链接）
            save_dir: 保存目录
            
        Returns:
            DownloadResult: 下载结果
        """
        try:
            # 1. 解析链接
            real_url = await self._resolve_url(url)
            if not real_url:
                return DownloadResult(success=False, error_message="无法解析链接")
            
            # 2. 获取笔记数据
            note_data = await self._get_note_data(real_url)
            if not note_data:
                return DownloadResult(success=False, error_message="无法获取笔记数据")
            
            # 3. 提取信息
            note_id = note_data.get("noteId", "")
            title = note_data.get("title", "")
            description = note_data.get("desc", "")
            author = note_data.get("user", {}).get("nickname", "")
            author_id = note_data.get("user", {}).get("userId", "")
            
            # 4. 提取图片链接
            image_urls = self._extract_image_urls(note_data)
            if not image_urls:
                return DownloadResult(
                    success=False,
                    note_id=note_id,
                    title=title,
                    description=description,
                    author=author,
                    author_id=author_id,
                    error_message="未找到图片"
                )
            
            # 5. 创建保存目录
            save_dir.mkdir(parents=True, exist_ok=True)
            
            # 6. 并行下载图片
            images = await self._download_images_parallel(image_urls, save_dir)
            
            return DownloadResult(
                success=True,
                note_id=note_id,
                title=title,
                description=description,
                author=author,
                author_id=author_id,
                images=images,
                image_urls=image_urls,
            )
            
        except Exception as e:
            return DownloadResult(success=False, error_message=str(e))
    
    async def _resolve_url(self, url: str) -> Optional[str]:
        """解析URL，将短链接转换为完整链接"""
        url = url.strip()
        
        # 检查是否是短链接
        if match := self.SHORT_PATTERN.search(url):
            short_url = match.group()
            if not short_url.startswith("http"):
                short_url = f"https://{short_url}"
            
            try:
                response = await self._client.get(short_url)
                url = str(response.url)
            except Exception:
                return None
        
        # 检查是否是有效的小红书链接
        if self.SHARE_PATTERN.search(url) or self.LINK_PATTERN.search(url):
            if not url.startswith("http"):
                url = f"https://{url}"
            return url
        
        return None
    
    async def _get_note_data(self, url: str) -> Optional[dict]:
        """获取笔记数据"""
        try:
            response = await self._client.get(url)
            response.raise_for_status()
            html = response.text
            
            # 调试：打印 HTML 长度
            logger.info(f"获取到 HTML 长度: {len(html)}")
            
            # 从 HTML 中提取 JSON 数据
            result = self._parse_html_data(html)
            if not result:
                # 保存 HTML 用于调试
                debug_path = Path(__file__).parent.parent / "debug_html.txt"
                with open(debug_path, "w", encoding="utf-8") as f:
                    f.write(html)
                logger.info(f"HTML 已保存到 {debug_path} 用于调试")
            return result
        except Exception as e:
            logger.error(f"获取笔记数据异常: {e}")
            return None
    
    def _parse_html_data(self, html: str) -> Optional[dict]:
        """从 HTML 中解析笔记数据"""
        try:
            tree = etree.HTML(html)
            # 查找包含数据的 script 标签
            scripts = tree.xpath('//script[contains(text(), "__INITIAL_STATE__")]')
            logger.info(f"找到 {len(scripts)} 个包含 __INITIAL_STATE__ 的 script 标签")
            
            if not scripts:
                # 尝试其他方式查找
                all_scripts = tree.xpath('//script')
                logger.info(f"页面共有 {len(all_scripts)} 个 script 标签")
                for i, s in enumerate(all_scripts):
                    text = s.text or ""
                    if "INITIAL" in text or "initialState" in text:
                        logger.info(f"Script {i} 包含可能的状态数据")
            
            for script in scripts:
                text = script.text or ""
                # 提取 JSON 数据 - 使用更宽松的正则
                match = re.search(r'__INITIAL_STATE__\s*=\s*({.+})', text, re.DOTALL)
                if match:
                    json_str = match.group(1)
                    # 处理 undefined
                    json_str = json_str.replace('undefined', 'null')
                    
                    try:
                        data = json.loads(json_str)
                        logger.info(f"成功解析 JSON，顶层 keys: {list(data.keys())}")
                        
                        # 提取笔记数据
                        note = data.get("note", {}).get("noteDetailMap", {})
                        if note:
                            first_key = list(note.keys())[0] if note else None
                            if first_key:
                                return note[first_key].get("note", {})
                        else:
                            logger.info(f"note.noteDetailMap 为空，尝试其他路径")
                            # 尝试其他可能的路径
                            if "note" in data:
                                logger.info(f"note 结构: {list(data['note'].keys()) if isinstance(data['note'], dict) else type(data['note'])}")
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON 解析失败: {e}")
                        # 尝试截取更短的部分
                        continue
            
            return None
        except Exception as e:
            logger.error(f"解析 HTML 异常: {e}")
            return None
    
    def _extract_image_urls(self, note_data: dict, format_: str = "jpeg") -> list[str]:
        """提取图片下载链接"""
        images = note_data.get("imageList", [])
        urls = []
        
        for img in images:
            # 优先使用 urlDefault
            url = img.get("urlDefault", "") or img.get("url", "")
            if url:
                # 提取图片 token
                token = self._extract_image_token(url)
                if token:
                    # 构建下载链接
                    download_url = f"https://ci.xiaohongshu.com/{token}?imageView2/format/{format_}"
                    # 处理转义字符
                    download_url = bytes(download_url, "utf-8").decode("unicode_escape")
                    urls.append(download_url)
        
        return urls
    
    @staticmethod
    def _extract_image_token(url: str) -> str:
        """从图片 URL 中提取 token"""
        try:
            parts = url.split("/")
            if len(parts) >= 6:
                token = "/".join(parts[5:]).split("!")[0]
                return token
        except Exception:
            pass
        return ""
    
    async def _download_images_parallel(
        self,
        urls: list[str],
        save_dir: Path,
        max_concurrent: int = 5
    ) -> list[Path]:
        """并行下载图片"""
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def download_one(url: str, index: int) -> Optional[Path]:
            async with semaphore:
                return await self._download_single_image(url, save_dir, index)
        
        tasks = [download_one(url, i + 1) for i, url in enumerate(urls)]
        results = await asyncio.gather(*tasks)
        
        return [r for r in results if r is not None]
    
    async def _download_single_image(
        self,
        url: str,
        save_dir: Path,
        index: int
    ) -> Optional[Path]:
        """下载单张图片"""
        try:
            response = await self._client.get(url)
            response.raise_for_status()
            
            # 确定文件扩展名
            content_type = response.headers.get("content-type", "")
            ext = self._get_extension_from_content_type(content_type)
            
            # 保存文件
            filename = f"{index}.{ext}"
            filepath = save_dir / filename
            
            with open(filepath, "wb") as f:
                f.write(response.content)
            
            return filepath
        except Exception:
            return None
    
    @staticmethod
    def _get_extension_from_content_type(content_type: str) -> str:
        """从 Content-Type 获取文件扩展名"""
        mapping = {
            "image/jpeg": "jpeg",
            "image/png": "png",
            "image/webp": "webp",
            "image/gif": "gif",
        }
        return mapping.get(content_type.split(";")[0].strip(), "jpeg")
