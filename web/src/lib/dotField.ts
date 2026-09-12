// Ambient dot field for hero panels: a hex-packed grid of dots that
// breathes in rings traveling outward from a focus point, and whose
// focus glides to the pointer when it's over the panel.
//
// This is a from-scratch Canvas 2D port (no Three.js/WebGL dependency)
// of the actual mechanics in two references, read directly from their
// source rather than guessed from the screenshots:
//
//  - https://github.com/mattrossman/breathing-dots-tutorial
//    (src/demos/Demo1.js, Demo2.js) — the breathing wave itself. Each
//    dot's rest position is scaled outward/inward from a focus point by
//    `roundedSquareWave(t, delta, a, f) = (2a/pi) * atan(sin(2*pi*t*f) / delta)`,
//    phase-delayed by `t = time - dist/speed` so rings travel outward,
//    with `dist` warped by `cos(angle * 8)` for the 8-lobed ripple and
//    `delta` growing with distance so outer rings soften. Demo2 moves
//    the focus point to the pointer instead of leaving it fixed at
//    center — adapted here as a continuous lerp instead of click-hold.
//  - https://github.com/brunoimbrizi/interactive-particles
//    (Particles.js, TouchTexture.js) — pointer proximity as the thing
//    that perturbs the field rather than a fixed animation; carried
//    over as the focus-follows-pointer behavior plus the soft
//    circular dot falloff from particle.frag's `smoothstep` edge.
//
// Not carried over: interactive-particles builds its dots from an
// image's pixels (this field has no source image), and breathing-dots'
// chromatic delay-trail post-processing needs render-target ping-pong
// that has no Canvas 2D equivalent worth the complexity for a page
// background.
import type { Attachment } from 'svelte/attachments';

interface DotFieldOptions {
	/** px between dots on the hex grid */
	spacing?: number;
	/** dot radius in px */
	radius?: number;
	/** dot color as an `r g b` triple, alpha applied per-dot */
	color?: string;
	/** how far a ring travels outward per second, in px */
	waveSpeed?: number;
	/** wave period in seconds */
	wavePeriod?: number;
	/** peak radial displacement as a fraction of each dot's distance from focus */
	amplitude?: number;
	/** px radius of the 8-lobed ripple warp */
	ringWarp?: number;
}

interface Dot {
	x: number;
	y: number;
}

function roundedSquareWave(t: number, delta: number, a: number, f: number) {
	// https://dsp.stackexchange.com/a/56529
	return ((2 * a) / Math.PI) * Math.atan(Math.sin(2 * Math.PI * t * f) / delta);
}

export function dotField(options: DotFieldOptions = {}): Attachment<HTMLCanvasElement> {
	return (canvas) => {
		if (typeof window === 'undefined') return;
		const context = canvas.getContext('2d');
		if (!context) return;

		const spacing = options.spacing ?? 26;
		const baseRadius = options.radius ?? 2.1;
		const color = options.color ?? '255 255 255';
		const waveSpeed = options.waveSpeed ?? 260;
		const wavePeriod = options.wavePeriod ?? 5.4;
		const amplitude = options.amplitude ?? 0.15;
		const ringWarp = options.ringWarp ?? spacing * 0.5;
		const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

		let dots: Dot[] = [];
		let width = 0;
		let height = 0;
		let raf = 0;
		const focus = { x: 0, y: 0 };
		const pointer = { x: 0, y: 0, active: false };

		function layout() {
			const rect = canvas.getBoundingClientRect();
			const dpr = Math.min(window.devicePixelRatio || 1, 2);
			width = rect.width;
			height = rect.height;
			canvas.width = Math.round(width * dpr);
			canvas.height = Math.round(height * dpr);
			context!.setTransform(dpr, 0, 0, dpr, 0, 0);
			focus.x = width / 2;
			focus.y = height / 2;

			// Hex-packed grid: alternate columns drop half a row.
			dots = [];
			const cols = Math.ceil(width / spacing) + 1;
			const rows = Math.ceil(height / spacing) + 2;
			for (let col = 0; col < cols; col++) {
				const xJitter = (Math.random() - 0.5) * spacing * 0.12;
				for (let row = 0; row < rows; row++) {
					const x = col * spacing + xJitter;
					const y = row * spacing + (col % 2 === 1 ? spacing / 2 : 0);
					dots.push({ x, y });
				}
			}
		}

		function frame(timeMs: number) {
			const time = timeMs * 0.001;

			// Focus drifts to the pointer while it's over the panel, and
			// back to center once it leaves — same math either way, so the
			// field never "resets", it just glides.
			const targetX = pointer.active ? pointer.x : width / 2;
			const targetY = pointer.active ? pointer.y : height / 2;
			focus.x += (targetX - focus.x) * 0.04;
			focus.y += (targetY - focus.y) * 0.04;

			context!.clearRect(0, 0, width, height);
			for (const dot of dots) {
				const dx = dot.x - focus.x;
				const dy = dot.y - focus.y;
				const angle = Math.atan2(dy, dx);
				const dist = Math.hypot(dx, dy) + Math.cos(angle * 8) * ringWarp;

				const t = time - dist / waveSpeed;
				const delta = 0.16 + dist * 0.0007;
				const wave = roundedSquareWave(t, delta, amplitude, 1 / wavePeriod);

				const scale = 1 + wave;
				const px = focus.x + dx * scale;
				const py = focus.y + dy * scale;
				const alpha = Math.min(0.55, Math.max(0.1, 0.26 + wave * 0.7));
				const r = Math.max(0.6, baseRadius * (1 + wave * 0.6));

				context!.beginPath();
				context!.fillStyle = `rgb(${color} / ${alpha.toFixed(3)})`;
				context!.arc(px, py, r, 0, Math.PI * 2);
				context!.fill();
			}
			raf = requestAnimationFrame(frame);
		}

		function drawStatic() {
			context!.clearRect(0, 0, width, height);
			context!.fillStyle = `rgb(${color} / 0.26)`;
			for (const dot of dots) {
				context!.beginPath();
				context!.arc(dot.x, dot.y, baseRadius, 0, Math.PI * 2);
				context!.fill();
			}
		}

		function handleMove(event: PointerEvent) {
			const rect = canvas.getBoundingClientRect();
			pointer.x = event.clientX - rect.left;
			pointer.y = event.clientY - rect.top;
			pointer.active = true;
		}

		function handleLeave() {
			pointer.active = false;
		}

		layout();

		if (reduceMotion) {
			drawStatic();
		} else {
			raf = requestAnimationFrame(frame);
			canvas.addEventListener('pointermove', handleMove);
			canvas.addEventListener('pointerleave', handleLeave);
		}

		const resizeObserver = new ResizeObserver(() => {
			layout();
			if (reduceMotion) drawStatic();
		});
		resizeObserver.observe(canvas);

		return () => {
			cancelAnimationFrame(raf);
			resizeObserver.disconnect();
			canvas.removeEventListener('pointermove', handleMove);
			canvas.removeEventListener('pointerleave', handleLeave);
		};
	};
}
