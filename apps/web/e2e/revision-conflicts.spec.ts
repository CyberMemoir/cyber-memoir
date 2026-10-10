import { mkdir } from "node:fs/promises";
import path from "node:path";
import {
  expect,
  test,
  type APIRequestContext,
  type Page,
} from "@playwright/test";
import type { Draft, Revision } from "../lib/api";
import { revisionChanges } from "../lib/revision-diff";

test.use({ extraHTTPHeaders: { "X-Memoir-E2E-Client": "revision-conflicts" } });
const auth = { Authorization: "Bearer e2e-reviewer-only" };
const name = "合成修订对照稿";
const definition = "合成修订对照稿仅用于软件验收，不是真实文化事实。";
const peerDefinition = "另一位编辑者的合成新定义，仅用于软件验收。";

async function fixture(request: APIRequestContext) {
  const source = await request.post("/api/v1/reviews/sources", {
    headers: auth,
    data: {
      platform: "web",
      url: "https://example.org/revision-conflict-test",
      title: "合成修订测试材料",
    },
  });
  expect(source.ok()).toBeTruthy();
  const sid = (await source.json()).source.id;
  const material = await request.post(`/api/v1/sources/${sid}/materials`, {
    data: {
      text: `${definition}\n${peerDefinition}`,
      locator: { note: "软件测试夹具，非真实材料" },
    },
  });
  const eid = (await material.json()).id;
  const payload = {
    canonical_name: name,
    aliases: [],
    definition,
    usage_context: "",
    origin_status: "unknown",
    claims: [
      {
        key: "definition",
        statement: definition,
        stance: "supports",
        evidence_ids: [eid],
      },
    ],
    events: [],
    relations: [],
  };
  const created = await request.post("/api/v1/reviews/drafts", {
    headers: auth,
    data: payload,
  });
  expect(created.ok()).toBeTruthy();
  return { revision: (await created.json()) as Revision, sid, eid, payload };
}

async function openEditor(page: Page, id: string) {
  await page.goto("/review");
  await page.getByLabel("审核者令牌").fill("e2e-reviewer-only");
  await page.getByRole("button", { name: "连接工作台" }).click();
  await page.locator(".review-item").filter({ hasText: name }).click();
  await expect(page.locator("[data-revision-id]")).toHaveAttribute(
    "data-revision-id",
    id,
  );
}

async function capture(page: Page, filename: string) {
  const directory = process.env.CYBER_MEMOIR_REVISION_QA;
  if (!directory) return;
  await mkdir(directory, { recursive: true });
  await page.evaluate(() => document.fonts.ready);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.evaluate(
    () =>
      new Promise<void>((resolve) =>
        requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
      ),
  );
  await page.screenshot({
    path: path.join(directory, filename),
    fullPage: true,
  });
}

async function clean(
  request: APIRequestContext,
  sid: string,
  id: string,
  memeId?: string,
) {
  const queue = (await (
    await request.get("/api/v1/reviews", { headers: auth })
  ).json()) as Revision[];
  for (const row of queue.filter(
    (row) =>
      row.id === id || row.payload._source_id === sid || row.meme_id === memeId,
  )) {
    const rejected = await request.post(`/api/v1/reviews/${row.id}/decision`, {
      headers: { ...auth, "If-Match": row.etag },
      data: {
        decision: "reject",
        reason: "合成修订测试清理，不公开文化事实。",
      },
    });
    expect(rejected.ok()).toBeTruthy();
  }
}

test("内容对照忽略引用顺序，但不能忽略反对/支持立场变化", () => {
  const draft: Draft = {
    canonical_name: name,
    aliases: ["B", "A"],
    definition,
    usage_context: "",
    origin_status: "unknown",
    events: [],
    relations: [],
    claims: [
      {
        key: "definition",
        statement: definition,
        stance: "supports",
        evidence_ids: ["a", "b"],
      },
    ],
  };
  expect(
    revisionChanges(draft, {
      ...draft,
      aliases: ["A", "B"],
      claims: [{ ...draft.claims[0], evidence_ids: ["b", "a"] }],
    }),
  ).toEqual([]);
  expect(
    revisionChanges(draft, {
      ...draft,
      claims: [{ ...draft.claims[0], stance: "contradicts" }],
    }).map(([field]) => field),
  ).toEqual(["claims"]);
  expect(
    revisionChanges(null, { ...draft, aliases: [], claims: [] }).map(
      ([field]) => field,
    ),
  ).toEqual(["canonical_name", "definition"]);
});

