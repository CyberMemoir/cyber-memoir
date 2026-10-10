import { expect, test } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve, join } from "node:path";
import {
  importReviews,
  loadQueue,
  pending,
  quoteFromSelection,
  sourceUrl,
  validateReview,
} from "../lib/semantic-review";

const root = resolve("../..");
const python = resolve("../backend/.venv/bin/python");
// Python produces the identity/hash fixture independently of the browser implementation.
function fixture() {
  return execFileSync(
    python,
    [
      "-c",
      `
import sys,pathlib,json
sys.path.insert(0,str(pathlib.Path.cwd()/'evals'))
from checkpoint import digest
e={'id':'synthetic-evidence','source_id':'synthetic-source','content_hash':'a'*64,'text':'星😀合成测试原文。\\n这些内容仅用于软件验收。','verified':True,'retracted':False,'locator':{'note':'合成测试定位'},'source':{'id':'synthetic-source','canonical_url':'https://example.org/synthetic','title':'合成来源'}}
for key,name,statement in [('definition','合成演示断言','这是一条合成测试断言，不是真实文化结论。'),('usage_context','合成使用语境','合成的使用语境，仅供测试。')]:
 c={'meme_id':'synthetic-meme','meme_revision':1,'key':key,'statement':statement,'stance':'supports','evidence_ids':['synthetic-evidence'],'meme_name':name}
 identity={k:c[k] for k in ['meme_id','meme_revision','key','statement','stance','evidence_ids']}
 print(json.dumps({'audit_id':digest(identity),'claim':c,'evidence':[e],'assessment':None,'reviewer':None,'reason':None,'queries':['合成测试问题']},ensure_ascii=False))
`,
    ],
    { cwd: root },
  );
}

