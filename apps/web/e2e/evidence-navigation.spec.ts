import { expect, test, type Page } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const memeId = "synthetic-evidence-navigation";
const ids = ["synthetic-definition", "synthetic-usage", "synthetic-counter"];
const definition = "合成证据导航梗仅用于软件验收，不代表真实互联网文化。";

function record() {
  const sources = ["xiaohongshu", "bilibili", "web"].map((platform, i) => ({
    id: `source-${i}`,
    platform,
    platform_item_id: `synthetic-${i}`,
    canonical_url: `https://example.org/synthetic/${i}`,
    title: `合成测试来源 ${i + 1}`,
    platform_published_at: "2026-10-08T16:00:00Z",
    created_at: "2026-10-09T08:00:00Z",
    availability: "material_available",
    source_tier: null,
    metadata_note: null,
  }));
  return {
    id: memeId,
    canonical_name: "合成证据导航梗",
    aliases: ["合成测试别名"],
    definition,
    usage_context: "只用于核对定位与引用跳转。",
    origin_status: "disputed",
    published_revision: 7,
    evidence: ids.map((id, i) => ({
      id,
      source_id: sources[i].id,
      source: sources[i],
      kind: ["manual", "subtitle", "ocr"][i],
      text: [
        definition,
        "合成字幕用法摘录。定位与时间都只用于测试。",
        "合成反对材料，不能用来确认起源。 ",
      ][i],
      locator: { note: "合成测试定位，不可用于文化归因", start_ms: i * 1000 },
      verified: true,
      retracted: false,
      content_hash: "a".repeat(64),
      artifact_hash: "b".repeat(64),
      created_at: "2026-10-09T08:01:00Z",
    })),
    claims: [
      {
        key: "definition",
        statement: definition,
        stance: "supports",
        evidence_ids: [ids[0]],
      },
      {
        key: "usage_context",
        statement: "只用于核对定位与引用跳转。",
        stance: "supports",
        evidence_ids: [ids[1]],
      },
      {
        key: "origin",
        statement: "这是模拟的起源说法，未形成已确认结论。",
        stance: "contradicts",
        evidence_ids: [ids[2]],
      },
    ],
    events: [
      {
        id: "synthetic-event",
        event_type: "observed_use",
        description: "仅用于测试的合成传播事件。",
        occurred_at_start: "2026-10-08T16:00:00Z",
        occurred_at_end: null,
        time_precision: "day",
        time_basis: "合成时间依据，不是历史材料",
        to_source_id: sources[1].id,
        target: {
          type: "source",
          id: sources[1].id,
          label: sources[1].title,
          url: sources[1].canonical_url,
        },
        evidence_ids: [ids[1]],
      },
    ],
    relations: [
      {
        id: "synthetic-relation",
        predicate: "documented_in",
        assertion_status: "supported",
        to_source_id: sources[0].id,
        to_meme_id: null,
        to_entity_id: null,
        target: {
          type: "source",
          id: sources[0].id,
          label: sources[0].title,
          url: sources[0].canonical_url,
        },
        evidence_ids: [ids[0]],
      },
    ],
  };
}

async function mock(page: Page, data = record(), delay = false) {
  await page.route("**/api/v1/universe", (route) =>
    route.fulfill({ status: 503 }),
  );
  await page.route(`**/api/v1/memes/${memeId}`, async (route) => {
    if (delay) await new Promise((resolve) => setTimeout(resolve, 120));
    await route.fulfill({ json: data });
  });
}

async function capture(page: Page, filename: string) {
  const directory = process.env.CYBER_MEMOIR_REFERENCE_QA;
  if (!directory) return;
  await mkdir(directory, { recursive: true });
  await page.evaluate(() => document.fonts.ready);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: path.join(directory, filename),
    fullPage: true,
  });
}

