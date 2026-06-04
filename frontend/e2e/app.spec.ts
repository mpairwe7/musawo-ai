/**
 * Browser E2E against the deployed frontend (baseURL from playwright.config).
 * Exercises the real path: browser → Next.js → /api proxy → FastAPI → render.
 */
import { test, expect } from "@playwright/test";

test.describe("Musawo AI — deployed frontend", () => {
  test("loads with welcome state and a usable composer", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator(".empty-state-title")).toContainText(/Musawo AI/i);
    await expect(page.getByLabel("Health question input")).toBeVisible();
    await expect(page.getByRole("button", { name: "Send message" })).toBeVisible();
  });

  test("sends a question and renders an assistant answer (full stack)", async ({ page }) => {
    test.setTimeout(120_000);
    await page.goto("/");
    await page.getByLabel("Health question input").fill(
      "What should a VHT do for a child with mild diarrhoea?"
    );
    await page.getByRole("button", { name: "Send message" }).click();

    // The user's message echoes immediately
    await expect(page.locator(".bubble.user").last()).toContainText(/diarrhoea/i);

    // The assistant answer streams in — wait for substantive content
    const answer = page.locator(".bubble.assistant .bubble-content").last();
    await expect(answer).toBeVisible({ timeout: 90_000 });
    await expect.poll(
      async () => (await answer.textContent())?.trim().length ?? 0,
      { timeout: 90_000, intervals: [1000] }
    ).toBeGreaterThan(40);
  });

  test("English 'Read aloud' narration calls the server TTS (Cloudflare MeloTTS)", async ({ page }) => {
    test.setTimeout(120_000);
    await page.goto("/");
    await page.getByLabel("Health question input").fill("How do I prevent malaria at home?");
    await page.getByRole("button", { name: "Send message" }).click();

    const answer = page.locator(".bubble.assistant .bubble-content").last();
    await expect(answer).toBeVisible({ timeout: 90_000 });
    await expect
      .poll(async () => (await answer.textContent())?.trim().length ?? 0, { timeout: 90_000, intervals: [1000] })
      .toBeGreaterThan(40);

    // Clicking "Read aloud" must hit the server TTS endpoint (English → Cloudflare
    // MeloTTS), not go straight to browser speechSynthesis.
    const ttsReq = page.waitForRequest(
      (r) => r.url().includes("/api/v1/voice/tts") && r.method() === "POST",
      { timeout: 15_000 },
    );
    await page.getByRole("button", { name: "Read aloud" }).first().click();
    const req = await ttsReq;
    const body = JSON.parse(req.postData() || "{}");
    expect(["en", "eng"]).toContain(body.locale); // English narration routed server-side
  });

  test("a comparison question renders cleanly — no vertical-character collapse", async ({ page }) => {
    test.setTimeout(120_000);
    await page.goto("/");
    await page.getByLabel("Health question input").fill(
      "Compare the symptoms of typhoid fever and malaria"
    );
    await page.getByRole("button", { name: "Send message" }).click();

    const answer = page.locator(".bubble.assistant .bubble-content").last();
    await expect(answer).toBeVisible({ timeout: 90_000 });
    await expect.poll(
      async () => (await answer.textContent())?.trim().length ?? 0,
      { timeout: 90_000, intervals: [1500] }
    ).toBeGreaterThan(60);

    // Regression guard for the screenshot bug: the content box must be a normal
    // wide block, never a squeezed sliver that wraps words one char per line.
    const box = await answer.boundingBox();
    expect(box, "answer should have a layout box").not.toBeNull();
    expect(box!.width).toBeGreaterThan(200);

    // Any rendered table must use the responsive wrapper (never a raw squeezed table).
    const tables = answer.locator("table");
    for (let i = 0; i < (await tables.count()); i++) {
      await expect(answer.locator(".md-table-wrap table")).toHaveCount(await tables.count());
    }

    // No multi-character medical term should be broken to a ~1-char-wide column.
    const strongs = answer.locator("strong");
    for (let i = 0; i < Math.min(await strongs.count(), 8); i++) {
      const sbox = await strongs.nth(i).boundingBox();
      const txt = (await strongs.nth(i).textContent())?.trim() ?? "";
      if (sbox && txt.length >= 4) {
        expect(sbox.width, `"${txt}" must not be squeezed into a vertical sliver`).toBeGreaterThan(20);
      }
    }
  });
});
