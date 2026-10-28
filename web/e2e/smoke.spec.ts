import { expect, test } from "@playwright/test";

// Welcome → pick a club → straight to its match → play → an insight appears → Spanish → Ask why → Best plays.
test("a fan's first match", async ({ page, request }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Atlético Chapinero" }).click();
  await page.getByRole("button", { name: "Start watching" }).click();
  await expect(page).toHaveURL(/\/match\//); // the club's first match, no list in between
  const matchId = page.url().split("/match/")[1];

  // Jump to a few seconds before the first moment ends, then play: its insight appears.
  const timeline = await (await request.get(`http://localhost:${process.env.E2E_API_PORT ?? "8100"}/api/matches/${matchId}/timeline`)).json();
  const first = timeline.moments.sort((a: { t_end: number }, b: { t_end: number }) => a.t_end - b.t_end).find((m: { period: number }) => m.period === 1);
  await page.getByRole("slider", { name: "Match time" }).fill(String(Math.max(0, Math.floor(first.t_end) - 4)));
  await page.getByRole("button", { name: "Play", exact: true }).click();
  const headline = page.locator("aside article h2").first();
  await expect(headline).toBeVisible({ timeout: 15_000 });
  const english = await headline.textContent();

  await page.getByRole("combobox", { name: "Language" }).selectOption("es");
  await expect(page.locator("html")).toHaveAttribute("lang", "es");
  await expect(headline).not.toHaveText(english ?? "");

  await page.getByRole("button", { name: "¿Por qué?" }).first().click();
  await expect(page.getByRole("heading", { name: "Los números en que se basa" })).toBeVisible();
  await expect(page.getByText(/posesión|possession/i).first()).toBeVisible();

  await page.getByRole("link", { name: "Mejores jugadas" }).first().click();
  await expect(page.getByRole("heading", { name: "Mejores jugadas", level: 1 })).toBeVisible();
  await page.getByRole("link", { name: "Volver al vivo" }).click();
  await expect(page).toHaveURL(new RegExp(`/match/${matchId}$`));
});
