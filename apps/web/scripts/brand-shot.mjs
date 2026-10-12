// Drive the brand onboarding wizard the way a merchant would, then photograph
// the result. Proves the five steps save and the inspector renders real rows.
import { chromium } from "playwright";
import { execFileSync } from "node:child_process";
import { mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const OUT = resolve(dirname(fileURLToPath(import.meta.url)), "../../../docs/screenshots");
mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const email = `brand-${Date.now()}@example.com`;

await page.goto("http://localhost:3000/", { waitUntil: "domcontentloaded" });
await page.waitForTimeout(2000);
await page.fill("#signin-email", email);
await page.fill("#signin-password", "Northwind2026");
await page.fill("#signin-name", "Ahsan Ali");
await page.fill("#signin-workspace", "Northwind Supply");
await page.click('button[type="submit"]');
await page.waitForSelector("text=Confirm email address", { timeout: 20000 });
await page.click("text=Confirm email address");
await page.waitForSelector("text=Waiting on you", { timeout: 20000 });

await page.goto("http://localhost:3000/brand", { waitUntil: "domcontentloaded" });
await page.waitForTimeout(2500);
await page.screenshot({ path: `${OUT}/brand-wizard-step1.png` });

const ANSWERS = [
  "Hard-wearing outdoor clothing for people who are outside whether or not the forecast is good. We make a small range and keep it in the line for years.",
  "Hikers and hill walkers in their 30s and 40s who have owned cheap gear, watched it fail on a wet weekend, and stopped buying it.",
  null, // tone: picked, not typed
  "Never call the fleece waterproof. Never use the word curated. No countdown timers.",
  "Short sentences. No exclamation marks. We sign off 'See you out there'.",
];

for (let step = 0; step < ANSWERS.length; step++) {
  const answer = ANSWERS[step];
  if (answer === null) {
    await page.click('[role="radio"]:has-text("Direct")');
    await page.waitForTimeout(300);
    await page.screenshot({ path: `${OUT}/brand-wizard-tone.png` });
  } else {
    await page.fill("textarea", answer);
  }
  await page.click('button:has-text("' + (step === ANSWERS.length - 1 ? "Finish" : "Next") + '")');
  await page.waitForTimeout(900);
}

await page.waitForSelector("text=Brand profile complete", { timeout: 15000 });
await page.waitForTimeout(500);
await page.screenshot({ path: `${OUT}/brand-complete.png`, fullPage: true });

// Reload: the answers must come back from the server, not from React state.
await page.reload({ waitUntil: "domcontentloaded" });
await page.waitForTimeout(2500);
const persisted = await page.locator("text=See you out there").count();
if (persisted === 0) throw new Error("answers did not survive a reload");

// Crawl the fixture storefront into this workspace, so the inspector has real
// rows to render. Development only: it is the same fixture the crawler tests
// use, which means the screenshots show text we can check against the source.
execFileSync("uv", ["run", "python", "scripts/seed-brand-fixture.py"], {
  cwd: "../api",
  stdio: "inherit",
});

await page.reload({ waitUntil: "domcontentloaded" });
await page.waitForSelector("text=words of voice", { timeout: 20000 });
await page.waitForTimeout(800);
await page.screenshot({ path: `${OUT}/brand-inspector.png`, fullPage: true });

// Open one page and read its full extracted text.
await page.click('button:has-text("Read")');
await page.waitForSelector('[role="dialog"]', { timeout: 10000 });
await page.waitForTimeout(700);
await page.screenshot({ path: `${OUT}/brand-page-reader.png` });
await page.keyboard.press("Escape");
await page.waitForTimeout(400);

// Exclude a page: the row must dim, the count must drop, and the warning that
// nothing is forgotten until a re-index must appear.
const before = await page.locator('li:has-text("words")').count();
await page.click('button[aria-label="Exclude this page"]');
await page.waitForSelector("text=next time the storefront is indexed", { timeout: 10000 });
await page.waitForTimeout(600);
await page.screenshot({ path: `${OUT}/brand-excluded.png`, fullPage: true });
const after = await page.locator('li:has-text("words")').count();
if (after !== before) throw new Error(`excluding removed the row: ${before} -> ${after}`);

const report = await page.evaluate(() => ({
  complete: !!document.body.textContent?.includes("Brand profile complete"),
  pagesListed: document.querySelectorAll("li a[href^=\"http://127\"]").length,
  excludedVisible: !!document.body.textContent?.includes("Excluded"),
  reindexWarned: !!document.body.textContent?.includes("next time the storefront is indexed"),
}));
console.log(JSON.stringify(report, null, 2));
await browser.close();
