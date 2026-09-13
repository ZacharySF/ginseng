export type Theme = 'light' | 'dark';
export const THEME_STORAGE_KEY = 'ginseng.theme';

let current = $state<Theme>(
	typeof document !== 'undefined' && document.documentElement.dataset.theme === 'dark'
		? 'dark' : 'light'
);

function apply(theme: Theme) {
	current = theme;
	document.documentElement.dataset.theme = theme;
}

function readPreference(): Theme {
	try {
		return localStorage.getItem(THEME_STORAGE_KEY) === 'dark' ? 'dark' : 'light';
	} catch {
		return current;
	}
}

export function initializeTheme() {
	apply(readPreference());
	function sync(event: StorageEvent) {
		if (event.key === THEME_STORAGE_KEY || event.key === null) apply(readPreference());
	}
	window.addEventListener('storage', sync);
	return () => window.removeEventListener('storage', sync);
}

export const themeStore = {
	get current() { return current; },
	toggle() {
		const next = current === 'dark' ? 'light' : 'dark';
		apply(next);
		// The switch still works if the browser blocks preference storage.
		try { localStorage.setItem(THEME_STORAGE_KEY, next); } catch { /* Session only. */ }
	}
};
