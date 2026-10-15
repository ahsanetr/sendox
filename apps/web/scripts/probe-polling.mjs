// Count API requests an idle signed-in page makes. Guards the fetcher-identity
// loop that made the Brand page fetch about five times a second forever.
import { chromium } from "playwright";
const b = await chromium.launch();
const p = await b.newPage();
const email = `probe-${Date.now()}@example.com`;
await p.goto("http://localhost:3000/", { waitUntil: "domcontentloaded" });
await p.waitForTimeout(2500);
await p.fill("#signin-email", email);
await p.fill("#signin-password", "Northwind2026");
await p.fill("#signin-name", "Probe");
await p.fill("#signin-workspace", "Probe Co");
await p.click('button[type="submit"]');
await p.waitForSelector("text=Confirm email address", { timeout: 20000 });
await p.click("text=Confirm email address");
await p.waitForSelector("text=Waiting on you", { timeout: 20000 });

for (const route of ["/", "/brand", "/contacts"]) {
  await p.goto(`http://localhost:3000${route}`, { waitUntil: "domcontentloaded" });
  await p.waitForTimeout(3000);          // let the page settle
  let n = 0;
  const count = (r) => { if (r.url().includes(":8000/")) n++; };
  p.on("request", count);
  await p.waitForTimeout(10000);         // then measure 10 idle seconds
  p.off("request", count);
  console.log(`${route.padEnd(10)} ${n} API requests in 10 idle seconds`);
}
await b.close();
