import type { PageLoad } from './$types';
import client from '$lib/api';

export const load: PageLoad = async ({ fetch, parent }) => {
	const { user } = await parent();
	const usersPromise = user?.is_superuser
		? client.GET('/api/v1/users/all', { fetch }).then(({ data }) => data ?? [])
		: Promise.resolve([]);

	let integrations = null;
	let integrationError: string | null = null;
	if (user?.is_superuser) {
		try {
			const response = await fetch('/api/v1/settings/integrations');
			if (response.ok) integrations = await response.json();
			else integrationError = 'MediaManager could not load the saved integration settings.';
		} catch {
			integrationError = 'MediaManager could not load the saved integration settings.';
		}
	}

	let recommendationMapping = null;
	let mappingError: string | null = null;
	try {
		const response = await fetch('/api/v1/settings/recommendation-mapping/me');
		if (response.ok) recommendationMapping = await response.json();
		else mappingError = 'MediaManager could not load your recommendation profile.';
	} catch {
		mappingError = 'MediaManager could not load your recommendation profile.';
	}

	return {
		users: await usersPromise,
		integrations,
		integrationError,
		recommendationMapping,
		mappingError
	};
};
