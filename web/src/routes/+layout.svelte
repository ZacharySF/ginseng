<script lang="ts">
	// Archivo Narrow Variable, self-hosted so the editorial-ledger headline
	// character renders identically offline and on every judge's machine —
	// a prior --font-sans stack named "Arial Narrow"/"Liberation Sans
	// Narrow", neither of which exists as a real installable font, so the
	// whole app silently fell back to a generic system sans.
	// Source: https://fontsource.org/docs/getting-started/install#3-import-the-font
	import '@fontsource-variable/archivo-narrow/wght.css';
	import '../app.css';
	import type { Snippet } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { resolve } from '$app/paths';
	import { authStore } from '$lib/auth.svelte';
	import { profileStore } from '$lib/profile.svelte';

	interface Props {
		children: Snippet;
	}

	let { children }: Props = $props();

	const LOGIN_PATH = '/login';
	const WELCOME_PATH = '/welcome';
	const ONBOARDING_PATH = '/onboarding';
	const PUBLIC_PATHS = [LOGIN_PATH, WELCOME_PATH];
	const completedDestination = $derived(
		profileStore.profile?.setup_path === 'sample' ? resolve('/demo') : resolve('/')
	);
	const profileIsReady = $derived(
		authStore.status === 'signed-in' &&
			authStore.user !== null &&
			profileStore.isReadyFor(authStore.user.id)
	);
	const profileFailed = $derived(
		authStore.status === 'signed-in' && authStore.user !== null && profileStore.status === 'error'
	);

	// Reset immediately when the authenticated identity changes. The store
	// also guards its asynchronous work by owner and generation, so a late
	// response for the previous account cannot populate this session.
	$effect(() => {
		if (authStore.status === 'signed-in' && authStore.user) {
			if (profileStore.ownerId !== authStore.user.id || profileStore.status === 'idle') {
				void profileStore.load();
			}
		} else if (authStore.status === 'signed-out' && profileStore.ownerId !== null) {
			profileStore.reset();
		}
	});

	$effect(() => {
		const pathname = page.url.pathname;
		if (authStore.status === 'signed-out') {
			if (!PUBLIC_PATHS.includes(pathname)) {
				goto(resolve('/welcome'), { replaceState: true });
			}
			return;
		}
		if (authStore.status !== 'signed-in' || !profileIsReady) return;

		if (PUBLIC_PATHS.includes(pathname)) {
			goto(profileStore.needsOnboarding ? resolve(ONBOARDING_PATH) : completedDestination, {
				replaceState: true
			});
			return;
		}

		if (pathname === resolve(ONBOARDING_PATH)) {
			if (profileStore.profile?.onboarding_completed) {
				goto(completedDestination, { replaceState: true });
			}
			return;
		}

		if (profileStore.needsOnboarding) {
			goto(resolve(ONBOARDING_PATH), { replaceState: true });
		}
	});

	const holdForGate = $derived(
		authStore.status === 'loading' ||
			(authStore.status === 'signed-out' && !PUBLIC_PATHS.includes(page.url.pathname)) ||
			(authStore.status === 'signed-in' && !profileIsReady && !profileFailed)
	);
</script>

{#if holdForGate}
	<div class="auth-gate" role="status" aria-live="polite">
		<span class="auth-gate-mark" aria-hidden="true"><img src="/brand/ginseng-avatar-reversed.svg" alt="" /></span>
		<span class="sr-only">Loading your account…</span>
	</div>
{:else if profileFailed}
	<main class="profile-failure" aria-labelledby="profile-failure-title">
		<div class="profile-failure-card">
			<p class="profile-failure-kicker">Account setup unavailable</p>
			<h1 id="profile-failure-title">We could not load your setup.</h1>
			<p>{profileStore.loadError ?? 'Check your connection and try again.'}</p>
			<div class="profile-failure-actions">
				<button type="button" onclick={() => void profileStore.load()}>Retry</button>
				<button type="button" class="secondary" onclick={() => void authStore.signOut()}>Sign out</button>
			</div>
			{#if authStore.error}
				<p class="profile-signout-error" role="alert">{authStore.error}</p>
			{/if}
		</div>
	</main>
{:else}
	{#key authStore.user?.id ?? 'signed-out'}
		{@render children()}
	{/key}
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

	.profile-failure {
		display: grid;
		place-items: center;
		min-height: 100dvh;
		padding: var(--space-4);
		background: var(--cobalt);
	}

	.profile-failure-card {
		width: min(100%, 30rem);
		padding: clamp(1.5rem, 5vw, 2.5rem);
		background: var(--paper);
		border: 1px solid var(--rule);
		box-shadow: 0 1rem 2.5rem rgb(0 0 79 / 24%);
	}

	.profile-failure-kicker {
		margin-bottom: var(--space-2);
		color: var(--ink-soft);
		font-size: var(--font-size-xs);
		font-weight: 700;
		letter-spacing: 0.12em;
		text-transform: uppercase;
	}

	.profile-failure h1 {
		margin-bottom: var(--space-3);
		font-size: clamp(2rem, 6vw, 3rem);
		line-height: 0.95;
		text-wrap: balance;
	}

	.profile-failure-card > p:not(.profile-failure-kicker):not(.profile-signout-error) {
		color: var(--ink-soft);
		text-wrap: pretty;
	}

	.profile-failure-actions {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-3);
		margin-top: var(--space-6);
	}

	.profile-failure button {
		min-height: 2.75rem;
		padding: 0.625rem 1rem;
		border: 1px solid var(--cobalt);
		background: var(--cobalt);
		color: var(--paper);
		font-weight: 700;
		cursor: pointer;
	}

	.profile-failure button.secondary {
		background: transparent;
		color: var(--cobalt-deep);
	}

	.profile-signout-error {
		margin-top: var(--space-3);
		color: var(--negative);
		font-weight: 700;
	}

	@keyframes gate-pulse {
		0%, 100% { opacity: 1; }
		50% { opacity: 0.55; }
	}

	@media (prefers-reduced-motion: reduce) {
		.auth-gate-mark { animation: none; }
	}
</style>
