import { expect, test } from "@playwright/test";
import { retryDelay } from "../lib/api";

const results = {
  items: [
    {
      id: "synthetic-busy",
      canonical_name: "合成忙碌验收记忆",
      aliases: [],
      definition: "合成测试，不是文化证据。",
      evidence: [],
      published_revision: 1,
      origin_status: "unknown",
    },
  ],
  total: 1,
  channels: [],
  degraded: [],
  scores_calibrated: false,
};

test("busy search retains results, honors Retry-After and retries captured query without automatic requests", async ({
  page,
}) => {
  await page.clock.install();
  const bodies: Array<{ query: string }> = [];
  await page.route("**/api/v1/universe", (route) =>
    route.fulfill({ status: 503 }),
  );
  await page.route("**/api/v1/search", (route) => {
    const body = route.request().postDataJSON();
    if (body.query) bodies.push(body);
    return body.query && bodies.length === 1
      ? route.fulfill({
          status: 503,
          headers: { "Retry-After": "1" },
          json: {
            detail: "计算服务暂忙，请稍后重试。",
            code: "inference_busy",
            retry_after_seconds: 7,
          },
        })
      : route.fulfill({ json: results });
  });
  await page.goto("/");
  await expect(page.locator(".meme-row")).toHaveCount(1);
  await page.getByRole("textbox", { name: "搜索记忆" }).fill("原合成查询");
  await page.getByRole("button", { name: "搜索记忆", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "重试（1s）", exact: true }),
  ).toBeDisabled();
  await expect(page.locator(".meme-row")).toHaveCount(1);
  await page
    .getByRole("textbox", { name: "搜索记忆" })
    .fill("尚未提交的新输入");
  await page.clock.fastForward(1200);
  await expect(
    page.getByRole("button", { name: "重试", exact: true }),
  ).toBeEnabled();
  expect(bodies).toHaveLength(1);
  await page.getByRole("button", { name: "重试", exact: true }).click();
  await expect(
    page.getByRole("alert").filter({ hasText: "计算服务暂忙" }),
  ).toHaveCount(0);
  expect(bodies).toHaveLength(2);
  expect(bodies[1].query).toBe("原合成查询");
});

test("busy answer uses body fallback and retries only the captured answer", async ({
  page,
}) => {
  await page.clock.install();
  let searches = 0;
  const answers: Array<{ query: string }> = [];
  await page.route("**/api/v1/universe", (route) =>
    route.fulfill({ status: 503 }),
  );
  await page.route("**/api/v1/search", (route) => {
    searches++;
    return route.fulfill({ json: results });
  });
  await page.route("**/api/v1/answers", (route) => {
    answers.push(route.request().postDataJSON());
    return answers.length === 1
      ? route.fulfill({
          status: 503,
          json: {
            detail: "合成计算暂忙",
            code: "inference_busy",
            retry_after_seconds: 1,
          },
        })
      : route.fulfill({
          json: {
            answer: "合成重试结果",
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
  await page.getByRole("textbox", { name: "搜索记忆" }).fill("原回答查询");
  await page.getByRole("checkbox", { name: "基于证据回答" }).check();
  await page.getByRole("button", { name: "搜索记忆", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "重试回答（1s）", exact: true }),
  ).toBeDisabled();
  const count = searches;
  await page
    .getByRole("textbox", { name: "搜索记忆" })
    .fill("不应作为重试参数");
  await page.clock.fastForward(1200);
  expect(answers).toHaveLength(1);
  await page.getByRole("button", { name: "重试回答", exact: true }).click();
  await expect(page.locator(".answer-text")).toHaveText("合成重试结果");
  expect(searches).toBe(count);
  expect(answers[1].query).toBe("原回答查询");
});

test("new search replaces busy cooldown and does not replay old query", async ({
  page,
}) => {
  await page.clock.install();
  const bodies: Array<{ query: string }> = [];
  await page.route("**/api/v1/universe", (route) =>
    route.fulfill({ status: 503 }),
  );
  await page.route("**/api/v1/search", (route) => {
    const body = route.request().postDataJSON();
    if (body.query) bodies.push(body);
    return body.query === "合成旧查询"
      ? route.fulfill({
          status: 503,
          json: {
            detail: "合成繁忙",
            code: "inference_busy",
            retry_after_seconds: 5,
          },
        })
      : route.fulfill({ json: results });
  });
  await page.goto("/");
  await expect(page.locator(".meme-row")).toHaveCount(1);
  await page.getByRole("textbox", { name: "搜索记忆" }).fill("合成旧查询");
  await page.getByRole("button", { name: "搜索记忆", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "重试（5s）", exact: true }),
  ).toBeDisabled();
  await page.getByRole("textbox", { name: "搜索记忆" }).fill("合成新查询");
  await page.getByRole("button", { name: "搜索记忆", exact: true }).click();
  await expect(
    page.getByRole("alert").filter({ hasText: "合成繁忙" }),
  ).toHaveCount(0);
  await page.clock.fastForward(6000);
  expect(bodies).toHaveLength(2);
  expect(bodies[1].query).toBe("合成新查询");
});

test("Retry-After parsing is bounded and malformed hints cannot freeze retry forever", () => {
  const now = Date.parse("Sat, 10 Oct 2026 12:00:00 GMT");
  expect(retryDelay("3", 7, now)).toBe(3);
  expect(retryDelay("900000", 2, now)).toBe(60);
  expect(retryDelay("Sat, 10 Oct 2026 12:00:05 GMT", 7, now)).toBe(5);
  expect(retryDelay("Sat, 10 Oct 2026 11:59:00 GMT", 7, now)).toBe(0);
  expect(retryDelay("bad", 2, now)).toBe(2);
  expect(retryDelay(null, Number.POSITIVE_INFINITY, now)).toBeUndefined();
  expect(retryDelay(null, -5, now)).toBeUndefined();
});

test("actual API busy response and Retry-After survive the Next rewrite", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("button", { name: "搜索记忆", exact: true }),
  ).toBeEnabled();
  await page.setExtraHTTPHeaders({
    "X-Memoir-E2E-Client": "busy-proxy",
    "X-Memoir-E2E-Inference-Busy": "search",
  });
  await page
    .getByRole("textbox", { name: "搜索记忆" })
    .fill("合成接口忙碌验收");
  const responsePromise = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/search") && response.status() === 503,
  );
  await page.getByRole("button", { name: "搜索记忆", exact: true }).click();
  const response = await responsePromise;
  expect(response.headers()["retry-after"]).toBe("2");
  expect((await response.json()).code).toBe("inference_busy");
  await expect(
    page.getByRole("button", { name: "重试（2s）", exact: true }),
  ).toBeDisabled();
  await page.setExtraHTTPHeaders({ "X-Memoir-E2E-Client": "busy-proxy" });
  await expect(
    page.getByRole("button", { name: "重试", exact: true }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "重试", exact: true }).click();
  await expect(
    page.getByRole("alert").filter({ hasText: "合成接口计算暂忙" }),
  ).toHaveCount(0);
});
