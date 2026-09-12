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
	/** Periodically draw a left-to-right market trace through existing
	 *  grid points. The trace is omitted for reduced-motion users. */
	stockTrace?: boolean;
}

interface Dot {
	x: number;
	y: number;
	renderX: number;
	renderY: number;
	renderRadius: number;
}

interface StockTrace {
	points: Dot[];
	startedAt: number;
	duration: number;
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
		let columns: Dot[][] = [];
		let stockTrace: StockTrace | null = null;
		let nextTraceAt = Number.POSITIVE_INFINITY;
		let width = 0;
		let height = 0;
		let viewportHeight = 0;
		let raf = 0;
		const focus = { x: 0, y: 0 };
		const pointer = { x: 0, y: 0, active: false };

		function layout() {
			const dpr = Math.min(window.devicePixelRatio || 1, 2);

			const rect = canvas.getBoundingClientRect();
			width = rect.width;
			viewportHeight = rect.height;
			height = viewportHeight;

			canvas.width = Math.round(width * dpr);
			canvas.height = Math.round(height * dpr);
			context!.setTransform(dpr, 0, 0, dpr, 0, 0);
			context!.lineCap = 'round';
			context!.lineJoin = 'round';
			focus.x = width / 2;
			focus.y = viewportHeight / 2;

			// Hex-packed grid extends three columns past each viewport edge
			// so traces enter and leave without clipped markers.
			dots = [];
			columns = [];
			const horizontalOverscan = 3;
			const cols = Math.ceil(width / spacing) + 1 + horizontalOverscan * 2;
			const rows = Math.ceil(viewportHeight / spacing) + 2;
			for (let col = 0; col < cols; col++) {
				const column: Dot[] = [];
				const xJitter = (Math.random() - 0.5) * spacing * 0.12;
				for (let row = 0; row < rows; row++) {
					const x = (col - horizontalOverscan) * spacing + xJitter;
					const y = row * spacing + (col % 2 === 1 ? spacing / 2 : 0);
					const dot = { x, y, renderX: x, renderY: y, renderRadius: baseRadius };
					column.push(dot);
					dots.push(dot);
				}
				columns.push(column);
			}

			stockTrace = null;
			nextTraceAt = options.stockTrace
				? performance.now() + 2400 + Math.random() * 1800
				: Number.POSITIVE_INFINITY;
		}

		function addAsteriskPath(x: number, y: number, radius: number) {
			const diagonalX = radius * 0.5;
			const diagonalY = radius * 0.8660254;

			context!.moveTo(x - radius, y);
			context!.lineTo(x + radius, y);
			context!.moveTo(x - diagonalX, y - diagonalY);
			context!.lineTo(x + diagonalX, y + diagonalY);
			context!.moveTo(x - diagonalX, y + diagonalY);
			context!.lineTo(x + diagonalX, y - diagonalY);
		}

		function createStockTrace(startedAt: number): StockTrace | null {
			if (columns.length < 2 || columns[0].length < 7) return null;

			const points: Dot[] = [];
			const lastRow = columns[0].length - 1;
			const minRow = 2;
			const maxRow = lastRow - 2;
			const rowRange = maxRow - minRow;
			let row = minRow + Math.floor(rowRange * (0.2 + Math.random() * 0.6));
			const columnStep = Math.max(1, Math.round(52 / spacing));

			for (let col = 0; col < columns.length; col += columnStep) {
				points.push(columns[col][row]);

				let rowStep = Math.floor(Math.random() * 5) - 2;
				if (rowStep === 0 && Math.random() < 0.7) {
					rowStep = Math.random() < 0.5 ? -1 : 1;
				}
				row = Math.max(minRow, Math.min(maxRow, row + rowStep));
			}

			const finalColumn = columns.at(-1)!;
			if (points.at(-1) !== finalColumn[row]) points.push(finalColumn[row]);

			return { points, startedAt, duration: 4800 };
		}

		function smoothstep(value: number) {
			const clamped = Math.max(0, Math.min(1, value));
			return clamped * clamped * (3 - 2 * clamped);
		}

		function drawTraceSegments(
			points: Dot[],
			pointIndex: number,
			segmentProgress: number,
			scrollY: number,
			direction: -1 | 0 | 1,
			strokeStyle: string
		) {
			context!.beginPath();
			for (let index = 0; index <= pointIndex && index < points.length - 1; index++) {
				const from = points[index];
				const to = points[index + 1];
				const ratio = index < pointIndex ? 1 : segmentProgress;
				if (ratio <= 0) continue;

				const deltaY = to.y - from.y;
				const segmentDirection = deltaY < -0.5 ? -1 : deltaY > 0.5 ? 1 : 0;
				if (segmentDirection !== direction) continue;

				context!.moveTo(from.renderX, from.renderY + scrollY);
				context!.lineTo(
					from.renderX + (to.renderX - from.renderX) * ratio,
					from.renderY + (to.renderY - from.renderY) * ratio + scrollY
				);
			}
			context!.lineWidth = 1.5;
			context!.strokeStyle = strokeStyle;
			context!.stroke();
		}