test("冲突保留本地文字，可对照/复制，再明确采用新基准保存", async ({
  page,
  request,
  context,
}) => {
  const { revision, sid } = await fixture(request);
  try {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    await openEditor(page, revision.id);
    await page.getByLabel("梗名称").fill("合成本地尚未提交的名称");
    const peer = await request.put(`/api/v1/reviews/${revision.id}`, {
      headers: { ...auth, "If-Match": revision.etag },
      data: {
        ...revision.payload,
        definition: peerDefinition,
        claims: [{ ...revision.payload.claims[0], statement: peerDefinition }],
      },
    });
    expect(peer.ok()).toBeTruthy();
    await page.getByRole("button", { name: "保存草稿", exact: true }).click();
    const conflict = page.getByRole("region", { name: "审核编辑冲突" });
    await expect(conflict).toBeVisible();
    await expect(page.getByLabel("梗名称")).toHaveValue(
      "合成本地尚未提交的名称",
    );
    await conflict.getByText(/冲突内容对照 ·/).click();
    await expect(conflict).toContainText(peerDefinition);
    await expect(conflict).toContainText("合成本地尚未提交的名称");
    await capture(page, "conflict-desktop.png");
    await page.setViewportSize({ width: 390, height: 844 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await capture(page, "conflict-mobile.png");
    await conflict.getByRole("button", { name: "复制本地编辑副本" }).click();
    await expect(conflict.getByRole("status")).toContainText("已复制");
    const copy = JSON.parse(
      await page.evaluate(() => navigator.clipboard.readText()),
    );
    expect(copy.local_editor.name).toBe("合成本地尚未提交的名称");
    expect(JSON.stringify(copy)).not.toContain("e2e-reviewer-only");
    await conflict
      .getByRole("button", { name: "以最新服务器版继续核对本地稿" })
      .click();
    await expect(page.getByLabel(/我已人工核对所有引用材料/)).not.toBeChecked();
    await page.getByRole("button", { name: "保存草稿", exact: true }).click();
    await expect(page.locator('.notice[role="status"]')).toContainText(
      "草稿已保存",
    );
    const latest = await (
      await request.get(`/api/v1/reviews/${revision.id}`, { headers: auth })
    ).json();
    expect(latest.payload.canonical_name).toBe("合成本地尚未提交的名称");
    expect(latest.payload.definition).toBe(definition);
  } finally {
    await clean(request, sid, revision.id);
  }
});

test("保存与审核决定之间的并发修改不能被批准，本地稿不被丢弃", async ({
  page,
  request,
}) => {
  const { revision, sid } = await fixture(request);
  try {
    await openEditor(page, revision.id);
    await page
      .getByLabel("审核理由", { exact: true })
      .fill("只核查合成原稿，不能批准别人的改动。");
    await page.getByLabel(/我已人工核对所有引用材料/).check();
    await page.route(
      `**/api/v1/reviews/${revision.id}/decision`,
      async (route) => {
        const latest = await (
          await request.get(`/api/v1/reviews/${revision.id}`, { headers: auth })
        ).json();
        const changed = await request.put(`/api/v1/reviews/${revision.id}`, {
          headers: { ...auth, "If-Match": latest.etag },
          data: {
            ...latest.payload,
            definition: peerDefinition,
            claims: [
              { ...latest.payload.claims[0], statement: peerDefinition },
            ],
          },
        });
        expect(changed.ok()).toBeTruthy();
        await route.continue(); // Real backend response, not a mocked success/failure.
      },
      { times: 1 },
    );
    await page.getByRole("button", { name: "审核通过并发布" }).click();
    await expect(
      page.getByRole("region", { name: "审核编辑冲突" }),
    ).toBeVisible();
    await expect(page.getByLabel(/定义 · 必须/)).toHaveValue(definition);
    expect(
      (await request.get(`/api/v1/memes/${revision.meme_id}`)).status(),
    ).toBe(404);
    await expect(page.getByLabel(/我已人工核对所有引用材料/)).not.toBeChecked();
  } finally {
    await clean(request, sid, revision.id);
  }
});

test("有效 JSON 中的错误数组格式不会清空编辑器或崩溃对照", async ({
  page,
  request,
}) => {
  const { revision, sid } = await fixture(request);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  try {
    await openEditor(page, revision.id);
    await page.getByText("传播事件、衍生关系与来源主张（结构化编辑）").click();
    await page
      .getByLabel("高级结构化编辑")
      .fill('{"claims": [null], "events": "不是数组", "relations": []}');
    await expect(page.getByLabel("梗名称")).toHaveValue(name);
    await page.getByRole("button", { name: "保存草稿", exact: true }).click();
    await expect(page.locator('.error[role="alert"]')).toContainText(
      "必须为数组",
    );
    expect(errors).toEqual([]);
  } finally {
    await clean(request, sid, revision.id);
  }
});

test("队列移除已处理稿件时仍保留本地文字，读取服务器稿需要明确放弃", async ({
  page,
  request,
}) => {
  const { revision, sid } = await fixture(request);
  try {
    await openEditor(page, revision.id);
    await page.getByLabel("梗名称").fill("合成保留的处理后本地文字");
    const rejected = await request.post(
      `/api/v1/reviews/${revision.id}/decision`,
      {
        headers: { ...auth, "If-Match": revision.etag },
        data: { decision: "reject", reason: "另一位编辑者处理合成稿" },
      },
    );
    expect(rejected.ok()).toBeTruthy();
    await page.getByRole("button", { name: "刷新队列" }).click();
    await expect(page.getByLabel("梗名称")).toHaveValue(
      "合成保留的处理后本地文字",
    );
    const conflict = page.getByRole("region", { name: "审核编辑冲突" });
    await expect(conflict).toBeVisible();
    page.once("dialog", (dialog) => dialog.dismiss());
    await conflict
      .getByRole("button", { name: "读取服务器稿，放弃本地改动" })
      .click();
    await expect(page.getByLabel("梗名称")).toHaveValue(
      "合成保留的处理后本地文字",
    );
    page.once("dialog", (dialog) => dialog.accept());
    await conflict
      .getByRole("button", { name: "读取服务器稿，放弃本地改动" })
      .click();
    await expect(page.getByLabel("梗名称")).toHaveValue(name);
    await expect(
      page.getByRole("button", { name: "保存草稿", exact: true }),
    ).toBeDisabled();
  } finally {
    await clean(request, sid, revision.id);
  }
});

test("历史修订可选择对照，重新起草绑定原条目而不是后来输入的 ID", async ({
  page,
  request,
}) => {
  const { revision, sid } = await fixture(request);
  try {
    const approved = await request.post(
      `/api/v1/reviews/${revision.id}/decision`,
      {
        headers: { ...auth, "If-Match": revision.etag },
        data: {
          decision: "approve",
          reason: "合成历史对照基准，仅软件验收",
          verified_evidence_ids: revision.payload.claims[0].evidence_ids,
        },
      },
    );
    expect(approved.ok()).toBeTruthy();
    const newer = await request.post(
      `/api/v1/reviews/drafts?meme_id=${revision.meme_id}`,
      {
        headers: auth,
        data: { ...revision.payload, canonical_name: "合成历史里的新候选" },
      },
    );
    const newerId = (await newer.json()).id;
    await page.goto("/review");
    await page.getByLabel("审核者令牌").fill("e2e-reviewer-only");
    await page.getByRole("button", { name: "连接工作台" }).click();
    await page.getByLabel("Meme ID", { exact: true }).fill(revision.meme_id);
    await page.getByRole("button", { name: "查看历史修订" }).click();
    const history = page.getByRole("region", { name: "历史修订对照" });
    await expect(history).toBeVisible();
    await page.getByLabel("对照基准修订").selectOption(revision.id);
    await page.getByLabel("对照目标修订").selectOption(newerId);
    await history.getByText(/历史内容对照 ·/).click();
    await expect(
      history.getByRole("region", { name: "历史内容对照" }),
    ).toContainText("合成历史里的新候选");
    await capture(page, "history-desktop.png");
    await page.setViewportSize({ width: 390, height: 844 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await capture(page, "history-mobile.png");
    await page
      .getByLabel("Meme ID", { exact: true })
      .fill("与历史无关的后来输入");
    const created = page.waitForResponse(
      (r) => r.url().includes("/reviews/drafts?meme_id=") && r.status() === 201,
    );
    await history
      .locator(".evidence-box")
      .filter({ hasText: "已批准修订 1" })
      .getByRole("button", { name: "基于此内容创建新修订" })
      .click();
    expect((await (await created).json()).meme_id).toBe(revision.meme_id);
  } finally {
    await request.post(`/api/v1/reviews/memes/${revision.meme_id}/retract`, {
      headers: auth,
      data: { reason: "合成历史对照清理" },
    });
    await clean(request, sid, revision.id, revision.meme_id);
  }
});
