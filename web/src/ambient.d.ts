// Ambient module declarations for SvelteKit environment variables and enhanced images

declare module '$env/dynamic/public' {
	export const env: {
		PUBLIC_API_URL: string;
		[key: string]: string | undefined;
	};
}

declare module '$env/static/public' {
	export const PUBLIC_VERSION: string;
	export const PUBLIC_API_URL: string;
}

// Enhanced image module declarations
declare module '*?enhanced' {
	const value: unknown;
	export default value;
}