		function drawStockTrace(timeMs: number, scrollY: number) {
			if (!options.stockTrace) return;

			if (!stockTrace && timeMs >= nextTraceAt) {
				stockTrace = createStockTrace(timeMs);
			}
			if (!stockTrace) return;

			const age = (timeMs - stockTrace.startedAt) / stockTrace.duration;
			if (age >= 1) {
				stockTrace = null;
				nextTraceAt = timeMs + 2600 + Math.random() * 2200;
				return;
			}

			const points = stockTrace.points;
			const drawProgress = smoothstep(age / 0.78);
			const progress = drawProgress * (points.length - 1);
			const pointIndex = Math.floor(progress);
			const segmentProgress = progress - pointIndex;
			const fade = age < 0.08
				? smoothstep(age / 0.08)
				: age > 0.86
					? 1 - smoothstep((age - 0.86) / 0.14)
					: 1;

			const lineAlpha = (0.82 * fade).toFixed(3);
			drawTraceSegments(
				points,
				pointIndex,
				segmentProgress,
				scrollY,
				-1,
				`rgb(133 251 175 / ${lineAlpha})`
			);
			drawTraceSegments(
				points,
				pointIndex,
				segmentProgress,
				scrollY,
				1,
				`rgb(255 140 151 / ${lineAlpha})`
			);
			drawTraceSegments(
				points,
				pointIndex,
				segmentProgress,
				scrollY,
				0,
				`rgb(${color} / ${(0.5 * fade).toFixed(3)})`
			);

			context!.beginPath();
			const lastHighlighted = Math.min(points.length - 1, Math.ceil(progress));
			for (let index = 0; index <= lastHighlighted; index++) {
				const arrival = smoothstep(progress - index + 0.5);
				if (arrival <= 0) continue;
				const point = points[index];
				addAsteriskPath(
					point.renderX,
					point.renderY + scrollY,
					point.renderRadius * (1 + arrival * 0.9)
				);
			}
			context!.lineWidth = Math.max(0.9, baseRadius * 0.68);
			context!.strokeStyle = `rgb(${color} / ${(0.78 * fade).toFixed(3)})`;
			context!.stroke();
		}

		function frame(timeMs: number) {
			const time = timeMs * 0.001;
			const scrollY = 0;
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
			context!.beginPath();
			for (const dot of dots) {
				const dx = dot.x - focus.x;
				const dy = dot.y - focus.y;
				const angle = Math.atan2(dy, dx);
				const dist = Math.hypot(dx, dy) + Math.cos(angle * 8) * ringWarp;

				const t = time - dist / waveSpeed;
				const delta = 0.16 + dist * 0.0007;
				const wave = roundedSquareWave(t, delta, amplitude, 1 / wavePeriod);

				const scale = 1 + wave;
				dot.renderX = focus.x + dx * scale;
				dot.renderY = focus.y + dy * scale;
				dot.renderRadius = Math.max(0.6, baseRadius * (1 + wave * 0.6));

				addAsteriskPath(dot.renderX, dot.renderY + scrollY, dot.renderRadius);
			}
			context!.lineWidth = Math.max(0.55, baseRadius * 0.38);
			context!.strokeStyle = `rgb(${color} / 0.3)`;
			context!.stroke();
			drawStockTrace(timeMs, scrollY);
			raf = requestAnimationFrame(frame);
		}

		function drawStatic() {
			const scrollY = 0;
			context!.clearRect(0, scrollY, width, viewportHeight);
			context!.beginPath();
			for (const dot of dots) {
				addAsteriskPath(dot.x, dot.y + scrollY, baseRadius);
			}
			context!.lineWidth = Math.max(0.55, baseRadius * 0.38);
			context!.strokeStyle = `rgb(${color} / 0.26)`;
			context!.stroke();
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
			listenTarget.addEventListener('pointermove', handleMove as EventListener);
			if (options.boundless) {
				// There is no reliable "pointerleave the document" event;
				// this fires when the cursor exits the browser viewport.
				document.addEventListener('mouseleave', handleLeave);
			} else {
				listenTarget.addEventListener('pointerleave', handleLeave as EventListener);
			}
		}

		const resizeObserver = new ResizeObserver(() => {
			layout();
			if (reduceMotion) drawStatic();
		});
		resizeObserver.observe(canvas);

		return () => {
			cancelAnimationFrame(raf);
			resizeObserver.disconnect();
			listenTarget.removeEventListener('pointermove', handleMove as EventListener);
			if (options.boundless) {
				document.removeEventListener('mouseleave', handleLeave);
			} else {
				listenTarget.removeEventListener('pointerleave', handleLeave as EventListener);
			}
		};
	};
}
