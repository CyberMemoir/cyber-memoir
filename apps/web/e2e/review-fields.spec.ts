import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";
import type { Draft } from "../lib/api";
import {
  fieldClaims,
  initialFieldEvidence,
  missingFieldSupport,
  supplementalClaims,
} from "../lib/review-claims";

// The isolated backend maps this test-only header to a separate client address.
// Production still uses the actual remote IP and keeps its 60/minute cap.
test.use({
  extraHTTPHeaders: { "X-Memoir-E2E-Client": "review-field-references" },
});

const auth = { Authorization: "Bearer e2e-reviewer-only" };
const name = "合成逐字段审核梗";
const definition = "合成逐字段审核梗是仅用于软件验收的虚构定义。";
const nextDefinition = "合成逐字段审核梗是一份软件验收用的虚构定义。";
const usage = "只在合成的软件测试场景中使用，不代表真实文化。";
const nextUsage = "只在浏览器软件验收场景中使用，不代表真实文化。";

function syntheticDraft(): Draft {
  return {
    canonical_name: name,
    aliases: [],
    definition,
    usage_context: usage,
    origin_status: "unknown",
    events: [],
    relations: [],
    claims: [
      {
        key: "definition",
        statement: definition,
        stance: "supports",
        evidence_ids: ["synthetic-definition"],
      },
      {
        key: "usage_context",
        statement: usage,
        stance: "supports",
        evidence_ids: ["synthetic-usage"],
      },
      {
        key: "definition",
        statement: definition,
        stance: "contradicts",
        evidence_ids: ["synthetic-counter"],
      },
      {
        key: "definition",
        statement: "合成局部补充",
        stance: "supports",
        evidence_ids: ["synthetic-partial"],
      },
      {
        key: "origin",
        statement: "合成起源反对意见",
        stance: "contradicts",
        evidence_ids: ["synthetic-origin"],
      },
    ],
  };
}

test("字段初始化只读取对应完整断言的支持引用", () => {
  expect(initialFieldEvidence(syntheticDraft())).toEqual({
    definition: ["synthetic-definition"],
    usage_context: ["synthetic-usage"],
  });
});

test("完整字段的反对意见、局部断言与起源引用留在结构化编辑中", () => {
  const draft = syntheticDraft();
  expect(supplementalClaims(draft, false)).toEqual(draft.claims.slice(2));
});

test("尚未选择引用的文字可以保存为草稿，不创建空引用断言", () => {
  const draft = syntheticDraft();
  expect(
    fieldClaims(draft, draft, { definition: [], usage_context: [] }, false),
  ).toEqual([]);
  expect(missingFieldSupport({ ...draft, claims: [] })).toBe("definition");
});

test("追加用法完整保留所有旧字段引用，不把反对材料改成支持", () => {
  const draft = syntheticDraft();
  const fields = fieldClaims(
    draft,
    { definition: "不得覆盖的文字", usage_context: "不得覆盖的语境" },
    { definition: ["synthetic-new"], usage_context: [] },
    true,
  );
  expect(fields).toEqual(draft.claims.slice(0, 4));
  expect(supplementalClaims(draft, true)).toEqual(draft.claims.slice(4));
});

test("高级编辑可提供显式完整支持，但旧文字或反对断言不能顶替", () => {
  const draft = syntheticDraft();
  expect(missingFieldSupport(draft)).toBeUndefined();
  expect(missingFieldSupport({ ...draft, definition: nextDefinition })).toBe(
    "definition",
  );
  expect(
    missingFieldSupport({
      ...draft,
      claims: draft.claims.filter((c) => c.key !== "usage_context"),
    }),
  ).toBe("usage_context");
  expect(
    fieldClaims(
      draft,
      draft,
      { definition: ["same", "same"], usage_context: [] },
      false,
    )[0].evidence_ids,
  ).toEqual(["same"]);
});

