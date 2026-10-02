import { expect, test } from "@playwright/test";

const SIZES = [
  { width: 1505, height: 1045 },
  { width: 1100, height: 820 },
  { width: 390, height: 844 },
];

// The old absolute caption and horizon could paint over other content. Both now
// stay in document flow; test their actual bounds across the responsive layouts.
test("馆藏与检索区域不侵入记忆索引", async ({ page }) => {
  for (const size of SIZES) {
    await page.setViewportSize(size);
    await page.goto("/");
    await expect(page.locator(".atlas-caption")).toBeVisible();
    const bounds = await page.evaluate(() => {
      const box = (selector: string) =>
        document.querySelector(selector)!.getBoundingClientRect();
      return {
        captionBottom: box(".atlas-caption").bottom,
        consoleBottom: box(".dome-console").bottom,
        introTop: box(".archive-intro").top,
      };
    });
    expect(bounds.captionBottom).toBeLessThanOrEqual(bounds.introTop);
    expect(bounds.consoleBottom).toBeLessThanOrEqual(bounds.introTop);
  }
});

const LONG =
  "合成夹具的虚构表述，长到足以把说明撑到第二行，用来验证标题和正文的边界。";
const sky = {
  timezone: "Asia/Shanghai",
  quiet_gap_days: 21,
  axis: { ticks: [], bands: [] },
  links: [],
  galaxies: Array.from({ length: 3 }, (_, index) => ({
    meme_id: `synthetic-layout-${index}`,
    name: `合成夹具长名称用于验证标题${index}`,
    definition: LONG,
    emergence: { at: null, date: "2026-03-07", basis: "derivative" },
    u: index / 2,
    stars: [],
    milestones: {},
    bands: [],
    ticks: [],
  })),
};

test("切换长标题馆藏时，说明不遮挡检索或标题", async ({ page }) => {
  await page.route("**/v1/universe", (route) => route.fulfill({ json: sky }));
  for (const size of SIZES) {
    await page.setViewportSize(size);
    await page.goto("/");
    await expect(page.locator(".atlas-caption h2")).toContainText("合成夹具");
    for (let index = 0; index < 3; index += 1) {
      await page.getByRole("button", { name: "下一条馆藏" }).click();
      const overlap = await page.evaluate(() => {
        const caption = document
          .querySelector(".atlas-caption")!
          .getBoundingClientRect();
        return [".dome-title", ".search-form"].some((selector) => {
          const target = document
            .querySelector(selector)!
            .getBoundingClientRect();
          return (
            caption.left < target.right &&
            caption.right > target.left &&
            caption.top < target.bottom &&
            caption.bottom > target.top
          );
        });
      });
      expect(overlap).toBe(false);
    }
  }
});
