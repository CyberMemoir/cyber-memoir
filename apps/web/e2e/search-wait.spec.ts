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

test("a new query ignores the old answer and independent retry keeps its captured inputs", async ({
  page,
}) => {
  let release: (() => void) | undefined;
  const answerBodies: { query: string; platform: string | null }[] = [];
  await page.route("**/api/v1/universe", (route) =>
    route.fulfill({ status: 503 }),
  );
  await page.route("**/api/v1/search", (route) =>
    route.fulfill({
      json: {
        items: [
          {
            id: "synthetic-new",
            canonical_name: "合成新查询结果",
            aliases: [],
            definition: "仅用于浏览器测试。",
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
    const body = route.request().postDataJSON();
    answerBodies.push(body);
    if (body.query === "旧合成查询") {
      await new Promise<void>((resolve) => {
        release = resolve;
      });
      await route
        .fulfill({
          json: {
            answer: "过时的旧回答",
            claims: [],
            citations: [],
            uncertainties: [],
            channels: [],
            mode: "extractive",
          },
        })
        .catch(() => {});
    } else if (answerBodies.length === 2) {
      await route.fulfill({ status: 503, json: { detail: "新查询合成失败" } });
    } else
      await route.fulfill({
        json: {
          answer: "新合成回答",
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
  await page.getByLabel("基于证据回答").check();
  await page.getByRole("textbox", { name: "搜索记忆" }).fill("旧合成查询");
  await page.getByRole("button", { name: "搜索记忆", exact: true }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "正在整理证据回答" }),
  ).toBeVisible();
  await page.getByRole("textbox", { name: "搜索记忆" }).fill("新合成查询");
  await page.getByRole("button", { name: "搜索记忆", exact: true }).click();
  await expect(
    page.getByRole("alert").filter({ hasText: "新查询合成失败" }),
  ).toBeVisible();
  release?.();
  await page.getByRole("textbox", { name: "搜索记忆" }).fill("尚未提交的编辑");
  await page.getByRole("button", { name: "重试回答", exact: true }).click();
  await expect(page.locator(".answer-text")).toHaveText("新合成回答");
  expect(answerBodies.map((x) => x.query)).toEqual([
    "旧合成查询",
    "新合成查询",
    "新合成查询",
  ]);
});

test("search timeout is bounded and preserves the submitted request for retry", async ({
  page,
}) => {
  await page.clock.install();
  let hold = false;
  const queries: string[] = [];
  await page.route("**/api/v1/universe", (route) =>
    route.fulfill({ status: 503 }),
  );
  await page.route("**/api/v1/search", (route) => {
    const body = route.request().postDataJSON();
    queries.push(body.query);
    if (hold) return;
    return route.fulfill({
      json: {
        items: [],
        total: 0,
        channels: [],
        degraded: [],
        query: body.query,
      },
    });
  });
  await page.goto("/");
  await expect(
    page.getByRole("button", { name: "搜索记忆", exact: true }),
  ).toBeEnabled();
  hold = true;
  await page.getByRole("textbox", { name: "搜索记忆" }).fill("合成超时查询");
  await page.getByRole("button", { name: "搜索记忆", exact: true }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "正在检索记忆" }),
  ).toBeVisible();
  await page.clock.fastForward(300001);
  await expect(
    page.getByRole("alert").filter({ hasText: "检索等待超时" }),
  ).toBeVisible();
  await page.getByRole("textbox", { name: "搜索记忆" }).fill("未提交的新描述");
  hold = false;
  await page.getByRole("button", { name: "重试", exact: true }).click();
  await expect(
    page.getByRole("alert").filter({ hasText: "检索等待超时" }),
  ).toHaveCount(0);
  expect(queries.slice(-2)).toEqual(["合成超时查询", "合成超时查询"]);
});

test("changed corpus offers a refresh of the captured query rather than a false no-evidence conclusion", async ({
  page,
}) => {
  const queries: string[] = [];
  await page.route("**/api/v1/universe", (route) =>
    route.fulfill({ status: 503 }),
  );
  await page.route("**/api/v1/search", (route) => {
    const body = route.request().postDataJSON();
    queries.push(body.query);
    return route.fulfill({
      json: {
        items: [],
        total: 0,
        query: body.query,
        channels: [],
        degraded: body.query ? ["corpus_changed_during_search"] : [],
      },
    });
  });
  await page.goto("/");
  await expect(
    page.getByRole("button", { name: "搜索记忆", exact: true }),
  ).toBeEnabled();
  await page
    .getByRole("textbox", { name: "搜索记忆" })
    .fill("合成档案更新查询");
  await page.getByRole("button", { name: "搜索记忆", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "公开档案在检索期间发生变化" }),
  ).toBeVisible();
  await page.getByRole("textbox", { name: "搜索记忆" }).fill("未提交的修改");
  await page.getByRole("button", { name: "刷新当前检索" }).click();
  await expect
    .poll(() => queries.slice(-2))
    .toEqual(["合成档案更新查询", "合成档案更新查询"]);
});
