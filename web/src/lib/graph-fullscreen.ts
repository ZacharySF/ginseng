/** Native element fullscreen, with an expanded viewport for unsupported browsers. */
export function createGraphFullscreen(onChange: (expanded: boolean) => void, plot: () => HTMLElement) {
	let stage: HTMLElement;
	let alive = false;
	let expanded = false;
	let fallback = false;
	let busy = false;
	let previousFocus: HTMLElement | null = null;
	let previousOverflow = '';
	let inertSiblings: { element: HTMLElement; inert: boolean }[] = [];

	function update(value: boolean) {
		if (expanded === value) return;
		expanded = value;
		stage.classList.toggle('is-expanded', value);
		stage.dataset.expanded = String(value);
		onChange(value);
		if (value) plot()?.focus({ preventScroll: true });
		else if (previousFocus?.isConnected) previousFocus.focus({ preventScroll: true });
	}
	function leaveFallback() {
		if (!fallback) return;
		fallback = false;
		document.body.style.overflow = previousOverflow;
		for (const { element, inert } of inertSiblings) element.inert = inert;
		inertSiblings = [];
		update(false);
	}
	function enterFallback() {
		fallback = true;
		previousOverflow = document.body.style.overflow;
		document.body.style.overflow = 'hidden';
		// Keep the expanded graph's controls reachable while excluding the page
		// behind it from keyboard and assistive-technology navigation.
		for (let branch: HTMLElement | null = stage; branch?.parentElement; branch = branch.parentElement) {
			for (const sibling of branch.parentElement.children) {
				if (sibling !== branch && sibling instanceof HTMLElement) {
					inertSiblings.push({ element: sibling, inert: sibling.inert });
					sibling.inert = true;
				}
			}
			if (branch.parentElement === document.body) break;
		}
		update(true);
	}
	async function toggle() {
		if (!alive || busy) return;
		busy = true;
		try {
			if (fallback) leaveFallback();
			else if (document.fullscreenElement === stage) await document.exitFullscreen();
			else {
				previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
				try {
					if (!stage.requestFullscreen) throw new Error('Element fullscreen unavailable');
					await stage.requestFullscreen();
					if (alive) update(document.fullscreenElement === stage);
				} catch {
					if (alive) enterFallback();
				}
			}
		} catch {
			// A browser may refuse an exit during its own fullscreen transition.
			// Keep the UI synchronized so the user can retry with Escape/button.
			if (alive) changed();
		} finally { busy = false; }
	}
	function changed() {
		if (!fallback) update(document.fullscreenElement === stage);
	}
	function keydown(event: KeyboardEvent) {
		if (!expanded) return;
		if (event.key === 'Escape') {
			event.preventDefault();
			void toggle();
		} else if (fallback && event.key === 'Tab') {
			const items = [...stage.querySelectorAll<HTMLElement>('button:not([disabled]), select:not([disabled]), input:not([disabled]), summary, a[href], [tabindex="0"]')].filter(item => item.getClientRects().length > 0);
			const first = items[0], last = items.at(-1);
			if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
			else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
		}
	}
	function attach(node: HTMLElement) {
		stage = node;
		alive = true;
		stage.dataset.expanded = 'false';
		document.addEventListener('fullscreenchange', changed);
		document.addEventListener('keydown', keydown);
		return { destroy() {
			alive = false;
			document.removeEventListener('fullscreenchange', changed);
			document.removeEventListener('keydown', keydown);
			leaveFallback();
			if (document.fullscreenElement === stage) void document.exitFullscreen().catch(() => {});
		} };
	}
	return { attach, toggle };
}
