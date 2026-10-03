import { expect, test } from "@playwright/test";

function searchPage(query: string, offset: number) {
  return {
    items: [
      {
        id: `synthetic-${offset}`,
        canonical_name: `合成分页记录 ${offset}`,
        aliases: [],
        definition: "仅用于浏览器测试，不写入真实档案。",
        evidence: [],
        published_revision: 1,
        origin_status: "unknown",
      },
    ],
    total: 2,
    channels: ["catalog"],
    degraded: [],
    scores_calibrated: false,
    query,
  };
}

test("retry preserves a failed page request despite edited input", async ({
  page,
}) => {
  const requests: { query: string; offset: number; platform: string | null }[] =
    [];
  let failPage = true;
  await page.route("**/api/v1/universe", (route) =>
    route.fulfill({ status: 503 }),
  );
  await page.route("**/api/v1/search", async (route) => {
    const body = route.request().postDataJSON();
    requests.push(body);
    if (body.offset && failPage) {
      failPage = false;
      await route.fulfill({ status: 503, json: { detail: "合成分页失败" } });
    } else {
      await route.fulfill({ json: searchPage(body.query, body.offset) });
    }
  });
  await page.goto("/");
  await expect(page.getByRole("button", { name: "加载更多" })).toBeEnabled();
  await page.getByRole("textbox", { name: "搜索记忆" }).fill("原查询");
  await page.getByRole("button", { name: "搜索记忆", exact: true }).click();
  await expect(page.getByRole("button", { name: "加载更多" })).toBeEnabled();
  await page.getByRole("button", { name: "加载更多" }).click();
  await expect(
    page.getByRole("alert").filter({ hasText: "合成分页失败" }),
  ).toBeVisible();
  await page
    .getByRole("textbox", { name: "搜索记忆" })
    .fill("尚未提交的新查询");
  await page.getByRole("button", { name: "重试", exact: true }).click();
  await expect(page.locator(".meme-row")).toHaveCount(2);
  expect(requests.slice(-2)).toEqual([
    { query: "原查询", platform: null, limit: 20, offset: 1 },
    { query: "原查询", platform: null, limit: 20, offset: 1 },
  ]);
});

test("pagination retains the evidence answer without another answer request", async ({
  page,
}) => {
  let answerRequests = 0;
  await page.route("**/api/v1/universe", (route) =>
    route.fulfill({ status: 503 }),
  );
  await page.route("**/api/v1/search", (route) => {
    const body = route.request().postDataJSON();
    return route.fulfill({ json: searchPage(body.query, body.offset) });
  });
  await page.route("**/api/v1/answers", (route) => {
    answerRequests++;
    return route.fulfill({
      json: {
        answer: "合成证据回答",
        claims: [],
        citations: [],
        uncertainties: [],
        channels: ["catalog"],
        mode: "extractive",
      },
    });
  });
  await page.goto("/");
  await expect(page.getByRole("button", { name: "加载更多" })).toBeEnabled();
  await page.getByRole("textbox", { name: "搜索记忆" }).fill("合成查询");
  await page.getByRole("checkbox", { name: "基于证据回答" }).check();
  await page.getByRole("button", { name: "搜索记忆", exact: true }).click();
  await expect(page.locator(".answer-text")).toHaveText("合成证据回答");
  await page.getByRole("button", { name: "加载更多" }).click();
  await expect(page.locator(".meme-row")).toHaveCount(2);
  await expect(
    page.getByRole("button", { name: "搜索记忆", exact: true }),
  ).toBeEnabled();
  await expect(page.locator(".answer-text")).toHaveText("合成证据回答");
  expect(answerRequests).toBe(1);
});

test("editing the search input does not change the query for the next page", async ({
  page,
}) => {
  const requests: { query: string; offset: number; platform: string | null }[] =
    [];
  await page.route("**/api/v1/search", async (route) => {
    const body = route.request().postDataJSON();
    requests.push(body);
    if (body.platform === "douyin") {
      await route.fulfill({ status: 503, json: { detail: "合成筛选失败" } });
      return;
    }
    await route.fulfill({
      json: {
        items: [
          {
            id: `test-${body.offset}`,
            canonical_name: `分页合成记录 ${body.offset}`,
            aliases: [],
            definition: "虚构的浏览器测试记录",
            evidence: [],
            published_revision: 1,
            origin_status: "unknown",
          },
        ],
        total: 2,
        channels: ["catalog"],
        degraded: [],
        scores_calibrated: false,
        query: body.query,
      },
    });
  });
  await page.goto("/");
  await expect(page.getByRole("button", { name: "加载更多" })).toBeEnabled();
  await page.getByRole("textbox", { name: "搜索记忆" }).fill("未提交的查询");
  await page.getByRole("button", { name: "加载更多" }).click();
  await expect(page.locator(".meme-row")).toHaveCount(2);
  // Development Strict Mode may repeat the initial catalogue effect.
  expect(
    requests.slice(-2).map(({ query, offset }) => ({ query, offset })),
  ).toEqual([
    { query: "", offset: 0 },
    { query: "", offset: 1 },
  ]);
  await page.getByRole("button", { name: "搜索记忆", exact: true }).click();
  await expect(page.locator(".meme-row")).toHaveCount(1);
  await page.getByRole("button", { name: "抖音", exact: true }).click();
  await expect(
    page.getByRole("alert").filter({ hasText: "合成筛选失败" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "加载更多" }).click();
  await expect(page.locator(".meme-row")).toHaveCount(2);
  expect(
    requests
      .filter(({ platform }) => platform !== "douyin")
      .slice(-2)
      .map(({ query, offset }) => ({ query, offset })),
  ).toEqual([
    { query: "未提交的查询", offset: 0 },
    { query: "未提交的查询", offset: 1 },
  ]);
  expect(requests.at(-1)?.platform).toBeNull();
});
