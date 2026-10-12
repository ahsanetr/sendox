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
// than by reading hex codes. Driven through the real picker and selected by
// label rather than position, so reordering the menu cannot silently make these
// screenshots lie about which scheme they show.
const SCHEMES = [
  ["Midnight", null], // the default: chosen by clearing the attribute, not setting it
  ["Swiss Blue", "swiss"],
  ["Graphite", "graphite"],
  ["Indigo", "indigo"],
  ["Teal", "teal"],
];

async function choose(label) {
  await page.click('button[aria-haspopup="menu"]');
  await page.click(`[role="menuitemradio"]:has-text("${label}")`);
  await page.waitForTimeout(400);
}

await page.goto("http://localhost:3000/contacts", { waitUntil: "domcontentloaded" });
await page.waitForTimeout(2000);

for (const [label, attr] of SCHEMES) {
  await choose(label);
  const applied = await page.evaluate(() => document.documentElement.dataset.scheme ?? null);
  if (applied !== attr) {
    throw new Error(`picking ${label} left data-scheme=${applied}, expected ${attr}`);
  }
  await page.screenshot({ path: `${OUT}/${LABEL}-scheme-${label.toLowerCase().replace(/ /g, "-")}.png` });
}

// A non-default choice must survive a reload...
await choose("Graphite");
await page.reload({ waitUntil: "domcontentloaded" });
await page.waitForTimeout(1500);
const kept = await page.evaluate(() => document.documentElement.dataset.scheme ?? null);
if (kept !== "graphite") throw new Error(`scheme did not persist: ${kept}`);

// ...and returning to the default must leave no attribute behind, because the
// default is what :root already says.
await choose("Midnight");
await page.reload({ waitUntil: "domcontentloaded" });
await page.waitForTimeout(1500);
const cleared = await page.evaluate(() => document.documentElement.dataset.scheme ?? null);
if (cleared !== null) throw new Error(`default left data-scheme=${cleared}`);

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
