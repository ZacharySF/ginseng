import type { Camera } from 'plotly.js';

type GraphCamera = Partial<Camera>;
type Controls = {
	read: () => GraphCamera | null;
	apply: (camera: GraphCamera) => Promise<void>;
	toggleFullscreen?: () => Promise<void>;
	onError: () => void;
};

const step = Math.PI / 30;
const elevationLimit = Math.PI / 2 - .05;
const arrows = new Set(['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown']);

/** Orbit the current focal point without changing zoom or rolling the scene. */
function orbit(camera: GraphCamera, key: string): GraphCamera {
	const center = { x: camera.center?.x ?? 0, y: camera.center?.y ?? 0, z: camera.center?.z ?? 0 };
	const x = (camera.eye?.x ?? 1.25) - center.x;
	const y = (camera.eye?.y ?? 1.25) - center.y;
	const z = (camera.eye?.z ?? 1.25) - center.z;
	const radius = Math.hypot(x, y, z) || 1;
	const azimuth = Math.atan2(y, x) + (key === 'ArrowRight' ? step : key === 'ArrowLeft' ? -step : 0);
	const elevation = Math.max(-elevationLimit, Math.min(elevationLimit,
		Math.atan2(z, Math.hypot(x, y)) + (key === 'ArrowUp' ? step : key === 'ArrowDown' ? -step : 0)));
	const horizontal = radius * Math.cos(elevation);
	return {
		...camera,
		center,
		eye: { x: center.x + horizontal * Math.cos(azimuth), y: center.y + horizontal * Math.sin(azimuth), z: center.z + radius * Math.sin(elevation) },
		up: { x: 0, y: 0, z: 1 }
	};
}

/** Focus-scoped controls shared by the two Plotly scenes. */
export function graphCameraKeys(node: HTMLElement, controls: Controls) {
	let alive = true;
	let busy = false;
	let desired: GraphCamera | null = null;
	async function flush() {
		busy = true;
		try {
			while (alive && desired) {
				const next = desired;
				await controls.apply(next);
				if (desired === next) desired = null;
			}
		} catch {
			desired = null;
			if (alive) controls.onError();
		} finally {
			busy = false;
		}
	}
	function keydown(event: KeyboardEvent) {
		if (event.target !== node || event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey) return;
		if (event.key.toLowerCase() === 'f' && controls.toggleFullscreen) {
			event.preventDefault();
			if (!event.repeat) void controls.toggleFullscreen();
			return;
		}
		if (event.shiftKey || !arrows.has(event.key)) return;
		const camera = desired ?? controls.read();
		if (!camera) return;
		event.preventDefault();
		// Accumulate held keys against the latest requested camera while Plotly
		// finishes a render, then coalesce pending redraws without losing steps.
		desired = orbit(camera, event.key);
		if (!busy) void flush();
	}
	function focus(event: PointerEvent) {
		if (event.button === 0) node.focus({ preventScroll: true });
	}
	node.addEventListener('keydown', keydown);
	node.addEventListener('pointerdown', focus, true);
	return { destroy() {
		alive = false;
		desired = null;
		node.removeEventListener('keydown', keydown);
		node.removeEventListener('pointerdown', focus, true);
	} };
}
