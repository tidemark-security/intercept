const path = require("path");
const { chromium } = require("/home/tidemark/projects/intercept/frontend/node_modules/playwright");

const options = ["bands", "dock", "tasks", "swimlane", "health"];

(async () => {
  const outDir = __dirname;
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1050 }, deviceScaleFactor: 1 });
  const fileUrl = `file://${path.join(outDir, "index.html")}`;
  await page.goto(fileUrl, { waitUntil: "networkidle" });

  for (const option of options) {
    await page.evaluate((activeOption) => {
      const tab = document.querySelector(`[data-option="${activeOption}"]`);
      if (tab instanceof HTMLButtonElement) {
        tab.click();
      }
    }, option);
    await page.waitForTimeout(100);
    await page.screenshot({
      path: path.join(outDir, `option-${options.indexOf(option) + 1}-${option}.png`),
      fullPage: true,
    });
  }

  await browser.close();
})();
