import { expect, test } from "@playwright/test";

/*
 * Two pieces of the home page overlap other content when their height is guessed
 * rather than measured, and both did: the horizon floor, 420px deep with 164px of
 * dome to cover, printed its black over the first record of the index; and the sky's
 * caption, 159px tall in a row that reserved 118px, printed over the headline.
 * Neither throws, neither changes a computed style, and neither shows in the markup -
 * they are visible only as text that looks dimmed or struck through. So they are
 * measured here.
 */

const SIZES = [
  { width: 1505, height: 1045 },
  { width: 1100, height: 820 },
  { width: 390, height: 844 },
];

test("穹顶的地平线不越过穹顶本身", async ({ page }) => {
  for (const size of SIZES) {
    await page.setViewportSize(size);
    await page.goto("/");
    await page.waitForSelector(".horizon");
    const overrun = await page.evaluate(() => {
      const box = (selector: string) =>
        document.querySelector(selector)!.getBoundingClientRect();
      return box(".horizon").bottom - box(".dome").bottom;
    });
    expect(overrun, `${size.width}px 宽时地平线越过穹顶`).toBeLessThanOrEqual(0);
  }
});

/*
 * The sky is stubbed rather than built through the API, because what this test needs
 * is not a meme but the worst case: a definition long enough to wrap the caption onto
 * its second line, at both ends of the arc. Nothing here is a claim about anything.
 */
const LONG =
  "合成夹具的虚构表述，长到足以把说明卡片撑到第二行，用来量它会不会压住标题。";
function sky(count: number) {
  return {
    timezone: "Asia/Shanghai",
    quiet_gap_days: 21,
    axis: { from: "2026-01-01", to: "2026-09-01", ticks: [], bands: [] },
    links: [],
    galaxies: Array.from({ length: count }, (_, index) => ({
      meme_id: `00000000-0000-4000-8000-00000000000${index}`,
      name: `合成夹具梗 ${index}`,
      definition: LONG,
      emergence: { at: null, date: "2026-03-07", basis: "derivative" },
      u: count === 1 ? 0 : index / (count - 1),
      stars: [],
      milestones: [],
      bands: [],
      ticks: [],
    })),
  };
}

test("天空说明不压住标题", async ({ page }) => {
  await page.route("**/v1/universe", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(sky(3)),
    }),
  );
  for (const size of SIZES) {
    await page.setViewportSize(size);
    await page.goto("/");
    await page.waitForSelector(".sky-caption");
    const galaxies = page.locator(".sky-galaxy");
    for (let index = 0; index < (await galaxies.count()); index += 1) {
      await galaxies.nth(index).hover({ force: true });
      await page.waitForTimeout(150);
      const gap = await page.evaluate(() => {
        const box = (selector: string) =>
          document.querySelector(selector)!.getBoundingClientRect();
        return box(".dome-title").top - box(".sky-caption").bottom;
      });
      expect(gap, `${size.width}px 宽、第 ${index} 个星系的说明压住标题`).toBeGreaterThan(0);
    }
  }
});
