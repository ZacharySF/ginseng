<script lang="ts">
	import { onDestroy, tick } from 'svelte';
	import {
		CHAT_MAX_HISTORY_TURNS,
		CHAT_MAX_MESSAGE_LENGTH,
		postChat,
		type ChatContext,
		type ChatTurn,
		type WorkspaceAdditionsProposal
	} from '$lib/chat';
	import {
		WORKSPACE_SAVED_EVENT,
		projectWorkspace,
		saveWorkspace,
		type ScheduledProjection
	} from '$lib/workspace';
	import { authStore } from '$lib/auth.svelte';

	interface Props {
		context: ChatContext | null;
	}

	let { context }: Props = $props();

	let dialog = $state<HTMLDialogElement>();
	let input = $state<HTMLTextAreaElement>();
	let transcript = $state<ChatTurn[]>([]);
	let draft = $state('');
	let sending = $state(false);
	let isOpen = $state(false);
	let requestError = $state<string | null>(null);
	let requestNotice = $state<string | null>(null);
	let savedRevision = $state<number | null>(null);
	let pendingText = $state<string | null>(null);
	let streamingText = $state('');
	let transcriptContainer = $state<HTMLDivElement>();
	let proposalCard = $state<ProposalCard | null>(null);
	let proposalSession = 0;

	interface ProposalCard {
		proposal: WorkspaceAdditionsProposal;
		kind: 'pending' | 'saving' | 'saved' | 'failed';
		confirmed: ScheduledProjection | null;
		note: string | null;
		savedRevision: number | null;
	}

	let controller: AbortController | null = null;
	let requestGeneration = 0;
	let contextInitialized = false;
	let previousContextKey: string | null = null;

	const sourceLabel = $derived(context?.source === 'personal' ? 'Personal saved data' : 'Simulated demo data');
	const contextKey = $derived(context ? JSON.stringify(context) : null);
	const trimmedDraft = $derived(draft.trim());
	const draftTooLong = $derived(draft.length > CHAT_MAX_MESSAGE_LENGTH);
	const notSignedIn = $derived(authStore.status !== 'signed-in' || !authStore.user);
	const proposalSaving = $derived(proposalCard?.kind === 'saving');
	const cannotSend = $derived(
		!context || notSignedIn || !trimmedDraft || draftTooLong || sending || proposalSaving
	);
	const recentExchangeCount = CHAT_MAX_HISTORY_TURNS / 2;
	const addedAccounts = $derived(proposalCard?.proposal.draft.accounts.filter(
		(account) => proposalCard?.proposal.added_account_ids.includes(account.id)
	) ?? []);
	const addedBills = $derived(proposalCard?.proposal.draft.bills.filter(
		(bill) => proposalCard?.proposal.added_bill_ids.includes(bill.id)
	) ?? []);
	const shownSchedule = $derived(proposalCard?.confirmed ??
		(proposalCard?.kind === 'pending' ? proposalCard.proposal.projection : null));

	function dismissActiveRequest({ invalidate = false }: { invalidate?: boolean } = {}): void {
		if (invalidate) requestGeneration += 1;
		streamingText = '';
		if (!controller) return;
		controller.abort();
		controller = null;
	}

	async function scrollTranscript(reviewProposal = false): Promise<void> {
		await tick();
		if (!transcriptContainer) return;
		const card = reviewProposal ? transcriptContainer.querySelector('.proposal-card') : null;
		if (card) {
			transcriptContainer.scrollTop += card.getBoundingClientRect().top - transcriptContainer.getBoundingClientRect().top;
		} else {
			transcriptContainer.scrollTop = transcriptContainer.scrollHeight;
		}
	}

	async function focusInput(force = false): Promise<void> {
		await tick();
		if (!dialog?.open) return;
		if (force || document.activeElement === document.body || document.activeElement === dialog) input?.focus();
	}

	const dollars = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' });
	function formatCents(cents: number): string {
		return dollars.format(cents / 100);
	}

	function discardProposal(): void {
		if (proposalSaving) return;
		proposalSession += 1;
		proposalCard = null;
		void focusInput(true);
	}

	async function approveAdditions(): Promise<void> {
		const card = proposalCard;
		const ownerId = authStore.user?.id;
		if (!card || card.kind !== 'pending' || !ownerId || notSignedIn || context?.source !== 'personal') return;
		const session = proposalSession;
		const isCurrent = () => session === proposalSession && ownerId === authStore.user?.id && proposalCard === card;
		card.kind = 'saving';
		try {
			const result = await saveWorkspace(card.proposal.draft);
			if (!isCurrent()) return;
			if (result.status !== 'ok') {
				card.kind = 'failed';
				card.note = result.status === 'engine-error' && result.http_status === 409
					? 'Your saved workspace changed. Ask again to prepare a fresh proposal.'
					: result.status === 'engine-unreachable' || result.http_status === undefined || result.http_status >= 500
						? 'The save result is unknown. Reload and reconcile your saved workspace before trying again.'
						: `The additions were not saved. ${result.message}`;
				return;
			}
			card.savedRevision = result.data.revision;
			savedRevision = result.data.revision;
			window.dispatchEvent(new CustomEvent(WORKSPACE_SAVED_EVENT, {
				detail: { ownerId, workspace: result.data }
			}));
			const projected = await projectWorkspace(card.proposal.horizon_days);
			if (!isCurrent()) return;
			card.kind = 'saved';
			if (projected.status === 'ok' && projected.data.input_revision === result.data.revision) {
				card.confirmed = projected.data;
			} else {
				card.note = projected.status === 'ok'
					? 'Saved successfully, but the workspace changed again. Request a new cash schedule.'
					: `Saved successfully. The cash schedule is unavailable: ${projected.message}`;
			}
		} catch {
			if (!isCurrent()) return;
			card.kind = card.savedRevision === null ? 'failed' : 'saved';
			card.note = card.savedRevision === null
				? 'The save result is unknown. Reload and reconcile your saved workspace before trying again.'
				: 'Saved successfully. Request a new cash schedule to see the result.';
		} finally {
			if (isCurrent()) {
				void scrollTranscript();
				void focusInput();
			}
		}
	}

	function openChat(): void {
		if (!dialog?.open) dialog?.showModal();
		isOpen = true;
		requestError = null;
		requestNotice = null;
		void focusInput(true);
	}

	function closeChat(): void {
		if (pendingText) draft = draft || pendingText;
		pendingText = null;
		sending = false;
		dismissActiveRequest({ invalidate: true });
		if (dialog?.open) dialog.close();
	}

	function handleDialogClose(): void {
		isOpen = false;
		dismissActiveRequest();
	}

	function handleDialogCancel(event: Event): void {
		event.preventDefault();
		closeChat();
	}

	function clearConversation(): void {
		if (proposalSaving) return;
		discardProposal();
		dismissActiveRequest({ invalidate: true });
		transcript = [];
		draft = '';
		sending = false;
		pendingText = null;
		requestError = null;
		requestNotice = null;
		savedRevision = null;
		void scrollTranscript();
		void focusInput();
	}

	function stopGenerating(): void {
		if (!sending) return;
		dismissActiveRequest({ invalidate: true });
		draft = draft || pendingText || '';
		pendingText = null;
		sending = false;
		requestNotice = 'Generation stopped. Your message is ready to resend.';
		void focusInput(true);
	}

	function handleComposerKeydown(event: KeyboardEvent): void {
		if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
			event.preventDefault();
			void sendMessage();
		}
	}

	async function sendMessage(): Promise<void> {
		const message = trimmedDraft;
		if (cannotSend || !context) return;
		discardProposal();

		const requestContext = context;
		const requestContextKey = contextKey;
		const generation = ++requestGeneration;
		const activeController = new AbortController();
		const history = transcript.slice(-CHAT_MAX_HISTORY_TURNS);

		controller = activeController;
		pendingText = message;
		streamingText = '';
		draft = '';
		requestError = null;
		requestNotice = null;
		sending = true;
		void scrollTranscript();

		try {
			const result = await postChat(message, requestContext, history, (delta) => {
				if (generation !== requestGeneration || requestContextKey !== contextKey || activeController.signal.aborted) return;
				const followReply = !transcriptContainer ||
					transcriptContainer.scrollHeight - transcriptContainer.scrollTop - transcriptContainer.clientHeight < 48;
				streamingText += delta;
				if (followReply) void scrollTranscript();
			}, activeController.signal);
			if (generation !== requestGeneration || requestContextKey !== contextKey || activeController.signal.aborted) return;

			if (result.status !== 'ok') {
				requestError = result.message;
				draft = draft || message;
				return;
			}

			const exchange: ChatTurn[] = [{ role: 'user', text: message }, { role: 'model', text: result.data.reply }];
			transcript = [...transcript, ...exchange].slice(-CHAT_MAX_HISTORY_TURNS);
			savedRevision = result.data.input_revision;
			if (result.data.proposal) {
				proposalCard = {
					proposal: result.data.proposal,
					kind: 'pending',
					confirmed: null,
					note: null,
					savedRevision: null
				};
			}
		} catch {
			if (generation !== requestGeneration || requestContextKey !== contextKey) return;
			requestError = 'The assistant could not complete this request.';
			draft = draft || message;
		} finally {
			if (generation === requestGeneration) {
				sending = false;
				pendingText = null;
				streamingText = '';
				if (controller === activeController) controller = null;
				void scrollTranscript(proposalCard?.kind === 'pending');
				void focusInput();
			}
		}
	}

	$effect(() => {
		if (!contextInitialized) {
			contextInitialized = true;
			previousContextKey = contextKey;
			return;
		}
		if (previousContextKey === contextKey) return;

		previousContextKey = contextKey;
		proposalSession += 1;
		proposalCard = null;
		requestGeneration += 1;
		dismissActiveRequest();
		if (pendingText) draft = draft || pendingText;
		pendingText = null;
		transcript = [];
		sending = false;
		requestError = null;
		requestNotice = null;
		savedRevision = null;
	});

	onDestroy(() => {
		proposalSession += 1;
		requestGeneration += 1;
		dismissActiveRequest();
	});
