import { expect, test, type Page } from "@playwright/test";
import type { Galaxy, Star, Universe } from "../lib/api";
import { layoutUniverse } from "../components/universe-layout";

// Synthetic UI fixtures. These are never published or written to the real vault.
function galaxy(index: number, u: number | null = 0.5): Galaxy {
  const stars: Star[] = Array.from(
    { length: index === 0 ? 25 : 2 },
    (_, n) => ({
      id: `synthetic-star-${index}-${n}`,
      stage: "derivative",
      kind: "source",
      target_id: null,
      label: "合成测试星体",
      url: null,
      bvid: null,
      tier: null,
      at: null,
      date: null,
      t: null,
      milestone: false,
      evidence_ids: [],
    }),
  );
  return {
    meme_id: `synthetic-${index}`,
    name: `合成馆藏长名称用于验证排版${index}`,
    definition: "仅用于浏览器布局验收的合成记录，不是真实文化事实。",
    emergence: {
      at: null,
      date: u === null ? null : "2026-05-04",
      basis: "derivative",
    },
    u,
    stars,
    milestones: {},
    bands: [],
    ticks: [],
  };
}

const catalogue: Universe = {
  timezone: "Asia/Shanghai",
  quiet_gap_days: 28,
  axis: {
    bands: [],
    ticks: [
      { t: 0, date: "2026-05-04" },
      { t: 1, date: "2026-09-12" },
    ],
  },
  galaxies: [galaxy(0, 0), galaxy(1, null), galaxy(2, 1)],
  links: [],
};

async function mockCatalogue(page: Page, universe = catalogue) {
  await page.route("**/api/v1/universe", (route) =>
    route.fulfill({ json: universe }),
  );
  await page.route("**/api/v1/search", (route) =>
    route.fulfill({
      json: {
        items: [],
        total: 0,
        channels: ["catalog"],
        degraded: [],
        scores_calibrated: false,
      },
    }),
  );
}

for (const viewport of [
  { width: 320, height: 780 },
  { width: 390, height: 844 },
  { width: 768, height: 1024 },
  { width: 1440, height: 900 },
]) {
  test(`search is in the first screen without page overflow at ${viewport.width}px`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    await mockCatalogue(page);
    await page.goto("/");
    const search = page.getByRole("button", { name: "搜索记忆", exact: true });
    await expect(search).toBeEnabled();
    const box = await search.boundingBox();
    expect(box!.y + box!.height).toBeLessThan(viewport.height);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await page.getByRole("button", { name: "下一条馆藏" }).click();
    await expect(page.locator(".atlas-meta")).toContainText("日期未确认");
    await page.getByRole("button", { name: "上一条馆藏" }).click();
    await expect(page.locator(".atlas-meta")).toContainText("25 颗证据星");
  });
}

test("dense and undated catalogues grow the map without losing records", () => {
  const data = {
    ...catalogue,
    galaxies: [
      ...Array.from({ length: 40 }, (_, i) => galaxy(i)),
      ...Array.from({ length: 15 }, (_, i) => galaxy(40 + i, null)),
    ],
  };
  const { placed, undated, height } = layoutUniverse(data);
  expect(placed.length + undated.length).toBe(55);
  expect(new Set(placed.map((item) => item.y)).size).toBe(40);
  expect(
    [...placed, ...undated].every((item) => item.y + item.radius + 40 < height),
  ).toBe(true);
  expect(
    layoutUniverse({ ...data, galaxies: [...data.galaxies].reverse() }),
  ).toEqual({ placed, undated, height });
});

test("mobile record and contribution pages keep content readable without overflow", async ({
  page,
}) => {
  await page.setViewportSize({ width: 320, height: 780 });
  await mockCatalogue(page);
  await page.route("**/api/v1/memes/synthetic-0", (route) =>
    route.fulfill({
      json: {
        id: "synthetic-0",
        canonical_name: "合成馆藏长名称用于验证排版",
        aliases: ["合成别名"],
        definition: "仅用于布局验证的合成定义。",
        usage_context: "",
        evidence: [],
        published_revision: 1,
        origin_status: "unknown",
        claims: [],
        events: [],
        relations: [],
      },
    }),
  );
  await page.goto("/memes/synthetic-0");
  const definition = page.getByRole("heading", { name: "它是什么意思" });
  await expect(definition).toBeVisible();
  expect((await definition.boundingBox())!.y).toBeLessThan(780);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  for (const url of ["/submit", "/review"]) {
    await page.goto(url);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  }
});

test("dense map labels do not overlap and a reset returns to the top", async ({
  page,
}) => {
  await mockCatalogue(page, {
    ...catalogue,
    galaxies: Array.from({ length: 20 }, (_, i) => galaxy(i)),
  });
  await page.goto("/universe");
  await expect(page.locator(".galaxy")).toHaveCount(20);
  await page.evaluate(() => document.fonts.ready);
  const overlapping = await page
    .locator(".galaxy-name, .galaxy-count")
    .evaluateAll((labels) => {
      const boxes = labels.map((node) =>
        (node as SVGGraphicsElement).getBBox(),
      );
      return boxes.some((a, i) =>
        boxes
          .slice(i + 1)
          .some(
            (b) =>
              a.x < b.x + b.width &&
              a.x + a.width > b.x &&
              a.y < b.y + b.height &&
              a.y + a.height > b.y,
          ),
      );
    });
  expect(overlapping).toBe(false);
  const stage = page.getByRole("region", { name: "可滚动星图" });
  await stage.hover();
  await page.mouse.wheel(0, 1000);
  await expect
    .poll(() => stage.evaluate((node) => node.scrollTop))
    .toBeGreaterThan(0);
  await page.getByRole("button", { name: "重置视图" }).click();
  await expect.poll(() => stage.evaluate((node) => node.scrollTop)).toBe(0);
  const last = page.locator(".galaxy").last();
  const lastId = await last.getAttribute("data-meme-id");
  await last.focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(new RegExp(`meme=${lastId}`));
  await expect(page.locator(".milestone-rail")).toBeVisible();
});

test("reduced motion and unavailable atlas leave search usable", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.route("**/api/v1/universe", (route) =>
    route.fulfill({ status: 503, json: { detail: "合成不可用状态" } }),
  );
  await page.route("**/api/v1/search", (route) =>
    route.fulfill({
      json: {
        items: [],
        total: 0,
        channels: ["catalog"],
        degraded: [],
        scores_calibrated: false,
      },
    }),
  );
  await page.goto("/");
  await expect(
    page.getByRole("button", { name: "搜索记忆", exact: true }),
  ).toBeEnabled();
  await expect(page.locator(".atlas-unavailable")).toBeVisible();
  expect(
    await page
      .locator(".sky-rotor")
      .evaluate((node) => getComputedStyle(node).animationName),
  ).toBe("none");
  await page.getByRole("textbox", { name: "搜索记忆" }).fill("合成搜索");
  await page.getByRole("button", { name: "搜索记忆", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "这段记忆，还缺少证据" }),
  ).toBeVisible();
});
