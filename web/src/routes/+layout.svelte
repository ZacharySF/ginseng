<script lang="ts">
	import '../app.css';
	import type { Snippet } from 'svelte';
	import { page } from '$app/state';

	interface NavItem {
		label: string;
		href: string;
	}

	interface Props {
		children: Snippet;
	}

	let { children }: Props = $props();

	const navItems: NavItem[] = [
		{ label: 'Today', href: '/' },
		{ label: 'Future', href: '/future' },
		{ label: 'Liquidity', href: '/liquidity' },
		{ label: 'Plans', href: '/plans' }
	];
</script>

<div class="app-shell">
	<header class="app-header">
		<span class="app-title">Ginseng</span>
		<nav class="app-nav" aria-label="Primary">
			{#each navItems as item (item.label)}
				{@const isActive = page.url.pathname === item.href}
				<a
					class="nav-link"
					class:nav-link--active={isActive}
					href={item.href}
					aria-current={isActive ? 'page' : undefined}
				>
					{item.label}
				</a>
			{/each}
		</nav>
	</header>
	<main class="app-main">
		{@render children()}
	</main>
</div>

<style>
	.app-shell {
		min-height: 100%;
		display: flex;
		flex-direction: column;
	}

	.app-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: var(--space-5) var(--space-6);
		border-bottom: 1px solid var(--color-border);
	}

	.app-title {
		font-size: var(--font-size-lg);
		font-weight: 700;
		letter-spacing: 0.02em;
	}

	.app-nav {
		display: flex;
		gap: var(--space-6);
	}

	.nav-link {
		font-size: var(--font-size-sm);
		font-weight: 600;
		letter-spacing: 0.03em;
		text-transform: uppercase;
		text-decoration: none;
		padding-block: var(--space-1);
	}

	.nav-link--active {
		color: var(--color-text);
		border-bottom: 2px solid var(--color-accent);
	}

	.nav-link:focus-visible {
		outline: 2px solid var(--color-accent);
		outline-offset: 4px;
	}

	.app-main {
		flex: 1;
		width: 100%;
		max-width: 960px;
		margin: 0 auto;
		padding: var(--space-7) var(--space-6);
	}
</style>