async function capture(page: Page, name: string) {
  const directory = process.env.CYBER_MEMOIR_REVIEW_QA;
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
  const layout = await page.evaluate(() => ({
    viewport: [innerWidth, innerHeight],
    documentHeight: document.documentElement.scrollHeight,
    bodyHeight: document.body.scrollHeight,
    footerBottom: document.querySelector("footer")?.getBoundingClientRect()
      .bottom,
  }));
  await page.screenshot({ path: path.join(directory, name), fullPage: true });
  await writeFile(
    path.join(directory, `${name}.layout.json`),
    JSON.stringify(layout),
  );
}

function signature(
  claims: {
    key: string;
    statement: string;
    stance: string;
    evidence_ids: string[];
  }[],
) {
  return claims
    .map((claim) =>
      JSON.stringify({
        key: claim.key,
        statement: claim.statement,
        stance: claim.stance,
        evidence_ids: [...claim.evidence_ids].sort(),
      }),
    )
    .sort();
}

test("逐字段审核保留原支持/反对绑定，文字变化不能自动复用引用", async ({
  page,
  request,
}) => {
  const registered = await request.post("/api/v1/reviews/sources", {
    headers: auth,
    data: {
      platform: "web",
      url: "https://example.org/field-review-synthetic",
      title: "合成字段审核材料",
    },
  });
  expect(registered.ok()).toBeTruthy();
  const source = (await registered.json()).source;
  const ids: string[] = [];
  for (const text of [
    `仅供软件测试的定义材料：\n${definition}\n${nextDefinition}`,
    `仅供软件测试的语境材料：\n${usage}\n${nextUsage}`,
    "仅供软件测试的反对材料：这段反对意见不支持定义或使用语境，也不确认起源。",
  ]) {
    const material = await request.post(
      `/api/v1/sources/${source.id}/materials`,
      {
        data: { text, locator: { note: "合成逐字段审核夹具，非真实文化材料" } },
      },
    );
    expect(material.ok()).toBeTruthy();
    ids.push((await material.json()).id);
  }
  const claims = [
    {
      key: "definition",
      statement: definition,
      stance: "supports",
      evidence_ids: [ids[0]],
    },
    {
      key: "usage_context",
      statement: usage,
      stance: "supports",
      evidence_ids: [ids[1]],
    },
    {
      key: "origin",
      statement: "合成起源反对意见，不确认实际起源。",
      stance: "contradicts",
      evidence_ids: [ids[2]],
    },
    {
      key: "definition",
      statement: "合成局部定义的反对意见。",
      stance: "contradicts",
      evidence_ids: [ids[2]],
    },
    {
      key: "definition",
      statement: "合成局部补充断言，不替代完整定义。",
      stance: "supports",
      evidence_ids: [ids[1]],
    },
  ];
  const created = await request.post("/api/v1/reviews/drafts", {
    headers: auth,
    data: { canonical_name: name, definition, usage_context: usage, claims },
  });
  expect(created.ok()).toBeTruthy();
  const revision = await created.json();
  await page.goto("/review");
  await page.getByLabel("审核者令牌").fill("e2e-reviewer-only");
  await page.getByRole("button", { name: "连接工作台" }).click();
  await page.locator(".review-item").filter({ hasText: name }).click();
  await expect(page.getByLabel("梗名称")).toHaveValue(name);
  await expect(page.locator(".review-columns .evidence-box")).toHaveCount(3);
  const baseline = process.env.CYBER_MEMOIR_REVIEW_QA_BASELINE === "1";
  await capture(
    page,
    baseline
      ? "review-fields-reference-desktop.png"
      : "review-fields-desktop.png",
  );
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await capture(
    page,
    baseline
      ? "review-fields-reference-mobile.png"
      : "review-fields-mobile.png",
  );
  await page.setViewportSize({ width: 1505, height: 1045 });

  const saved = page.waitForResponse(
    (r) => r.request().method() === "PUT" && r.url().endsWith(revision.id),
  );
  await page.getByRole("button", { name: "保存草稿", exact: true }).click();
  expect((await saved).ok()).toBeTruthy();
  await expect(page.getByRole("status")).toContainText("草稿已保存");
  const updated = (
    await (await request.get("/api/v1/reviews", { headers: auth })).json()
  ).find((item: { id: string }) => item.id === revision.id);
  // This assertion exposes the old UI's silent union of unrelated evidence and
  // loss of counter/partial claims before introducing any new UI expectations.
  expect(signature(updated.payload.claims)).toEqual(
    signature(revision.payload.claims),
  );

  const definitionBox = page
    .locator(".evidence-box")
    .filter({ hasText: "定义材料" });
  const usageBox = page
    .locator(".evidence-box")
    .filter({ hasText: "语境材料" });
  const counterBox = page
    .locator(".evidence-box")
    .filter({ hasText: "反对材料" });
  await expect(
    definitionBox.getByRole("checkbox", { name: "支持定义", exact: true }),
  ).toBeChecked();
  await expect(
    usageBox.getByRole("checkbox", { name: "支持使用语境", exact: true }),
  ).toBeChecked();
  await expect(
    counterBox.getByRole("checkbox", { name: "支持定义", exact: true }),
  ).not.toBeChecked();
  await expect(
    counterBox.getByRole("checkbox", { name: "支持使用语境", exact: true }),
  ).not.toBeChecked();
  await page.getByLabel("使用语境", { exact: true }).fill(nextUsage);
  await expect(
    usageBox.getByRole("checkbox", { name: "支持使用语境", exact: true }),
  ).not.toBeChecked();
  await expect(
    definitionBox.getByRole("checkbox", { name: "支持定义", exact: true }),
  ).toBeChecked();
  await usageBox
    .getByRole("checkbox", { name: "支持使用语境", exact: true })
    .check();
  await page.getByLabel(/定义 · 必须/).fill(nextDefinition);
  await expect(
    definitionBox.getByRole("checkbox", { name: "支持定义", exact: true }),
  ).not.toBeChecked();
  await expect(
    usageBox.getByRole("checkbox", { name: "支持使用语境", exact: true }),
  ).toBeChecked();
  await page
    .getByLabel("审核理由", { exact: true })
    .fill("已核对合成材料的分别绑定，非文化事实核验。");
  await page.getByLabel(/我已人工核对所有引用材料/).check();
  await page.getByRole("button", { name: "审核通过并发布" }).click();
  await expect(page.locator('.error[role="alert"]')).toContainText(
    "定义尚未选择完整字段的支持证据",
  );
  const stillDraft = (
    await (await request.get("/api/v1/reviews", { headers: auth })).json()
  ).find((item: { id: string }) => item.id === revision.id);
  expect(stillDraft.status).toBe("pending_review");
  expect(stillDraft.payload.definition).toBe(definition);
  await definitionBox
    .getByRole("checkbox", { name: "支持定义", exact: true })
    .check();
  await expect(page.getByLabel(/我已人工核对所有引用材料/)).not.toBeChecked();
  await page.getByLabel(/我已人工核对所有引用材料/).check();
  const decision = page.waitForResponse((r) =>
    r.url().endsWith(`${revision.id}/decision`),
  );
  await page.getByRole("button", { name: "审核通过并发布" }).click();
  expect((await decision).ok()).toBeTruthy();
  const published = await request.get(`/api/v1/memes/${revision.meme_id}`);
  expect(published.ok()).toBeTruthy();
  const result = await published.json();
  try {
    expect(signature(result.claims)).toEqual(
      signature([
        { ...claims[0], statement: nextDefinition },
        { ...claims[1], statement: nextUsage },
        ...claims.slice(2),
      ]),
    );
  } finally {
    const cleaned = await request.post(
      `/api/v1/reviews/memes/${revision.meme_id}/retract`,
      {
        headers: auth,
        data: { reason: "合成逐字段审核验收结束，清理公开夹具。" },
      },
    );
    expect(cleaned.ok()).toBeTruthy();
    const pending = await (
      await request.get("/api/v1/reviews", { headers: auth })
    ).json();
    for (const candidate of pending.filter(
      (item: { payload: Draft }) => item.payload._source_id === source.id,
    )) {
      const rejected = await request.post(
        `/api/v1/reviews/${candidate.id}/decision`,
        {
          headers: { ...auth, "If-Match": candidate.etag },
          data: {
            decision: "reject",
            reason: "清理这份合成材料产生的未发布候选。",
          },
        },
      );
      expect(rejected.ok()).toBeTruthy();
    }
  }
});

