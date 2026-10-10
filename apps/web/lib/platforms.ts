export const PLATFORMS = [
  ["bilibili", "Bilibili"],
  ["douyin", "抖音"],
  ["xiaohongshu", "小红书"],
  ["web", "网页"],
] as const;

export function platformLabel(platform: string | undefined) {
  return (
    PLATFORMS.find(([id]) => id === platform)?.[1] || platform || "平台未知"
  );
}
