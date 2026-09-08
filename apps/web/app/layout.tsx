import type { Metadata } from "next";
import { Header, Footer } from "@/components/shell";
import "./globals.css";
export const metadata: Metadata = {
  title: "Cyber Memoir · 赛博回忆录",
  description:
    "面向人类与 AI 的中文互联网文化记忆与检索基础设施。每一个解释，都有证据可循。",
};
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN" data-scroll-behavior="smooth">
      <body>
        <a href="#main" className="skip-link">
          跳至主内容
        </a>
        <Header />
        {children}
        <Footer />
      </body>
    </html>
  );
}
