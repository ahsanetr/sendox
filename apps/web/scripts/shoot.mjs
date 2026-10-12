// Screenshot the app for visual review. Signs in first, because every page
// behind the shell is useless to look at while signed out.
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const LABEL = process.argv[2] ?? "shot";
const OUT = resolve(dirname(fileURLToPath(import.meta.url)), "../../../docs/screenshots");
mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

const email = `shot-${Date.now()}@example.com`;
await page.goto("http://localhost:3000/", { waitUntil: "domcontentloaded" });
await page.waitForTimeout(2500);
await page.screenshot({ path: `${OUT}/${LABEL}-signin.png` });

await page.fill("#signin-email", email);
await page.fill("#signin-password", "Northwind2026");
await page.fill("#signin-name", "Ahsan Ali");
await page.fill("#signin-workspace", "Northwind Supply");
await page.click('button[type="submit"]');
await page.waitForSelector("text=Confirm email address", { timeout: 20000 });
await page.click("text=Confirm email address");
await page.waitForSelector("text=Waiting on you", { timeout: 20000 });

for (const [route, name] of [
  ["/", "home"],
  ["/brand", "brand"],
  ["/contacts", "contacts"],
  ["/settings", "settings"],
]) {
  await page.goto(`http://localhost:3000${route}`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(2500);
  await page.screenshot({ path: `${OUT}/${LABEL}-${name}.png`, fullPage: true });
}

// One frame per colour scheme, so the choice can be made by looking rather
// than by reading hex codes. Driven through the real picker, not by setting the
// attribute directly — that way the screenshots also prove the control works.
const SCHEMES = ["swiss", "graphite", "indigo", "teal", "midnight"];
await page.goto("http://localhost:3000/contacts", { waitUntil: "domcontentloaded" });
await page.waitForTimeout(2000);
for (const scheme of SCHEMES) {
  await page.click('button[aria-haspopup="menu"]');
  await page.click(`[role="menuitemradio"]:nth-of-type(${SCHEMES.indexOf(scheme) + 1})`);
  await page.waitForTimeout(400);
  const applied = await page.evaluate(() => document.documentElement.dataset.scheme);
  if (applied !== scheme) throw new Error(`picker set ${applied}, expected ${scheme}`);
  await page.screenshot({ path: `${OUT}/${LABEL}-scheme-${scheme}.png` });
}
// Leave it on the default, and check the choice survives a reload.
await page.click('button[aria-haspopup="menu"]');
await page.click('[role="menuitemradio"]:nth-of-type(1)');
await page.reload({ waitUntil: "domcontentloaded" });
await page.waitForTimeout(1500);
const persisted = await page.evaluate(() => document.documentElement.dataset.scheme);
if (persisted !== "swiss") throw new Error(`scheme did not persist: ${persisted}`);

// Open the picker for one screenshot, so the menu itself gets reviewed too.
await page.click('button[aria-haspopup="menu"]');
await page.waitForTimeout(400);
await page.screenshot({ path: `${OUT}/${LABEL}-scheme-menu.png` });
await page.keyboard.press("Escape");
await page.goto("http://localhost:3000/", { waitUntil: "domcontentloaded" });
await page.waitForTimeout(2000);

// What font is the browser actually using? The whole reason for this script.
const report = await page.evaluate(() => {
  const aside = document.querySelector("aside");
  return {
    font: getComputedStyle(document.body).fontFamily,
    railHeight: aside ? Math.round(aside.getBoundingClientRect().height) : 0,
    docHeight: document.documentElement.scrollHeight,
  };
});
console.log(JSON.stringify(report, null, 2));
await browser.close();
