<script lang="ts">
	/** A screen projection of the real camera's world axes. */
	let { camera }: { camera: { eye?: { x?: number; y?: number; z?: number }; up?: { x?: number; y?: number; z?: number }; center?: { x?: number; y?: number; z?: number } } } = $props();
	const axes = $derived.by(() => {
		const eye = camera.eye ?? {}, center = camera.center ?? {}, up = camera.up ?? {};
		const normal = (v: number[]) => { const length = Math.hypot(...v) || 1; return v.map(x => x / length); };
		const cross = (a: number[], b: number[]) => [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]];
		const forward = normal([(eye.x ?? 1)-(center.x ?? 0), (eye.y ?? 1)-(center.y ?? 0), (eye.z ?? 1)-(center.z ?? 0)]);
		const right = normal(cross([up.x ?? 0, up.y ?? 0, up.z ?? 1], forward));
		const vertical = cross(forward, right);
		return ['X', 'Y', 'Z'].map((label, i) => ({ label, x: 36 + right[i]*22, y: 36 - vertical[i]*22, depth: forward[i], color: ['#4e9dff', '#70dfff', '#e1f6ff'][i] })).sort((a, b) => a.depth - b.depth);
	});
</script>
<svg class="orientation-gizmo" viewBox="0 0 72 72" aria-hidden="true">
	<circle cx="36" cy="36" r="26" fill="none" stroke="#426888" stroke-opacity=".25" stroke-dasharray="1 4"/>
	{#each axes as axis}
		<line x1="36" y1="36" x2={axis.x} y2={axis.y} stroke={axis.color} stroke-width="1.2"/>
		<circle cx={axis.x} cy={axis.y} r="1.5" fill={axis.color}/>
		<text x={36 + (axis.x-36)*1.35} y={39 + (axis.y-36)*1.35} text-anchor="middle" fill={axis.color}>{axis.label}</text>
	{/each}
	<circle cx="36" cy="36" r="2" fill="#b3dfff"/>
</svg>
<style>
	.orientation-gizmo { display: block; width: 4rem; height: 4rem; overflow: visible; pointer-events: none; }
	text { font: 9px var(--font-mono); }
</style>
