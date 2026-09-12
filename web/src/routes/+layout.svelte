<script lang="ts">
	// Archivo Narrow Variable, self-hosted so the editorial-ledger headline
	// character renders identically offline and on every judge's machine —
	// a prior --font-sans stack named "Arial Narrow"/"Liberation Sans
	// Narrow", neither of which exists as a real installable font, so the
	// whole app silently fell back to a generic system sans.
	// Source: https://fontsource.org/docs/getting-started/install#3-import-the-font
	import '@fontsource-variable/archivo-narrow/wght.css';
	import '@fontsource/playfair-display/700.css';
	import '@fontsource/playfair-display/700-italic.css';
	import '../app.css';
	import type { Snippet } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { resolve } from '$app/paths';
	import { authStore } from '$lib/auth.svelte';

	interface Props {
		children: Snippet;
	}

	let { children }: Props = $props();

	const LOGIN_PATH = '/login';
	const WELCOME_PATH = '/welcome';
	const PUBLIC_PATHS = [LOGIN_PATH, WELCOME_PATH];

	// Every route below `/` needs a signed-in session except the public
	// marketing/auth pair; `unconfigured` (no Supabase env at all, e.g.
	// local dev without `web/.env`) bypasses the gate so the offline
	// cash-model demo keeps working without an account. Signed-out
	// visitors land on the landing page, not straight on the form — the
	// landing page's own CTAs link into `/login`.
	$effect(() => {
		if (authStore.status === 'signed-out' && !PUBLIC_PATHS.includes(page.url.pathname)) {
			goto(resolve('/welcome'), { replaceState: true });
		} else if (authStore.status === 'signed-in' && PUBLIC_PATHS.includes(page.url.pathname)) {
			goto(resolve('/'), { replaceState: true });
		}
	});

	const holdForGate = $derived(
		authStore.status === 'loading' ||
			(authStore.status === 'signed-out' && !PUBLIC_PATHS.includes(page.url.pathname)) ||
			(authStore.status === 'signed-in' && PUBLIC_PATHS.includes(page.url.pathname))
	);
</script>

{#if holdForGate}
	<div class="auth-gate" role="status" aria-live="polite">
		<span class="auth-gate-mark" aria-hidden="true"><img src="/brand/ginseng-avatar-reversed.svg" alt="" /></span>
	</div>
{:else}
	{@render children()}
{/if}

<style>
	.auth-gate {
		display: grid;
		place-items: center;
		min-height: 100dvh;
		background: var(--cobalt);
	}

	.auth-gate-mark {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 2.4rem;
		height: 2.4rem;
		animation: gate-pulse 1.1s ease-in-out infinite;
	}

	.auth-gate-mark img { width: 100%; height: 100%; object-fit: contain; }

	@keyframes gate-pulse {
		0%, 100% { opacity: 1; }
		50% { opacity: 0.55; }
	}

	@media (prefers-reduced-motion: reduce) {
		.auth-gate-mark { animation: none; }
	}
</style>
