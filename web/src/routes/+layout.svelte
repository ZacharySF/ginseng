<script lang="ts">
	import '../app.css';
	import type { Snippet } from 'svelte';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { scenarioStore } from '$lib/scenario.svelte';

	type AppRoute = '/' | '/future' | '/liquidity' | '/plans';

	interface NavItem {
		label: string;
		shortLabel: string;
		href: AppRoute;
		index: string;
	}

	interface Props {
		children: Snippet;
	}

	let { children }: Props = $props();

	const navItems: NavItem[] = [
		{ label: 'Workspace', shortLabel: 'Work', href: '/', index: '01' },
		{ label: 'Events', shortLabel: 'Events', href: '/future', index: '02' },
		{ label: 'Reserve', shortLabel: 'Reserve', href: '/liquidity', index: '03' },
		{ label: 'Funding', shortLabel: 'Funding', href: '/plans', index: '04' }
	];

	function isActive(href: string) {
		return page.url.pathname === href;
	}
</script>

<div class="terminal-shell">
	<header class="terminal-topbar">
		<a class="terminal-brand" href={resolve('/')} aria-label="Ginseng workspace">
			<span class="brand-mark" aria-hidden="true"><span></span><span></span><span></span></span>
			<span>Ginseng</span>
		</a>
		<div class="topbar-context">
			<span>Cash workspace</span>
			<span aria-hidden="true">/</span>
			<span>{scenarioStore.request.horizon_days} day forward view</span>
		</div>
		<p class="topbar-status"><i aria-hidden="true"></i>Model ready</p>
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
					{item.index}
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
		grid-template-columns: 3.45rem minmax(0, 1fr);
		grid-template-rows: 3rem minmax(0, 1fr);
		height: 100dvh;
		background: #050505;
	}

	.terminal-topbar {
		grid-column: 1 / -1;
		display: flex;
		align-items: center;
		gap: 1rem;
		min-width: 0;
		padding: 0 0.8rem;
		background: #0c0c0d;
		border-bottom: 1px solid #28282b;
		color: #e9e9eb;
	}

	.terminal-brand {
		display: inline-flex;
		align-items: center;
		gap: 0.55rem;
		flex: none;
		color: #f5f5f6;
		font-size: 0.9rem;
		font-weight: 760;
		letter-spacing: -0.04em;
		text-decoration: none;
	}

	.brand-mark {
		display: inline-flex;
		align-items: end;
		gap: 2px;
		width: 1rem;
		height: 1rem;
		padding: 2px;
		background: #f3f3f3;
		border-radius: 0.15rem;
	}

	.brand-mark span {
		flex: 1;
		background: #080809;
	}

	.brand-mark span:nth-child(1) {
		height: 40%;
	}

	.brand-mark span:nth-child(2) {
		height: 72%;
	}

	.brand-mark span:nth-child(3) {
		height: 100%;
	}

	.topbar-context,
	.topbar-status,
	.rail-meta {
		color: #86868b;
		font-family: var(--font-mono);
		font-size: 0.63rem;
		letter-spacing: 0.045em;
		text-transform: uppercase;
	}

	.topbar-context {
		display: flex;
		gap: 0.45rem;
		white-space: nowrap;
	}

	.topbar-status {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
		margin-left: auto;
		white-space: nowrap;
	}

	.topbar-status i {
		width: 0.4rem;
		height: 0.4rem;
		background: #38d3ba;
		border-radius: 50%;
	}

	.terminal-rail {
		display: flex;
		flex-direction: column;
		align-items: stretch;
		background: #0a0a0b;
		border-right: 1px solid #28282b;
	}

	.terminal-rail nav {
		display: grid;
		gap: 0.15rem;
		padding: 0.4rem;
	}

	.rail-link {
		display: grid;
		place-items: center;
		min-width: 2.5rem;
		min-height: 2.5rem;
		border: 1px solid transparent;
		border-radius: 0.25rem;
		color: #828288;
		font-family: var(--font-mono);
		font-size: 0.63rem;
		font-weight: 700;
		letter-spacing: 0.02em;
		text-decoration: none;
	}

	.rail-link:hover {
		background: #1a1a1c;
		border-color: #303034;
		color: #f2f2f3;
	}

	.rail-link--active {
		background: #29292c;
		border-color: #5b5b62;
		color: #fff;
	}

	.rail-meta {
		margin: auto 0 0;
		padding: 0.8rem 0.15rem;
		border-top: 1px solid #28282b;
		font-size: 0.55rem;
		line-height: 1.5;
		text-align: center;
	}

	.app-main {
		min-width: 0;
		min-height: 0;
		width: 100%;
		overflow-y: auto;
	}

	.mobile-nav {
		display: none;
	}

	@media (max-width: 48rem) {
		.terminal-shell {
			display: block;
			height: auto;
			min-height: 100dvh;
			padding-bottom: 4.65rem;
		}

		.terminal-topbar {
			position: sticky;
			z-index: 5;
			top: 0;
			min-height: 2.85rem;
			padding: 0 0.75rem;
		}

		.topbar-context {
			overflow: hidden;
			text-overflow: ellipsis;
		}

		.topbar-context span:last-child,
		.topbar-context span:nth-child(2),
		.topbar-status {
			display: none;
		}

		.terminal-rail {
			display: none;
		}

		.app-main {
			width: 100%;
			overflow-y: visible;
		}

		.mobile-nav {
			position: fixed;
			z-index: 10;
			right: 0;
			bottom: 0;
			left: 0;
			display: grid;
			grid-template-columns: repeat(4, 1fr);
			padding: 0.3rem max(0.45rem, env(safe-area-inset-right)) calc(0.3rem + env(safe-area-inset-bottom)) max(0.45rem, env(safe-area-inset-left));
			background: #111113;
			border-top: 1px solid #343439;
		}

		.mobile-nav-link {
			display: grid;
			place-items: center;
			min-height: 2.7rem;
			border-radius: 0.3rem;
			color: #98989e;
			font-size: 0.66rem;
			font-weight: 700;
			text-decoration: none;
		}

		.mobile-nav-link--active {
			background: #2b2b2f;
			color: #fff;
		}
	}
</style>
