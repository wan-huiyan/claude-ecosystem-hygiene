import puppeteer from "puppeteer";
import { fileURLToPath } from "url";
import { dirname, resolve } from "path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const htmlPath = resolve(__dirname, "demo-ecosystem-audit.html");

const browser = await puppeteer.launch({ headless: "new" });
const page = await browser.newPage();
await page.setViewport({ width: 1200, height: 1400, deviceScaleFactor: 2 });
await page.goto(`file://${htmlPath}`, { waitUntil: "networkidle0", timeout: 30000 });
await new Promise((r) => setTimeout(r, 2500)); // wait for fonts + any animations

// Force all radar/counter/bar animations to their final state
await page.evaluate(() => {
  document.querySelectorAll("section").forEach((s) => s.classList.add("visible"));
  document.querySelectorAll(".bar-fill[data-width]").forEach((el) => {
    el.style.width = el.dataset.width + "%";
  });
  document.querySelectorAll(".stat-number[data-target], .hero-stat-num[data-target]").forEach((el) => {
    el.textContent = el.dataset.target;
  });
});
await new Promise((r) => setTimeout(r, 500));

// Scroll to the radar section and capture the hero + radar together
await page.evaluate(() => {
  window.scrollTo(0, 0);
});

// Full-width screenshot of the top ~1500px (hero, radar, stats area)
await page.screenshot({
  path: resolve(__dirname, "demo-screenshot.png"),
  clip: { x: 0, y: 0, width: 1200, height: 1500 },
});

console.log("✓ demo-screenshot.png");
await browser.close();