test("定义、语境、事件与关联有编号引用，并可从证据返回对应断言", async ({
  page,
}) => {
  await mock(page);
  if (process.env.CYBER_MEMOIR_BASELINE_URL) {
    await page.goto(`${process.env.CYBER_MEMOIR_BASELINE_URL}/memes/${memeId}`);
    await expect(
      page.getByRole("heading", { name: "合成证据导航梗", exact: true }),
    ).toBeVisible();
    await capture(page, "detail-reference-desktop.png");
  }
  await page.goto(`/memes/${memeId}`);
  await expect(
    page.getByRole("heading", { name: "合成证据导航梗", exact: true }),
  ).toBeVisible();
  await capture(page, "detail-citations-desktop.png");
  await page.setViewportSize({ width: 390, height: 844 });
  await capture(page, "detail-citations-mobile.png");
  await page.setViewportSize({ width: 1505, height: 1045 });
  const usage = page.locator("#claim-usage_context");
  await usage.getByRole("link", { name: /查看证据 2/ }).click();
  const evidence = page.locator(`#evidence-${ids[1]}`);
  await expect(evidence).toHaveAttribute("aria-current", "true");
  await expect(evidence).toBeFocused();
  await evidence.getByRole("link", { name: "返回使用语境" }).click();
  await expect(usage).toBeFocused();
  await page
    .locator("#event-synthetic-event")
    .getByRole("link", { name: /查看证据 2/ })
    .click();
  await expect(evidence).toBeFocused();
  await expect(page.locator("#event-synthetic-event time")).toHaveText(
    "2026年10月9日",
  );
  await page
    .locator("#relation-synthetic-relation")
    .getByRole("link", { name: /查看证据 1/ })
    .click();
  await expect(page.locator(`#evidence-${ids[0]}`)).toBeFocused();
  await expect(page.locator("#origin")).toContainText("不能作为已确认起源");
});

test("从引用打开被筛掉的证据会清除筛选，浏览器返回/前进保留定位", async ({
  page,
}) => {
  await mock(page);
  await page.goto(`/memes/${memeId}#claim-usage_context`);
  await page.getByLabel("证据平台").selectOption("web");
  await page.getByRole("searchbox", { name: "在证据中查找" }).fill("反对");
  await expect(page.locator(".evidence-inspector .evidence-box")).toHaveCount(
    1,
  );
  await page
    .locator("#claim-definition")
    .getByRole("link", { name: /查看证据 1/ })
    .click();
  await expect(page.locator(`#evidence-${ids[0]}`)).toBeFocused();
  await expect(page.getByLabel("证据平台")).toHaveValue("");
  await expect(
    page.getByRole("searchbox", { name: "在证据中查找" }),
  ).toHaveValue("");
  await expect(page.locator(".evidence-inspector .evidence-box")).toHaveCount(
    3,
  );
  await page.goBack();
  await expect(page.locator("#claim-usage_context")).toBeFocused();
  await page.goForward();
  await expect(page.locator(`#evidence-${ids[0]}`)).toBeFocused();
});

test("异步加载的引用直达证据，旧版本与缺失引用有明确提示", async ({ page }) => {
  await mock(page, record(), true);
  await page.goto(`/memes/${memeId}?expected_revision=6#evidence-${ids[2]}`);
  await expect(page.locator(`#evidence-${ids[2]}`)).toBeFocused();
  await expect(page.locator(".reference-status")).toContainText(
    "链接记录的是修订 6",
  );
  await expect(page.locator(".reference-status")).toContainText(
    "当前公开修订为 7",
  );
  await page.goto(`/memes/${memeId}#evidence-not-public`);
  await expect(page.locator(".reference-status")).toContainText(
    "当前公开修订不包含这条证据",
  );
  await expect(page.locator(".evidence-inspector .evidence-box")).toHaveCount(
    3,
  );
});

test("复制引用包含条目、当前修订与证据 ID，复制失败不伪报成功", async ({
  page,
  context,
}) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await mock(page);
  await page.goto(`/memes/${memeId}`);
  const evidence = page.locator(`#evidence-${ids[0]}`);
  await evidence.getByRole("button", { name: "复制引用链接" }).click();
  await expect(evidence.getByRole("status")).toHaveText("引用链接已复制。");
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(
    `http://127.0.0.1:3101/memes/${memeId}?expected_revision=7#evidence-${ids[0]}`,
  );
  await page.evaluate(() => {
    Object.defineProperty(navigator.clipboard, "writeText", {
      value: () => Promise.reject(new Error("synthetic denial")),
    });
  });
  await evidence.getByRole("button", { name: "复制引用链接" }).click();
  await expect(evidence.getByRole("status")).toContainText("复制失败");
});

