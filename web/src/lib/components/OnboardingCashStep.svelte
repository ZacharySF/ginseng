<script lang="ts">
	import CurrencyInput from '$lib/components/CurrencyInput.svelte';
	import type { CashAccount } from '$lib/workspace';

	interface Props {
		asOf: string | null;
		accounts: CashAccount[];
		disabled?: boolean;
	}

	let { asOf = $bindable(), accounts = $bindable(), disabled = false }: Props = $props();

	function addAccount(): void {
		if (disabled || accounts.length >= 50) return;
		accounts = [
			...accounts,
			{ id: crypto.randomUUID(), name: '', kind: 'checking', balance_cents: 0 }
		];
	}

	function removeAccount(id: string): void {
		if (disabled || accounts.length <= 1) return;
		accounts = accounts.filter((account) => account.id !== id);
	}
</script>

<div class="step-heading">
	<p class="eyebrow">Opening snapshot</p>
	<h1>What cash do you have today?</h1>
	<p>Enter settled checking and savings balances from one opening calendar day. You can change these later in Data.</p>
</div>

<label class="opening-date">
	<span>Balances reflect the opening of</span>
	<input type="date" min="1900-01-01" max="2100-12-31" value={asOf ?? ''} onchange={(event) => asOf = event.currentTarget.value} {disabled} required />
</label>

<div class="account-list">
	{#each accounts as account, index (account.id)}
		<section class="account-row" aria-label={`Cash account ${index + 1}`}>
			<div class="row-heading">
				<strong>Account {index + 1}</strong>
				<button type="button" class="remove-button" disabled={disabled || accounts.length <= 1} onclick={() => removeAccount(account.id)}>Remove</button>
			</div>
			<div class="field-grid">
				<label><span>Account name</span><input bind:value={account.name} maxlength="100" placeholder="e.g. Main checking" {disabled} required /></label>
				<label><span>Type</span><select bind:value={account.kind} {disabled}><option value="checking">Checking</option><option value="savings">Savings</option></select></label>
				<label class="balance-field"><span>Opening balance</span><span class="money-input"><span aria-hidden="true">$</span><CurrencyInput bind:value={account.balance_cents} inputmode="decimal" {disabled} required /></span></label>
			</div>
		</section>
	{/each}
</div>

<button type="button" class="add-button" disabled={disabled || accounts.length >= 50} onclick={addAccount}>Add another account</button>
<p class="helper">Use the balance available at the start of the selected day. Negative checking balances are allowed.</p>

<style>
	.step-heading { display:grid; gap:.38rem; }
	.step-heading p { margin:0; color:var(--ink-soft); font-size:.88rem; line-height:1.5; }
	.eyebrow { font-family:var(--font-mono); font-size:.63rem !important; font-weight:700; letter-spacing:.07em; text-transform:uppercase; }
	h1 { margin:0; color:var(--ink); font-size:clamp(1.55rem,3vw,2.05rem); letter-spacing:-.025em; line-height:1.08; text-wrap:balance; }
	.opening-date,label { display:grid; gap:.32rem; color:var(--ink-soft); font-size:.73rem; font-weight:650; }
	.opening-date { max-width:18rem; }
	input,select { width:100%; min-height:2.75rem; padding:0 .65rem; background:var(--paper); border:1px solid var(--control-border); color:var(--ink); }
	input:focus,select:focus { border-color:var(--cobalt); box-shadow:0 0 0 1px var(--cobalt); outline:0; }
	.account-list { display:grid; gap:.7rem; }
	.account-row { display:grid; gap:.7rem; padding:.9rem; background:var(--paper-soft); border:1px solid var(--rule); }
	.row-heading { display:flex; align-items:center; justify-content:space-between; gap:.7rem; }
	.row-heading strong { color:var(--ink); font-size:.82rem; }
	.field-grid { display:grid; grid-template-columns:minmax(0,1.35fr) minmax(8rem,.8fr); gap:.7rem; }
	.balance-field { grid-column:1 / -1; }
	.money-input { display:grid; grid-template-columns:auto minmax(0,1fr); align-items:center; background:var(--paper); border:1px solid var(--control-border); }
	.money-input:focus-within { border-color:var(--cobalt); box-shadow:0 0 0 1px var(--cobalt); }
	.money-input > span { padding-left:.65rem; color:var(--ink-soft); }
	.money-input :global(input) { border:0; box-shadow:none; }
	.add-button,.remove-button { min-height:2.75rem; background:var(--paper); border:1px solid var(--control-border); color:var(--cobalt); font-family:var(--font-mono); font-size:.66rem; font-weight:700; letter-spacing:.04em; text-transform:uppercase; cursor:pointer; }
	.add-button { width:100%; }
	.remove-button { min-height:2.4rem; padding:0 .55rem; }
	button:disabled { cursor:not-allowed; opacity:.5; }
	.helper { margin:-.35rem 0 0; color:var(--ink-soft); font-size:.75rem; line-height:1.45; }
	@media(max-width:34rem){.field-grid{grid-template-columns:1fr}.balance-field{grid-column:auto}}
</style>