test("local review selects literal emoji, saves, exports Python-valid records and reloads without upload", async ({
  page,
}) => {
  const raw = fixture();
  const directory = mkdtempSync(join(tmpdir(), "memoir-semantic-ui-"));
  try {
    const apiCalls: string[] = [];
    page.on("request", (request) => {
      if (request.url().includes("/api/")) apiCalls.push(request.url());
    });
    await page.goto("/review/semantic");
    await page.getByLabel("导入审计队列").setInputFiles({
      name: "synthetic.jsonl",
      mimeType: "application/json",
      buffer: raw,
    });
    await expect(page.getByText("已复核 0 / 待复核 2")).toBeVisible();
    await page.getByLabel("复核结论").selectOption("supported");
    await page.getByLabel("复核者", { exact: true }).fill("合成软件验收者");
    await page
      .getByLabel("复核理由")
      .fill("仅为合成测试，保存文字可对应测试断言。");
    await page.locator(".semantic-evidence-text").evaluate((element) => {
      const range = document.createRange();
      range.setStart(element.firstChild!, 1);
      range.setEnd(element.firstChild!, 3);
      const selection = window.getSelection()!;
      selection.removeAllRanges();
      selection.addRange(range);
      element.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));
    });
    await page.getByRole("button", { name: "添加选中摘录" }).click();
    await expect(page.locator(".semantic-quotes blockquote")).toHaveText("😀");
    await page.getByRole("button", { name: "保存这条复核" }).click();
    await expect(page.getByText("已复核 1 / 待复核 1")).toBeVisible();
    const downloadPromise = page.waitForEvent("download");
    await page.getByRole("button", { name: "导出复核 JSON" }).click();
    const download = await downloadPromise;
    const reviewPath = join(directory, "reviews.json");
    await download.saveAs(reviewPath);
    const queuePath = join(directory, "queue.jsonl");
    writeFileSync(queuePath, raw);
    execFileSync(
      python,
      [
        "evals/semantic_review.py",
        "validate",
        "--queue",
        queuePath,
        "--reviews",
        reviewPath,
        "--out",
        join(directory, "report.json"),
      ],
      { cwd: root },
    );
    const summary = JSON.parse(
      readFileSync(join(directory, "report.json"), "utf8"),
    );
    expect(summary.assessed).toBe(1);
    expect(summary.pending).toBe(1);
    expect(summary.reviews[0].quotes[0]).toMatchObject({
      start: 1,
      end: 2,
      exact: "😀",
    });
    await page.reload();
    await page.getByLabel("导入审计队列").setInputFiles({
      name: "synthetic.jsonl",
      mimeType: "application/json",
      buffer: raw,
    });
    await page.getByLabel("加载复核文件").setInputFiles(reviewPath);
    await expect(page.getByText("已复核 1 / 待复核 1")).toBeVisible();
    page.once("dialog", (dialog) => dialog.accept());
    await page.getByRole("button", { name: "撤回本地评级" }).click();
    await expect(page.getByText("已复核 0 / 待复核 2")).toBeVisible();
    await expect(page.getByLabel("复核理由")).toHaveValue("");
    await expect(page.locator(".semantic-quotes blockquote")).toHaveCount(0);
    const pendingDownload = page.waitForEvent("download");
    await page.getByRole("button", { name: "导出复核 JSON" }).click();
    const pendingPath = join(directory, "pending.json");
    await (await pendingDownload).saveAs(pendingPath);
    expect(JSON.parse(readFileSync(pendingPath, "utf8")).reviews).toEqual(
      (await loadQueue(new Uint8Array(raw))).rows.map((row) =>
        pending(row.audit_id),
      ),
    );
    expect(apiCalls).toEqual([]);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

test("invalid queue/review files preserve working state and never turn pending into supported", async ({
  page,
}) => {
  const raw = fixture();
  await page.goto("/review/semantic");
  await page.getByLabel("导入审计队列").setInputFiles({
    name: "queue.jsonl",
    mimeType: "application/json",
    buffer: raw,
  });
  await expect(page.getByText("已复核 0 / 待复核 2")).toBeVisible();
  const queue = await loadQueue(new Uint8Array(raw));
  const bad = {
    schema_version: 1,
    scope: "saved_evidence_text_not_publication",
    queue_sha256: "0".repeat(64),
    reviews: [],
  };
  await page.getByLabel("加载复核文件").setInputFiles({
    name: "wrong.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(bad)),
  });
  await expect(
    page.locator(".semantic-workspace").getByRole("alert"),
  ).toContainText("不属于当前固定队列");
  await expect(page.getByText("已复核 0 / 待复核 2")).toBeVisible();
  await page.getByRole("button", { name: "保存这条复核" }).click();
  await expect(
    page.locator(".semantic-workspace").getByRole("alert"),
  ).toContainText("请选择结论");
  const changed = raw
    .toString("utf8")
    .replace("这是一条合成测试断言", "篡改过的合成测试断言");
  await page.getByLabel("导入审计队列").setInputFiles({
    name: "changed.jsonl",
    mimeType: "application/json",
    buffer: Buffer.from(changed),
  });
  await expect(
    page.locator(".semantic-workspace").getByRole("alert"),
  ).toContainText("摘要不匹配");
  await expect(page.getByText("已复核 0 / 待复核 2")).toBeVisible();
  expect(queue.rows).toHaveLength(2);
});

test("dirty work cannot be silently discarded or exported as a valid assessment", async ({
  page,
}) => {
  await page.goto("/review/semantic");
  await page.getByLabel("导入审计队列").setInputFiles({
    name: "queue.jsonl",
    mimeType: "application/json",
    buffer: fixture(),
  });
  await page.getByLabel("复核理由").fill("尚未保存的合成编辑");
  page.once("dialog", (dialog) => dialog.dismiss());
  await page.getByRole("button", { name: /合成使用语境/ }).click();
  await expect(page.getByLabel("复核理由")).toHaveValue("尚未保存的合成编辑");
  page.once("dialog", (dialog) => dialog.dismiss());
  await page.getByLabel("导入审计队列").setInputFiles({
    name: "replacement.jsonl",
    mimeType: "application/json",
    buffer: fixture(),
  });
  await expect(page.getByLabel("复核理由")).toHaveValue("尚未保存的合成编辑");
  await page.getByRole("button", { name: "导出复核 JSON" }).click();
  await expect(
    page.locator(".semantic-workspace").getByRole("alert"),
  ).toContainText("请先保存当前复核");
});

test("Unicode positions, invalid dates, unknown fields and unsafe source links are rejected", async () => {
  const queue = await loadQueue(new Uint8Array(fixture()));
  const row = queue.rows[0];
  expect(quoteFromSelection(row.evidence[0], 1, 3)).toMatchObject({
    start: 1,
    end: 2,
    exact: "😀",
  });
  expect(() => quoteFromSelection(row.evidence[0], 2, 3)).toThrow();
  const record = {
    ...pending(row.audit_id),
    assessment: "supported",
    reviewer: "合成",
    reason: "合成理由",
    reviewed_at: "2026-02-30T12:00:00Z",
    quotes: [quoteFromSelection(row.evidence[0], 1, 3)],
  };
  expect(() => validateReview(record, row)).toThrow(/合法/);
  expect(() =>
    validateReview(
      { ...record, reviewed_at: "2026-10-10T12:00:00Z", publish: true },
      row,
    ),
  ).toThrow(/未知字段/);
  expect(sourceUrl("javascript:alert(1)")).toBeUndefined();
  expect(sourceUrl("https://secret@example.org/")).toBeUndefined();
  expect(() =>
    importReviews(
      new TextEncoder().encode(
        JSON.stringify({
          schema_version: 1,
          scope: "saved_evidence_text_not_publication",
          queue_sha256: queue.sha,
          reviews: [pending(row.audit_id), pending(row.audit_id)],
        }),
      ),
      queue,
    ),
  ).toThrow(/重复/);
});

test("queue filters keep dirty work, next pending respects saved state, and export never truncates to a subset", async ({
  page,
}) => {
  const apiCalls: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/")) apiCalls.push(request.url());
  });
  await page.goto("/review/semantic");
  await page.getByLabel("导入审计队列").setInputFiles({
    name: "queue.jsonl",
    mimeType: "application/json",
    buffer: fixture(),
  });
  await page.getByLabel("复核理由").fill("第一条未保存的合成稿");
  await page.getByLabel("筛选断言").fill("  合成的使用语境  ");
  await expect(page.getByText("显示 1 / 2 条")).toBeVisible();
  await expect(
    page.getByText("当前断言不在筛选结果中；编辑仍保留。"),
  ).toBeVisible();
  await expect(page.getByLabel("复核理由")).toHaveValue("第一条未保存的合成稿");
  page.once("dialog", (dialog) => dialog.dismiss());
  await page.getByRole("button", { name: "下一条待复核" }).click();
  await expect(page.getByLabel("复核理由")).toHaveValue("第一条未保存的合成稿");
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "下一条待复核" }).click();
  await expect(page.getByLabel("复核理由")).toHaveValue("");
  await expect(page.getByLabel("复核结论")).toHaveValue("");
  await expect(
    page.getByRole("button", { name: "下一条待复核" }),
  ).toBeDisabled();
  await page.getByLabel("复核结论").selectOption("unverifiable");
  await page.getByLabel("复核者", { exact: true }).fill("合成测试者");
  await page.getByLabel("复核理由").fill("合成：仅供流程验收，没有实际核验。");
  await page.getByRole("button", { name: "保存这条复核" }).click();
  await page.getByLabel("筛选断言").fill("");
  await page.getByLabel("已保存状态").selectOption("pending");
  await expect(page.getByText("显示 1 / 2 条")).toBeVisible();
  await expect(
    page.getByText("当前断言不在筛选结果中；编辑仍保留。"),
  ).toBeVisible();
  await page.getByRole("button", { name: "下一条待复核" }).click();
  await expect(page.getByLabel("复核结论")).toHaveValue("");
  await page.getByLabel("复核结论").selectOption("unsupported");
  await page.getByLabel("复核者", { exact: true }).fill("合成测试者");
  await page.getByLabel("复核理由").fill("合成：仅测试分类，不是真实判断。");
  // A dirty choice is not counted as saved or silently removed from the pending list.
  await expect(page.getByText("显示 1 / 2 条")).toBeVisible();
  await page.getByRole("button", { name: "保存这条复核" }).click();
  await expect(page.getByText("显示 0 / 2 条")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "下一条待复核" }),
  ).toBeDisabled();
  await page.getByLabel("已保存状态").selectOption("reviewed");
  await expect(page.getByText("显示 2 / 2 条")).toBeVisible();
  await page.getByLabel("已保存状态").selectOption("unsupported");
  await expect(page.getByText("显示 1 / 2 条")).toBeVisible();
  await page.getByLabel("筛选断言").fill("没有这个合成断言");
  await expect(
    page.getByText("当前筛选无匹配；不会改变复核记录。"),
  ).toBeVisible();
  const directory = mkdtempSync(join(tmpdir(), "memoir-filter-export-"));
  try {
    const downloading = page.waitForEvent("download");
    await page.getByRole("button", { name: "导出复核 JSON" }).click();
    const path = join(directory, "reviews.json");
    await (await downloading).saveAs(path);
    const data = JSON.parse(readFileSync(path, "utf8"));
    expect(
      data.reviews.map((row: { assessment: string }) => row.assessment),
    ).toEqual(["unsupported", "unverifiable"]);
    expect(data.reviews).toHaveLength(2);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
  await page.getByLabel("导入审计队列").setInputFiles({
    name: "new.jsonl",
    mimeType: "application/json",
    buffer: fixture(),
  });
  await expect(page.getByLabel("筛选断言")).toHaveValue("");
  await expect(page.getByLabel("已保存状态")).toHaveValue("all");
  await expect(page.getByText("已复核 0 / 待复核 2")).toBeVisible();
  expect(apiCalls).toEqual([]);
});

