<script lang="ts">
	import type { Snippet } from 'svelte';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { authStore } from '$lib/auth.svelte';
	import { scenarioStore } from '$lib/scenario.svelte';

	type AppRoute = '/' | '/future' | '/liquidity' | '/plans';
	type NavIcon = 'workspace' | 'events' | 'reserve' | 'funding';

	interface NavItem {
		label: string;
		shortLabel: string;
		href: AppRoute;
		icon: NavIcon;
	}

	interface Props {
		children: Snippet;
	}

	let { children }: Props = $props();

	const navItems: NavItem[] = [
		{ label: 'Workspace', shortLabel: 'Work', href: '/', icon: 'workspace' },
		{ label: 'Events', shortLabel: 'Events', href: '/future', icon: 'events' },
		{ label: 'Reserve', shortLabel: 'Reserve', href: '/liquidity', icon: 'reserve' },
		{ label: 'Funding', shortLabel: 'Funding', href: '/plans', icon: 'funding' }
	];

	function isActive(href: string) {
		return page.url.pathname === href;
	}
</script>

<div class="terminal-shell">
	<header class="terminal-topbar">
		<a class="terminal-brand" href={resolve('/')} aria-label="Ginseng workspace">
			<span class="brand-mark" aria-hidden="true"><img src="/brand/ginseng-avatar-reversed.svg" alt="" /></span>
			<span>Ginseng</span>
		</a>
		<div class="topbar-context">
			<span>Cash workspace</span>
			<span aria-hidden="true">/</span>
			<span>{scenarioStore.request.horizon_days} day forward view</span>
		</div>
		<div class="topbar-actions">
			<p class="topbar-status"><i aria-hidden="true"></i>Model ready</p>
			{#if authStore.status === 'signed-in' && authStore.user}
				<div class="account-chip">
					<span class="account-email">{authStore.displayName ?? authStore.user.email}</span>
					<button type="button" onclick={() => authStore.signOut()}>Sign out</button>
				</div>
			{/if}
		</div>
	</header>

	<aside class="terminal-rail">
		<nav aria-label="Primary">
			{#each navItems as item (item.href)}
				<a
					class="rail-link"
					class:rail-link--active={isActive(item.href)}
					href={resolve(item.href)}
					aria-current={isActive(item.href) ? 'page' : undefined}
					aria-label={item.label}
					title={item.label}
				>
					<svg aria-hidden="true" viewBox="0 0 24 24">
						{#if item.icon === 'workspace'}
							<path d="M4 19V5m0 14h16M7 15l3-4 3 2 5-7" />
						{:else if item.icon === 'events'}
							<rect x="4" y="5" width="16" height="15" rx="2" />
							<path d="M8 3v4m8-4v4M4 10h16m-8 3v4m-3-2h6" />
						{:else if item.icon === 'reserve'}
							<path d="M12 3 19 6v5c0 4.3-2.9 7.6-7 10-4.1-2.4-7-5.7-7-10V6l7-3Z" />
							<path d="M9 12h6m-3-3v6" />
						{:else}
							<path d="M5 7h14M5 12h14M5 17h14" />
							<circle cx="8" cy="7" r="1.5" />
							<circle cx="15" cy="12" r="1.5" />
							<circle cx="10" cy="17" r="1.5" />
						{/if}
					</svg>
				</a>
			{/each}
		</nav>
		<p class="rail-meta">{scenarioStore.request.paths.toLocaleString()}<br />paths</p>
	</aside>

	<main class="app-main">
		{@render children()}
	</main>

	<nav class="mobile-nav" aria-label="Primary">
		{#each navItems as item (item.href)}
			<a
				class="mobile-nav-link"
				class:mobile-nav-link--active={isActive(item.href)}
				href={resolve(item.href)}
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
		grid-template-columns: 4rem minmax(0, 1fr);
		grid-template-rows: 3.25rem minmax(0, 1fr);
		height: 100dvh;
		background: var(--cobalt);
	}

	.terminal-topbar {
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
		gap: 0.6rem;
		flex: none;
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
		width: 1.7rem;
		height: 1.7rem;
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
		gap: 0.45rem;
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
		min-height: 1.9rem;
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

	.account-chip button:hover {
		background: rgb(255 255 255 / 14%);
		border-color: rgb(255 255 255 / 55%);
	}

	.terminal-rail {
		display: flex;
		flex-direction: column;
		align-items: stretch;
		background: var(--cobalt);
		border-right: 1px solid rgb(255 255 255 / 30%);
	}

	.terminal-rail nav {
		display: grid;
		gap: 0.35rem;
		padding: 0.55rem;
	}

	.rail-link {
		display: grid;
		place-items: center;
		min-width: 2.85rem;
		min-height: 2.85rem;
		border: 1px solid transparent;
		color: rgb(255 255 255 / 70%);
		text-decoration: none;
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

	.rail-link:hover {
		background: rgb(255 255 255 / 15%);
		color: var(--paper);
	}

	.rail-link:active { transform: scale(0.97); }

	.rail-link--active {
		background: var(--paper);
		border-color: var(--paper);
		color: var(--cobalt);
	}

	.rail-meta {
		margin: auto 0 0;
		padding: 0.9rem 0.15rem;
		border-top: 1px solid rgb(255 255 255 / 25%);
		font-size: 0.53rem;
		line-height: 1.5;
		text-align: center;
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
			overflow: hidden;
			text-overflow: ellipsis;
		}

		.topbar-context span:last-child,
		.topbar-context span:nth-child(2),
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
			grid-template-columns: repeat(4, 1fr);
			padding: 0.3rem max(0.45rem, env(safe-area-inset-right)) calc(0.3rem + env(safe-area-inset-bottom)) max(0.45rem, env(safe-area-inset-left));
			background: var(--cobalt-deep);
			border-top: 1px solid rgb(255 255 255 / 28%);
		}

		.mobile-nav-link {
			display: grid;
			place-items: center;
			min-height: 2.8rem;
			color: rgb(255 255 255 / 70%);
			font-family: var(--font-mono);
			font-size: 0.63rem;
			font-weight: 700;
			letter-spacing: 0.045em;
			text-decoration: none;
			text-transform: uppercase;
		}

		.mobile-nav-link--active {
			background: var(--paper);
			color: var(--cobalt);
		}
	}
</style>
