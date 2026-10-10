// Real browser smoke test. It mutates only an explicitly marked synthetic demo.
import { createRequire } from "node:module";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const require = createRequire(path.join(root, "apps/web/package.json"));
const { chromium, expect: baseExpect } = require("@playwright/test");
const expect = baseExpect.configure({ timeout: 15000 });
const url = new URL(
  process.env.CYBER_MEMOIR_DEMO_URL || "http://127.0.0.1:3102",
);
if (
  url.protocol !== "http:" ||
  !["127.0.0.1", "localhost"].includes(url.hostname) ||
  url.username ||
  url.password
)
  throw new Error("Use the loopback-only local demo URL");

const browser = await chromium.launch();
try {
  const context = await browser.newContext({
    baseURL: url.origin,
    viewport: { width: 1440, height: 1040 },
    reducedMotion: "reduce",
    permissions: ["clipboard-read", "clipboard-write"],
  });
  const marker = await context.request.get("/api/health/ready");
  if (marker.headers()["x-cyber-memoir-demo"] !== "synthetic-only")
    throw new Error(
      "Refusing to mutate an unmarked backend; run make demo first",
    );
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));

  async function capture(name) {
    const directory = process.env.CYBER_MEMOIR_QA_DIR;
    if (!directory) return;
    await mkdir(directory, { recursive: true });
    await page.evaluate(() => document.fonts.ready);
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: path.join(directory, name), fullPage: true });
  }
  async function noOverflow() {
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  }

  await page.goto("/");
  await expect(page.getByLabel("本地合成演示说明")).toBeVisible();
  await capture("demo-home-desktop.png");
  await page.setViewportSize({ width: 390, height: 844 });
  await noOverflow();
  await capture("demo-home-mobile.png");
  await page.setViewportSize({ width: 1440, height: 1040 });
  await page.getByRole("textbox", { name: "搜索记忆" }).fill("合成星灯");
  await page.getByLabel("基于证据回答").check();
  await page.getByRole("button", { name: "搜索记忆", exact: true }).click();
  await expect(page.locator(".answer-text")).toContainText("虚构表达");
  await page
    .getByRole("heading", { name: "合成演示：星灯亮起", level: 3 })
    .click();
  await expect(
    page.getByRole("heading", {
      name: "合成演示：星灯亮起",
      level: 1,
      exact: true,
    }),
  ).toBeVisible();
  await capture("demo-detail-desktop.png");
  const definition = page.locator("#claim-definition");
  await definition.getByRole("link", { name: /查看证据 1/ }).click();
  const evidence = page.locator('.evidence-box[aria-current="true"]');
  await expect(evidence).toBeFocused();
  await evidence.getByRole("button", { name: "复制引用链接" }).click();
  await expect(evidence.getByRole("status")).toHaveText("引用链接已复制。");
  const shared = await page.evaluate(() => navigator.clipboard.readText());
  expect(shared).toContain("?expected_revision=1#evidence-");
  await page.goto(shared);
  await expect(
    page.locator('.evidence-box[aria-current="true"]'),
  ).toBeFocused();
  await page.getByRole("link", { name: "返回含义", exact: true }).click();
  await expect(definition).toBeFocused();
  await page.setViewportSize({ width: 390, height: 844 });
  await noOverflow();
  await capture("demo-detail-mobile.png");

  await page.goto("/review");
  await page.getByLabel("审核者令牌").fill("local-synthetic-demo-only");
  await page.getByRole("button", { name: "连接工作台" }).click();
  await expect(page.getByLabel("梗名称")).toHaveValue("合成演示：等待审核");
  await noOverflow();
  await capture("demo-review-mobile.png");
  await page.setViewportSize({ width: 1440, height: 1040 });
  await capture("demo-review-desktop.png");
  await page
    .getByLabel("审核理由", { exact: true })
    .fill("本地合成演示软件验收，不代表真实文化核验。");
  await page.getByLabel(/我已人工核对所有引用材料/).check();
  const decision = page.waitForResponse(
    (r) => r.url().endsWith("/decision") && r.status() === 200,
  );
  await page.getByRole("button", { name: "审核通过并发布" }).click();
  const memeId = (await (await decision).json()).meme_id;
  await expect(page.getByRole("status")).toContainText("审核决定已保存");
  expect((await context.request.get(`/api/v1/memes/${memeId}`)).status()).toBe(
    200,
  );
  await page.getByLabel("Meme ID", { exact: true }).fill(memeId);
  await page
    .getByLabel(/操作理由/)
    .fill("本地合成演示软件验收结束，撤回夹具。");
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "撤回条目", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("条目已撤回");
  expect((await context.request.get(`/api/v1/memes/${memeId}`)).status()).toBe(
    404,
  );

  await page.goto("/submit");
  await page
    .getByLabel(/Bilibili \/ 抖音视频链接/)
    .fill("https://www.bilibili.com/video/BV1DEMO00002");
  await page.getByRole("button", { name: "登记原始来源" }).click();
  await expect(
    page.getByRole("heading", { name: /补充可核查材料/ }),
  ).toBeVisible();
  await page
    .getByLabel("原文摘录")
    .fill("本地合成演示补充文本，非真实文化事实。");
  await page.getByLabel("定位与核查说明").fill("合成软件夹具第一段。");
  await page.getByRole("button", { name: "保存证据材料" }).click();
  await expect(page.getByRole("status")).toContainText("材料已保存");
  await page.goto("/review");
  await page.getByLabel("审核者令牌").fill("local-synthetic-demo-only");
  await page.getByRole("button", { name: "连接工作台" }).click();
  await expect(page.getByLabel("梗名称")).toHaveValue("合成演示：新提交的材料");
  expect(errors).toEqual([]);
  console.log(
    "PASS: real search/answer, citation/share/backlink, review/retract, submit/material/worker, desktop/mobile; no page errors",
  );
} finally {
  await browser.close();
}