test("next pending wraps frozen queue order and reselecting the active item cannot discard a dirty draft", async ({
  page,
}) => {
  await page.goto("/review/semantic");
  await page.getByLabel("导入审计队列").setInputFiles({
    name: "queue.jsonl",
    mimeType: "application/json",
    buffer: fixture(),
  });
  await page.getByRole("button", { name: "下一条待复核" }).click();
  await expect(
    page
      .getByRole("region", { name: "断言复核编辑" })
      .getByRole("heading", { level: 2 }),
  ).toHaveText("合成使用语境");
  await page.getByRole("button", { name: "下一条待复核" }).click();
  await expect(
    page
      .getByRole("region", { name: "断言复核编辑" })
      .getByRole("heading", { level: 2 }),
  ).toHaveText("合成演示断言");
  await page.getByLabel("复核理由").fill("选中条目的合成脏稿");
  await page.getByRole("button", { name: /合成演示断言.*待复核/ }).click();
  await expect(page.getByLabel("复核理由")).toHaveValue("选中条目的合成脏稿");
});

test("each of the five saved verdicts has its own filter and is never treated as pending", async ({
  page,
}) => {
  const raw = fixture();
  const queue = await loadQueue(new Uint8Array(raw));
  await page.goto("/review/semantic");
  await page.getByLabel("导入审计队列").setInputFiles({
    name: "queue.jsonl",
    mimeType: "application/json",
    buffer: raw,
  });
  for (const assessment of [
    "supported",
    "partial",
    "unsupported",
    "contradicted",
    "unverifiable",
  ]) {
    const reviews = queue.rows.map((row, index) =>
      index
        ? pending(row.audit_id)
        : {
            ...pending(row.audit_id),
            assessment,
            reviewer: "合成测试者",
            reason: "合成流程验收",
            reviewed_at: "2026-10-10T12:00:00Z",
            quotes: [quoteFromSelection(row.evidence[0], 0, 1)],
          },
    );
    await page.getByLabel("加载复核文件").setInputFiles({
      name: "review.json",
      mimeType: "application/json",
      buffer: Buffer.from(
        JSON.stringify({
          schema_version: 1,
          scope: "saved_evidence_text_not_publication",
          queue_sha256: queue.sha,
          reviews,
        }),
      ),
    });
    await expect(page.getByLabel("复核结论")).toHaveValue(assessment);
    await page.getByLabel("已保存状态").selectOption(assessment);
    await expect(page.getByText("显示 1 / 2 条")).toBeVisible();
    await expect(
      page.getByRole("button", { name: /合成使用语境.*待复核/ }),
    ).toHaveCount(0);
    await page.getByLabel("已保存状态").selectOption("pending");
    await expect(page.getByText("显示 1 / 2 条")).toBeVisible();
    await expect(
      page.getByRole("button", { name: /合成使用语境.*待复核/ }),
    ).toBeVisible();
  }
});

