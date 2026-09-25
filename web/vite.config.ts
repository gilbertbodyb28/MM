import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';
import { enhancedImages } from '@sveltejs/enhanced-img';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig(() => ({
	plugins: [tailwindcss(), enhancedImages(), sveltekit()],
	server: {
		host: '0.0.0.0', // Allow external connections (required for Docker)
		port: 5173,
		strictPort: true, // Fail if port is already in use
		watch: {
			usePolling: true, // Required for file watching in Docker on some systems
			interval: 100 // Check for changes every 100ms
		},
		proxy: {
			// Use same-origin API requests in development to avoid browser CORS differences
			// between localhost, 127.0.0.1 and the Docker frontend hostname.
			'/api': {
				target: process.env.VITE_API_PROXY_TARGET ?? 'http://127.0.0.1:8000',
				changeOrigin: true
			}
		}
	}
}));
