<script lang="ts">
	import { themeStore } from '$lib/theme.svelte';
	let { tone = 'surface' }: { tone?: 'surface' | 'brand' } = $props();
</script>

<button
	type="button"
	class="theme-toggle"
	class:on-brand={tone === 'brand'}
	aria-label="Dark mode"
	aria-pressed={themeStore.current === 'dark'}
	title={themeStore.current === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
	onclick={() => themeStore.toggle()}
>
	<svg viewBox="0 0 24 24" aria-hidden="true">
		{#if themeStore.current === 'dark'}
			<circle cx="12" cy="12" r="4" />
			<path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5" />
		{:else}
			<path d="M20.4 14.5A9 9 0 0 1 9.5 3.6a9 9 0 1 0 10.9 10.9Z" />
		{/if}
	</svg>
	<span>Dark mode</span>
</button>

<style>
	.theme-toggle { display: inline-flex; flex: none; align-items: center; justify-content: center; gap: .45rem; min-height: 2.75rem; padding: .45rem .65rem; border: 1px solid var(--control-border); background: var(--paper); color: var(--ink); font: 700 .62rem var(--font-mono); text-transform: uppercase; white-space: nowrap; cursor: pointer; }
	.theme-toggle:hover { background: var(--paper-deep); }
	.theme-toggle[aria-pressed='true'] { box-shadow: inset 0 -2px var(--cobalt); }
	.theme-toggle:focus-visible { outline: 2px solid var(--cobalt-bright); outline-offset: 3px; }
	.theme-toggle.on-brand { background: transparent; color: var(--on-brand); border-color: rgb(255 255 255 / 45%); }
	.theme-toggle.on-brand:hover, .theme-toggle.on-brand[aria-pressed='true'] { background: rgb(255 255 255 / 14%); }
	.theme-toggle.on-brand:focus-visible { outline-color: var(--on-brand); }
	svg { width: 1.1rem; height: 1.1rem; fill: none; stroke: currentColor; stroke-width: 1.7; stroke-linecap: round; stroke-linejoin: round; }
	@media (max-width: 48rem) { .theme-toggle { width: 2.75rem; padding: .5rem; } span { display: none; } }
</style>
