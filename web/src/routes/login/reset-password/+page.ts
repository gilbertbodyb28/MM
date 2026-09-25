export function load({ url }) {
	console.log('got token: ', url.searchParams.get('token'));
	return { token: url.searchParams.get('token') };
}
