import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Mimic Them - 一键复刻爆款小红书小姐姐",
  description: "使用AI技术一键复刻小红书爆款图片，生成相似风格的系列图片和文案",
  icons: {
    icon: "/favicon.ico",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" className="dark">
      <body className="antialiased">
        {children}
      </body>
    </html>
  );
}
