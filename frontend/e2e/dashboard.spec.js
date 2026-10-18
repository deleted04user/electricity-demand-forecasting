import { expect, test } from '@playwright/test'

function apiResponse(page, path, method = 'GET') {
  return page.waitForResponse(response =>
    new URL(response.url()).pathname === path && response.request().method() === method)
}

function futureTable(page) {
  return page.getByRole('table').filter({
    has: page.getByRole('columnheader', { name: 'Timestamp', exact: true }),
  })
}

test('dashboard renders real historical and recursive forecasts', async ({ page, request }) => {
  const browserErrors = []
  page.on('pageerror', error => browserErrors.push(error.message))

  const health = await request.get('/api/health')
  expect(health.ok()).toBeTruthy()
  expect(await health.json()).toMatchObject({ status: 'ok' })

  const overviewResponse = apiResponse(page, '/api/overview')
  await page.goto('/')
  await expect(page.getByRole('heading', { name: /Electricity Demand Forecasting/ })).toBeVisible()
  const overview = await (await overviewResponse).json()
  const observationCard = page.locator('.metric-card').filter({ hasText: 'Total Observations' })
  await expect(observationCard.locator('.metric-value')).toHaveText(overview.total_observations.toLocaleString('en-US'))

  const metaResponse = apiResponse(page, '/api/meta')
  const historicalResponse = apiResponse(page, '/api/forecast')
  await page.getByRole('button', { name: 'Forecast', exact: true }).click()
  const meta = await (await metaResponse).json()
  const historical = await (await historicalResponse).json()
  await expect(page.getByLabel('Date:')).toHaveValue(meta.max_date)
  const predictedCard = page.locator('.metric-card').filter({ hasText: 'Predicted Demand' })
  await expect(predictedCard.locator('.metric-value')).toHaveText(`${historical.predicted} MW`)

  // Changing the hour must request and display a different historical slice.
  const changedResponse = apiResponse(page, '/api/forecast')
  await page.getByRole('slider', { name: /Hour:/ }).press('ArrowRight')
  const changed = await changedResponse
  expect(new URL(changed.url()).searchParams.get('hour')).toBe('13')
  await expect(predictedCard.locator('.metric-value')).toHaveText(`${(await changed.json()).predicted} MW`)

  await page.getByLabel('Horizon (hours):').fill('3')
  const forecastResponse = apiResponse(page, '/api/forecast/future', 'POST')
  await page.getByRole('button', { name: 'Generate future forecast' }).click()
  const response = await forecastResponse
  expect(response.ok()).toBeTruthy()
  expect(response.request().postDataJSON()).toEqual({ start: meta.future_start, horizon: 3 })
  const forecast = await response.json()
  expect(forecast.forecast).toHaveLength(3)
  const rows = futureTable(page).locator('tbody tr')
  await expect(rows).toHaveCount(3)
  for (const [index, row] of forecast.forecast.entries()) {
    expect(Number.isFinite(row.predicted)).toBeTruthy()
    await expect(rows.nth(index).getByRole('cell').nth(0)).toHaveText(row.timestamp)
    await expect(rows.nth(index).getByRole('cell').nth(1)).toHaveText(String(row.predicted))
  }
  expect(browserErrors).toEqual([])
  await test.info().attach('forecast dashboard', {
    body: await page.screenshot({ fullPage: true }),
    contentType: 'image/png',
  })
})

test('failed forecast shows its error and recovers with a real API response', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'Forecast', exact: true }).click()
  const generate = page.getByRole('button', { name: 'Generate future forecast' })
  await expect(generate).toBeEnabled()
  await page.getByLabel('Horizon (hours):').fill('2')

  // Only the deliberate failure is intercepted. Recovery uses the live backend.
  await page.route('**/api/forecast/future', route => route.fulfill({
    status: 503,
    contentType: 'application/json',
    body: JSON.stringify({ detail: 'Forecast temporarily unavailable. Please try again.' }),
  }))
  await generate.click()
  await expect(page.locator('.error')).toHaveText('Forecast temporarily unavailable. Please try again.')
  await expect(generate).toBeEnabled()
  await expect(futureTable(page)).toHaveCount(0)

  await page.unroute('**/api/forecast/future')
  const recoveryResponse = apiResponse(page, '/api/forecast/future', 'POST')
  await generate.click()
  expect((await recoveryResponse).ok()).toBeTruthy()
  await expect(futureTable(page).locator('tbody tr')).toHaveCount(2)
  await expect(page.locator('.error')).toHaveCount(0)
})
