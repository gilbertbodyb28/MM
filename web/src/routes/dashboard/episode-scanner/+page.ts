import type { PageLoad } from './$types';
import client from '$lib/api';

export const load: PageLoad = async ({ fetch }) => {
	try {
		const { data } = await client.GET('/api/v1/episode-scanner/status', { fetch });
		if (data) return { status: data, statusError: null };
	} catch {
		// Fall through to the error state below.
	}
	return { status: null, statusError: 'Scannerns status kunde inte hämtas.' };
};
