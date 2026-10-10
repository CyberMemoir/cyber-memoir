import { createHash } from "node:crypto";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { expect, test } from "@playwright/test";

const name = "合成跨平台导入验收梗";
const definition = "仅用于浏览器验收的合成定义，不代表真实互联网文化。";
const auth = { Authorization: "Bearer e2e-reviewer-only" };

function files() {
  const entries =
    JSON.stringify({
      canonical_name: name,
      operation: "create_new",
      definition,
      usage_context: "",
      aliases: [],
      origin_status: "unknown",
      event_type: "observed_use",
      sources: [
        {
          platform: "xiaohongshu",
          url: "https://www.xiaohongshu.com/explore/0123456789abcdef01234567",
          text_parts: [definition],
        },
        {
          platform: "web",
          url: "https://example.org/memoir-test?id=1",
          text_parts: ["第二份合成用法摘录，仅用于验收多来源显示。"],
        },
      ],
    }) + "\n";
  const manifest = {
    schema_version: 1,
    groups: 1,
    new_groups: 1,
    existing_groups: 0,
    meme_source_associations: 2,
    entries_sha256: createHash("sha256").update(entries).digest("hex"),
    automatic_import: false,
  };
  return { entries, manifest };
}

async function screenshot(
  page: import("@playwright/test").Page,
  filename: string,
) {
  const directory = process.env.CYBER_MEMOIR_QA_DIR;
  if (!directory) return;
  await mkdir(directory, { recursive: true });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({
    path: path.join(directory, filename),
    fullPage: true,
  });
}

