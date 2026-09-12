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
	/** Track the pointer across the whole document instead of just this
	 *  canvas's parent, and never "leave" until the pointer exits the
	 *  window. For a page-spanning field whose own parent no longer
	 *  contains the content painted over it (that content lives in
	 *  unrelated sibling sections), so parentElement-scoped tracking
	 *  would silently stop updating the moment the cursor crosses any
	 *  of it. */
	boundless?: boolean;
	/** Size the canvas to the full document height and shift the drawn
	 *  dots by the live scroll offset each frame, instead of sizing to
	 *  the canvas's own (viewport-sized) layout box. Used instead of
	 *  position:fixed/sticky to make the pattern look pinned to the
	 *  viewport while scrolling: backdrop-filter reliably blurring a
	 *  fixed/sticky backdrop is inconsistently supported across
	 *  browsers, but blurring ordinary scrolling content — which is
	 *  what this canvas becomes in this mode — is the well-tested case. */
	pinned?: boolean;
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
		let viewportHeight = 0;
		let raf = 0;
		const focus = { x: 0, y: 0 };
		const pointer = { x: 0, y: 0, active: false };

		function layout() {
			const dpr = Math.min(window.devicePixelRatio || 1, 2);

			if (options.pinned) {
				width = window.innerWidth;
				viewportHeight = window.innerHeight;
				height = Math.max(viewportHeight, document.documentElement.scrollHeight);
				canvas.style.width = `${width}px`;
				canvas.style.height = `${height}px`;
			} else {
				const rect = canvas.getBoundingClientRect();
				width = rect.width;
				viewportHeight = rect.height;
				height = viewportHeight;
			}

			canvas.width = Math.round(width * dpr);
			canvas.height = Math.round(height * dpr);
			context!.setTransform(dpr, 0, 0, dpr, 0, 0);
			focus.x = width / 2;
			focus.y = viewportHeight / 2;

			// Hex-packed grid: alternate columns drop half a row. Laid out
			// per viewport, not per document — in pinned mode the same
			// viewport-sized tile is redrawn into whichever band of the
			// tall canvas is currently on screen (see `frame`).
			dots = [];
			const cols = Math.ceil(width / spacing) + 1;
			const rows = Math.ceil(viewportHeight / spacing) + 2;
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
			const scrollY = options.pinned ? window.scrollY : 0;
			// Overscanned so dots animating past the viewport edge (the
			// wave can push them outward by up to ~amplitude of their
			// focus distance) don't leave a stale trailing edge.
			const overscan = 120;

			// Focus drifts to the pointer while it's over the panel, and
			// back to center once it leaves — same math either way, so the
			// field never "resets", it just glides.
			const targetX = pointer.active ? pointer.x : width / 2;
			const targetY = pointer.active ? pointer.y : viewportHeight / 2;
			focus.x += (targetX - focus.x) * 0.04;
			focus.y += (targetY - focus.y) * 0.04;

			context!.clearRect(0, scrollY - overscan, width, viewportHeight + overscan * 2);
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
				context!.arc(px, py + scrollY, r, 0, Math.PI * 2);
				context!.fill();
			}
			raf = requestAnimationFrame(frame);
		}

		function drawStatic() {
			const scrollY = options.pinned ? window.scrollY : 0;
			context!.clearRect(0, scrollY, width, viewportHeight);
			context!.fillStyle = `rgb(${color} / 0.26)`;
			for (const dot of dots) {
				context!.beginPath();
				context!.arc(dot.x, dot.y + scrollY, baseRadius, 0, Math.PI * 2);
				context!.fill();
			}
		}

		// Listen on the parent section by default, not the canvas itself:
		// `.hero-copy` (headline, body, buttons) paints on top of the
		// canvas and would otherwise steal pointermove/pointerleave the
		// instant the cursor crosses onto it, snapping the focus back to
		// center mid-hover. pointermove bubbles up from any descendant;
		// pointerleave only fires once the pointer exits the whole
		// section, not on parent-to-child handoffs, so this tracks the
		// cursor everywhere inside the panel and only resets on a true
		// exit. `boundless` widens this to the whole document, for a
		// field whose overlapping content isn't a descendant at all.
		const listenTarget: Document | HTMLElement = options.boundless
			? document
			: (canvas.parentElement ?? canvas);

		function handleMove(event: PointerEvent) {
			if (options.pinned) {
				// Viewport-relative, matching the viewport-relative dot/focus
				// math — not canvas-relative, since the canvas is now much
				// taller than the viewport.
				pointer.x = event.clientX;
				pointer.y = event.clientY;
			} else {
				const rect = canvas.getBoundingClientRect();
				pointer.x = event.clientX - rect.left;
				pointer.y = event.clientY - rect.top;
			}
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
			listenTarget.addEventListener('pointermove', handleMove as EventListener);
			if (options.boundless) {
				// There is no reliable "pointerleave the document" event;
				// this fires when the cursor exits the browser viewport.
				document.addEventListener('mouseleave', handleLeave);
			} else {
				listenTarget.addEventListener('pointerleave', handleLeave as EventListener);
			}
		}

		// In pinned mode the canvas's own size is set by `layout()` itself
		// (from document.documentElement.scrollHeight); observing the
		// canvas would re-trigger on every layout() call. Observe
		// document.body instead — .ambient-field clips to it (overflow:
		// hidden), so the canvas can never grow it, only shrink/grow in
		// response to it.
		const resizeObserver = new ResizeObserver(() => {
			layout();
			if (reduceMotion) drawStatic();
		});
		resizeObserver.observe(options.pinned ? document.body : canvas);
		if (options.pinned) window.addEventListener('resize', layout);

		return () => {
			cancelAnimationFrame(raf);
			resizeObserver.disconnect();
			if (options.pinned) window.removeEventListener('resize', layout);
			listenTarget.removeEventListener('pointermove', handleMove as EventListener);
			if (options.boundless) {
				document.removeEventListener('mouseleave', handleLeave);
			} else {
				listenTarget.removeEventListener('pointerleave', handleLeave as EventListener);
			}
		};
	};
}
