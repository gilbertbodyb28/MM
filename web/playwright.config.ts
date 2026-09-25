import { defineConfig } from '@playwright/test';

export default defineConfig({
	testDir: './tests/visual',

	fullyParallel: false,
	workers: 1,

	use: {
		baseURL: 'http://127.0.0.1:5173',
		browserName: 'chromium',

		storageState: 'playwright/.auth/user.json',

		viewport: {
			width: 1448,
			height: 1086
		},

		deviceScaleFactor: 1,

		screenshot: 'only-on-failure',
		trace: 'retain-on-failure',
		video: 'off'
	},

	webServer: {
		command: 'npm run dev',
		url: 'http://127.0.0.1:5173',
		reuseExistingServer: true,
		timeout: 120000
	}
});
