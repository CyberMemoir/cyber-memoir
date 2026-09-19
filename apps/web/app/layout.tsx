import type { Metadata, Viewport } from "next";
import { Header, Footer } from "@/components/shell";
import { NightSky } from "@/components/night-sky";
import "./fonts.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "Cyber Memoir · 赛博回忆录",
  description:
    "面向人类与 AI 的中文互联网文化记忆与检索基础设施。每一个解释，都有证据可循。",
};

export const viewport: Viewport = {
  themeColor: "#030305",
  colorScheme: "dark",
};

/* The direction this interface was built to, kept in the emitted markup so the
   finished page can be audited against it. */
const CONTRACT = `<!--
THESIS: The archive is a planetarium show. Ask for a meme and the dome turns to its galaxy, where every lit star is a dated piece of evidence; it refuses the encyclopedia page of cards and paragraphs.
OWN-WORLD: A night dome (#030305) of colourless starlight; one mint projector light (#7fe3c0) marks every control; the four role colours belong to evidence alone. Noto Serif SC for names and headings, Jost for numerals and dates, hairline instruments.
STORY: A curious netizen sees real memes glowing across the sky, asks at the console, gets an evidenced answer or an honest abstention, then flies into the meme's galaxy to see where it came from.
FIRST VIEWPORT: Upper half, the ecliptic: every published meme as a small spiral galaxy ordered by date, a projector pointer touring them. Lower half, on the horizon: a two-line serif headline and a full-width search console.
FORM: Planetarium show, fourth of seven grounded candidates; seed 402c824e.
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
-->`;

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN" data-scroll-behavior="smooth">
      <body>
        <div hidden dangerouslySetInnerHTML={{ __html: CONTRACT }} />
        <NightSky />
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
