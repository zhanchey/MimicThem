"""
FastAPI 路由和 SSE 实时状态更新
实现 MimicThem 完整工作流
"""

import asyncio
import base64
import json
import configparser
import logging
from pathlib import Path
from datetime import datetime
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel

from services.xhs_downloader import XHSDownloader, DownloadResult
from services.seed import Seed
from services.seedream import Seedream

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

# 获取配置
def get_config():
    """读取配置文件"""
    config = configparser.ConfigParser()
    config_path = Path(__file__).parent.parent / "config.ini"
    
    if not config_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")
    
    config.read(config_path, encoding="utf-8")
    return config


def sse_event(event_type: str, data: dict) -> str:
    """生成 SSE 事件格式"""
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


class MimicRequest(BaseModel):
    """复刻请求"""
    url: str


@router.post("/mimic")
async def mimic_workflow(request: MimicRequest):
    """
    一键复刻工作流
    返回 SSE 流，实时推送各阶段状态和结果
    """
    async def event_generator() -> AsyncGenerator[str, None]:
        config = get_config()
        api_key = config.get("api", "ARK_API_KEY")
        variant_count = config.getint("generation", "variant_count", fallback=5)
        image_size = config.get("generation", "image_size", fallback="3072x4096")
        model_id = config.get("generation", "model_id", fallback="seedream-4.5")
        watermark = config.getboolean("generation", "watermark", fallback=False)
        
        # 创建数据目录
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        data_dir = Path(__file__).parent.parent / "data"
        
        try:
            # ========== 1. 解析 URL ==========
            logger.info(f"开始处理请求: {request.url}")
            yield sse_event("status", {"step": "parsing", "message": "正在解析URL..."})
            
            async with XHSDownloader() as downloader:
                # 解析 URL 获取真实链接
                logger.info("正在解析 URL...")
                real_url = await downloader._resolve_url(request.url)
                logger.info(f"解析结果: {real_url}")
                if not real_url:
                    logger.error("无法解析小红书链接")
                    yield sse_event("error", {"message": "无法解析小红书链接"})
                    return
                
                # 获取笔记数据
                logger.info(f"正在获取笔记数据: {real_url}")
                note_data = await downloader._get_note_data(real_url)
                logger.info(f"笔记数据: {bool(note_data)}")
                if not note_data:
                    logger.error("无法获取笔记数据")
                    yield sse_event("error", {"message": "无法获取笔记数据"})
                    return
                
                note_id = note_data.get("noteId", timestamp)
                title = note_data.get("title", "")
                description = note_data.get("desc", "")
                author = note_data.get("user", {}).get("nickname", "")
                
                # 创建保存目录
                save_dir = data_dir / note_id
                original_dir = save_dir / "original"
                generated_dir = save_dir / "generated"
                original_dir.mkdir(parents=True, exist_ok=True)
                generated_dir.mkdir(parents=True, exist_ok=True)
                
                yield sse_event("info", {
                    "note_id": note_id,
                    "title": title,
                    "author": author
                })
                
                # ========== 2. 下载图片（并行，即时返回）==========
                logger.info("开始下载原始图片...")
                yield sse_event("status", {"step": "downloading", "message": "正在下载原始图片..."})
                
                image_urls = downloader._extract_image_urls(note_data)
                logger.info(f"找到 {len(image_urls)} 张图片")
                if not image_urls:
                    logger.error("未找到图片")
                    yield sse_event("error", {"message": "未找到图片"})
                    return
                
                # 并行下载，每张下载完成后立即发送 SSE 事件
                downloaded_images = []
                async def download_and_notify(url: str, index: int):
                    """下载单张图片并立即通知"""
                    img_path = await downloader._download_single_image(url, original_dir, index)
                    if img_path:
                        logger.info(f"图片 {index} 下载完成: {img_path.name}")
                        return {
                            "path": img_path,
                            "url": f"/api/images/{note_id}/original/{img_path.name}",
                            "index": index
                        }
                    return None
                
                # 创建下载任务
                tasks = [download_and_notify(url, i + 1) for i, url in enumerate(image_urls)]
                
                # 使用 as_completed 实现即时返回
                for coro in asyncio.as_completed(tasks):
                    result = await coro
                    if result:
                        downloaded_images.append(result["path"])
                        # 立即发送这张图片
                        yield sse_event("original_image", {
                            "url": result["url"],
                            "index": result["index"],
                            "caption": description if result["index"] == 1 else None,
                            "title": title if result["index"] == 1 else None
                        })
                
                logger.info(f"成功下载 {len(downloaded_images)} 张图片")
                
                if not downloaded_images:
                    logger.error("图片下载失败")
                    yield sse_event("error", {"message": "图片下载失败"})
                    return
                
                # 选择第一张图片作为参考
                reference_image = downloaded_images[0]
                
            # ========== 3. 反推提示词 ==========
            logger.info("开始反推提示词...")
            yield sse_event("status", {"step": "understanding", "message": "正在分析图片，生成提示词..."})
            
            seed = Seed(api_key=api_key)
            
            understand_prompt = """如果我想用图片生成模型seedream生成这张图片，提示词应该是怎样的？
我只需要正向提示词，不需要反向提示词，另外请直接输出提示词文本，不要任何多余的其他内容！
对于人物和环境的描绘一定要细致，尽你所能务必准确描写人物的身材、五官、表情、气质和给人的感受等特点。
我需要通过你输出的提示词文本来还原这张图片！。"""
            
            logger.info("调用 Seed API 分析图片...")
            understand_response = seed.understand(
                prompt=understand_prompt,
                image_path=reference_image,
                enable_thinking=False
            )
            
            if not understand_response.success:
                logger.error(f"图片分析失败: {understand_response.error_message}")
                yield sse_event("error", {"message": f"图片分析失败: {understand_response.error_message}"})
                return
            
            base_prompt = understand_response.content
            logger.info(f"反推提示词完成，长度: {len(base_prompt)}")
            yield sse_event("prompt", {"base_prompt": base_prompt})
            
            # ========== 4. 生成变体提示词 ==========
            logger.info("开始生成变体提示词...")
            yield sse_event("status", {"step": "variants", "message": "正在生成变体提示词..."})
            
            variant_prompt = f'''你是一位专业的AI绘图提示词专家。基于以下原始提示词，请生成{variant_count}段变体提示词，用于图生图模型。

原始提示词:
{base_prompt}

要求:
1. 这{variant_count + 1}张图片（原始1张 + 变体{variant_count}张）应该构成一个系列组图
2. 人物必须保持相同：相同的外貌特征、身材、气质
3. 场景保持相似或相关联的环境氛围
4. 每段提示词的人物姿势、动作必须不同，展现不同的姿态美感
5. 保持相同的画面风格、色调、光线质感
6. 每段提示词都要有足够的细节描述，能够独立使用，细节非常重要！
7. 姿势可以是站、坐、蹲、躺、走等各种，不必拘泥于一种姿态，动作也可以多样一点
8. 不必每张图片人物都看着镜头

请严格按照以下JSON格式输出，不要包含任何其他内容:
{{
    "prompts": [
        "提示词1...",
        "提示词2...",
        ...
    ]
}}'''
            
            logger.info("调用 Seed API 生成变体提示词...")
            variant_response = seed.generate(
                prompt=variant_prompt,
                enable_thinking=False
            )
            
            if not variant_response.success:
                logger.error(f"生成变体提示词失败: {variant_response.error_message}")
                yield sse_event("error", {"message": f"生成变体提示词失败: {variant_response.error_message}"})
                return
            
            # 解析 JSON
            try:
                content = variant_response.content.strip()
                if content.startswith("```json"):
                    content = content[7:]
                if content.startswith("```"):
                    content = content[3:]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()
                
                prompts_data = json.loads(content)
                variant_prompts = prompts_data.get("prompts", [])[:variant_count]
                logger.info(f"解析到 {len(variant_prompts)} 个变体提示词")
            except json.JSONDecodeError as e:
                logger.error(f"解析变体提示词JSON失败: {e}")
                yield sse_event("error", {"message": f"解析变体提示词失败: {str(e)}"})
                return
            
            yield sse_event("prompts", {"variants": variant_prompts})
            
            # ========== 5. 文生图 ==========
            logger.info("开始文生图...")
            yield sse_event("status", {"step": "text2img", "message": "正在生成基础图片..."})
            
            seedream = Seedream(api_key=api_key, model=model_id)
            
            # 使用 asyncio.to_thread 将同步调用转为异步
            def do_text2img():
                return seedream.text_to_image(
                    prompt=base_prompt,
                    size=image_size,
                    response_format="b64_json",
                    watermark=watermark
                )
            
            logger.info("调用 Seedream API 文生图...")
            text2img_response = await asyncio.to_thread(do_text2img)
            
            if not text2img_response.success or not text2img_response.images:
                logger.error(f"文生图失败: {text2img_response.error_message}")
                yield sse_event("error", {"message": f"文生图失败: {text2img_response.error_message}"})
                return
            
            # 保存基础图片
            base_image_path = generated_dir / "base.png"
            base_image_data = base64.b64decode(text2img_response.images[0].b64_json)
            with open(base_image_path, "wb") as f:
                f.write(base_image_data)
            
            logger.info(f"文生图完成: {base_image_path}")
            yield sse_event("image", {
                "type": "generated",
                "index": 0,
                "url": f"/api/images/{note_id}/generated/base.png",
                "label": "文生图"
            })
            
            # ========== 6. 图文生图（真正并行）==========
            logger.info(f"开始图生图，共 {len(variant_prompts)} 张变体（并行处理）...")
            yield sse_event("status", {"step": "img2img", "message": "正在并行生成变体图片..."})
            
            # 同步函数：生成单个变体（在线程池中执行）
            def generate_variant_sync(prompt: str, index: int) -> dict:
                """同步生成单个变体（将在独立线程中执行）"""
                try:
                    full_prompt = f"保持和参考图同一人物。{prompt}"
                    logger.info(f"[线程] 开始生成变体 {index}...")
                    
                    # 每个线程使用独立的 Seedream 实例
                    variant_seedream = Seedream(api_key=api_key, model=model_id)
                    response = variant_seedream.image_to_image(
                        prompt=full_prompt,
                        image=base_image_path,
                        size=image_size,
                        response_format="b64_json",
                        watermark=watermark
                    )
                    
                    if response.success and response.images:
                        variant_path = generated_dir / f"variant_{index}.png"
                        image_data = base64.b64decode(response.images[0].b64_json)
                        with open(variant_path, "wb") as f:
                            f.write(image_data)
                        logger.info(f"[线程] 变体 {index} 生成完成: {variant_path}")
                        return {
                            "index": index,
                            "url": f"/api/images/{note_id}/generated/variant_{index}.png",
                            "success": True
                        }
                    logger.error(f"[线程] 变体 {index} 生成失败: {response.error_message}")
                    return {"index": index, "success": False, "error": response.error_message}
                except Exception as e:
                    logger.error(f"[线程] 变体 {index} 异常: {e}")
                    return {"index": index, "success": False, "error": str(e)}
            
            # 创建异步任务列表（使用 to_thread 在线程池中并行执行）
            async def run_variant_task(prompt: str, index: int):
                return await asyncio.to_thread(generate_variant_sync, prompt, index)
            
            tasks = [run_variant_task(prompt, i + 1) for i, prompt in enumerate(variant_prompts)]
            
            # 使用 asyncio.as_completed 实现结果即时返回
            for coro in asyncio.as_completed(tasks):
                result = await coro
                if result and result.get("success"):
                    logger.info(f"变体 {result['index']} 已返回前端")
                    yield sse_event("image", {
                        "type": "variant",
                        "index": result["index"],
                        "url": result["url"],
                        "label": f"变体{result['index']}"
                    })
                else:
                    logger.warning(f"变体{result['index']}生成失败: {result.get('error', '未知错误')}")
                    yield sse_event("warning", {
                        "message": f"变体{result['index']}生成失败: {result.get('error', '未知错误')}"
                    })
            
            # ========== 7. 生成诗意文案 ==========
            logger.info("开始生成文案...")
            yield sse_event("status", {"step": "copywriting", "message": "正在生成文案..."})
            
            copywriting_prompt = f'''基于以下图片描述，创作一段有诗意且符合图片意境的文案，适合发布在小红书。

图片描述：
{base_prompt}

要求：
1. 文案要有诗意，营造氛围感
2. 不要具体描述人物外貌
3. 不要太长，1-2句话即可
4. 文案后面带上5-6个#开头的标签
5. 标签要贴合图片主题，常见的有：#少女感 #氛围感 #写真 #阳光 #清晨 #温柔 等

示例格式：
"在柔光里，慢慢松下来，少女、阳光、清晨真的是绝配"
#少女感 #阳光 #清晨 #氛围感 #写真 #温柔

请直接输出文案和标签，不要其他内容：'''
            
            logger.info("调用 Seed API 生成文案...")
            copywriting_response = seed.generate(
                prompt=copywriting_prompt,
                enable_thinking=False
            )
            
            if copywriting_response.success:
                generated_caption = copywriting_response.content.strip()
                logger.info("文案生成完成")
            else:
                generated_caption = "图片真好看~\n#写真 #氛围感 #美图"
                logger.warning(f"文案生成失败，使用默认文案: {copywriting_response.error_message}")
            
            yield sse_event("caption", {"text": generated_caption})
            
            # ========== 8. 保存文案到文件 ==========
            info_path = save_dir / "info.txt"
            with open(info_path, "w", encoding="utf-8") as f:
                f.write(f"原始标题: {title}\n")
                f.write(f"原始文案: {description}\n")
                f.write(f"作者: {author}\n")
                f.write(f"笔记ID: {note_id}\n")
                f.write("-" * 50 + "\n")
                f.write(f"反推提示词:\n{base_prompt}\n")
                f.write("-" * 50 + "\n")
                f.write(f"生成文案:\n{generated_caption}\n")
            
            # ========== 9. 完成 ==========
            logger.info(f"========== 复刻完成！笔记ID: {note_id} ==========")
            yield sse_event("complete", {
                "message": "复刻完成！",
                "note_id": note_id
            })
            
        except Exception as e:
            logger.error(f"处理失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            yield sse_event("error", {"message": f"处理失败: {str(e)}"})
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Content-Type": "text/event-stream; charset=utf-8",
        }
    )


@router.get("/images/{note_id}/{folder}/{filename}")
async def get_image(note_id: str, folder: str, filename: str):
    """获取图片文件"""
    data_dir = Path(__file__).parent.parent / "data"
    image_path = data_dir / note_id / folder / filename
    
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="图片不存在")
    
    return FileResponse(image_path)


@router.get("/download/{note_id}/{folder}/{filename}")
async def download_image(note_id: str, folder: str, filename: str):
    """下载图片文件"""
    data_dir = Path(__file__).parent.parent / "data"
    image_path = data_dir / note_id / folder / filename
    
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="图片不存在")
    
    return FileResponse(
        image_path,
        media_type="application/octet-stream",
        filename=filename
    )
