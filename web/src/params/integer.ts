import type { ParamMatcher } from '@sveltejs/kit';

export const match = ((param: string) => {
	return Number.isInteger(parseInt(param, 10));
}) satisfies ParamMatcher;
