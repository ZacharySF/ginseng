<script lang="ts">
	import { resolve } from '$app/paths';
	import { parallax } from '$lib/parallax';
	import { dotField } from '$lib/dotField';

	type StepIcon = 'workspace' | 'events' | 'reserve' | 'funding';

	interface Step {
		icon: StepIcon;
		title: string;
		body: string;
	}

	const steps: Step[] = [
		{
			icon: 'workspace',
			title: 'Model your account',
			body: '2,000 simulated cash paths project your next 14, 30, or 60 days from your real income and spending pattern.'
		},
		{
			icon: 'events',
			title: "Add what's coming",
			body: "Insert a real future obligation — a deposit, a bill, a repair. Today's cash and your portfolio stay untouched; only the timeline changes."
		},
		{
			icon: 'reserve',
			title: 'See the exact reserve',
			body: 'A running-minimum liquidity requirement at your coverage target, computed straight from the simulated paths.'
		},
		{
			icon: 'funding',
			title: 'Compare ways to close it',
			body: 'Credit, liquidation, and hybrid plans, evaluated on the exact same simulated future so the differences are real.'
		}
	];
</script>

<svelte:head>
	<title>Ginseng — Liquidity workspace</title>
	<meta
		name="description"
		content="Ginseng models the dollar amount your next 30 days actually require, and compares the ways to close the gap."
	/>
</svelte:head>