test("reading a replacement review file freezes task ownership until the validated file is ready", async ({
  page,
}) => {
  const raw = fixture();
  const queue = await loadQueue(new Uint8Array(raw));
  await page.goto("/review/semantic");
  await page.getByLabel("导入审计队列").setInputFiles({
    name: "queue.jsonl",
    mimeType: "application/json",
    buffer: raw,
  });
  await expect(page.getByText("显示 2 / 2 条")).toBeVisible();
  await page.evaluate(() => {
    const original = File.prototype.arrayBuffer;
    File.prototype.arrayBuffer = function () {
      const file = this;
      File.prototype.arrayBuffer = original;
      return new Promise<ArrayBuffer>((resolve) => {
        (
          window as unknown as { releaseReviewRead: () => void }
        ).releaseReviewRead = () => {
          void original.call(file).then(resolve);
        };
      });
    };
  });
  await page.getByLabel("加载复核文件").setInputFiles({
    name: "pending.json",
    mimeType: "application/json",
    buffer: Buffer.from(
      JSON.stringify({
        schema_version: 1,
        scope: "saved_evidence_text_not_publication",
        queue_sha256: queue.sha,
        reviews: queue.rows.map((row) => pending(row.audit_id)),
      }),
    ),
  });
  for (const label of [
    "筛选断言",
    "已保存状态",
    "复核结论",
    "复核者",
    "复核理由",
  ]) {
    await expect(page.getByLabel(label)).toBeDisabled();
  }
  await expect(
    page.getByRole("button", { name: /合成使用语境.*待复核/ }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "下一条待复核" }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "保存这条复核" }),
  ).toBeDisabled();
  await page.evaluate(() =>
    (
      window as unknown as { releaseReviewRead: () => void }
    ).releaseReviewRead(),
  );
  await expect(page.getByLabel("复核理由")).toBeEnabled();
  await expect(
    page
      .getByRole("region", { name: "断言复核编辑" })
      .getByRole("heading", { level: 2 }),
  ).toHaveText("合成演示断言");
  await expect(
    page.getByRole("button", { name: /合成使用语境.*待复核/ }),
  ).toBeEnabled();
});
