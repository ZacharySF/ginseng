<script lang="ts">
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { authStore } from '$lib/auth.svelte';
	import { parallax } from '$lib/parallax';
	import { dotField } from '$lib/dotField';

	type Mode = 'sign-in' | 'sign-up';

	let mode = $state<Mode>(page.url.searchParams.get('mode') === 'sign-up' ? 'sign-up' : 'sign-in');
	let firstName = $state('');
	let lastName = $state('');
	let email = $state('');
	let password = $state('');
	let submitting = $state(false);
	let errorMessage = $state('');
	let confirmationPending = $state(false);

	const canSubmit = $derived(
		email.trim().length > 3 &&
			password.length >= 6 &&
			(mode === 'sign-in' || (firstName.trim().length > 0 && lastName.trim().length > 0)) &&
			!submitting
	);

	async function handleSubmit(event: SubmitEvent) {
		event.preventDefault();
		if (!canSubmit) return;

		submitting = true;
		errorMessage = '';
		try {
			if (mode === 'sign-in') {
				await authStore.signInWithPassword(email.trim(), password);
			} else {
				const { needsEmailConfirmation } = await authStore.signUp(
					email.trim(),
					password,
					firstName.trim(),
					lastName.trim()
				);
				if (needsEmailConfirmation) {
					confirmationPending = true;
				}
			}
		} catch (error) {
			errorMessage = error instanceof Error ? error.message : 'Something went wrong. Try again.';
		} finally {
			submitting = false;
		}
	}

	function switchMode(next: Mode) {
		mode = next;
		errorMessage = '';
		confirmationPending = false;
	}
</script>

<svelte:head>
	<title>Ginseng — Sign in</title>
	<meta name="description" content="Sign in to your Ginseng liquidity workspace." />
</svelte:head>