<div class="welcome">
	<div class="ambient-field" aria-hidden="true">
		<canvas {@attach dotField()}></canvas>
	</div>

	<header class="welcome-nav">
		<a class="nav-brand" href={resolve('/welcome')}>
			<span class="nav-mark" aria-hidden="true"><img src="/brand/ginseng-avatar-reversed.svg" alt="" /></span>
			<span>Ginseng</span>
		</a>
		<nav class="nav-actions" aria-label="Account">
			<a href={resolve('/login')}>Sign in</a>
			<a class="nav-cta" href={resolve('/login?mode=sign-up')}>Create account</a>
		</nav>
	</header>

	<section class="hero" {@attach parallax()}>
		<div class="hero-copy" data-parallax-strength="22 14">
			<p class="hero-kicker">Liquidity workspace</p>
			<h1>Ginseng</h1>
			<p class="hero-tagline">A timing problem, modeled.</p>
			<p class="hero-body">
				Variable-income earners can hold plenty of assets and still have a timing problem.
				Ginseng runs 2,000 simulated cash paths to show the dollar amount your next 30 days
				actually require — and compares the credit, liquidation, and hybrid ways to close the
				gap.
			</p>
			<div class="hero-actions">
				<a class="hero-cta" href={resolve('/login?mode=sign-up')}>Create free account</a>
				<a class="hero-secondary" href={resolve('/login')}>Sign in</a>
			</div>
		</div>
	</section>

	<section class="how" aria-labelledby="how-heading">
		<p class="section-kicker">How it works</p>
		<h2 id="how-heading">Four steps, one model.</h2>
		<div class="how-grid">
			{#each steps as step (step.title)}
				<article class="how-step">
					<span class="how-icon" aria-hidden="true">
						<svg viewBox="0 0 24 24">
							{#if step.icon === 'workspace'}
								<path d="M4 19V5m0 14h16M7 15l3-4 3 2 5-7" />
							{:else if step.icon === 'events'}
								<rect x="4" y="5" width="16" height="15" rx="2" />
								<path d="M8 3v4m8-4v4M4 10h16m-8 3v4m-3-2h6" />
							{:else if step.icon === 'reserve'}
								<path d="M12 3 19 6v5c0 4.3-2.9 7.6-7 10-4.1-2.4-7-5.7-7-10V6l7-3Z" />
								<path d="M9 12h6m-3-3v6" />
							{:else}
								<path d="M5 7h14M5 12h14M5 17h14" />
								<circle cx="8" cy="7" r="1.5" />
								<circle cx="15" cy="12" r="1.5" />
								<circle cx="10" cy="17" r="1.5" />
							{/if}
						</svg>
					</span>
					<h3>{step.title}</h3>
					<p>{step.body}</p>
				</article>
			{/each}
		</div>
	</section>

	<section class="frozen">
		<p class="frozen-statement">The market didn't change.<br />The person did.</p>
		<p class="frozen-body">
			Every plan comparison runs on the exact same simulated futures. Your portfolio value and
			volatility stay frozen beside a funding requirement that moved — because the shock was a
			future obligation, not a market event.
		</p>
	</section>

	<section class="final-cta">
		<h2>See your next 30 days.</h2>
		<a class="cta-button" href={resolve('/login?mode=sign-up')}>Create free account</a>
		<p class="final-note">No credit card. No bank connection required.</p>
	</section>

	<footer class="welcome-footer">
		<span class="footer-mark">Ginseng</span>
	</footer>
</div>

<style>
	.welcome {
		color: var(--ink);
	}

	.ambient-field {
		position: fixed;
		inset: 0;
		background: var(--cobalt-deep);
	}

	.ambient-field canvas {
		width: 100%;
		height: 100%;
		display: block;
	}

	.welcome-nav {
		position: sticky;
		z-index: 5;
		top: 0;
		display: flex;
		align-items: center;
		justify-content: space-between;
		min-height: 3.5rem;
		padding: 0 1.5rem;
		background: var(--cobalt-deep);
		border-bottom: 1px solid rgb(255 255 255 / 28%);
	}

	.nav-brand {
		display: inline-flex;
		align-items: center;
		gap: 0.55rem;
		color: var(--paper);
		font-family: var(--font-sans);
		font-size: 1rem;
		font-weight: 800;
		letter-spacing: -0.04em;
		text-decoration: none;
	}

	.nav-mark {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 1.4rem;
		height: 1.4rem;
	}

	.nav-mark img {
		width: 100%;
		height: 100%;
		object-fit: contain;
	}

	.nav-actions {
		display: flex;
		align-items: center;
		gap: 1rem;
	}

	.nav-actions a {
		color: rgb(255 255 255 / 82%);
		font-family: var(--font-mono);
		font-size: 0.72rem;
		font-weight: 700;
		letter-spacing: 0.03em;
		text-decoration: none;
		text-transform: uppercase;
	}

	.nav-actions a:hover { color: var(--paper); }

	.nav-actions a.nav-cta {
		padding: 0.5rem 0.85rem;
		background: var(--paper);
		color: var(--cobalt);
	}

	.nav-actions a.nav-cta:hover { background: var(--paper-deep); color: var(--cobalt); }

	.hero {
		position: relative;
		overflow: hidden;
		display: flex;
		align-items: center;
		min-height: calc(100dvh - 3.5rem);
		padding: 3rem 1.75rem;
		background: transparent;
	}

	.hero-copy {
		position: relative;
		display: grid;
		gap: 1.2rem;
		max-width: 42rem;
		margin: 0 auto;
		color: var(--paper);
		transform: translate3d(0, 0, 0);
		transition: transform 240ms cubic-bezier(0.23, 1, 0.32, 1);
		will-change: transform;
	}

	@media (prefers-reduced-motion: reduce) {
		.hero-copy { transition: none; }
	}


	.hero-kicker {
		margin: 0;
		color: rgb(255 255 255 / 74%);
		font-family: var(--font-mono);
		font-size: 0.72rem;
		font-weight: 700;
		letter-spacing: 0.08em;
		text-transform: uppercase;
	}

	.hero-copy h1 {
		margin: 0;
		font-size: clamp(2.6rem, 6vw, 4.8rem);
		font-weight: 800;
		letter-spacing: -0.035em;
		line-height: 0.98;
		text-wrap: balance;
	}

	.hero-tagline {
		margin: 0;
		color: rgb(255 255 255 / 88%);
		font-size: clamp(1.4rem, 2.4vw, 1.9rem);
		font-weight: 700;
		letter-spacing: -0.015em;
		text-wrap: balance;
	}

	.hero-body {
		margin: 0;
		max-width: 52ch;
		color: rgb(255 255 255 / 80%);
		font-size: 1.05rem;
		line-height: 1.55;
		text-wrap: pretty;
	}

	.hero-actions {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 1.1rem;
		margin-top: 0.4rem;
	}

	.hero-cta, .cta-button {
		display: inline-flex;
		align-items: center;
		min-height: 3rem;
		padding: 0 1.4rem;
		background: var(--paper);
		color: var(--cobalt);
		font-family: var(--font-mono);
		font-size: 0.76rem;
		font-weight: 700;
		letter-spacing: 0.04em;
		text-decoration: none;
		text-transform: uppercase;
		transition: background-color 160ms ease, transform 160ms ease;
	}

	.hero-cta:hover, .cta-button:hover { background: var(--paper-deep); }
	.hero-cta:active, .cta-button:active { transform: scale(0.98); }

	.hero-secondary {
		color: var(--paper);
		font-family: var(--font-mono);
		font-size: 0.76rem;
		font-weight: 700;
		letter-spacing: 0.04em;
		text-decoration: none;
		text-transform: uppercase;
		border-bottom: 1px solid rgb(255 255 255 / 40%);
	}

	.hero-secondary:hover { border-color: var(--paper); }

	.how {
		position: relative;
		padding: 5rem 1.75rem;
		max-width: 68rem;
		margin: 0 auto;
		background: var(--paper);
	}

	.section-kicker {
		margin: 0 0 0.4rem;
		color: var(--ink-muted);
		font-family: var(--font-mono);
		font-size: 0.68rem;
		font-weight: 700;
		letter-spacing: 0.08em;
		text-transform: uppercase;
	}

	.how h2 {
		margin: 0 0 2.5rem;
		max-width: 30ch;
		font-size: clamp(1.7rem, 3vw, 2.4rem);
		font-weight: 800;
		letter-spacing: -0.025em;
		text-wrap: balance;
	}

	.how-grid {
		display: grid;
		grid-template-columns: repeat(4, minmax(0, 1fr));
		gap: 2px;
		background: var(--rule);
		border: 1px solid var(--rule);
	}

	.how-step {
		display: grid;
		align-content: start;
		gap: 0.75rem;
		padding: 1.5rem 1.3rem;
		background: var(--paper);
	}

	.how-icon {
		display: grid;
		place-items: center;
		width: 2.6rem;
		height: 2.6rem;
		background: var(--cobalt);
	}

	.how-icon svg {
		width: 1.25rem;
		height: 1.25rem;
		fill: none;
		stroke: var(--paper);
		stroke-width: 1.75;
		stroke-linecap: round;
		stroke-linejoin: round;
	}

	.how-step h3 {
		margin: 0;
		color: var(--ink);
		font-size: 1rem;
		font-weight: 750;
		letter-spacing: -0.015em;
	}

	.how-step p {
		margin: 0;
		color: var(--ink-soft);
		font-size: 0.85rem;
		line-height: 1.5;
	}

	.frozen {
		position: relative;
		display: grid;
		place-items: center;
		gap: 1.2rem;
		padding: 6rem 1.75rem;
		background: rgb(0 0 0 / 55%);
		text-align: center;
	}

	.frozen-statement {
		margin: 0;
		max-width: 24ch;
		color: var(--paper);
		font-size: clamp(1.9rem, 4vw, 3rem);
		font-weight: 800;
		letter-spacing: -0.03em;
		line-height: 1.08;
		text-wrap: balance;
	}

	.frozen-body {
		margin: 0;
		max-width: 46ch;
		color: rgb(255 255 255 / 72%);
		font-size: 0.95rem;
		line-height: 1.55;
		text-wrap: pretty;
	}

	.final-cta {
		position: relative;
		display: grid;
		place-items: center;
		gap: 1.1rem;
		padding: 6rem 1.75rem;
		background: var(--paper);
		text-align: center;
	}

	.final-cta h2 {
		margin: 0;
		font-size: clamp(1.8rem, 3.4vw, 2.6rem);
		font-weight: 800;
		letter-spacing: -0.03em;
	}

	.final-note {
		margin: 0;
		color: var(--ink-muted);
		font-size: 0.82rem;
	}

	.welcome-footer {
		position: relative;
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.55rem;
		padding: 1.6rem;
		border-top: 1px solid var(--rule);
		background: var(--paper);
		color: var(--ink-muted);
		font-family: var(--font-mono);
		font-size: 0.7rem;
		font-weight: 700;
		letter-spacing: 0.04em;
		text-transform: uppercase;
	}


	@media (max-width: 64rem) {
		.how-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
	}

	@media (max-width: 48rem) {
		.welcome-nav { padding: 0 1rem; }
		.hero { padding: 2.5rem 1.25rem; align-items: start; min-height: auto; padding-top: 3.5rem; padding-bottom: 3.5rem; }
		.how { padding: 3.5rem 1.25rem; }
		.how-grid { grid-template-columns: 1fr; }
		.frozen { padding: 4rem 1.25rem; }
		.final-cta { padding: 4rem 1.25rem; }
	}
</style>
