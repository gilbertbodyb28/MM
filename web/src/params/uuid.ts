import type { ParamMatcher } from '@sveltejs/kit';
import { validate as uuidValidate } from 'uuid';

export const match = ((param: string) => {
	return uuidValidate(param);
}) satisfies ParamMatcher;
