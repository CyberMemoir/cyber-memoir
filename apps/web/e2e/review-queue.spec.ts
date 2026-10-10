import { expect, test } from "@playwright/test";

function revision(id: string, name: string) {
  return {
    id,
    meme_id: `meme-${id}`,
    status: "pending_review",
    based_on_revision: 0,
    created_at: "2026-10-09T12:00:00Z",
    payload: {
      canonical_name: name,
      aliases: [],
      definition: "合成队列夹具，非文化事实。",
      usage_context: "",
      origin_status: "unknown",
      claims: [],
      events: [],
      relations: [],
    },
  };
}

test("材料任务尚未结束时自动更新审核队列，保留编辑并在令牌变化后停止", async ({
  page,
}) => {
  await page.clock.install();
  let calls = 0;
  await page.route("**/api/v1/reviews/queue", (route) => {
    ++calls;
    return route.fulfill({
      json: {
        items:
          calls === 1
            ? []
            : calls === 2
              ? [revision("synthetic-one", "合成新候选")]
              : [
                  revision("synthetic-one", "服务端原标题"),
                  revision("synthetic-two", "第二份合成候选"),
                ],
        pending_jobs: calls < 3 ? 1 : 0,
        running_jobs: 0,
        failed_jobs: 0,
        checked_at: "2026-10-09T12:00:00Z",
      },
    });
  });
  await page.goto("/review");
  await page.getByLabel("审核者令牌").fill("synthetic-test-token");
  await page.getByRole("button", { name: "连接工作台" }).click();
  await expect(
    page.getByRole("heading", { name: "材料任务尚未结束" }),
  ).toBeVisible();
  await expect(page.locator(".queue-processing")).toContainText("1 个待处理");
  await page.clock.fastForward(2100);
  await expect(page.getByLabel("梗名称")).toHaveValue("合成新候选");
  await page.getByLabel("梗名称").fill("正在编辑的合成名字");
  await page.clock.fastForward(2100);
  await expect(
    page
      .locator(".review-list")
      .getByRole("button", { name: /第二份合成候选/ }),
  ).toBeVisible();
  await expect(page.getByLabel("梗名称")).toHaveValue("正在编辑的合成名字");
  expect(calls).toBe(3);
  await page.getByLabel("审核者令牌").fill("changed-token");
  await expect(page.locator(".review-columns")).toHaveCount(0);
  await page.clock.fastForward(31000);
  expect(calls).toBe(3);
});
