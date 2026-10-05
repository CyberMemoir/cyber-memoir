import { expect, test } from "@playwright/test";

test("answer timeout preserves results and offers an independent retry", async ({
  page,
}) => {
  await page.clock.install();
  await page.route("**/api/v1/universe", (route) =>
    route.fulfill({ status: 503 }),
  );
  await page.route("**/api/v1/search", (route) =>
    route.fulfill({
      json: {
        items: [
          {
            id: "synthetic",
            canonical_name: "合成记忆",
            aliases: [],
            definition: "仅用于测试",
            evidence: [],
            published_revision: 1,
            origin_status: "unknown",
          },
        ],
        total: 1,
        channels: [],
        degraded: [],
        scores_calibrated: false,
      },
    }),
  );
  await page.route("**/api/v1/answers", () => {});
  await page.goto("/");
  await expect(page.locator(".meme-row")).toHaveCount(1);
  await page.getByRole("textbox", { name: "搜索记忆" }).fill("合成测试查询");
  await page.getByRole("checkbox", { name: "基于证据回答" }).check();
  await page.getByRole("button", { name: "搜索记忆", exact: true }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "正在整理证据回答" }),
  ).toBeVisible();
  await page.clock.fastForward(300001);
  await expect(
    page.getByRole("alert").filter({ hasText: "回答等待超时" }),
  ).toBeVisible();
  await expect(page.locator(".meme-row")).toHaveCount(1);
  await expect(
    page.getByRole("button", { name: "重试回答", exact: true }),
  ).toBeEnabled();
});

test("answer failure keeps results and retries only the answer", async ({
  page,
}) => {
  let searches = 0;
  let answers = 0;
  await page.route("**/api/v1/universe", (route) =>
    route.fulfill({ status: 503 }),
  );
  await page.route("**/api/v1/search", (route) => {
    searches++;
    return route.fulfill({
      json: {
        items: [
          {
            id: "synthetic",
            canonical_name: "合成记忆",
            aliases: [],
            definition: "仅用于测试",
            evidence: [],
            published_revision: 1,
            origin_status: "unknown",
          },
        ],
        total: 1,
        channels: [],
        degraded: [],
        scores_calibrated: false,
      },
    });
  });
  await page.route("**/api/v1/answers", (route) => {
    answers++;
    return answers === 1
      ? route.fulfill({ status: 503, json: { detail: "合成回答失败" } })
      : route.fulfill({
          json: {
            answer: "合成证据回答",
            claims: [],
            citations: [],
            uncertainties: [],
            channels: [],
            mode: "extractive",
          },
        });
  });
  await page.goto("/");
  await expect(page.locator(".meme-row")).toHaveCount(1);
  await page.getByRole("textbox", { name: "搜索记忆" }).fill("测试查询");
  await page.getByRole("checkbox", { name: "基于证据回答" }).check();
  await page.getByRole("button", { name: "搜索记忆", exact: true }).click();
  await expect(
    page.getByRole("alert").filter({ hasText: "合成回答失败" }),
  ).toBeVisible();
  await expect(page.locator(".meme-row")).toHaveCount(1);
  const before = searches;
  await page.getByRole("button", { name: "重试回答", exact: true }).click();
  await expect(page.locator(".answer-text")).toHaveText("合成证据回答");
  expect(searches).toBe(before);
  expect(answers).toBe(2);
});

test("slow answer leaves results usable and cancellation ignores a late response", async ({
  page,
}) => {
  let release: (() => void) | undefined;
  await page.route("**/api/v1/universe", (route) =>
    route.fulfill({ status: 503 }),
  );
  await page.route("**/api/v1/search", (route) =>
    route.fulfill({
      json: {
        items: [
          {
            id: "synthetic",
            canonical_name: "合成记忆",
            aliases: [],
            definition: "仅用于测试",
            evidence: [],
            published_revision: 1,
            origin_status: "unknown",
          },
        ],
        total: 1,
        channels: [],
        degraded: [],
        scores_calibrated: false,
      },
    }),
  );
  await page.route("**/api/v1/answers", async (route) => {
    await new Promise<void>((resolve) => {
      release = resolve;
    });
    await route
      .fulfill({
        json: {
          answer: "不应出现的旧回答",
          claims: [],
          citations: [],
          uncertainties: [],
          channels: [],
          mode: "extractive",
        },
      })
      .catch(() => {});
  });
  await page.goto("/");
  await expect(page.locator(".meme-row")).toHaveCount(1);
  await page.getByRole("textbox", { name: "搜索记忆" }).fill("测试查询");
  await page.getByRole("checkbox", { name: "基于证据回答" }).check();
  await page.getByRole("button", { name: "搜索记忆", exact: true }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "正在整理证据回答" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "搜索记忆", exact: true }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "取消等待", exact: true }).click();
  release?.();
  await expect(
    page.getByRole("button", { name: "重试回答", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".meme-row")).toHaveCount(1);
  await expect(page.locator(".answer-text")).toHaveCount(0);
});