test("未知起源不变成确认结论；空筛选、手机与桌面可用", async ({ page }) => {
  const data = record();
  data.origin_status = "unknown";
  await mock(page, data);
  await page.goto(`/memes/${memeId}`);
  await expect(page.locator("#origin")).toContainText("尚未确认");
  await page
    .getByRole("searchbox", { name: "在证据中查找" })
    .fill("不存在的合成文字");
  await expect(page.locator(".evidence-filter-status")).toContainText("0 / 3");
  await page.getByRole("button", { name: "清除证据筛选" }).click();
  await expect(page.locator(".evidence-inspector .evidence-box")).toHaveCount(
    3,
  );
  for (const width of [320, 390, 1505]) {
    await page.setViewportSize({ width, height: 1045 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await expect(
      page.getByRole("navigation", { name: "档案阅读导航" }),
    ).toBeVisible();
  }
});

test("回答引用能定位到断言所属条目与版本，不使用共享引用的其他版本", async ({
  page,
}) => {
  await mock(page);
  await page.route("**/api/v1/search", (route) =>
    route.fulfill({
      json: {
        items: [],
        total: 0,
        channels: [],
        degraded: [],
        query: "合成问题",
      },
    }),
  );
  await page.route("**/api/v1/answers", (route) =>
    route.fulfill({
      json: {
        answer: definition,
        mode: "extractive",
        retrieval_version: "v1-evidence-locked",
        channels: [],
        degraded: [],
        uncertainties: [],
        claims: [
          {
            ...record().claims[0],
            meme_id: memeId,
            meme_name: "合成证据导航梗",
            meme_revision: 7,
            origin_status: "unknown",
          },
        ],
        citations: [
          {
            evidence_id: ids[0],
            source_id: "source-0",
            url: "https://example.org/synthetic/0",
            text: definition,
            locator: {},
            content_hash: "a".repeat(64),
            meme_revision: 99,
            published_at: null,
          },
        ],
      },
    }),
  );
  await page.goto("/");
  await page.getByRole("textbox", { name: "搜索记忆" }).fill("合成问题");
  await page.getByLabel("基于证据回答").check();
  await page.getByRole("button", { name: "搜索记忆", exact: true }).click();
  await page.getByRole("link", { name: "查看合成证据导航梗的引用" }).click();
  await expect(page).toHaveURL(
    new RegExp(`expected_revision=7#evidence-${ids[0]}`),
  );
  await expect(page.locator(`#evidence-${ids[0]}`)).toBeFocused();
});

test("客户端跳转到不可用条目时不会保留上一档案和证据", async ({ page }) => {
  const data = record();
  const relation = data.relations[0];
  // The target was public in the loaded snapshot, but is unavailable at navigation time.
  const target = {
    ...relation,
    to_source_id: null,
    to_meme_id: "synthetic-withdrawn",
    target: {
      type: "meme",
      id: "synthetic-withdrawn",
      label: "合成不可用目标",
      url: null,
    },
  };
  await mock(page, { ...data, relations: [target] } as unknown as ReturnType<
    typeof record
  >);
  await page.route("**/api/v1/memes/synthetic-withdrawn", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 120));
    await route.fulfill({
      status: 404,
      json: { detail: "未公开的条目或其证据已失效" },
    });
  });
  await page.goto(`/memes/${memeId}`);
  await page.getByRole("link", { name: "合成不可用目标" }).click();
  await expect(
    page.getByRole("alert").filter({ hasText: "证据已失效" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "合成证据导航梗", exact: true }),
  ).toHaveCount(0);
  await expect(page.locator(".evidence-box")).toHaveCount(0);
});

test("事件日期按年/月精度显示，不把边界日期当作精确日", async ({ page }) => {
  const data = record();
  data.events[0].time_precision = "year";
  await mock(page, data);
  await page.goto(`/memes/${memeId}`);
  await expect(page.locator("#event-synthetic-event time")).toHaveText(
    "2026年",
  );
  data.events[0].time_precision = "month";
  await page.reload();
  await expect(page.locator("#event-synthetic-event time")).toHaveText(
    "2026年10月",
  );
});

test("支持状态与反对材料不一致时不显示已确认起源", async ({ page }) => {
  const data = record();
  data.origin_status = "supported";
  await mock(page, data);
  await page.goto(`/memes/${memeId}`);
  await expect(page.locator(".detail-header")).toContainText(
    "起源支持材料待核查",
  );
  await expect(page.locator("#origin")).toContainText("不能在本页确认");
  await expect(page.locator(".detail-header")).not.toContainText(
    "有证据支持的来源主张",
  );
});
