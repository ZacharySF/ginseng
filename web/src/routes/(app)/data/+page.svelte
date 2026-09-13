<script lang="ts">
	import { page } from '$app/state';
	import FinancialDataEditor from '$lib/components/FinancialDataEditor.svelte';

	const SECTIONS = ['cash', 'income', 'history', 'assumptions', 'credit', 'investments', 'policy'] as const;
	const section = $derived.by(() => {
		const requested = page.url.searchParams.get('section');
		return SECTIONS.find((candidate) => candidate === requested) ?? 'cash';
	});
</script>

<svelte:head>
	<title>Ginseng — Financial data</title>
	<meta
		name="description"
		content="Enter, review, reconcile, and save personal cash, history, assumptions, credit, investments, and funding policy."
	/>
</svelte:head>

<FinancialDataEditor {section} />
