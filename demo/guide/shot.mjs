// Takes the screenshots of the demo guide. Runs inside the Playwright image against the demo stack on the host:
//   ./capture.sh   (Git Bash, macOS, Linux)    or    ./capture.ps1   (PowerShell)
import { chromium } from "playwright";

const HOST = process.env.HOST ?? "host.docker.internal";
const APP = `http://${HOST}:8080`, PANEL = `http://${HOST}:8090`, MAIL = `http://${HOST}:8025`;
const out = process.argv[2];
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();
const snap = async (name, opts = {}) => {
  await page.waitForTimeout(opts.wait ?? 2500);
  await page.screenshot({ path: `${out}/${name}.png`, fullPage: opts.full ?? false });
  console.log(name);
};
const act = (node, action) => fetch(`${PANEL}/act`, { method: "POST", body: JSON.stringify({ node, action }) });
const sleep = (s) => new Promise((r) => setTimeout(r, s * 1000));
const hiveLink = async (n) => {
  await page.goto(APP);
  await page.waitForSelector("a[href^='/colmena/']");
  const links = await page.$$eval("a[href^='/colmena/']", (a) => a.map((x) => x.getAttribute("href")));
  const names = await page.$$eval("a[href^='/colmena/']", (a) => a.map((x) => x.textContent));
  return links[names.findIndex((t) => t.includes(`Hive ${n}`))];
};

await page.goto(`${APP}/auth`);
await snap("01-login", { wait: 1500 });
await page.fill('input[type="email"]', "demo@smarthive.dev");
await page.fill('input[type="password"]', "SmartHive-Demo-2026");
await page.click('button[type="submit"]');
await page.waitForSelector("a[href^='/colmena/']", { timeout: 20000 });
await snap("02-dashboard-calm");

await page.goto(`${APP}${await hiveLink(3)}`);
await snap("03-hive-anomaly", { full: true, wait: 4000 });

await page.goto(PANEL);
await snap("04-control-panel", { wait: 1500 });

// the scenarios, all at once; the alerts need a couple of minutes to build up
for (const [n, a] of [["sim-0002", "hornet"], ["sim-0001", "varroa"], ["sim-0005", "heat"], ["sim-0004", "off"], ["sim-0003", "shb"]]) await act(n, a);
await sleep(200);
await page.goto(PANEL);
await snap("05-control-panel-running", { wait: 1500 });
await page.goto(APP);
await snap("06-dashboard-alerts", { wait: 4000 });
await page.goto(`${APP}${await hiveLink(2)}`);
await snap("07-hive-hornet", { full: true, wait: 4000 });
await page.goto(`${APP}/alertas`);
await snap("08-alerts", { full: true });
const first = await page.$("a[href^='/alertas/']");
if (first) { await first.click(); await snap("09-alert-detail", { full: true, wait: 3000 }); }
await page.goto(MAIL);
await snap("10-mailpit", { wait: 3000 });
const mail = await page.$("a.message, .message a, [href*='/view/']");
if (mail) { await mail.click(); await snap("11-email", { wait: 3000 }); }
await page.goto(`${APP}/gestion`);
await snap("12-setup", { full: true });
await page.goto(`${APP}/api/v1/docs`);
await snap("13-api-docs", { wait: 3000 });
await browser.close();
