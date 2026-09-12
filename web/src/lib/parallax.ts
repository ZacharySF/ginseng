// Pointer-driven depth-layer motion for hero panels.
//
// Each layer inside the attached element opts into its own amount of
// movement via `data-parallax-strength="<x-px> <y-px>"` — the maximum
// translation in each axis at the pointer's extremes. On move, this writes
// `element.style.transform` directly on every such layer; the CSS on each
// layer only needs a `transition: transform …` for the smoothing and
// `will-change: transform`.
//
// This writes the literal `transform` property rather than a custom
// property feeding a `calc(var(...))` transform: CSS transition detection
// for `transform` driven purely through an inherited custom-property
// change is not dependable across engines — a direct `transform` write is
// the standard, portable way to drive this effect. It only ever writes
// `transform`, never a layout-affecting property, so nothing sized by the
// container (a grid column, a panel width) can move.
//
// Svelte 5.29+ attachments over a `use:` action — no directive wiring
// needed at the call site.
import type { Attachment } from 'svelte/attachments';

interface Layer {
	el: HTMLElement;
	strengthX: number;
	strengthY: number;
}

export function parallax(): Attachment<HTMLElement> {
	return (node) => {
		if (typeof window === 'undefined') return;
		if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

		const layers: Layer[] = Array.from(
			node.querySelectorAll<HTMLElement>('[data-parallax-strength]')
		)
			.map((el) => {
				const [x, y] = (el.dataset.parallaxStrength ?? '0 0').split(/\s+/).map(Number);
				return { el, strengthX: x || 0, strengthY: y || 0 };
			})
			.filter((layer) => layer.strengthX !== 0 || layer.strengthY !== 0);

		if (layers.length === 0) return;

		function setOffset(nx: number, ny: number) {
			const clampedX = Math.max(-1, Math.min(1, nx));
			const clampedY = Math.max(-1, Math.min(1, ny));
			for (const layer of layers) {
				layer.el.style.transform = `translate3d(${(clampedX * layer.strengthX).toFixed(2)}px, ${(clampedY * layer.strengthY).toFixed(2)}px, 0)`;
			}
		}

		function handleMove(event: PointerEvent) {
			const bounds = node.getBoundingClientRect();
			setOffset(
				((event.clientX - bounds.left) / bounds.width) * 2 - 1,
				((event.clientY - bounds.top) / bounds.height) * 2 - 1
			);
		}

		function handleLeave() {
			setOffset(0, 0);
		}

		node.addEventListener('pointermove', handleMove);
		node.addEventListener('pointerleave', handleLeave);

		return () => {
			node.removeEventListener('pointermove', handleMove);
			node.removeEventListener('pointerleave', handleLeave);
		};
	};
}
