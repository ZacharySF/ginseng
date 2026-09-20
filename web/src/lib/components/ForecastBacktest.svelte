<script lang="ts">
 import { resolve } from '$app/paths';
 import ModelEvidencePanel from '$lib/components/ModelEvidencePanel.svelte';
 import type { BacktestSummary } from '$lib/finance';
 import type { ScenarioResponse } from '$lib/types';
 let { modelMode, response, accuracy, error, loading, onRun }: {
   modelMode: 'scheduled' | 'assumptions' | 'history'; response: ScenarioResponse;
   accuracy: BacktestSummary | null; error: string | null; loading: boolean;
   onRun: () => void | Promise<void>;
 } = $props();
</script>
<ModelEvidencePanel {response} report={accuracy?.calibration ?? null} {error} {loading} {onRun} allowHistorical={modelMode === 'history'} />
{#if modelMode !== 'history'}<p class="scope">Historical validation requires classified history. <a href={resolve('/data?section=history')}>Review history inputs</a>.</p>{/if}
{#if accuracy?.information_timing === 'retrospective_current_records'}<p class="scope">Retrospective evaluation with current records. Historical arrival times and revisions are unavailable; this is not a point-in-time archive.</p>{/if}
{#if accuracy?.warning}<p class="scope" role="status">{accuracy.warning}</p>{/if}
<style>.scope { padding:1rem; background:var(--paper-soft); color:var(--ink-soft); } a {color:var(--link);}</style>
