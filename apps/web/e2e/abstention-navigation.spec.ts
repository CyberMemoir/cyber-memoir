import { expect, test } from "@playwright/test";
import { memoryUrl } from "../lib/citations";

const meme = {
  id: "synthetic-candidate",
  canonical_name: "合成浏览候选",
  aliases: [],
  definition: "仅用于测试，不是文化证据。",
  usage_context: "",
  origin_status: "unknown",
  published_revision: 7,
  claims: [],
  evidence: [],
  events: [],
  relations: [],
};
const search = {
  items: [meme],
  total: 1,
  channels: [],
  degraded: [],
  scores_calibrated: true,
};
const abstained = {
  answer: "找到了候选记忆，但相关性评分不足，暂不将它们作为证据回答。",
  claims: [],
  citations: [],
  uncertainties: [],
  mode: "extractive",
  retrieval_version: "synthetic",
  channels: [],
  degraded: [],
  abstention_reason: "low_relevance",
  related_memories: [
    { id: meme.id, canonical_name: meme.canonical_name, published_revision: 7 },
  ],
};

test("navigation candidate is explicitly not a claim and opens the captured revision without a new query", async ({
  page,
}) => {
  let searches = 0,
    answers = 0;
  await page.route("**/api/v1/universe", (route) =>
    route.fulfill({ status: 503 }),
  );
  await page.route("**/api/v1/search", (route) => {
    searches++;
    return route.fulfill({ json: search });
  });
  await page.route("**/api/v1/answers", (route) => {
    answers++;
    return route.fulfill({ json: abstained });
  });
  await page.route("**/api/v1/memes/synthetic-candidate", (route) =>
    route.fulfill({ json: meme }),
  );
  await page.goto("/");
  await expect(page.locator(".meme-row")).toHaveCount(1);
  await page.getByRole("textbox", { name: "搜索记忆" }).fill("合成模糊描述");
  await page.getByRole("checkbox", { name: "基于证据回答" }).check();
  await page.getByRole("button", { name: "搜索记忆", exact: true }).click();
  await expect(
    page.getByText("候选记忆仅供浏览，不是本次提问的证据回答："),
  ).toBeVisible();
  const candidate = page
    .getByRole("navigation", { name: "仅供浏览的候选记忆" })
    .getByRole("link");
  await expect(candidate).toHaveAttribute(
    "href",
    "/memes/synthetic-candidate?expected_revision=7",
  );
  const before = searches;
  await candidate.click();
  await expect(page).toHaveURL(
    /\/memes\/synthetic-candidate\?expected_revision=7$/,
  );
  await expect(
    page.getByRole("heading", { name: "合成浏览候选", exact: true }),
  ).toBeVisible();
  expect(searches).toBe(before);
  expect(answers).toBe(1);
});

test("legacy abstention has no invented navigation and long current names do not overflow mobile", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.route("**/api/v1/universe", (route) =>
    route.fulfill({ status: 503 }),
  );
  await page.route("**/api/v1/search", (route) =>
    route.fulfill({ json: search }),
  );
  let current = false;
  await page.route("**/api/v1/answers", (route) =>
    route.fulfill({
      json: current
        ? {
            ...abstained,
            related_memories: [
              {
                ...abstained.related_memories[0],
                canonical_name: "合成" + "x".repeat(180),
              },
            ],
          }
        : {
            answer: "合成旧接口弃答",
            claims: [],
            citations: [],
            uncertainties: [],
            mode: "extractive",
            retrieval_version: "synthetic",
            channels: [],
            degraded: [],
          },
    }),
  );
  await page.goto("/");
  await expect(page.locator(".meme-row")).toHaveCount(1);
  await page.getByRole("textbox", { name: "搜索记忆" }).fill("合成模糊查询");
  await page.getByRole("checkbox", { name: "基于证据回答" }).check();
  await page.getByRole("button", { name: "搜索记忆", exact: true }).click();
  await expect(page.locator(".answer-text")).toHaveText("合成旧接口弃答");
  await expect(
    page.getByRole("navigation", { name: "仅供浏览的候选记忆" }),
  ).toHaveCount(0);
  current = true;
  await page.getByRole("button", { name: "搜索记忆", exact: true }).click();
  await expect(
    page.getByRole("navigation", { name: "仅供浏览的候选记忆" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("navigation URLs are revision-bound and have no fabricated evidence anchor", () => {
  expect(memoryUrl("a/b ?#", 7)).toBe(
    "/memes/a%2Fb%20%3F%23?expected_revision=7",
  );
  expect(memoryUrl("synthetic", undefined)).toBe("/memes/synthetic");
});

test("actual empty API answer explains current public retrieval without invented candidates", async ({
  page,
}) => {
  await page.setExtraHTTPHeaders({
    "X-Memoir-E2E-Client": "abstention-native",
  });
  await page.goto("/");
  await expect(
    page.getByRole("button", { name: "搜索记忆", exact: true }),
  ).toBeEnabled();
  await page
    .getByRole("textbox", { name: "搜索记忆" })
    .fill(`合成未匹配查询-${Date.now()}`);
  await page.getByRole("checkbox", { name: "基于证据回答" }).check();
  const responsePromise = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/answers") && response.status() === 200,
  );
  await page.getByRole("button", { name: "搜索记忆", exact: true }).click();
  const body = await (await responsePromise).json();
  expect(body.abstention_reason).toBe("no_public_matches");
  expect(body.related_memories).toEqual([]);
  expect(body.claims).toEqual([]);
  await expect(page.locator(".answer-text")).toContainText("当前检索结果");
  await expect(
    page.getByRole("navigation", { name: "仅供浏览的候选记忆" }),
  ).toHaveCount(0);
});
