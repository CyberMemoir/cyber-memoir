import { expect, test, type APIRequestContext } from "@playwright/test";

/**
 * The e2e backend is synthetic: it has no real memes, so this spec builds its own
 * through the public API, exactly as workflow.spec.ts does. Nothing here is a claim
 * about internet culture; the text exists to make evidence resolvable, and the BV id
 * is the one url the synthetic server will answer for.
 */
const REVIEWER = { Authorization: "Bearer e2e-reviewer-only" };
/** baseURL is the web app, whose /api rewrite points at whoever holds :8100; the
 *  fixture must be built on the synthetic backend this run started. */
const API = "http://127.0.0.1:8101";
const SOURCE_URL = "https://www.bilibili.com/video/BV1TEST00001";
/** 2021-05-03T16:00Z is midnight on 2021-05-04 in Beijing; that is the point. The
 *  remix instant is the same trick a day later: it reads 06-03, not 06-02. */
const SOURCE_PUBLISHED = "2021-05-03T16:00:00Z";
const BRIDGE = "2021-06-02T16:00:00Z";

const PARENT = "合成星图父梗";
const CHILD = "合成星图子梗";
const SOURCE_TITLE = "合成星图素材来源";
const DERIVATIVE = "合成星图衍生视频";
const DEFINITION = "合成星图夹具的虚构表述，仅用于浏览器自动化验收，不是文化事实。";

type Fixture = { parentId: string; childId: string };

