<script lang="ts">
	import { type Snippet } from 'svelte';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { authStore } from '$lib/auth.svelte';
	import AgentChat from '$lib/components/AgentChat.svelte';
	import { scenarioStore } from '$lib/scenario.svelte';
	import { financialStore } from '$lib/finance.svelte';
	import type { ChatContext, DemoChatContext } from '$lib/chat';

	type AppRoute = '/' | '/future' | '/liquidity' | '/plans' | '/data' | '/demo' | '/demo/future' | '/demo/liquidity' | '/demo/plans';
	type NavIcon = 'workspace' | 'data' | 'demo' | 'events' | 'reserve' | 'funding';

	interface NavItem {
		label: string;
		shortLabel: string;
		href: AppRoute;
		icon: NavIcon;
		kind?: 'back';
	}

	interface Props {
		children: Snippet;
	}

	let { children }: Props = $props();
	let isSigningOut = $state(false);

	const personalNavItems: NavItem[] = [
		{ label: 'Overview', shortLabel: 'Overview', href: '/', icon: 'workspace' },
		{ label: 'Events', shortLabel: 'Events', href: '/future', icon: 'events' },
		{ label: 'Reserve', shortLabel: 'Reserve', href: '/liquidity', icon: 'reserve' },
		{ label: 'Funding', shortLabel: 'Funding', href: '/plans', icon: 'funding' },
		{ label: 'Data', shortLabel: 'Data', href: '/data', icon: 'data' },
		{ label: 'Try an example', shortLabel: 'Example', href: '/demo', icon: 'demo' }
	];
	const demoNavItems: NavItem[] = [
		{ label: 'Overview', shortLabel: 'Overview', href: '/demo', icon: 'demo' },
		{ label: 'Events', shortLabel: 'Events', href: '/demo/future', icon: 'events' },
		{ label: 'Reserve', shortLabel: 'Reserve', href: '/demo/liquidity', icon: 'reserve' },
		{ label: 'Funding', shortLabel: 'Funding', href: '/demo/plans', icon: 'funding' },
		{ label: 'Back to my workspace', shortLabel: 'Back', href: '/', icon: 'workspace', kind: 'back' }
	];
	const demoRoot = resolve('/demo');
	const isDemoRoute = $derived(
		page.url.pathname === demoRoot || page.url.pathname.startsWith(`${demoRoot}/`)
	);
	const navItems = $derived(isDemoRoute ? demoNavItems : personalNavItems);
	const navHeading = $derived(isDemoRoute ? 'Example scenario' : 'My workspace');

	function isChatHorizon(value: number): value is DemoChatContext['horizon_days'] {
		return value === 14 || value === 30 || value === 60;
	}

	function currentDemoContext(): ChatContext | null {
		const response = scenarioStore.response;
		const request = scenarioStore.request;
		if (
			scenarioStore.loadState !== 'ready' ||
			!response ||
			!isChatHorizon(request.horizon_days) ||
			![
				response.coverage_target,
				response.operating_buffer,
				response.funding_gap,
				response.required_liquidity_reserve,
				response.coverage_at_current_funding
			].every(Number.isFinite) ||
			!request.obligations.every(
				(obligation) =>
					obligation.label.trim().length > 0 &&
					Number.isFinite(obligation.amount) &&
					Number.isInteger(obligation.due_in_days)
			)
		) {
			return null;
		}
		return {
			source: 'demo',
			scenario: {
				horizon_days: request.horizon_days,
				coverage_target: response.coverage_target,
				operating_buffer: response.operating_buffer,
				funding_gap: response.funding_gap,
				required_liquidity_reserve: response.required_liquidity_reserve,
				coverage_at_current_funding: response.coverage_at_current_funding,
				obligations: request.obligations.map(({ label, amount, due_in_days }) => ({ label, amount, due_in_days }))
			}
		};
	}

	function currentPersonalContext(): ChatContext | null {
		const workspace = financialStore.workspace;
		if (!workspace || !isChatHorizon(financialStore.horizonDays)) return null;
		return {
			source: 'personal',
			horizon_days: financialStore.horizonDays,
			expected_revision: workspace.revision,
			...(financialStore.scenario === null ? {} : { overrides: financialStore.scenario })
		};
	}

	const chatContext: ChatContext | null = $derived(
		isDemoRoute ? currentDemoContext() : currentPersonalContext()
	);

	function isActive(href: AppRoute) {
		return page.url.pathname === resolve(href);
	}

	async function signOut(): Promise<void> {
		if (isSigningOut) return;
		isSigningOut = true;
		try {
			await authStore.signOut();
		} catch {
			authStore.error = 'Could not sign out. Check your connection and try again.';
		} finally {
			isSigningOut = false;
		}
	}
