import { test, expect } from '@playwright/test';

test('MediaManager Sol Ultra visual target', async ({ page }) => {
	await page.goto('/', {
		waitUntil: 'domcontentloaded'
	});

	// Wait for fonts.
	await page.evaluate(async () => {
		await document.fonts.ready;
	});

	// Disable CSS motion that can create unstable screenshots.
	await page.addStyleTag({
		content: `
			*,
			*::before,
			*::after {
				animation-duration: 0s !important;
				animation-delay: 0s !important;
				transition-duration: 0s !important;
				transition-delay: 0s !important;
				scroll-behavior: auto !important;
			}
		`
	});

	// Give asynchronous UI, images and dashboard widgets time to settle.
	await page.waitForTimeout(4000);

	await expect(page).toHaveScreenshot('sol-ultra.png', {
		fullPage: false,
		animations: 'disabled',
		caret: 'hide',
		timeout: 15000
	});
});
