// Optional browser regression, run against a local production preview (not StrictMode dev).
// Uses an existing Playwright installation; does not add app dependencies or contact a backend.
const assert = require('node:assert/strict');
const { chromium } = require(process.env.BM_PLAYWRIGHT_MODULE || 'playwright');
const origin = process.env.BM_UI_ORIGIN || 'http://127.0.0.1:5187';
assert(['localhost', '127.0.0.1'].includes(new URL(origin).hostname), 'Use a local preview only');

const product = {
  id: 1,
  name: 'UI fixture',
  sku: 'qa-only',
  price: '100.00',
  unit: 'pcs',
  min_quantity: '1.000',
  quantity_step: '1.000',
  description: '',
  image: null,
  categories: [],
  is_available: true,
};
const calendar = {
  timezone: 'Europe/Moscow',
  generated_at: '2026-11-21T10:00:00+03:00',
  preparation_minutes: 60,
  configured: true,
  days: Array.from({ length: 8 }, (_, i) => ({
    date: `2026-11-${21 + i}`,
    weekday: 'Тестовый день',
    slots:
      i > 1
        ? []
        : ['11:30', '13:00'].map((time) => ({
            time,
            at: `2026-11-${21 + i}T${time}:00+03:00`,
            available: true,
          })),
  })),
};

async function run() {
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.BM_BROWSER_EXECUTABLE
      ? { executablePath: process.env.BM_BROWSER_EXECUTABLE }
      : {}),
  });
  try {
    for (const width of [320, 390]) {
      const context = await browser.newContext({
        viewport: { width, height: 844 },
        timezoneId: 'Pacific/Auckland',
        reducedMotion: 'reduce',
      });
      const unexpected = [],
        errors = [];
      await context.route('https://telegram.org/**', (route) => route.abort());
      await context.route('**/api/**', async (route) => {
        const path = new URL(route.request().url()).pathname;
        let data;
        if (route.request().method() !== 'GET')
          unexpected.push(route.request().method() + ' ' + path);
        if (path === '/api/session/')
          data = {
            authenticated: true,
            csrf_token: 'ui-only',
            checkout_enabled: true,
            weight_estimate: true,
            user: { id: '999900001', first_name: 'QA', phone: '+70000000000', photo_url: null },
            store: { address: 'UI fixture', phone: null, email: null },
          };
        else if (path === '/api/cart/')
          data = { revision: 1, items: [{ product_id: 1, quantity: '1.000', product }] };
        else if (path === '/api/pickup-slots/') data = calendar;
        else if (path === '/api/products/1/') data = product;
        else if (path === '/api/products/')
          data = { count: 1, next: null, previous: null, results: [product] };
        else {
          unexpected.push(path);
          data = {};
        }
        await route.fulfill({ contentType: 'application/json', body: JSON.stringify(data) });
      });
      const page = await context.newPage();
      page.on('pageerror', (error) => errors.push(error.message));
      await page.goto(origin + '/checkout');
      assert(
        (await page.locator('script[type=module]').first().getAttribute('src')).includes(
          '/assets/',
        ),
        'Build and use vite preview: development StrictMode can mask hidden-dialog scroll failures',
      );
      const field = page.locator('.pickup-field');
      const dialog = page.locator('dialog.pickup-sheet');
      const hour = page.getByRole('listbox', { name: 'Часы', exact: true });
      const minute = page.getByRole('listbox', { name: 'Минуты', exact: true });
      const apply = page.getByRole('button', { name: 'Выбрать время', exact: true });
      await field.waitFor();
      await page.waitForFunction(
        () => !document.querySelector('.pickup-field').textContent.includes('Проверяем'),
      );
      await field.click();
      await page.waitForFunction(
        () => document.querySelector('.pickup-sheet-footer button')?.disabled === false,
      );
      // The first available slot is :30. The visual center must agree with aria-selected immediately.
      assert.equal(await minute.getByRole('option', { selected: true }).innerText(), '30');
      assert.equal(await minute.evaluate((el) => el.scrollTop), 44);
      await minute.evaluate((el) => el.scrollTo({ top: 0, behavior: 'instant' }));
      await page.waitForFunction(
        () => document.querySelectorAll('.pickup-wheel')[1].scrollTop === 44,
      );
      assert.deepEqual(await hour.getByRole('option').allTextContents(), ['11', '13']);
      await hour.focus();
      await page.keyboard.press('End');
      await page.waitForFunction(
        () => document.querySelector('.pickup-wheel [aria-selected=true]').textContent === '13',
      );
      assert.equal(await minute.getByRole('option', { selected: true }).innerText(), '00');
      await apply.click();
      await dialog.waitFor({ state: 'hidden' });
      assert((await field.innerText()).includes('21.11.2026, 13:00'));
      assert(await field.evaluate((el) => document.activeElement === el));
      await field.click();
      await page.waitForFunction(
        () => document.querySelector('.pickup-sheet-footer button')?.disabled === false,
      );
      assert.equal(await hour.evaluate((el) => el.scrollTop), 44);
      await page.keyboard.press('Escape');
      await dialog.waitFor({ state: 'hidden' });
      assert((await field.innerText()).includes('13:00'));
      assert.deepEqual(unexpected, []);
      assert.deepEqual(errors, []);
      console.log(
        `PASS production first :30, invalid minute, hour, reopen, cancel, focus at ${width}px`,
      );
      await context.close();
    }
  } finally {
    await browser.close();
  }
}
run().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