</script>

<button
	class="chat-launcher"
	type="button"
	aria-haspopup="dialog"
	aria-expanded={isOpen}
	onclick={openChat}
>
	<span>Assistant</span>
</button>

<dialog bind:this={dialog} class="chat-dialog" aria-labelledby="chat-title" onclose={handleDialogClose} oncancel={handleDialogCancel}>
	<div class="chat-surface">
		<header class="chat-header">
			<div class="chat-title-block">
				<div>
					<p class="chat-kicker">Ginseng assistant</p>
					<h2 id="chat-title">Ask about this cash position</h2>
					<p class="chat-source">{sourceLabel}</p>
				</div>
			</div>
			<button class="icon-button" type="button" onclick={closeChat} aria-label="Close Ginseng assistant">×</button>
		</header>

		<div class="chat-body">
			<section class="chat-context" aria-label="Assistant data notice">
				{#if notSignedIn}
					<p>Sign in to send questions to the assistant.</p>
				{:else if context?.source === 'personal'}
					<p>Uses your latest saved inputs and 30-day schedule, not unsaved drafts.</p>
				{:else if context?.source === 'demo'}
					<p>Uses the current simulated scenario only. It is not your personal financial data.</p>
				{:else}
					<p>Demo scenario context is unavailable. Load a current scenario before asking about simulated data.</p>
				{/if}
			</section>

			<div bind:this={transcriptContainer} class="chat-transcript" aria-label="Conversation" aria-live="polite" aria-busy={sending}>
				{#if transcript.length === 0 && !pendingText}
					<p class="empty-state">{context?.source === 'personal' ? 'Ask about saved balances, bill timing, or the scheduled balance after bills.' : 'Ask about coverage, timing, reserves, or upcoming obligations in this simulated scenario.'}</p>
				{/if}
				{#each transcript as turn, index (index)}
					<article class:user-message={turn.role === 'user'} class="message-row">
						<div class="message-content">
							<p class="message-label">{turn.role === 'user' ? 'You' : 'Ginseng assistant'}</p>
							<p class="message-copy">{turn.text}</p>
							{#if turn.role === 'model' && context?.source === 'personal' && savedRevision !== null && index === transcript.length - 1}
								<p class="revision-note">Saved workspace revision {savedRevision}</p>
							{/if}
						</div>
					</article>
				{/each}
				{#if pendingText}
					<article class="message-row user-message">
						<div class="message-content">
							<p class="message-label">You</p>
							<p class="message-copy">{pendingText}</p>
						</div>
					</article>
				{/if}
				{#if streamingText}
					<article class="message-row streaming-message">
						<div class="message-content">
							<p class="message-label">Ginseng assistant</p>
							<p class="message-copy">{streamingText}</p>
						</div>
					</article>
				{/if}
				{#if proposalCard}
					<section class="proposal-card" aria-labelledby="proposal-title" aria-busy={proposalSaving}>
						<h3 id="proposal-title">{proposalCard.kind === 'saved' ? 'Additions saved' : 'Review additions'}</h3>
						<p>{proposalCard.kind === 'saved' ? `Saved revision ${proposalCard.savedRevision}.` : 'Nothing is saved until you approve.'} {addedAccounts.length} account(s) and {addedBills.length} bill(s).</p>
						<p>Opening balances as of {proposalCard.proposal.draft.as_of}. Existing saved records are kept; unsaved form edits are not included.</p>
						<ul class="proposal-items">
							{#each addedAccounts as account (account.id)}
								<li><strong>{account.name}</strong> · {account.kind}<br />{formatCents(account.balance_cents)}</li>
							{/each}
							{#each addedBills as bill (bill.id)}
								<li><strong>{bill.label}</strong> · {formatCents(bill.amount_cents)}<br />Due {bill.due_date}</li>
							{/each}
						</ul>
						{#if shownSchedule}
							<p><strong>{proposalCard.kind === 'saved' ? 'Saved cash schedule' : 'After approval'} · {proposalCard.proposal.horizon_days} days</strong></p>
							<dl class="proposal-totals">
								<div><dt>Cash for scheduled bills</dt><dd>{formatCents(shownSchedule.scheduled_bills_cents)}</dd></div>
								<div><dt>Cash after bills</dt><dd>{formatCents(shownSchedule.ending_balance_cents)}</dd></div>
								<div><dt>Additional cash needed</dt><dd>{formatCents(Math.max(0, -shownSchedule.lowest_balance_cents))}</dd></div>
							</dl>
							<p>Known bills only, not a probabilistic reserve. Bills outside this horizon are not included.</p>
						{:else if proposalCard.kind === 'pending' && proposalCard.proposal.projection_error}
							<p>Cash schedule unavailable: {proposalCard.proposal.projection_error}</p>
						{/if}
						{#if proposalCard.note}
							<p role={proposalCard.kind === 'failed' ? 'alert' : 'status'}>{proposalCard.note}</p>
						{/if}
						{#if proposalSaving}
							<p role="status">{proposalCard.savedRevision === null ? 'Saving additions…' : 'Calculating saved schedule…'}</p>
						{:else if proposalCard.kind === 'pending'}
							<div class="proposal-actions">
								<button class="secondary-action" type="button" onclick={discardProposal}>Discard</button>
								<button class="send-action" type="button" onclick={approveAdditions}>Approve additions</button>
							</div>
						{/if}
					</section>
				{/if}
			</div>
			{#if sending}
				<p class="generating" role="status">{streamingText ? 'Responding…' : 'Generating response…'}</p>
			{/if}

			{#if requestError}
				<p class="request-error" role="alert">{requestError} Your message is ready to resend.</p>
			{/if}
			{#if requestNotice}
				<p class="request-notice" role="status">{requestNotice}</p>
			{/if}
		</div>

		<form class="chat-composer" onsubmit={(event) => { event.preventDefault(); void sendMessage(); }}>
			<label for="chat-message">Question</label>
			<textarea
				bind:this={input}
				id="chat-message"
				bind:value={draft}
				rows="3"
				maxlength={CHAT_MAX_MESSAGE_LENGTH}
				placeholder={notSignedIn ? 'Sign in to ask a question' : context ? 'Ask about this cash position…' : 'Scenario context unavailable'}
				disabled={!context || notSignedIn || sending || proposalSaving}
				onkeydown={handleComposerKeydown}
			></textarea>
			<div class="composer-meta">
				<p>{draft.length}/{CHAT_MAX_MESSAGE_LENGTH} characters · Recent {recentExchangeCount} exchanges are retained for this session only.</p>
				<p class="disclosure">By sending, you send your question, conversation, and relevant financial context to Google Gemini.</p>
				<p>AI responses may be wrong. Changes require your approval. The assistant never moves bank money.</p>
			</div>
			<div class="composer-actions">
				<button class="secondary-action" type="button" onclick={clearConversation} disabled={proposalSaving || (transcript.length === 0 && !draft && !pendingText && !sending && !requestError && !requestNotice && !proposalCard)}>New chat</button>
				{#if sending}
					<button class="secondary-action" type="button" onclick={stopGenerating}>Stop</button>
				{/if}
				<button class="send-action" type="submit" disabled={cannotSend}>Send</button>
			</div>
		</form>
	</div>
</dialog>

<style>
	.chat-launcher,
	.icon-button,
	.secondary-action,
	.send-action {
		font: inherit;
		cursor: pointer;
	}

	.chat-launcher {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		min-width: 0;
		min-height: 2.75rem;
		padding: 0.25rem 0.65rem;
		background: rgb(255 255 255 / 11%);
		border: 1px solid rgb(255 255 255 / 40%);
		border-radius: 0.2rem;
		color: var(--on-brand);
		font-family: var(--font-mono);
		font-size: 0.62rem;
		font-weight: 700;
		letter-spacing: 0.04em;
		text-transform: uppercase;
	}

	.chat-launcher:hover,
	.chat-launcher[aria-expanded='true'] {
		background: var(--paper);
		border-color: var(--paper);
		color: var(--cobalt);
	}

	.chat-launcher:active,
	.icon-button:active,
	.secondary-action:active,
	.send-action:active { transform: scale(0.97); }

	.chat-launcher:focus-visible,
	.icon-button:focus-visible { outline-color: var(--cobalt-bright); }

	.chat-dialog {
		position: fixed;
		inset: 3.8rem 1rem auto auto;
		width: min(31rem, calc(100vw - 2rem));
		max-width: none;
		height: min(42rem, calc(100dvh - 4.8rem));
		max-height: none;
		margin: 0;
		padding: 0;
		background: var(--paper);
		border: 1px solid var(--cobalt-deep);
		box-shadow: 0.45rem 0.45rem 0 rgb(0 0 79 / 24%);
		color: var(--ink);
	}

	.chat-dialog::backdrop { background: rgb(0 0 79 / 44%); }

	.chat-surface {
		display: grid;
		grid-template-rows: auto minmax(14rem, 1fr) auto;
		height: 100%;
	}

	.chat-header {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 1rem;
		padding: 0.85rem;
		background: var(--brand-blue);
		color: var(--on-brand);
	}

	.chat-title-block { min-width: 0; }


	.chat-kicker,
	.chat-source,
	.message-label,
	.revision-note,
	.composer-meta,
	.chat-composer label {
		font-family: var(--font-mono);
		font-size: 0.62rem;
		font-weight: 700;
		letter-spacing: 0.05em;
		text-transform: uppercase;
	}

	.chat-kicker { margin: 0 0 0.12rem; color: rgb(255 255 255 / 78%); }
	.chat-header h2 { margin: 0; font-size: clamp(1.05rem, 2vw, 1.35rem); letter-spacing: -0.03em; line-height: 1.05; text-wrap: balance; }
	.chat-source { margin: 0.3rem 0 0; color: rgb(255 255 255 / 84%); }

	.icon-button {
		display: grid;
		flex: 0 0 auto;
		place-items: center;
		width: 2.75rem;
		height: 2.75rem;
		padding: 0;
		background: transparent;
		border: 1px solid rgb(255 255 255 / 64%);
		border-radius: 0.2rem;
		color: var(--on-brand);
		font-size: 1.5rem;
		line-height: 1;
	}

	.icon-button:hover { background: rgb(255 255 255 / 15%); }

	.chat-body {
		display: grid;
		grid-template-rows: auto minmax(0, 1fr) auto;
		min-height: 0;
	}

	.chat-context {
		display: grid;
		gap: 0.25rem;
		padding: 0.65rem 0.85rem;
		background: var(--paper-soft);
		border-bottom: 1px solid var(--rule);
		color: var(--ink-soft);
		font-size: 0.78rem;
		line-height: 1.35;
	}

	.chat-context p { margin: 0; text-wrap: pretty; }

	.proposal-card {
		padding: 0.85rem;
		border: 1px solid var(--cobalt);
		background: var(--paper-soft);
		font-size: 0.85rem;
		line-height: 1.45;
		overflow-wrap: anywhere;
	}
	.proposal-card h3 { margin: 0 0 0.5rem; color: var(--cobalt); font-size: 1rem; }
	.proposal-card p { margin: 0.5rem 0; }
	.proposal-items { margin: 0.75rem 0; padding-left: 1.1rem; }
	.proposal-items li + li { margin-top: 0.5rem; }
	.proposal-totals { margin: 0.75rem 0; }
	.proposal-totals div { display: flex; justify-content: space-between; gap: 0.75rem; padding: 0.3rem 0; border-bottom: 1px solid var(--rule); }
	.proposal-totals dd { margin: 0; font-variant-numeric: tabular-nums; white-space: nowrap; }
	.proposal-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 0.5rem; margin-top: 0.75rem; }

	.chat-transcript {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
		min-height: 0;
		overflow-y: auto;
		padding: 0.85rem;
		scroll-padding-bottom: 0.75rem;
	}

	.empty-state {
		max-width: 36ch;
		margin: auto 0;
		color: var(--ink-soft);
		font-size: 0.9rem;
		line-height: 1.45;
		text-wrap: pretty;
	}

	.message-row {
		display: flex;
		align-items: flex-start;
		gap: 0.45rem;
		max-width: 88%;
	}

	.user-message {
		align-self: flex-end;
		flex-direction: row-reverse;
	}

	.message-content { display: grid; min-width: 0; gap: 0.22rem; }
	.user-message .message-content { justify-items: end; }
	.message-label { margin: 0; color: var(--ink-soft); }
	.user-message .message-label { color: var(--cobalt); }

	.message-copy {
		max-width: 100%;
		margin: 0;
		padding: 0.58rem 0.7rem;
		background: var(--paper-soft);
		border: 1px solid var(--rule);
		border-radius: 0.65rem 0.65rem 0.65rem 0.15rem;
		color: var(--ink);
		font-size: 0.9rem;
		line-height: 1.42;
		overflow-wrap: anywhere;
		white-space: pre-wrap;
	}

	.user-message .message-copy {
		background: var(--brand-blue);
		border-color: var(--cobalt);
		border-radius: 0.65rem 0.65rem 0.15rem 0.65rem;
		color: var(--on-brand);
	}

	.revision-note { margin: 0; color: var(--ink-soft); }

	.generating,
	.request-notice,
	.request-error {
		margin: 0;
		padding: 0.65rem 0.85rem;
		font-size: 0.82rem;
		line-height: 1.35;
	}

	.generating {
		margin: 0 0.85rem;
		padding: 0;
		color: var(--ink-soft);
		font-family: var(--font-mono);
		font-size: 0.72rem;
		font-weight: 700;
		letter-spacing: 0.03em;
	}

	.request-notice { background: var(--paper-soft); border-top: 1px solid var(--rule); color: var(--ink-soft); }
	.request-error { background: var(--negative-soft); border-top: 1px solid var(--negative); color: var(--ink); }

	.chat-composer {
		display: grid;
		gap: 0.45rem;
		padding: 0.75rem 0.85rem 0.85rem;
		border-top: 1px solid var(--rule-strong);
	}

	.chat-composer label { color: var(--ink); }

	.chat-composer textarea {
		box-sizing: border-box;
		width: 100%;
		min-height: 5rem;
		resize: vertical;
		padding: 0.6rem 0.7rem;
		background: var(--paper-soft);
		border: 1px solid var(--control-border);
		border-radius: 0.2rem;
		color: var(--ink);
		font: inherit;
		font-size: 0.9rem;
		line-height: 1.4;
	}

	.chat-composer textarea::placeholder { color: var(--ink-soft); opacity: 1; }
	.chat-composer textarea:disabled { cursor: not-allowed; opacity: 0.7; }

	.composer-meta { display: grid; gap: 0.3rem; color: var(--ink-soft); line-height: 1.35; }
	.composer-meta p { margin: 0; }
	.disclosure { color: var(--ink); text-transform: none; letter-spacing: 0; font-family: var(--font-sans); font-size: 0.75rem; font-weight: 600; }

	.composer-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 0.45rem; }

	.secondary-action,
	.send-action {
		min-height: 2.75rem;
		padding: 0.45rem 0.8rem;
		border: 1px solid var(--control-border);
		border-radius: 0.2rem;
		font-family: var(--font-mono);
		font-size: 0.7rem;
		font-weight: 700;
		letter-spacing: 0.04em;
		text-transform: uppercase;
	}

	.secondary-action { background: var(--paper); color: var(--ink); }
	.secondary-action:hover:not(:disabled) { background: var(--paper-soft); }
	.send-action { background: var(--brand-blue); border-color: var(--cobalt); color: var(--on-brand); }
	.send-action:hover:not(:disabled) { background: var(--cobalt-deep); }
	.secondary-action:disabled,
	.send-action:disabled { cursor: not-allowed; opacity: 0.55; }

	@media (max-width: 48rem) {
		.chat-dialog {
			inset: 0;
			width: 100vw;
			height: 100dvh;
			border: 0;
			box-shadow: none;
		}

		.chat-header { padding: 0.75rem; }
		.chat-transcript { padding: 0.75rem; }
		.message-row { max-width: 94%; }
		.chat-composer { padding: 0.65rem 0.75rem calc(0.65rem + env(safe-area-inset-bottom)); }
		.composer-actions { justify-content: stretch; }
		.composer-actions button { flex: 1; }
	}

	@media (prefers-reduced-motion: reduce) {
		.chat-launcher:active,
		.icon-button:active,
		.secondary-action:active,
		.send-action:active { transform: none; }
	}
</style>
