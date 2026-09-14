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
/** A remix the archive can date in no way at all: evidence exists, the day does not. */
const UNDATED = "合成星图无日期视频";
const DEFINITION = "合成星图夹具的虚构表述，仅用于浏览器自动化验收，不是文化事实。";

type Fixture = { parentId: string; childId: string; undatedId: string };

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
 * Three memes: the parent is built on upstream material, the child is built on the
 * parent, and a third is built on nothing anyone dated. The third exists so that a
 * stage whose only star is undated can be told apart from a stage with no evidence,
 * which is the whole of INV-4.
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

  const undatedId = await publish(
    request,
    {
      canonical_name: UNDATED,
      definition: DEFINITION,
      usage_context: "",
      origin_status: "unknown",
      claims: [
        { key: "definition", statement: DEFINITION, evidence_ids: [evidenceId] },
      ],
      events: [
        {
          // No date, and no source to borrow one from, so the star this produces is
          // evidenced and undated. It is the stage's only star, which is the case
          // that must not read as 无证据.
          event_type: "remix",
          description: UNDATED,
          time_precision: "unknown",
          time_basis: "synthetic fixture without a date",
          evidence_ids: [evidenceId],
        },
      ],
      relations: [],
    },
    evidenceId,
  );
  return { parentId, childId, undatedId };
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
  for (const name of [CHILD, PARENT, UNDATED]) {
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
  // INV-1: the date is the Beijing calendar day, read from `date` and never sliced
  // out of the UTC instant. On this SQLite-backed harness the assertion proves the
  // day travelled through the API correctly; it cannot catch a client that slices
  // `at`, because SQLite drops the zone without converting. The real guards for the
  // UTC shift are tests/test_timescale.py and a check against PostgreSQL.
  await expect(rail.locator('[data-stage="source"]')).toContainText(PARENT);
  await expect(rail.locator('[data-stage="source"]')).toContainText("2021-05-04");
  // INV-4b, the distinction this rail exists to protect: this stage's only star is
  // evidenced and undated, so the slot shows that star and absolutely does not claim
  // 无证据 - which is what the derived_meme slot below does claim.
  await expect(rail.locator('[data-stage="derivative"]')).toContainText(
    SOURCE_TITLE,
  );
  await expect(rail.locator('[data-stage="derivative"]')).toContainText("2021-06-03");
  await expect(rail.locator('[data-stage="derivative"]')).not.toContainText(
    "无证据",
  );
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
  // Ordered by date: the upstream source, then the remix. The undated star is not in
  // that order at all - it is in the section below.
  const dated = list.locator("ol").first().locator(".list-row");
  await expect(dated.first()).toContainText("2021-05-04");
  await expect(dated.nth(1)).toContainText("2021-06-03");
  await expect(dated.nth(2)).toHaveCount(0);
  // INV-4a: the rail calls the genuinely empty stage what it is.
  await expect(list.locator(".milestone-empty").first()).toHaveText("无证据");
});

test("只有无日期星体的阶段，不会显示成无证据", async ({ page }) => {
  // Its own galaxy, because that is the case the distinction is for: one star, no
  // date, and a stage that must not be described as empty.
  await page.goto(`/universe?meme=${fixture.undatedId}`);
  const rail = page.locator(".milestone-rail");
  await expect(rail).toBeVisible();
  const slot = rail.locator('[data-stage="derivative"]');
  await expect(slot).toContainText(UNDATED);
  await expect(slot).toContainText("无日期");
  await expect(slot).not.toContainText("无证据");
  // INV-4b on the star itself: it is the only star in the map, and it is drawn on
  // the 无日期 ring outside the rim rather than on the time axis.
  await expect(page.locator(".undated-ring")).toBeVisible();
  await expect(page.locator(".star")).toHaveCount(1);
  const placed = await page.evaluate(() => {
    const centre = { x: 540, y: 500 };
    const star = document.querySelector(".star") as SVGGraphicsElement | null;
    if (!star) return 0;
    const box = star.getBBox();
    return Math.round(
      Math.hypot(box.x + box.width / 2 - centre.x, box.y + box.height / 2 - centre.y),
    );
  });
  // R_IN is 190 and R_OUT is 460; the undated ring is 545.
  expect(placed).toBeGreaterThan(500);
  // And in the list view it reads as a star without a date, not as a stage without
  // evidence: the 无日期 section holds it and the rail still shows no 无证据.
  await page.getByRole("button", { name: "列表视图" }).click({ timeout: 15000 });
  const list = page.locator(".universe-list");
  const noDate = list.locator("ol").first();
  await expect(noDate.locator(".list-row").first()).toContainText(UNDATED);
  await expect(noDate.locator(".list-date").first()).toHaveText("无日期");
  // Three of the four stages really are empty here; the fourth is not, which is the
  // whole point of the case.
  await expect(list.locator(".milestone-empty")).toHaveCount(3);
});
