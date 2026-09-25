import { env } from '$env/dynamic/public';
import type { PageLoad } from './$types';

export type CalendarMediaType = 'movie' | 'episode';

export interface CalendarItem {
	id: string;
	media_type: CalendarMediaType;
	media_id: string;
	poster_id: string | null;
	season_id: string | null;
	name: string;
	episode_title: string | null;
	overview: string | null;
	release_date: string;
	season_number: number | null;
	episode_number: number | null;
	available: boolean;
}

function calendarEndpoint(): string {
	const baseUrl = env.PUBLIC_API_URL?.replace(/\/$/, '') ?? '';
	return `${baseUrl}/api/v1/calendar`;
}

export const load: PageLoad = async ({ fetch }) => {
	try {
		const response = await fetch(calendarEndpoint(), {
			headers: { Accept: 'application/json' },
			credentials: 'include'
		});

		if (!response.ok) {
			return {
				items: [] as CalendarItem[],
				loadError: `The release calendar could not be loaded (${response.status}).`
			};
		}

		const payload: unknown = await response.json();
		const items = Array.isArray(payload)
			? payload
			: typeof payload === 'object' && payload !== null && 'items' in payload
				? (payload as { items?: unknown }).items
				: [];

		return {
			items: (Array.isArray(items) ? items : []) as CalendarItem[],
			loadError: null
		};
	} catch (error) {
		console.error('Failed to load release calendar', error);
		return {
			items: [] as CalendarItem[],
			loadError: 'The release calendar is temporarily unavailable.'
		};
	}
};