</script>

<div class="terminal-shell">
	<header class="terminal-topbar">
		<a class="terminal-brand" href={resolve('/')} aria-label="Ginseng workspace">
			<span class="brand-mark" aria-hidden="true"><img src="/brand/ginseng-avatar-reversed.svg" alt="" /></span>
			<span>Ginseng</span>
		</a>
		<div class="topbar-context">
			<span>{isDemoRoute ? 'Synthetic example' : 'Personal workspace'}</span>
		</div>
		<div class="topbar-actions">
			<p class:topbar-status--demo={isDemoRoute} class="topbar-status"><i aria-hidden="true"></i>{isDemoRoute ? 'Synthetic example data' : 'Saved personal inputs'}</p>
			{#key `${authStore.user?.id ?? 'signed-out'}-${isDemoRoute ? 'demo' : 'personal'}`}
				<AgentChat context={chatContext} />
			{/key}
			{#if authStore.status === 'signed-in' && authStore.user}
				<div class="account-chip">
					<span class="account-email">{authStore.displayName ?? authStore.user.email}</span>
					<button type="button" onclick={signOut} disabled={isSigningOut}>{isSigningOut ? 'Signing out…' : 'Sign out'}</button>
				</div>
			{/if}
		</div>
		{#if authStore.error}<p class="signout-error" role="alert">{authStore.error}</p>{/if}
	</header>

	<aside class="terminal-rail">
		<p class="rail-heading">{navHeading}</p>
		<nav aria-label={isDemoRoute ? 'Example navigation' : 'Personal navigation'}>
			{#each navItems as item (item.href)}
				<a
					class="rail-link"
					class:rail-link--active={isActive(item.href)}
					class:rail-link--back={item.kind === 'back'}
					href={resolve(item.href)}
					aria-current={isActive(item.href) ? 'page' : undefined}
					title={item.label}
				>
					<svg aria-hidden="true" viewBox="0 0 24 24">
						{#if item.icon === 'workspace'}
							<path d="M4 19V5m0 14h16M7 15l3-4 3 2 5-7" />
						{:else if item.icon === 'demo'}
							<rect x="4" y="5" width="16" height="15" rx="2" />
							<path d="m10 10 5 2-5 2v-4Z" />
						{:else if item.icon === 'events'}
							<rect x="4" y="5" width="16" height="15" rx="2" />
							<path d="M8 3v4m8-4v4M4 10h16m-8 3v4m-3-2h6" />
						{:else if item.icon === 'reserve'}
							<path d="M12 3 19 6v5c0 4.3-2.9 7.6-7 10-4.1-2.4-7-5.7-7-10V6l7-3Z" />
							<path d="M9 12h6m-3-3v6" />
						{:else if item.icon === 'funding'}
							<path d="M5 7h14M5 12h14M5 17h14" />
							<circle cx="8" cy="7" r="1.5" />
							<circle cx="15" cy="12" r="1.5" />
							<circle cx="10" cy="17" r="1.5" />
						{:else}
							<path d="M5 5h14v14H5z" />
							<path d="M8 9h8M8 13h8M8 17h5" />
						{/if}
					</svg>
					<span class="rail-link-label">{item.label}</span>
				</a>
			{/each}
		</nav>
		<p class="rail-meta">
			{#if isDemoRoute}
				Synthetic example<br />not personal data
			{:else}
				Saved personal<br />plan
			{/if}
		</p>
	</aside>

	<main class="app-main">
		{@render children()}
	</main>

	<nav
		class="mobile-nav"
		class:mobile-nav--demo={isDemoRoute}
		class:mobile-nav--personal={!isDemoRoute}
		aria-label={isDemoRoute ? 'Example navigation' : 'Personal navigation'}
	>
		{#each navItems as item (item.href)}
			<a
				class="mobile-nav-link"
				class:mobile-nav-link--active={isActive(item.href)}
				class:mobile-nav-link--back={item.kind === 'back'}
				href={resolve(item.href)}
				aria-label={item.label}
				aria-current={isActive(item.href) ? 'page' : undefined}
			>
				<span>{item.shortLabel}</span>
			</a>
		{/each}
	</nav>
</div>

<style>
	.terminal-shell {
		display: grid;
		grid-template-columns: 10.75rem minmax(0, 1fr);
		grid-template-rows: 3.25rem minmax(0, 1fr);
		height: 100dvh;
		background: var(--cobalt);
	}

	.terminal-topbar {
		position: relative;
		grid-column: 1 / -1;
		display: flex;
		align-items: center;
		gap: 1rem;
		min-width: 0;
		padding: 0 1rem;
		background: var(--cobalt-deep);
		border-bottom: 1px solid rgb(255 255 255 / 28%);
		color: var(--paper);
	}

	.terminal-brand {
		display: inline-flex;
		align-items: center;
		gap: 0.55rem;
		flex: none;
		min-height: 2.75rem;
		color: var(--paper);
		font-family: var(--font-sans);
		font-size: 1rem;
		font-weight: 800;
		letter-spacing: -0.04em;
		text-decoration: none;
	}

	.brand-mark {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 1.4rem;
		height: 1.4rem;
	}

	.brand-mark img {
		width: 100%;
		height: 100%;
		object-fit: contain;
	}

	.topbar-context,
	.topbar-status,
	.rail-meta {
		color: rgb(255 255 255 / 74%);
		font-family: var(--font-mono);
		font-size: 0.62rem;
		letter-spacing: 0.06em;
		text-transform: uppercase;
	}

	.topbar-context {
		display: flex;
		flex: 1 1 auto;
		gap: 0.45rem;
		min-width: 0;
		white-space: nowrap;
	}

	.topbar-actions {
		display: flex;
		align-items: center;
		gap: 0.9rem;
		margin-left: auto;
	}

	.topbar-status {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
		white-space: nowrap;
	}

	.topbar-status i {
		width: 0.45rem;
		height: 0.45rem;
		background: #b8c7ff;
		border-radius: 50%;
		box-shadow: 0 0 0 2px rgb(184 199 255 / 20%);
	}

	.topbar-status--demo i {
		background: var(--paper);
		box-shadow: 0 0 0 2px rgb(255 255 255 / 20%);
	}

	.account-chip {
		display: flex;
		align-items: center;
		gap: 0.55rem;
		padding-left: 0.9rem;
		border-left: 1px solid rgb(255 255 255 / 28%);
	}

	.account-email {
		overflow: hidden;
		max-width: 12rem;
		color: rgb(255 255 255 / 74%);
		font-family: var(--font-mono);
		font-size: 0.62rem;
		letter-spacing: 0.04em;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.account-chip button {
		min-height: 2.75rem;
		padding: 0 0.55rem;
		background: transparent;
		border: 1px solid rgb(255 255 255 / 32%);
		color: var(--paper);
		font-family: var(--font-mono);
		font-size: 0.62rem;
		font-weight: 700;
		letter-spacing: 0.03em;
		text-transform: uppercase;
		cursor: pointer;
	}

	.account-chip button:hover:not(:disabled) {
		background: rgb(255 255 255 / 14%);
		border-color: rgb(255 255 255 / 55%);
	}

	.account-chip button:disabled {
		cursor: wait;
		opacity: 0.65;
	}

	.signout-error {
		position: absolute;
		z-index: 11;
		top: calc(100% + 0.45rem);
		right: 1rem;
		max-width: min(28rem, calc(100vw - 2rem));
		margin: 0;
		padding: 0.5rem 0.65rem;
		background: var(--negative);
		border: 1px solid var(--paper);
		color: var(--paper);
		font-size: 0.78rem;
	}

	.terminal-rail {
		display: flex;
		flex-direction: column;
		align-items: stretch;
		background: var(--cobalt);
		border-right: 1px solid rgb(255 255 255 / 30%);
	}

	.rail-heading {
		margin: 0;
		padding: 0.95rem 0.85rem 0.35rem;
		color: rgb(255 255 255 / 74%);
		font-family: var(--font-mono);
		font-size: 0.62rem;
		font-weight: 700;
		letter-spacing: 0.06em;
		text-transform: uppercase;
	}

	.terminal-rail nav {
		display: grid;
		gap: 0.35rem;
		padding: 0.35rem 0.55rem 0.55rem;
	}

	.rail-link {
		display: grid;
		grid-template-columns: 1.2rem minmax(0, 1fr);
		align-items: center;
		gap: 0.65rem;
		min-height: 2.8rem;
		padding: 0 0.7rem;
		border: 1px solid transparent;
		color: rgb(255 255 255 / 70%);
		font-family: var(--font-mono);
		font-size: 0.65rem;
		font-weight: 700;
		letter-spacing: 0.025em;
		line-height: 1.2;
		text-decoration: none;
		text-transform: uppercase;
		transition: background-color 160ms ease, color 160ms ease, transform 160ms ease;
	}

	.rail-link svg {
		width: 1.2rem;
		height: 1.2rem;
		fill: none;
		stroke: currentColor;
		stroke-width: 1.75;
		stroke-linecap: round;
		stroke-linejoin: round;
	}

	.rail-link-label {
		min-width: 0;
		overflow-wrap: anywhere;
	}

	.rail-link:hover {
		background: rgb(255 255 255 / 15%);
		color: var(--paper);
	}

	.rail-link:active { transform: scale(0.97); }

	.terminal-brand:focus-visible,
	.account-chip button:focus-visible,
	.rail-link:focus-visible,
	.mobile-nav-link:focus-visible {
		outline: 2px solid var(--paper);
		outline-offset: 2px;
	}

	.rail-link--active {
		background: var(--paper);
		border-color: var(--paper);
		color: var(--cobalt);
	}

	.rail-link--back {
		margin-top: 0.35rem;
		border-top-color: rgb(255 255 255 / 30%);
	}

	.rail-meta {
		margin: auto 0 0;
		padding: 0.9rem 0.85rem;
		border-top: 1px solid rgb(255 255 255 / 25%);
		font-size: 0.53rem;
		line-height: 1.5;
		text-align: left;
	}

	.app-main {
		min-width: 0;
		min-height: 0;
		width: 100%;
		background: var(--paper);
		overflow-y: auto;
	}

	.mobile-nav { display: none; }

	@media (max-width: 48rem) {
		.terminal-shell {
			display: block;
			height: auto;
			min-height: 100dvh;
			padding-bottom: 4.9rem;
		}

		.terminal-topbar {
			position: sticky;
			z-index: 5;
			top: 0;
			min-height: 3rem;
			padding: 0 0.8rem;
		}

		.topbar-context {
			min-width: 0;
			overflow: hidden;
			text-overflow: ellipsis;
		}

		.topbar-status { display: none; }

		.account-chip { padding-left: 0; border-left: 0; }
		.account-email { display: none; }

		.terminal-rail { display: none; }
		.app-main { width: 100%; overflow-y: visible; }

		.mobile-nav {
			position: fixed;
			z-index: 10;
			right: 0;
			bottom: 0;
			left: 0;
			display: grid;
			grid-template-columns: repeat(4, minmax(0, 1fr));
			padding: 0.3rem max(0.45rem, env(safe-area-inset-right)) calc(0.3rem + env(safe-area-inset-bottom)) max(0.45rem, env(safe-area-inset-left));
			background: var(--cobalt-deep);
			border-top: 1px solid rgb(255 255 255 / 28%);
		}

		.mobile-nav--demo {
			grid-template-columns: repeat(5, minmax(0, 1fr));
		}

		.mobile-nav--personal {
			grid-template-columns: repeat(6, minmax(0, 1fr));
		}

		.mobile-nav-link {
			display: grid;
			min-width: 0;
			min-height: 2.8rem;
			place-items: center;
			padding: 0 0.2rem;
			color: rgb(255 255 255 / 70%);
			font-family: var(--font-mono);
			font-size: 0.55rem;
			font-weight: 700;
			letter-spacing: 0.025em;
			line-height: 1.15;
			text-align: center;
			text-decoration: none;
			text-transform: uppercase;
		}

		.mobile-nav-link span {
			min-width: 0;
			overflow-wrap: anywhere;
		}

		.mobile-nav-link--active {
			background: var(--paper);
			color: var(--cobalt);
		}

		.mobile-nav-link--back {
			color: var(--paper);
		}
	}

	@media (max-width: 28rem) {
		.topbar-context { display: none; }
	}
</style>
