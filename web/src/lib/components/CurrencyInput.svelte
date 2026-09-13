<script lang="ts">
	import type { HTMLInputAttributes } from 'svelte/elements';
	import { parseUsdCents } from '$lib/workspace';

	interface Props extends Omit<HTMLInputAttributes, 'value' | 'type' | 'oninput' | 'onblur'> {
		value: number;
	}

	let { value = $bindable(), ...attributes }: Props = $props();
	let text = $derived(formatCents(value));

	function formatCents(cents: number): string {
		if (!Number.isFinite(cents)) return '';
		const sign = cents < 0 ? '-' : '';
		const digits = Math.abs(Math.trunc(cents)).toString().padStart(3, '0');
		return `${sign}${digits.slice(0, -2)}.${digits.slice(-2)}`;
	}


	function update(event: Event): void {
		const input = event.currentTarget as HTMLInputElement;
		const cents = parseUsdCents(input.value);
		input.setCustomValidity(cents === null && input.value.trim() ? 'Enter a supported USD amount with at most two decimal places.' : '');
		if (cents !== null) value = cents;
		// Override the formatted value after updating cents, preserving the caret.
		text = input.value;
	}
</script>

<input
	{...attributes}
	type="text"
	value={text}
	oninput={update}
	onblur={(event) => { if (event.currentTarget.validity.valid) text = formatCents(value); }}
/>