test("跨平台文件预演 → 待审 → 人工核对 → 平台检索，不自动发布", async ({
  page,
}) => {
  const { entries, manifest } = files();
  await page.goto("/review");
  await page.getByLabel("审核者令牌").fill("e2e-reviewer-only");
  await page.getByRole("button", { name: "连接工作台" }).click();
  await expect(
    page.getByText("导入已采集的数据", { exact: true }),
  ).toBeVisible();
  await screenshot(page, "review-reference.png");
  await page.getByText("导入已采集的数据", { exact: true }).click();
  const confirm = page.getByRole("button", { name: "确认生成待审稿" });
  await expect(confirm).toHaveCount(0);
  await page.getByLabel("交付清单 manifest.json").setInputFiles({
    name: "manifest.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(manifest)),
  });
  await page.getByLabel("条目文件 entries.jsonl").setInputFiles({
    name: "entries.jsonl",
    mimeType: "text/plain",
    buffer: Buffer.from(entries),
  });
  await page.getByRole("button", { name: "校验并预演" }).click();
  await expect(
    page.getByRole("region", { name: "导入预演结果" }),
  ).toContainText("2 个独立来源 / 2 个来源关联");
  await screenshot(page, "import-preview-desktop.png");
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await screenshot(page, "import-preview-mobile.png");
  await page.setViewportSize({ width: 1505, height: 1045 });
  const imported = page.waitForResponse(
    (response) =>
      response.url().includes("/v1/reviews/imports?") && response.ok(),
  );
  await confirm.click();
  const result = await (await imported).json();
  const item = result.items[0];
  await expect(page.getByRole("status")).toContainText("本次未发布任何条目");
  await page
    .locator(".review-list")
    .getByRole("button", { name: new RegExp(name) })
    .click();
  await expect(page.locator(".evidence-box")).toHaveCount(2);
  await expect(page.getByLabel("梗名称")).toHaveValue(name);
  const unpublished = await page.request.get(`/api/v1/memes/${item.meme_id}`);
  expect(unpublished.status()).toBe(404);
  await screenshot(page, "import-review-desktop.png");

  await page
    .locator(".evidence-box")
    .filter({ hasText: definition })
    .getByRole("checkbox")
    .check();
  await page
    .getByLabel("审核理由", { exact: true })
    .fill("已核对合成测试材料，非文化事实发布。 ");
  await page.getByLabel(/我已人工核对所有引用材料/).check();
  await page.getByRole("button", { name: "审核通过并发布" }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "审核决定已保存" }),
  ).toBeVisible();
  await page.goto("/");
  await page.getByRole("textbox", { name: "搜索记忆" }).fill(name);
  await page.getByRole("button", { name: "小红书", exact: true }).click();
  await expect(
    page.getByRole("heading", { name, level: 3, exact: true }),
  ).toBeVisible();
  await expect(
    page.locator(".row-meta").filter({ hasText: "份证据" }),
  ).toContainText("小红书 / 网页");
  await page.getByRole("button", { name: "网页", exact: true }).click();
  await expect(
    page.getByRole("heading", { name, level: 3, exact: true }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  const appendEntries =
    JSON.stringify({
      canonical_name: name,
      operation: "append_derivatives",
      origin_verified: false,
      preserve_existing_fields: [
        "definition",
        "usage_context",
        "aliases",
        "origin_status",
      ],
      sources: [
        {
          platform: "web",
          url: "https://example.org/memoir-test?id=2",
          text_parts: ["第三份合成用法，非文化事实。"],
        },
      ],
    }) + "\n";
  const append = await page.request.post("/api/v1/reviews/imports", {
    headers: auth,
    data: {
      manifest: {
        ...manifest,
        new_groups: 0,
        existing_groups: 1,
        meme_source_associations: 1,
        entries_sha256: createHash("sha256")
          .update(appendEntries)
          .digest("hex"),
      },
      entries_jsonl: appendEntries,
    },
  });
  expect(append.ok()).toBe(true);
  await page.setViewportSize({ width: 1505, height: 1045 });
  await page.goto("/review");
  await page.getByLabel("审核者令牌").fill("e2e-reviewer-only");
  await page.getByRole("button", { name: "连接工作台" }).click();
  await page
    .locator(".review-list")
    .getByRole("button", { name: new RegExp(name) })
    .click();
  await expect(page.getByLabel("梗名称")).toBeDisabled();
  await expect(page.getByLabel(/定义 · 必须/)).toBeDisabled();
  await expect(page.locator(".evidence-box")).toHaveCount(3);
  await page
    .getByLabel("审核理由", { exact: true })
    .fill("仅追加已核对的合成用法材料。 ");
  await page.getByLabel(/我已人工核对所有引用材料/).check();
  await page.getByRole("button", { name: "审核通过并发布" }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "审核决定已保存" }),
  ).toBeVisible();
  const after = await page.request.get(`/api/v1/memes/${item.meme_id}`);
  const afterData = await after.json();
  expect(afterData.definition).toBe(definition);
  expect(afterData.events).toHaveLength(3);
  const cleanup = await page.request.post(
    `/api/v1/reviews/memes/${item.meme_id}/retract`,
    {
      headers: auth,
      data: { reason: "浏览器验收结束，撤回合成数据。" },
    },
  );
  expect(cleanup.ok()).toBe(true);
});

test("坏摘要拒绝导入且不能跳过预演", async ({ page }) => {
  const { entries, manifest } = files();
  await page.goto("/review");
  await page.getByLabel("审核者令牌").fill("e2e-reviewer-only");
  await page.getByRole("button", { name: "连接工作台" }).click();
  await page.getByText("导入已采集的数据", { exact: true }).click();
  await page.getByLabel("交付清单 manifest.json").setInputFiles({
    name: "manifest.json",
    mimeType: "application/json",
    buffer: Buffer.from(
      JSON.stringify({ ...manifest, entries_sha256: "0".repeat(64) }),
    ),
  });
  await page.getByLabel("条目文件 entries.jsonl").setInputFiles({
    name: "entries.jsonl",
    mimeType: "text/plain",
    buffer: Buffer.from(entries),
  });
  await page.getByRole("button", { name: "校验并预演" }).click();
  await expect(
    page.locator(".import-workbench").getByRole("alert"),
  ).toContainText("SHA-256");
  await expect(
    page.getByRole("button", { name: "确认生成待审稿" }),
  ).toHaveCount(0);
});
