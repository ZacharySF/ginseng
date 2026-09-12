// Ginseng is served as a single static bundle (adapter-static, fallback: 'index.html').
// SvelteKit only reads page options (ssr, prerender) from route module files, never
// from +layout.svelte / +page.svelte, so this file is required alongside +layout.svelte.
export const ssr = false;
export const prerender = false;
