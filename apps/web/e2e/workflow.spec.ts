import { expect, test } from "@playwright/test";

test("人工提交 → 材料 → 审核 → 搜索/回答 → 详情 → 撤回", async ({ page }) => {
  const definition =
    "合成验收梗是浏览器自动化测试使用的虚构表述，不代表真实文化事实。";
  await page.goto("/submit");
  await page
    .getByLabel(/Bilibili \/ 抖音视频链接/)
    .fill("https://www.bilibili.com/video/BV1TEST00001");
  await page.getByRole("button", { name: "登记原始来源" }).click();
  await expect(
    page.getByRole("heading", { name: /补充可核查材料/ }),
  ).toBeVisible();
  await page.getByLabel("原文摘录").fill(definition);
  await page
    .getByLabel("定位与核查说明")
    .fill("合成测试材料第 1 段，不可引用为真实史料");
  await page.getByRole("button", { name: "保存证据材料" }).click();
  await expect(page.getByRole("status")).toContainText("材料已保存");
  await page.getByRole("link", { name: "审核工作台", exact: true }).click();
  await page.getByLabel("审核者令牌").fill("e2e-reviewer-only");
  await page.getByRole("button", { name: "连接工作台" }).click();
  await expect(page.getByLabel("梗名称")).toBeVisible();
  await page.getByLabel("梗名称").fill("合成验收梗");
  await page.getByLabel(/定义 · 必须/).fill(definition);
  await page
    .locator(".evidence-box")
    .filter({ hasText: definition })
    .getByRole("checkbox")
    .check();
  await page
    .getByLabel("审核理由", { exact: true })
    .fill("已核对合成测试文本和定位，只用于验证软件闭环。");
  await page.getByLabel(/我已人工核对所有引用材料/).check();
  const published = page.waitForResponse(
    (r) => r.url().endsWith("/decision") && r.status() === 200,
  );
  await page.getByRole("button", { name: "审核通过并发布" }).click();
  const memeId = (await (await published).json()).meme_id;
  await expect(page.getByRole("status")).toContainText("审核决定已保存");
  await page.getByRole("link", { name: "记忆索引", exact: true }).click();
  await page.getByRole("textbox", { name: "搜索记忆" }).fill("合成验收梗");
  await page.getByLabel("基于证据回答").check();
  await page.getByRole("button", { name: "搜索记忆", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "基于证据的回答" }),
  ).toBeVisible();
  await expect(page.locator(".answer-text")).toContainText(definition);
  await page.getByRole("heading", { name: "合成验收梗", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "回到证据本身" }),
  ).toBeVisible();
  await expect(page.locator("blockquote")).toContainText(definition);
  await page.getByRole("link", { name: "审核工作台", exact: true }).click();
  await page.getByLabel("审核者令牌").fill("e2e-reviewer-only");
  await page.getByRole("button", { name: "连接工作台" }).click();
  await page.getByLabel("Meme ID", { exact: true }).fill(memeId);
  await page.getByLabel(/操作理由/).fill("自动化验收结束，撤回合成测试记录。");
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "撤回条目", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("条目已撤回");
  await page.getByRole("link", { name: "记忆索引", exact: true }).click();
  await page.getByRole("textbox", { name: "搜索记忆" }).fill("合成验收梗");
  await page.getByRole("button", { name: "搜索记忆", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "这段记忆，还缺少证据" }),
  ).toBeVisible();
});

test("手机空态、导航、表单无水平溢出", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "第一条记忆，从一个链接开始" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.getByRole("link", { name: /提交第一个来源/ }).click();
  await expect(
    page.getByRole("heading", { name: "让一段记忆，有据可查。" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("错误令牌不能进入审核工作台", async ({ page }) => {
  await page.goto("/review");
  await page.getByLabel("审核者令牌").fill("wrong-token");
  await page.getByRole("button", { name: "连接工作台" }).click();
  await expect(page.locator(".error[role=alert]")).toContainText(
    "需要审核者令牌",
  );
  await expect(
    page.getByRole("heading", { name: "版本与索引管理" }),
  ).toHaveCount(0);
});