<div class="auth-screen" {@attach parallax()}>
	<section class="auth-hero">
		<canvas class="hero-field" {@attach dotField({ spacing: 30, radius: 1.5 })}></canvas>
		<div class="hero-copy" data-parallax-strength="22 14">
			<a class="hero-kicker" href={resolve('/welcome')}>Ginseng · Liquidity workspace</a>
			<h1>A timing problem, modeled.</h1>
			<p class="hero-body">
				2,000 simulated cash paths show the dollar amount your next 30 days actually require
				— and what closes the gap when today's cash can't.
			</p>
		</div>
	</section>

	<section class="auth-panel">
		<div class="auth-card">
			<div class="auth-mode" role="group" aria-label="Choose sign in or create account">
				<button
					type="button"
					class:active={mode === 'sign-in'}
					aria-pressed={mode === 'sign-in'}
					onclick={() => switchMode('sign-in')}
				>
					Sign in
				</button>
				<button
					type="button"
					class:active={mode === 'sign-up'}
					aria-pressed={mode === 'sign-up'}
					onclick={() => switchMode('sign-up')}
				>
					Create account
				</button>
			</div>

			{#if authStore.status === 'unconfigured'}
				<p class="auth-status-message">
					Supabase is not configured for this build. Set <code>PUBLIC_SUPABASE_URL</code> and
					<code>PUBLIC_SUPABASE_PUBLISHABLE_KEY</code> in <code>web/.env</code> to continue.
				</p>
			{:else if confirmationPending}
				<div class="auth-confirm">
					<p>Check <strong>{email}</strong> for a confirmation link.</p>
					<span>Sign-in unlocks once the email is confirmed.</span>
					<button type="button" class="text-button" onclick={() => switchMode('sign-in')}>
						Back to sign in
					</button>
				</div>
			{:else}
				<form onsubmit={handleSubmit}>
					{#if mode === 'sign-up'}
						<div class="name-row">
							<label>
								<span>First name</span>
								<input type="text" autocomplete="given-name" bind:value={firstName} required />
							</label>
							<label>
								<span>Last name</span>
								<input type="text" autocomplete="family-name" bind:value={lastName} required />
							</label>
						</div>
					{/if}
					<label>
						<span>Email</span>
						<input type="email" autocomplete="email" bind:value={email} required />
					</label>
					<label>
						<span>Password</span>
						<input
							type="password"
							autocomplete={mode === 'sign-in' ? 'current-password' : 'new-password'}
							minlength="6"
							bind:value={password}
							required
						/>
					</label>
					{#if errorMessage}
						<p class="auth-error" role="alert">{errorMessage}</p>
					{/if}
					<button type="submit" class="auth-submit" disabled={!canSubmit}>
						{#if submitting}
							{mode === 'sign-in' ? 'Signing in…' : 'Creating account…'}
						{:else}
							{mode === 'sign-in' ? 'Sign in' : 'Create account'}
						{/if}
					</button>
				</form>
			{/if}
		</div>
	</section>
</div>

<style>
	.auth-screen {
		display: grid;
		grid-template-columns: minmax(0, 1.15fr) minmax(20rem, 0.85fr);
		min-height: 100dvh;
		background: var(--paper);
	}

	.auth-hero {
		position: relative;
		overflow: hidden;
		display: flex;
		align-items: end;
		padding: 2.5rem;
		background: var(--cobalt-deep);
	}

	.hero-field {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
	}

	/* Foreground layer: most movement — the copy is what the eye reads
	   first, so it leads the parallax. Transform only; the panel's own
	   size (set by .auth-screen's grid-template-columns) is untouched. */
	.hero-copy {
		position: relative;
		display: grid;
		gap: 0.9rem;
		max-width: 30rem;
		color: var(--paper);
		transform: translate3d(0, 0, 0);
		transition: transform 650ms cubic-bezier(0.19, 1, 0.22, 1);
		will-change: transform;
	}

	@media (prefers-reduced-motion: reduce) {
		.hero-copy { transition: none; }
	}

	.hero-kicker {
		margin: 0;
		color: rgb(255 255 255 / 74%);
		font-family: var(--font-mono);
		font-size: 0.68rem;
		font-weight: 700;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		text-decoration: none;
		justify-self: start;
	}

	.hero-kicker:hover { color: var(--paper); }
	.hero-kicker:focus-visible { outline: 2px solid var(--paper); outline-offset: 3px; }

	.hero-copy h1 {
		margin: 0;
		font-family: var(--font-serif);
		font-size: clamp(2.1rem, 3.8vw, 3.2rem);
		font-weight: 700;
		letter-spacing: -0.01em;
		line-height: 1.05;
		text-wrap: balance;
	}

	.hero-body {
		margin: 0;
		max-width: 38ch;
		color: rgb(255 255 255 / 78%);
		font-size: 0.92rem;
		line-height: 1.5;
		text-wrap: pretty;
	}

	.auth-panel {
		display: grid;
		place-items: center;
		padding: 2rem;
	}

	.auth-card {
		display: grid;
		gap: 1.1rem;
		width: 100%;
		max-width: 22rem;
	}

	.auth-mode {
		display: grid;
		grid-template-columns: 1fr 1fr;
		border: 1px solid var(--control-border);
	}

	.auth-mode button {
		min-height: 2.6rem;
		background: var(--paper);
		border: 0;
		color: var(--ink-soft);
		font-family: var(--font-mono);
		font-size: 0.68rem;
		font-weight: 700;
		letter-spacing: 0.04em;
		text-transform: uppercase;
		cursor: pointer;
	}

	.auth-mode button:not(:last-child) { border-right: 1px solid var(--control-border); }
	.auth-mode button.active { background: var(--cobalt); color: var(--paper); }
	.auth-mode button:hover:not(.active) { background: var(--paper-deep); }

	form {
		display: grid;
		gap: 0.9rem;
	}

	.name-row {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 0.7rem;
	}

	label {
		display: grid;
		gap: 0.35rem;
		color: var(--ink-muted);
		font-family: var(--font-mono);
		font-size: 0.65rem;
		font-weight: 700;
		letter-spacing: 0.05em;
		text-transform: uppercase;
	}

	input {
		min-height: 2.65rem;
		padding: 0 0.75rem;
		background: var(--paper-deep);
		border: 1px solid var(--control-border);
		color: var(--ink);
		font-family: var(--font-sans);
		font-size: 0.95rem;
	}

	input:focus-visible {
		outline: 2px solid var(--cobalt);
		outline-offset: 1px;
	}

	.auth-error {
		margin: 0;
		padding: 0.6rem 0.7rem;
		background: var(--negative-soft);
		border-left: 3px solid var(--negative);
		color: var(--negative);
		font-size: 0.82rem;
		line-height: 1.4;
	}

	.auth-submit {
		min-height: 2.85rem;
		margin-top: 0.15rem;
		background: var(--cobalt);
		border: 1px solid var(--cobalt);
		color: var(--paper);
		font-family: var(--font-mono);
		font-size: 0.72rem;
		font-weight: 700;
		letter-spacing: 0.04em;
		text-transform: uppercase;
		cursor: pointer;
		transition: background-color 160ms ease;
	}

	.auth-submit:hover:not(:disabled) { background: var(--cobalt-bright); }
	.auth-submit:active:not(:disabled) { transform: scale(0.98); }

	.auth-submit:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.auth-status-message {
		margin: 0;
		padding: 0.9rem;
		background: var(--paper-soft);
		border-left: 3px solid var(--warning);
		color: var(--ink-soft);
		font-size: 0.85rem;
		line-height: 1.5;
	}

	.auth-status-message code {
		font-family: var(--font-mono);
		font-size: 0.82em;
	}

	.auth-confirm {
		display: grid;
		gap: 0.5rem;
		padding: 1rem;
		background: var(--paper-soft);
		border-left: 3px solid var(--cobalt);
	}

	.auth-confirm p {
		margin: 0;
		color: var(--ink);
		font-size: 0.9rem;
	}

	.auth-confirm span {
		color: var(--ink-muted);
		font-size: 0.8rem;
		line-height: 1.4;
	}

	.text-button {
		justify-self: start;
		padding: 0;
		background: none;
		border: 0;
		color: var(--cobalt);
		font-family: var(--font-mono);
		font-size: 0.7rem;
		font-weight: 700;
		letter-spacing: 0.03em;
		text-transform: uppercase;
		cursor: pointer;
	}

	.text-button:hover { color: var(--cobalt-deep); }

	@media (max-width: 56rem) {
		.auth-screen {
			grid-template-columns: 1fr;
			min-height: auto;
		}

		.auth-panel { order: 1; padding: 2.5rem 1.25rem 1.5rem; }

		.auth-hero {
			order: 2;
			align-items: start;
			min-height: 14rem;
			padding: 1.75rem 1.25rem;
		}

		.hero-body { display: none; }
	}

	@media (max-width: 26rem) {
		.auth-panel { padding: 2rem 1rem 1.5rem; }
		.auth-hero { min-height: 11rem; padding: 1.5rem 1rem; }
		.name-row { grid-template-columns: 1fr; }
	}
</style>
