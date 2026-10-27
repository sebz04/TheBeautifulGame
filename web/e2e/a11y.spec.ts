import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const PREFS = { mode: "fan", focus: "team", lang: "en", favorite_club_id: "chapinero", favorite_player_id: null, sides: {} };

async function matchPath(page: Page): Promise<string> {
  await page.goto("/matches");
  return (await page.getByRole("list").getByRole("link").first().getAttribute("href")) ?? "/matches";
}

for (const width of [1280, 375]) {
  test.describe(`at ${width} px`, () => {
    test.use({ viewport: { width, height: 900 } });

    test("welcome, match list, match, and best plays have no serious accessibility problems", async ({ page }) => {
      await page.goto("/welcome");
      await page.getByRole("button", { name: "Atlético Chapinero" }).waitFor();
      const pages: [string, () => Promise<void>][] = [["/welcome", async () => {}]];
      await page.addInitScript((p) => localStorage.setItem("matchmind.prefs", JSON.stringify(p)), PREFS);
      const match = await matchPath(page);
      pages.push(["/matches", async () => {}], [match, async () => {}], [`${match}/best-plays`, async () => {}]);
      for (const [path] of pages) {
        await page.goto(path);
        await page.waitForLoadState("networkidle");
        const results = await new AxeBuilder({ page }).analyze();
        const serious = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
        expect(serious.map((v) => `${path}: ${v.id} (${v.nodes.length})`)).toEqual([]);
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
        expect(overflow, `${path} scrolls sideways`).toBeLessThanOrEqual(0);
      }
    });
  });
}

test("the match page works by keyboard alone", async ({ page }) => {
  await page.addInitScript((p) => localStorage.setItem("matchmind.prefs", JSON.stringify(p)), PREFS);
  await page.goto(await matchPath(page));
  await page.waitForLoadState("networkidle");
  const reached = new Set<string>();
  for (let i = 0; i < 40; i++) {
    await page.keyboard.press("Tab");
    reached.add(await page.evaluate(() => document.activeElement?.getAttribute("aria-label") ?? document.activeElement?.textContent?.trim() ?? ""));
  }
  for (const control of ["Play", "Match time", "Fan", "Scout", "Game"]) expect([...reached]).toContain(control);
  // Tabs follow the ARIA pattern: one tab stop, arrow keys move between tabs.
  await page.getByRole("tab", { name: "Game" }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("tab", { name: "Team" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("tab", { name: "Team" })).toBeFocused();
  // Space plays and pauses from the playback bar; Escape closes "About this match".
  await page.getByRole("button", { name: "About this match" }).press("Enter");
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("dialog").press("Escape");
  await expect(page.getByRole("dialog")).toBeHidden();
});
