"use client";

import { useState, useRef, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Toaster, toast } from "sonner";
import {
  X,
  ClipboardPaste,
  Sparkles,
  Download,
  Copy,
  Check,
  Loader2,
  ImageIcon,
  Wand2,
  FileText,
  Link2,
  Images,
  Type,
  Palette,
  ZoomIn,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { saveAs } from "file-saver";

// 工作流步骤
const WORKFLOW_STEPS = [
  { id: "parsing", label: "解析URL", icon: Link2 },
  { id: "downloading", label: "下载图片", icon: Images },
  { id: "understanding", label: "反推提示词", icon: Wand2 },
  { id: "variants", label: "生成变体", icon: Palette },
  { id: "text2img", label: "文生图", icon: ImageIcon },
  { id: "img2img", label: "图生图", icon: Sparkles },
  { id: "copywriting", label: "生成文案", icon: FileText },
];

interface GeneratedImage {
  index: number;
  url: string;
  label: string;
  type: "generated" | "variant";
}

export default function Home() {
  const [url, setUrl] = useState("");
  const [isProcessing, setIsProcessing] = useState(false);
  const [currentStep, setCurrentStep] = useState<string | null>(null);
  const [completedSteps, setCompletedSteps] = useState<string[]>([]);
  const [statusMessage, setStatusMessage] = useState("");

  // 数据状态
  const [noteInfo, setNoteInfo] = useState<{
    title: string;
    author: string;
    noteId: string;
  } | null>(null);
  const [originalImages, setOriginalImages] = useState<string[]>([]);
  const [originalCaption, setOriginalCaption] = useState("");
  const [basePrompt, setBasePrompt] = useState("");
  const [variantPrompts, setVariantPrompts] = useState<string[]>([]);
  const [generatedImages, setGeneratedImages] = useState<GeneratedImage[]>([]);
  const [generatedCaption, setGeneratedCaption] = useState("");

  const [copiedPrompt, setCopiedPrompt] = useState(false);
  const [copiedCaption, setCopiedCaption] = useState(false);

  // 图片放大查看状态
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const [lightboxImages, setLightboxImages] = useState<{url: string; label: string}[]>([]);
  const [lightboxIndex, setLightboxIndex] = useState(0);

  const eventSourceRef = useRef<EventSource | null>(null);

  const handlePaste = async () => {
    try {
      const text = await navigator.clipboard.readText();
      setUrl(text);
    } catch {
      toast.error("无法访问剪贴板");
    }
  };

  const handleClear = () => {
    setUrl("");
  };

  const resetState = () => {
    setCurrentStep(null);
    setCompletedSteps([]);
    setStatusMessage("");
    setNoteInfo(null);
    setOriginalImages([]);
    setOriginalCaption("");
    setBasePrompt("");
    setVariantPrompts([]);
    setGeneratedImages([]);
    setGeneratedCaption("");
  };

  const handleMimic = useCallback(async () => {
    if (!url.trim()) {
      toast.error("请输入小红书链接");
      return;
    }

    resetState();
    setIsProcessing(true);

    try {
      const response = await fetch("http://localhost:8000/api/mimic", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ url: url.trim() }),
      });

      if (!response.ok) {
        throw new Error("请求失败");
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error("无法读取响应");
      }

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("event: ")) {
            const eventType = line.slice(7).trim();
            continue;
          }
          if (line.startsWith("data: ")) {
            const data = JSON.parse(line.slice(6));
            handleSSEEvent(data);
          }
        }
      }
    } catch (error) {
      toast.error("处理失败，请检查后端服务是否启动");
      console.error(error);
    } finally {
      setIsProcessing(false);
      setCurrentStep(null);
    }
  }, [url]);

  const handleSSEEvent = (data: Record<string, unknown>) => {
    // 处理不同类型的事件
    if (data.step) {
      const step = data.step as string;
      setCurrentStep(step);
      if (data.message) {
        setStatusMessage(data.message as string);
      }
      // 标记上一步完成
      const stepIndex = WORKFLOW_STEPS.findIndex((s) => s.id === step);
      if (stepIndex > 0) {
        const prevSteps = WORKFLOW_STEPS.slice(0, stepIndex).map((s) => s.id);
        setCompletedSteps(prevSteps);
      }
    }

    if (data.note_id) {
      setNoteInfo({
        title: (data.title as string) || "",
        author: (data.author as string) || "",
        noteId: data.note_id as string,
      });
    }

    // 处理单张原始图片（即时返回）
    if (data.url && !data.type) {
      // original_image 事件
      setOriginalImages((prev) => {
        const newUrl = data.url as string;
        if (prev.includes(newUrl)) return prev;
        return [...prev, newUrl].sort();
      });
      if (data.caption) {
        setOriginalCaption(data.caption as string);
      }
    }

    // 兼容旧的批量图片事件
    if (data.type === "original" && data.urls) {
      setOriginalImages(data.urls as string[]);
      if (data.caption) {
        setOriginalCaption(data.caption as string);
      }
    }

    if (data.base_prompt) {
      setBasePrompt(data.base_prompt as string);
    }

    if (data.variants) {
      setVariantPrompts(data.variants as string[]);
    }

    if (data.type === "generated" || data.type === "variant") {
      setGeneratedImages((prev) => {
        const newImage: GeneratedImage = {
          index: data.index as number,
          url: data.url as string,
          label: data.label as string,
          type: data.type as "generated" | "variant",
        };
        // 避免重复
        const exists = prev.some(
          (img) => img.index === newImage.index && img.type === newImage.type
        );
        if (exists) return prev;
        return [...prev, newImage].sort((a, b) => a.index - b.index);
      });
    }

    if (data.text && !data.type) {
      setGeneratedCaption(data.text as string);
    }

    if (data.message === "复刻完成！") {
      setCompletedSteps(WORKFLOW_STEPS.map((s) => s.id));
      toast.success("复刻完成！");
    }

    // 处理错误事件
    if (data.error || (data.message && typeof data.message === 'string' && 
        (data.message.includes("失败") || data.message.includes("无法") || data.message.includes("错误")))) {
      const errorMsg = data.error || data.message;
      console.error("SSE Error:", errorMsg);
      toast.error(errorMsg as string);
      setIsProcessing(false);
    }
  };

  const copyToClipboard = async (text: string, type: "prompt" | "caption") => {
    try {
      await navigator.clipboard.writeText(text);
      if (type === "prompt") {
        setCopiedPrompt(true);
        setTimeout(() => setCopiedPrompt(false), 2000);
      } else {
        setCopiedCaption(true);
        setTimeout(() => setCopiedCaption(false), 2000);
      }
      toast.success("已复制到剪贴板");
    } catch {
      toast.error("复制失败");
    }
  };

  const downloadImage = async (url: string, filename: string) => {
    try {
      const response = await fetch(url);
      const blob = await response.blob();
      saveAs(blob, filename);
      toast.success(`已下载 ${filename}`);
    } catch {
      toast.error("下载失败");
    }
  };

  // 打开图片放大查看
  const openLightbox = (images: {url: string; label: string}[], index: number) => {
    setLightboxImages(images);
    setLightboxIndex(index);
    setLightboxOpen(true);
  };

  // 关闭图片放大查看
  const closeLightbox = () => {
    setLightboxOpen(false);
    setLightboxImages([]);
    setLightboxIndex(0);
  };

  // 上一张/下一张
  const prevImage = () => {
    setLightboxIndex((prev) => (prev > 0 ? prev - 1 : lightboxImages.length - 1));
  };
  const nextImage = () => {
    setLightboxIndex((prev) => (prev < lightboxImages.length - 1 ? prev + 1 : 0));
  };

  const downloadAllImages = async () => {
    try {
      toast.info("开始下载所有图片...");
      let count = 0;
      const total = originalImages.length + generatedImages.length;

      // 逐张下载原始图片
      for (let i = 0; i < originalImages.length; i++) {
        const response = await fetch(`http://localhost:8000${originalImages[i]}`);
        const blob = await response.blob();
        saveAs(blob, `original_${i + 1}.jpg`);
        count++;
      }

      // 逐张下载生成图片
      for (const img of generatedImages) {
        const response = await fetch(`http://localhost:8000${img.url}`);
        const blob = await response.blob();
        const ext = img.url.includes('.png') ? 'png' : 'jpg';
        saveAs(blob, `${img.label}.${ext}`);
        count++;
      }

      toast.success(`已下载 ${count} 张图片`);
    } catch {
      toast.error("下载失败");
    }
  };

  const handleCopyAll = async () => {
    // 先复制文案
    if (generatedCaption) {
      try {
        await navigator.clipboard.writeText(generatedCaption);
        toast.success("文案已复制到剪贴板");
      } catch {
        toast.error("复制文案失败");
      }
    }
    // 再下载图片
    await downloadAllImages();
  };

  return (
    <main className="min-h-screen relative overflow-hidden">
      {/* 渐变背景 */}
      <div className="fixed inset-0 bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900" />
      <div className="fixed inset-0 bg-[url('data:image/svg+xml,%3Csvg viewBox=%220 0 200 200%22 xmlns=%22http://www.w3.org/2000/svg%22%3E%3Cfilter id=%22noise%22%3E%3CfeTurbulence type=%22fractalNoise%22 baseFrequency=%220.65%22 numOctaves=%223%22 stitchTiles=%22stitch%22/%3E%3C/filter%3E%3Crect width=%22100%25%22 height=%22100%25%22 filter=%22url(%23noise)%22/%3E%3C/svg%3E')] opacity-[0.03]" />

      {/* 动态光效 */}
      <div className="fixed top-[-50%] left-[-50%] w-[200%] h-[200%] animate-[spin_60s_linear_infinite]">
        <div className="absolute top-1/2 left-1/2 w-96 h-96 bg-purple-500/20 rounded-full blur-[120px]" />
        <div className="absolute top-1/3 left-1/3 w-72 h-72 bg-blue-500/20 rounded-full blur-[100px]" />
        <div className="absolute bottom-1/3 right-1/3 w-80 h-80 bg-pink-500/15 rounded-full blur-[110px]" />
      </div>

      <div className="relative z-10 container mx-auto px-4 py-8 max-w-6xl">
        {/* Hero Section */}
        <div className="text-center mb-12 animate-in fade-in slide-in-from-bottom-4 duration-700">
          <h1
            className="text-6xl md:text-7xl font-bold mb-4 bg-gradient-to-r from-white via-purple-200 to-pink-200 bg-clip-text text-transparent"
            style={{ fontFamily: "Orbitron, sans-serif" }}
          >
            Mimic Them
          </h1>
          <p
            className="text-xl md:text-2xl text-purple-200/80"
            style={{ fontFamily: "Noto Sans SC, sans-serif" }}
          >
            一键复刻爆款小红书小姐姐
          </p>
        </div>

        {/* URL Input Card */}
        <Card className="mb-8 bg-white/5 backdrop-blur-xl border-white/10 shadow-2xl animate-in fade-in slide-in-from-bottom-4 duration-700 delay-100">
          <CardContent className="p-6">
            <div className="flex gap-3">
              <div className="relative flex-1">
                <Input
                  placeholder="请粘贴小红书图文链接..."
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  className="h-14 pl-5 pr-20 text-lg bg-white/5 border-white/20 text-white placeholder:text-white/40 focus:border-purple-400 focus:ring-purple-400/20"
                  style={{ fontFamily: "Noto Sans SC, sans-serif" }}
                  disabled={isProcessing}
                />
                <div className="absolute right-2 top-1/2 -translate-y-1/2 flex gap-1">
                  {url && (
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={handleClear}
                      className="h-10 w-10 text-white/60 hover:text-white hover:bg-white/10"
                    >
                      <X className="h-5 w-5" />
                    </Button>
                  )}
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={handlePaste}
                    className="h-10 w-10 text-white/60 hover:text-white hover:bg-white/10"
                  >
                    <ClipboardPaste className="h-5 w-5" />
                  </Button>
                </div>
              </div>
              <Button
                onClick={handleMimic}
                disabled={isProcessing || !url.trim()}
                className="h-14 px-8 text-lg font-semibold bg-gradient-to-r from-purple-500 to-pink-500 hover:from-purple-600 hover:to-pink-600 text-white border-0 shadow-lg shadow-purple-500/25 transition-all duration-300 hover:shadow-purple-500/40 hover:scale-105 disabled:opacity-50 disabled:hover:scale-100"
                style={{ fontFamily: "Noto Sans SC, sans-serif" }}
              >
                {isProcessing ? (
                  <>
                    <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                    处理中...
                  </>
                ) : (
                  <>
                    <Sparkles className="mr-2 h-5 w-5" />
                    一键复刻
                  </>
                )}
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Progress Steps */}
        {(isProcessing || completedSteps.length > 0) && (
          <Card className="mb-8 bg-white/5 backdrop-blur-xl border-white/10 shadow-2xl animate-in fade-in slide-in-from-bottom-4 duration-500">
            <CardContent className="p-6">
              <div className="flex items-center justify-between overflow-x-auto pb-2">
                {WORKFLOW_STEPS.map((step, index) => {
                  const Icon = step.icon;
                  const isCompleted = completedSteps.includes(step.id);
                  const isCurrent = currentStep === step.id;

                  return (
                    <div key={step.id} className="flex items-center">
                      <div className="flex flex-col items-center min-w-[80px]">
                        <div
                          className={`
                            w-12 h-12 rounded-full flex items-center justify-center mb-2 transition-all duration-500
                            ${
                              isCompleted
                                ? "bg-green-500/20 text-green-400 border-2 border-green-400"
                                : isCurrent
                                ? "bg-purple-500/20 text-purple-400 border-2 border-purple-400 animate-pulse"
                                : "bg-white/5 text-white/30 border border-white/10"
                            }
                          `}
                        >
                          {isCompleted ? (
                            <Check className="h-5 w-5" />
                          ) : isCurrent ? (
                            <Loader2 className="h-5 w-5 animate-spin" />
                          ) : (
                            <Icon className="h-5 w-5" />
                          )}
                        </div>
                        <span
                          className={`text-xs whitespace-nowrap ${
                            isCompleted
                              ? "text-green-400"
                              : isCurrent
                              ? "text-purple-400"
                              : "text-white/40"
                          }`}
                          style={{ fontFamily: "Noto Sans SC, sans-serif" }}
                        >
                          {step.label}
                        </span>
                      </div>
                      {index < WORKFLOW_STEPS.length - 1 && (
                        <div
                          className={`w-8 h-0.5 mx-2 transition-all duration-500 ${
                            completedSteps.includes(
                              WORKFLOW_STEPS[index + 1]?.id
                            ) || completedSteps.includes(step.id)
                              ? "bg-green-400/50"
                              : "bg-white/10"
                          }`}
                        />
                      )}
                    </div>
                  );
                })}
              </div>
              {statusMessage && (
                <p
                  className="text-center text-purple-300/80 mt-4 text-sm"
                  style={{ fontFamily: "Noto Sans SC, sans-serif" }}
                >
                  {statusMessage}
                </p>
              )}
            </CardContent>
          </Card>
        )}

        {/* Original Images */}
        {originalImages.length > 0 && (
          <Card className="mb-8 bg-white/5 backdrop-blur-xl border-white/10 shadow-2xl animate-in fade-in slide-in-from-bottom-4 duration-500">
            <CardContent className="p-6">
              <div className="flex items-center gap-3 mb-4">
                <Badge
                  variant="secondary"
                  className="bg-blue-500/20 text-blue-300 border-blue-400/30"
                >
                  <Images className="h-3 w-3 mr-1" />
                  原始图片
                </Badge>
                {noteInfo && (
                  <span
                    className="text-white/60 text-sm"
                    style={{ fontFamily: "Noto Sans SC, sans-serif" }}
                  >
                    {noteInfo.title} · {noteInfo.author}
                  </span>
                )}
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4 mb-4">
                {originalImages.map((img, index) => (
                  <div key={index} className="relative group">
                    <div 
                      className="aspect-[3/4] rounded-lg overflow-hidden bg-white/5 cursor-pointer"
                      onClick={() => openLightbox(
                        originalImages.map((u, i) => ({ url: `http://localhost:8000${u}`, label: `原始图片 ${i + 1}` })),
                        index
                      )}
                    >
                      <img
                        src={`http://localhost:8000${img}`}
                        alt={`原始图片 ${index + 1}`}
                        className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
                      />
                      <div className="absolute inset-0 bg-black/0 group-hover:bg-black/20 transition-colors flex items-center justify-center">
                        <ZoomIn className="h-8 w-8 text-white opacity-0 group-hover:opacity-100 transition-opacity" />
                      </div>
                    </div>
                    <Button
                      variant="secondary"
                      size="icon"
                      className="absolute bottom-2 right-2 h-8 w-8 bg-black/50 hover:bg-black/70 text-white opacity-0 group-hover:opacity-100 transition-opacity"
                      onClick={(e) => {
                        e.stopPropagation();
                        downloadImage(
                          `http://localhost:8000${img}`,
                          `original_${index + 1}.jpg`
                        );
                      }}
                    >
                      <Download className="h-4 w-4" />
                    </Button>
                  </div>
                ))}
              </div>
              {originalCaption && (
                <p
                  className="text-white/70 text-sm leading-relaxed"
                  style={{ fontFamily: "Noto Sans SC, sans-serif" }}
                >
                  {originalCaption}
                </p>
              )}
            </CardContent>
          </Card>
        )}

        {/* Base Prompt */}
        {basePrompt && (
          <Card className="mb-8 bg-white/5 backdrop-blur-xl border-white/10 shadow-2xl animate-in fade-in slide-in-from-bottom-4 duration-500">
            <CardContent className="p-6">
              <div className="flex items-center justify-between mb-4">
                <Badge
                  variant="secondary"
                  className="bg-purple-500/20 text-purple-300 border-purple-400/30"
                >
                  <Wand2 className="h-3 w-3 mr-1" />
                  反推提示词
                </Badge>
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-white/60 hover:text-white hover:bg-white/10"
                  onClick={() => copyToClipboard(basePrompt, "prompt")}
                >
                  {copiedPrompt ? (
                    <Check className="h-4 w-4 mr-1" />
                  ) : (
                    <Copy className="h-4 w-4 mr-1" />
                  )}
                  复制
                </Button>
              </div>
              <p
                className="text-white/80 text-sm leading-relaxed whitespace-pre-wrap"
                style={{ fontFamily: "Noto Sans SC, sans-serif" }}
              >
                {basePrompt}
              </p>
            </CardContent>
          </Card>
        )}

        {/* Generated Images */}
        {generatedImages.length > 0 && (
          <Card className="mb-8 bg-white/5 backdrop-blur-xl border-white/10 shadow-2xl animate-in fade-in slide-in-from-bottom-4 duration-500">
            <CardContent className="p-6">
              <div className="flex items-center gap-3 mb-4">
                <Badge
                  variant="secondary"
                  className="bg-pink-500/20 text-pink-300 border-pink-400/30"
                >
                  <Sparkles className="h-3 w-3 mr-1" />
                  AI 生成图片
                </Badge>
                <span
                  className="text-white/40 text-xs"
                  style={{ fontFamily: "Noto Sans SC, sans-serif" }}
                >
                  {generatedImages.length} 张
                </span>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
                {generatedImages.map((image, idx) => (
                  <div key={`${image.type}-${image.index}`} className="relative group">
                    <div 
                      className="aspect-[3/4] rounded-lg overflow-hidden bg-white/5 border border-white/10 cursor-pointer"
                      onClick={() => openLightbox(
                        generatedImages.map((img) => ({ url: `http://localhost:8000${img.url}`, label: img.label })),
                        idx
                      )}
                    >
                      <img
                        src={`http://localhost:8000${image.url}`}
                        alt={image.label}
                        className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
                      />
                      <div className="absolute inset-0 bg-black/0 group-hover:bg-black/20 transition-colors flex items-center justify-center">
                        <ZoomIn className="h-8 w-8 text-white opacity-0 group-hover:opacity-100 transition-opacity" />
                      </div>
                    </div>
                    <Badge
                      className="absolute top-2 left-2 bg-black/50 text-white text-xs"
                      variant="secondary"
                    >
                      {image.label}
                    </Badge>
                    <Button
                      variant="secondary"
                      size="icon"
                      className="absolute bottom-2 right-2 h-8 w-8 bg-black/50 hover:bg-black/70 text-white opacity-0 group-hover:opacity-100 transition-opacity"
                      onClick={(e) => {
                        e.stopPropagation();
                        downloadImage(
                          `http://localhost:8000${image.url}`,
                          `${image.label}.png`
                        );
                      }}
                    >
                      <Download className="h-4 w-4" />
                    </Button>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Generated Caption */}
        {generatedCaption && (
          <Card className="mb-8 bg-white/5 backdrop-blur-xl border-white/10 shadow-2xl animate-in fade-in slide-in-from-bottom-4 duration-500">
            <CardContent className="p-6">
              <div className="flex items-center justify-between mb-4">
                <Badge
                  variant="secondary"
                  className="bg-green-500/20 text-green-300 border-green-400/30"
                >
                  <FileText className="h-3 w-3 mr-1" />
                  生成文案
                </Badge>
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-white/60 hover:text-white hover:bg-white/10"
                  onClick={() => copyToClipboard(generatedCaption, "caption")}
                >
                  {copiedCaption ? (
                    <Check className="h-4 w-4 mr-1" />
                  ) : (
                    <Copy className="h-4 w-4 mr-1" />
                  )}
                  复制
                </Button>
              </div>
              <p
                className="text-white/90 text-lg leading-relaxed whitespace-pre-wrap"
                style={{ fontFamily: "Noto Sans SC, sans-serif" }}
              >
                {generatedCaption}
              </p>
            </CardContent>
          </Card>
        )}

        {/* Action Buttons */}
        {generatedImages.length > 0 && generatedCaption && (
          <div className="flex flex-wrap justify-center gap-4 animate-in fade-in slide-in-from-bottom-4 duration-500">
            <Button
              onClick={handleCopyAll}
              className="h-12 px-6 text-base font-semibold bg-gradient-to-r from-green-500 to-emerald-500 hover:from-green-600 hover:to-emerald-600 text-white border-0 shadow-lg shadow-green-500/25"
              style={{ fontFamily: "Noto Sans SC, sans-serif" }}
            >
              <Copy className="mr-2 h-5 w-5" />
              一键复制全部
            </Button>
            <Button
              onClick={downloadAllImages}
              variant="outline"
              className="h-12 px-6 text-base font-semibold bg-white/5 border-white/20 text-white hover:bg-white/10 hover:text-white"
              style={{ fontFamily: "Noto Sans SC, sans-serif" }}
            >
              <Download className="mr-2 h-5 w-5" />
              下载全部图片
            </Button>
            <Button
              onClick={() => copyToClipboard(generatedCaption, "caption")}
              variant="outline"
              className="h-12 px-6 text-base font-semibold bg-white/5 border-white/20 text-white hover:bg-white/10 hover:text-white"
              style={{ fontFamily: "Noto Sans SC, sans-serif" }}
            >
              <FileText className="mr-2 h-5 w-5" />
              复制文案
            </Button>
          </div>
        )}

        {/* Footer */}
        <footer className="mt-16 text-center text-white/30 text-sm">
          <p style={{ fontFamily: "Noto Sans SC, sans-serif" }}>
            MimicThem - 仅支持图文链接，不支持视频内容
          </p>
        </footer>
      </div>

      <Toaster
        position="top-center"
        toastOptions={{
          style: {
            background: "rgba(0, 0, 0, 0.8)",
            backdropFilter: "blur(12px)",
            color: "white",
            border: "1px solid rgba(255, 255, 255, 0.1)",
          },
        }}
      />

      {/* 图片放大查看 Lightbox */}
      {lightboxOpen && (
        <div 
          className="fixed inset-0 z-50 bg-black/95 flex items-center justify-center"
          onClick={closeLightbox}
        >
          {/* 关闭按钮 */}
          <Button
            variant="ghost"
            size="icon"
            className="absolute top-4 right-4 h-12 w-12 text-white/70 hover:text-white hover:bg-white/10 z-10"
            onClick={closeLightbox}
          >
            <X className="h-8 w-8" />
          </Button>

          {/* 上一张按钮 */}
          {lightboxImages.length > 1 && (
            <Button
              variant="ghost"
              size="icon"
              className="absolute left-4 top-1/2 -translate-y-1/2 h-12 w-12 text-white/70 hover:text-white hover:bg-white/10 z-10"
              onClick={(e) => {
                e.stopPropagation();
                prevImage();
              }}
            >
              <ChevronLeft className="h-8 w-8" />
            </Button>
          )}

          {/* 下一张按钮 */}
          {lightboxImages.length > 1 && (
            <Button
              variant="ghost"
              size="icon"
              className="absolute right-4 top-1/2 -translate-y-1/2 h-12 w-12 text-white/70 hover:text-white hover:bg-white/10 z-10"
              onClick={(e) => {
                e.stopPropagation();
                nextImage();
              }}
            >
              <ChevronRight className="h-8 w-8" />
            </Button>
          )}

          {/* 图片容器 */}
          <div 
            className="max-w-[90vw] max-h-[85vh] flex flex-col items-center"
            onClick={(e) => e.stopPropagation()}
          >
            <img
              src={lightboxImages[lightboxIndex]?.url}
              alt={lightboxImages[lightboxIndex]?.label}
              className="max-w-full max-h-[80vh] object-contain rounded-lg"
            />
            <div className="mt-4 flex items-center gap-4">
              <span className="text-white/80 text-lg" style={{ fontFamily: "Noto Sans SC, sans-serif" }}>
                {lightboxImages[lightboxIndex]?.label}
              </span>
              <span className="text-white/50 text-sm">
                {lightboxIndex + 1} / {lightboxImages.length}
              </span>
              <Button
                variant="secondary"
                size="sm"
                className="bg-white/10 hover:bg-white/20 text-white border-0"
                onClick={() => {
                  const img = lightboxImages[lightboxIndex];
                  if (img) {
                    const filename = img.label.replace(/\s+/g, '_') + (img.url.includes('.png') ? '.png' : '.jpg');
                    downloadImage(img.url, filename);
                  }
                }}
              >
                <Download className="h-4 w-4 mr-1" />
                下载
              </Button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