test("Worker 候选加载全部跨来源引用，而不是只显示最初来源", async ({
  page,
  request,
}) => {
  const title = "合成带跨来源引用的候选";
  const fixtures = [
    { slug: "base", title, text: "合成主来源的定义材料，非真实文化事实。" },
    {
      slug: "counter",
      title: "合成独立反对来源",
      text: "其他来源的合成反对意见，不支持主来源的定义。",
    },
  ];
  const sources: string[] = [];
  const evidence: string[] = [];
  for (const fixture of fixtures) {
    const registered = await request.post("/api/v1/reviews/sources", {
      headers: auth,
      data: {
        platform: "web",
        url: `https://example.org/cross-source-review-${fixture.slug}`,
        title: fixture.title,
      },
    });
    expect(registered.ok()).toBeTruthy();
    sources.push((await registered.json()).source.id);
    const material = await request.post(
      `/api/v1/sources/${sources.at(-1)}/materials`,
      {
        data: { text: fixture.text, locator: { note: "合成跨来源引用测试" } },
      },
    );
    expect(material.ok()).toBeTruthy();
    evidence.push((await material.json()).id);
  }
  let original: { id: string; payload: Draft; etag: string } | undefined;
  await expect
    .poll(async () => {
      const queue = await (
        await request.get("/api/v1/reviews", { headers: auth })
      ).json();
      original = queue.find(
        (item: { payload: Draft }) => item.payload._source_id === sources[0],
      );
      return Boolean(original);
    })
    .toBe(true);
  const updated = await request.put(`/api/v1/reviews/${original!.id}`, {
    headers: { ...auth, "If-Match": original!.etag },
    data: {
      canonical_name: title,
      definition: fixtures[0].text,
      claims: [
        {
          key: "definition",
          statement: fixtures[0].text,
          evidence_ids: [evidence[0]],
          stance: "supports",
        },
        {
          key: "origin",
          statement: fixtures[1].text,
          evidence_ids: [evidence[1]],
          stance: "contradicts",
        },
      ],
    },
  });
  expect(updated.ok()).toBeTruthy();
  try {
    await page.goto("/review");
    await page.getByLabel("审核者令牌").fill("e2e-reviewer-only");
    await page.getByRole("button", { name: "连接工作台" }).click();
    await page.locator(".review-item").filter({ hasText: title }).click();
    await expect(page.locator(".review-columns .evidence-box")).toHaveCount(2);
    const counter = page
      .locator(".evidence-box")
      .filter({ hasText: fixtures[1].text });
    await expect(counter).toContainText("合成独立反对来源");
    await expect(
      counter.getByRole("checkbox", { name: "支持定义", exact: true }),
    ).not.toBeChecked();
  } finally {
    const pending = await (
      await request.get("/api/v1/reviews", { headers: auth })
    ).json();
    for (const candidate of pending.filter((item: { payload: Draft }) =>
      sources.includes(item.payload._source_id || ""),
    )) {
      const rejected = await request.post(
        `/api/v1/reviews/${candidate.id}/decision`,
        {
          headers: { ...auth, "If-Match": candidate.etag },
          data: {
            decision: "reject",
            reason: "清理合成跨来源候选，不发布为文化资料。",
          },
        },
      );
      expect(rejected.ok()).toBeTruthy();
    }
  }
});

test("隔离的浏览器测试客户端仍执行 60 次每分钟限流", async ({ request }) => {
  for (let attempt = 1; attempt <= 61; attempt += 1) {
    const response = await request.post("/api/v1/reviews/drafts", {
      // No Authorization: no data is created. The separate address only avoids
      // sharing this scenario's budget with other unrelated browser scenarios.
      headers: { "X-Memoir-E2E-Client": "review-rate-cap" },
      data: { canonical_name: "合成限流请求，未授权，不会创建条目" },
    });
    expect(response.status()).toBe(attempt <= 60 ? 401 : 429);
  }
});
