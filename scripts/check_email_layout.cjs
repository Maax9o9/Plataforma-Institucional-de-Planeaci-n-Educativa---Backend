// Prueba local de presentación en Chromium. No sustituye ensayos en clientes de correo.
const { chromium } = require('playwright');
const fs = require('node:fs/promises');
const path = require('node:path');

(async () => {
  const directory = path.resolve(process.argv[2] || 'var/email-previews');
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const page = await browser.newPage();
    await page.route('https://**/*', route => route.abort());
    const files = (await fs.readdir(directory)).filter(name => name.endsWith('.html'));
    let checked = 0;
    for (const file of files) {
      for (const width of [320, 375, 600, 1024]) {
        await page.setViewportSize({ width, height: 900 });
        await page.setContent(await fs.readFile(path.join(directory, file), 'utf8'));
        const layout = await page.evaluate(() => ({
          width: innerWidth,
          scroll: document.documentElement.scrollWidth,
          brokenImages: [...document.images].filter(image => !image.complete || !image.naturalWidth).length,
        }));
        if (layout.scroll > width || layout.brokenImages) {
          throw new Error(`${file} at ${width}px: ${JSON.stringify(layout)}`);
        }
        if (['invitacion.html', 'poa_captura_7d.html'].includes(file) && [375, 1024].includes(width)) {
          await page.screenshot({ path: path.join(directory, `${file}-${width}.png`), fullPage: true });
        }
        checked++;
      }
    }
    console.log(`Verified ${checked} layouts across ${files.length} templates.`);
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
