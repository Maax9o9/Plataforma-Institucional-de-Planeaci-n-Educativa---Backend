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
      for (const theme of ['light', 'dark']) {
        for (const width of [320, 375, 600, 720, 1024, 1440]) {
          await page.emulateMedia({ colorScheme: theme });
          await page.setViewportSize({ width, height: 900 });
          await page.setContent(await fs.readFile(path.join(directory, file), 'utf8'));
          const layout = await page.evaluate(() => {
            const rgb = value => value.match(/[\d.]+/g).slice(0, 3).map(Number);
            const luminance = value => rgb(value).map(n => {
              const v = n / 255;
              return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
            }).reduce((sum, v, i) => sum + v * [0.2126, 0.7152, 0.0722][i], 0);
            const contrast = (foreground, background) => {
              const a = luminance(foreground), b = luminance(background);
              return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
            };
            const color = selector => getComputedStyle(document.querySelector(selector)).color;
            const background = selector => getComputedStyle(document.querySelector(selector)).backgroundColor;
            return {
              width: innerWidth,
              scroll: document.documentElement.scrollWidth,
              cardWidth: document.querySelector('.email-card').getBoundingClientRect().width,
              canvas: background('.canvas'),
              logo: background('.logo-plate'),
              contrast: {
                footer: contrast(color('.footer-copy'), background('.footer')),
                privacy: contrast(color('.footer-link'), background('.footer')),
                button: contrast(color('.cta-link'), background('.cta-cell')),
                // Worst-case hero: white dragon behind the least opaque gradient stop.
                copy: contrast(color('.copy'), 'rgb(51, 62, 159)'),
                label: contrast(color('.label'), 'rgb(51, 62, 159)'),
              },
              brokenImages: [...document.images].filter(image => !image.complete || !image.naturalWidth).length,
            };
          });
          if (layout.scroll > width || layout.brokenImages || layout.cardWidth > 721 ||
              (width >= 1024 && Math.abs(layout.cardWidth - 720) > 1) ||
              layout.logo !== 'rgb(255, 255, 255)' ||
              (theme === 'dark' && layout.canvas !== 'rgb(13, 18, 32)') ||
              Object.values(layout.contrast).some(value => value < 4.5)) {
            throw new Error(`${file} ${theme} at ${width}px: ${JSON.stringify(layout)}`);
          }
          if (['invitacion.html', 'poa_captura_7d.html'].includes(file) && [375, 1024].includes(width)) {
            await page.screenshot({ path: path.join(directory, `${file}-${theme}-${width}.png`), fullPage: true });
          }
          checked++;
        }
      }
    }
    console.log(`Verified ${checked} light/dark layouts across ${files.length} templates, including contrast and desktop width.`);

    // Simulations only: not an Outlook/Gmail device test or their complete sanitizer.
    const sample = await fs.readFile(path.join(directory, 'poa_captura_7d.html'), 'utf8');
    await page.emulateMedia({ colorScheme: 'light' });
    for (const mode of ['outlook-dark', 'gmail-inversion']) {
      await page.setViewportSize({ width: 375, height: 900 });
      await page.setContent(sample);
      await page.evaluate(mode => {
        if (mode === 'outlook-dark') {
          document.body.setAttribute('data-ogsc', '');
          document.body.setAttribute('data-ogsb', '');
        } else {
          const wrapper = document.createElement('div');
          wrapper.className = 'email-body';
          wrapper.append(...document.body.childNodes);
          document.body.append(document.createElement('u'), wrapper);
          document.querySelectorAll('.gmail-screen,.gmail-difference').forEach(el => {
            el.style.backgroundColor = '#ffffff';
          });
          document.querySelectorAll('.greeting,.title,.copy,.label,.fallback,.fallback a').forEach(el => {
            el.style.setProperty('color', '#000000', 'important');
          });
          document.querySelector('.canvas').style.backgroundColor = '#0d1220';
          document.querySelector('.footer').style.backgroundColor = '#181e32';
          document.querySelectorAll('.footer-copy,.footer-link').forEach(el => el.style.color = '#ffffff');
          document.querySelector('.cta-cell').style.backgroundColor = '#124941';
          document.querySelector('.cta-link').style.color = '#ffffff';
        }
      }, mode);
      const state = await page.evaluate(() => ({
        scroll: document.documentElement.scrollWidth,
        footer: getComputedStyle(document.querySelector('.footer')).backgroundColor,
        blend: getComputedStyle(document.querySelector('.gmail-difference')).mixBlendMode,
      }));
      if (state.scroll > 375 || state.footer !== 'rgb(24, 30, 50)' ||
          (mode === 'gmail-inversion' && state.blend !== 'difference')) {
        throw new Error(`Simulation ${mode}: ${JSON.stringify(state)}`);
      }
      await page.screenshot({ path: path.join(directory, `simulation-${mode}-375.png`), fullPage: true });
    }
    console.log('Verified two additional targeted-client simulations (not real mail clients).');
    for (const theme of ['light', 'dark']) {
      for (const width of [320, 1440]) {
        await page.emulateMedia({ colorScheme: theme });
        await page.setViewportSize({ width, height: 900 });
        await page.setContent(sample);
        await page.evaluate(() => {
          document.querySelector('.greeting').textContent = 'N'.repeat(150);
          document.querySelector('.title').textContent = 'T'.repeat(160);
          document.querySelector('.copy').textContent = 'C'.repeat(6000);
          document.querySelector('.cta-link').textContent = 'B'.repeat(60);
        });
        if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)) {
          throw new Error(`Long custom text overflows in ${theme} at ${width}px`);
        }
      }
    }
    console.log('Verified four maximum-length custom-text layouts without horizontal overflow.');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