async function waitForEvidence(
  request: APIRequestContext,
  sourceId: string,
): Promise<string> {
  for (let attempt = 0; attempt < 80; attempt += 1) {
    const response = await request.get(
      `${API}/v1/reviews/sources/${sourceId}`,
      { headers: REVIEWER },
    );
    if (response.ok()) {
      const body = await response.json();
      if (body.evidence?.length) return body.evidence[0].id as string;
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error("the e2e worker did not produce evidence in time");
}

async function publish(
  request: APIRequestContext,
  draft: Record<string, unknown>,
  evidenceId: string,
): Promise<string> {
  const created = await request.post(`${API}/v1/reviews/drafts`, {
    headers: REVIEWER,
    data: draft,
  });
  expect(created.ok()).toBeTruthy();
  const revision = await created.json();
  const decided = await request.post(
    `${API}/v1/reviews/${revision.id}/decision`,
    {
      headers: REVIEWER,
      data: {
        decision: "approve",
        reason: "合成星图夹具，仅用于浏览器验收。",
        // The reviewer confirms each new piece of evidence by hand; approving
        // without this is refused, which is why the API needs it named here.
        verified_evidence_ids: [evidenceId],
      },
    },
  );
  if (!decided.ok()) {
    throw new Error(
      `publish failed: ${decided.status()} ${await decided.text()}`,
    );
  }
  return revision.meme_id as string;
}

/**
 * One source, two memes. The parent is built on upstream material and the child is
 * built on the parent, which gives the child a source star, a derivative star and a
 * derived_meme star, and leaves the parent's derivative and derived_meme slots with
 * no evidence at all.
 */
async function buildFixture(request: APIRequestContext): Promise<Fixture> {
  const submitted = await request.post(`${API}/v1/submissions`, {
    data: { url: SOURCE_URL, title: "合成浏览器验收来源" },
  });
  expect(submitted.ok()).toBeTruthy();
  const { source } = await submitted.json();
  const evidenceId = await waitForEvidence(request, source.id);
  const stamped = await request.post(
    `${API}/v1/reviews/sources/${source.id}/metadata`,
    {
      headers: REVIEWER,
      data: {
        reason: "合成测试：登记平台发布时间，用于验证北京时间换算。",
        platform_published_at: SOURCE_PUBLISHED,
        title: SOURCE_TITLE,
      },
    },
  );
  expect(stamped.ok()).toBeTruthy();

  const parentId = await publish(
    request,
    {
      canonical_name: PARENT,
      definition: DEFINITION,
      usage_context: "",
      origin_status: "unknown",
      claims: [
        { key: "definition", statement: DEFINITION, evidence_ids: [evidenceId] },
      ],
      events: [],
      relations: [
        {
          predicate: "derived_from",
          target_type: "source",
          target_id: source.id,
          assertion_status: "supported",
          evidence_ids: [evidenceId],
        },
      ],
    },
    evidenceId,
  );

  const childId = await publish(
    request,
    {
      canonical_name: CHILD,
      definition: DEFINITION,
      usage_context: "",
      origin_status: "unknown",
      claims: [
        { key: "definition", statement: DEFINITION, evidence_ids: [evidenceId] },
      ],
      events: [
        {
          event_type: "remix",
          description: DERIVATIVE,
          occurred_at_start: BRIDGE,
          time_precision: "day",
          time_basis: "synthetic fixture",
          to_source_id: source.id,
          evidence_ids: [evidenceId],
        },
      ],
      relations: [
        {
          predicate: "derived_from",
          target_type: "meme",
          target_id: parentId,
          assertion_status: "supported",
          evidence_ids: [evidenceId],
        },
      ],
    },
    evidenceId,
  );
  return { parentId, childId };
}

let fixture: Fixture;

/**
 * The suite shares one synthetic database, and workflow.spec.ts asserts on an empty
 * catalogue. Withdrawing these memes afterwards puts the catalogue back as this run
 * found it, and it exercises the retraction path on the way out. The names are looked
 * up again rather than trusted from the fixture, so a partly built fixture is still
 * cleaned up.
 */
async function withdraw(request: APIRequestContext): Promise<void> {
  for (const name of [CHILD, PARENT]) {
    const found = await request.get(
      `${API}/v1/memes?name=${encodeURIComponent(name)}`,
    );
    if (!found.ok()) continue;
    for (const meme of await found.json()) {
      const withdrawn = await request.post(
        `${API}/v1/reviews/memes/${meme.id}/retract`,
        {
          headers: REVIEWER,
          data: { reason: "合成星图夹具，浏览器验收结束，撤回。" },
        },
      );
      expect(withdrawn.ok()).toBeTruthy();
    }
  }
  // 404 rather than 200 is what the rest of the suite depends on being true.
  await expect
    .poll(async () => {
      const still = await request.get(`${API}/v1/memes?name=${encodeURIComponent(CHILD)}`);
      return (await still.json()).length;
    })
    .toBe(0);
}

test.beforeAll(async ({ request }) => {
  await withdraw(request); // in case an interrupted run left a fixture behind
  fixture = await buildFixture(request);
});

test.afterAll(async ({ request }) => {
  await withdraw(request);
});

test("宇宙视图画时间轴，点击星系进入并显示里程碑轨道", async ({ page }) => {
  await page.goto("/universe");
  const picture = page.locator(".universe-svg");
  await expect(picture).toBeVisible();
  // INV-10: the direction of time is on the picture, not in a manual.
  await expect(picture).toContainText("时间 →");
  await expect(picture).toContainText(CHILD);
  const glyph = page.locator(`.galaxy[data-meme-id="${fixture.childId}"]`);
  await expect(glyph).toBeVisible();
  await glyph.click();
  await expect(page).toHaveURL(new RegExp(`meme=${fixture.childId}`));
  const rail = page.locator(".milestone-rail");
  await expect(rail).toBeVisible();
  await expect(rail).toContainText("按阶段排列，非时间顺序");
  // INV-1: the date is the Beijing calendar day, read from `date`, never sliced out
  // of the UTC instant - the upstream source really is the 4th, not the 3rd.
  await expect(rail.locator('[data-stage="source"]')).toContainText(PARENT);
  await expect(rail.locator('[data-stage="source"]')).toContainText("2021-05-04");
  // A derivative star is named after the source it remixes; the event's own
  // description is what the star panel shows, not what the milestone rail shows.
  await expect(rail.locator('[data-stage="derivative"]')).toContainText(
    SOURCE_TITLE,
  );
  await expect(rail.locator('[data-stage="derivative"]')).toContainText("2021-06-03");
  // INV-4a: a stage with no evidence at all is drawn as an empty slot.
  await expect(rail.locator('[data-stage="derived_meme"]')).toContainText("无证据");
});

test("直接打开 ?meme= 进入同一个星系，浏览器返回回到宇宙", async ({ page }) => {
  // Entering the universe first is what gives the back button somewhere to go.
  await page.goto("/universe");
  await page.waitForSelector(".galaxy");
  await page.goto(`/universe?meme=${fixture.childId}`);
  await expect(page.locator(".milestone-rail")).toBeVisible();
  await expect(page.locator(".universe-crumbs")).toContainText(CHILD);
  await page.goBack();
  await expect(page).toHaveURL(/\/universe$/);
  await expect(page.locator(".universe-svg")).toContainText("时间 →");
  await expect(page.locator(".milestone-rail")).toHaveCount(0);
});

test("点击星体打开面板，面板显示证据原文，Escape 关闭", async ({ page }) => {
  await page.goto(`/universe?meme=${fixture.childId}`);
  // A star whose kind is a meme opens that galaxy instead of a panel, so this one
  // is a video. It is aimed at its lower edge because a milestone's halo widens a
  // neighbour's tap target, and the centre of a crowded pair hits the wrong star.
  const star = page.locator('.star.stage-derivative[data-kind="source"]').first();
  await expect(star).toBeVisible();
  const box = await star.boundingBox();
  if (!box) throw new Error("the star had no box to click");
  await star.click({ position: { x: box.width / 2, y: box.height - 2 } });
  const panel = page.locator(".star-panel");
  await expect(panel).toBeVisible();
  await expect(panel).toContainText("2021-06-03");
  await expect(panel.locator(".star-evidence-item blockquote")).toContainText(
    "合成",
  );
  await expect(panel).toContainText("内容哈希");
  await page.keyboard.press("Escape");
  await expect(panel).toHaveCount(0);
});

test("列表视图按日期排列星体，并保留无证据与无日期的区别", async ({ page }) => {
  await page.goto(`/universe?meme=${fixture.childId}`);
  await page.getByRole("button", { name: "列表视图" }).click();
  const list = page.locator(".universe-list");
  await expect(list).toBeVisible();
  // Ordered by date: the upstream source first, then the remix.
  const rows = list.locator(".list-row");
  await expect(rows.first()).toContainText("2021-05-04");
  await expect(rows.nth(1)).toContainText("2021-06-03");
  // INV-4: "no date" is drawn, and it is not the same statement as "no evidence".
  await expect(list).toContainText("无日期");
  await expect(list.locator(".milestone-empty").first()).toHaveText("无证据");
});
