import { Suspense } from "react";
import type { Metadata } from "next";
import { UniverseExplorer } from "@/components/universe-explorer";

export const metadata: Metadata = {
  title: "梗的星图 · Cyber Memoir",
  description:
    "每一个已发布的梗，按照有证据的日期摆在时间轴上。可核查的、尚未定日的、完全没有证据的，各不相同。",
};

/**
 * `?meme=<id>` opens one galaxy, so the level being shown lives in the URL and the
 * browser's own back button walks back out to the universe. The parameter is read
 * on the server and handed to the client, which then fetches /v1/universe itself.
 */
export default async function UniversePage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const params = await searchParams;
  const meme = params.meme;
  const memeId = Array.isArray(meme) ? meme[0] ?? "" : meme ?? "";
  return (
    <main id="main" className="page-main universe-main">
      <header className="universe-header">
        <h1 className="page-title">梗的星图</h1>
        <p className="page-subtitle">
          每一个点是一条有证据的记载。位置来自日期，颜色来自它在这个梗的传播中扮演的角色。
        </p>
      </header>
      <Suspense
        fallback={
          <p className="loading-line" role="status">
            正在读取星图…
          </p>
        }
      >
        <UniverseExplorer initialMemeId={memeId} />
      </Suspense>
    </main>
  );
}
