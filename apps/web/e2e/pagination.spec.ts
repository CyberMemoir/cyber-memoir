import { expect, test } from "@playwright/test";

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
