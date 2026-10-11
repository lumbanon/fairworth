import { test, expect } from '@playwright/test'

test('landing page renders demo data without runtime errors or horizontal overflow', async ({
  page,
}, testInfo) => {
  const errors = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(
    'Understand What a Stock Is Worth.',
  )
  await expect(
    page.getByText(
      'Illustrative data — not live market prices or actual valuations.',
    ),
  ).toBeVisible()
  await expect(page.locator('.recharts-surface')).toBeVisible()
  await page.evaluate(() => document.fonts.ready)
  await page.screenshot({
    path: `test-results/preview-${testInfo.project.name}.png`,
    fullPage: true,
  })
  await page.screenshot({
    path: `test-results/preview-${testInfo.project.name}-top.png`,
  })
  for (const width of [320, 390, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    await expect
      .poll(() =>
        page.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth,
        ),
      )
      .toBe(true)
  }
  await page
    .getByRole('heading', { name: 'Value has more than one lens.' })
    .scrollIntoViewIfNeeded()
  await expect(
    page.getByRole('row', { name: /REIT AFFO Valuation/ }),
  ).toBeVisible()
  expect(errors).toEqual([])
})

test('search normalizes tickers and supports Enter', async ({ page }) => {
  await page.goto('/')
  const search = page.getByRole('combobox', {
    name: 'Search by company or ticker',
    exact: true,
  })
  await search.fill('  msft  ')
  await expect(search).toHaveValue('  MSFT  ')
  await search.press('Enter')
  await expect(page).toHaveURL('/stocks/MSFT')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(
    'Microsoft Corporation (MSFT)',
  )
  await expect(
    page.getByText('Demo financial data — not live market information.'),
  ).toBeVisible()
})

test('search reports empty and malformed tickers and accepts share classes', async ({
  page,
}) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'Search stock', exact: true }).click()
  await expect(page.getByRole('alert')).toHaveText(
    'Enter a company name or ticker to get started.',
  )
  const search = page.getByRole('combobox', {
    name: 'Search by company or ticker',
    exact: true,
  })
  await search.fill('AAA123')
  await search.press('Enter')
  await expect(page.getByRole('alert')).toContainText('Use 1–5 letters')
  await expect(search).toHaveAttribute('aria-invalid', 'true')
  await search.fill('brk.b')
  await search.press('Enter')
  await expect(page).toHaveURL('/stocks/BRK.B')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(
    'No demo dataset for BRK.B.',
  )
})

test('company suggestions work with keyboard and pointer', async ({ page }) => {
  await page.goto('/')
  const search = page.getByRole('combobox', {
    name: 'Search by company or ticker',
    exact: true,
  })
  await search.fill('nvidia')
  await expect(page.getByRole('option', { name: /NVDA NVIDIA/ })).toBeVisible()
  await search.press('ArrowDown')
  await expect(search).toHaveAttribute('aria-activedescendant', /option-0/)
  await search.press('Enter')
  await expect(page).toHaveURL('/stocks/NVDA')
  await page.goto('/')
  await search.fill('Apple')
  await page.getByRole('option', { name: /AAPL Apple/ }).click()
  await expect(page).toHaveURL('/stocks/AAPL')
})

test('navigation scrolls to sections and mobile menu supports Escape', async ({
  page,
}, testInfo) => {
  await page.goto('/')
  const mobile = testInfo.project.name === 'mobile'
  if (mobile) {
    const toggle = page.locator('.mobile-toggle')
    await toggle.click()
    await expect(toggle).toHaveAttribute('aria-expanded', 'true')
    await page.keyboard.press('Escape')
    await expect(toggle).toHaveAttribute('aria-expanded', 'false')
    await expect(toggle).toBeFocused()
    await toggle.click()
  }
  const nav = page.getByRole('navigation', {
    name: mobile ? 'Mobile navigation' : 'Main navigation',
    exact: true,
  })
  await nav.getByRole('link', { name: 'Features', exact: true }).click()
  await expect(page).toHaveURL('/#features')
  await expect(
    page.getByRole('heading', { name: 'More context. Better conviction.' }),
  ).toBeInViewport()
  if (mobile)
    await expect(
      page.getByRole('button', { name: 'Open navigation menu' }),
    ).toHaveAttribute('aria-expanded', 'false')
  await expect(page.locator('.site-header')).toBeInViewport()
})

test('model filters show appropriate methods and retain all 12 in the default view', async ({
  page,
}) => {
  await page.goto('/#valuation-models')
  const table = page.getByRole('table').nth(1)
  await expect(table.getByRole('row')).toHaveCount(13)
  await page.getByRole('button', { name: 'Cash flow', exact: true }).click()
  await expect(table.getByRole('row')).toHaveCount(3)
  await expect(page.getByText('2 methods · planned')).toBeVisible()
  await page.getByRole('button', { name: 'Specialized', exact: true }).click()
  await expect(table.getByRole('row', { name: /Reverse DCF/ })).toBeVisible()
  await page.getByRole('button', { name: 'All models', exact: true }).click()
  await expect(table.getByRole('row')).toHaveCount(13)
})

test('CTA and footer links lead to clearly labeled routes', async ({
  page,
}) => {
  await page.goto('/')
  for (const label of ['Analyze a Stock', 'Start Analyzing']) {
    await page.getByRole('link', { name: label, exact: true }).click()
    await expect(page).toHaveURL('/dashboard')
    await expect(
      page.getByRole('heading', { name: 'Valuation overview' }),
    ).toBeVisible()
    await page.goto('/')
  }
  for (const [label, route, heading] of [
    ['Methodology', 'methodology', 'Methodology'],
    ['About', 'about', 'About Fairworth'],
    ['Privacy Policy', 'privacy', 'Privacy Policy'],
    ['Terms of Service', 'terms', 'Terms of Service'],
  ]) {
    await page
      .getByRole('contentinfo')
      .getByRole('link', { name: label, exact: true })
      .click()
    await expect(page).toHaveURL(`/${route}`)
    await expect(page.getByRole('heading', { level: 1 })).toHaveText(heading)
    await page.goto('/')
  }
  await page.goto('/signin')
  await expect(
    page.getByText(/Authentication and user accounts are not implemented/),
  ).toBeVisible()
  await page.getByRole('link', { name: 'Explore the Preview' }).click()
  await expect(page).toHaveURL('/dashboard')
  await page
    .getByRole('combobox', { name: 'Search by company or ticker', exact: true })
    .fill('oracle')
  await page
    .getByRole('combobox', { name: 'Search by company or ticker', exact: true })
    .press('Enter')
  await expect(page).toHaveURL('/stocks/ORCL')
  await page
    .getByRole('navigation', { name: 'Research navigation' })
    .getByRole('link', { name: 'Dashboard', exact: true })
    .click()
  await expect(page).toHaveURL('/dashboard')
})

test('direct routes handle invalid tickers and unknown pages', async ({
  page,
}) => {
  await page.goto('/stocks/123')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(
    'That ticker format isn’t supported.',
  )
  await page.goto('/unknown/page')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(
    'Page not found',
  )
})
