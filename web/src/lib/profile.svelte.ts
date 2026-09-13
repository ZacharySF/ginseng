// Reactive profile store backed by the `public.profiles` table.
//
// The store is passive on purpose: the root layout's `$effect` observes
// `authStore.status` and calls `load()` once a session exists. Supabase
// docs recommend public tables referencing `auth.users` guarded by RLS
// (policies live in `supabase/migrations/0001_onboarding.sql`):
//   https://supabase.com/docs/guides/auth/managing-user-data
import { supabase, supabaseConfigured } from './supabase';
import { authStore } from './auth.svelte';

export type SetupPath = 'manual' | 'sample' | 'import';

export interface Profile {
	id: string;
	first_name: string | null;
	last_name: string | null;
	onboarding_step: number;
	onboarding_completed: boolean;
	setup_path: SetupPath | null;
}

export type ProfileStatus = 'idle' | 'loading' | 'loaded' | 'missing' | 'error' | 'bypassed';

const PROFILE_COLUMNS = 'id, first_name, last_name, onboarding_step, onboarding_completed, setup_path';

class ProfileStore {
	profile = $state<Profile | null>(null);
	status = $state<ProfileStatus>(supabaseConfigured ? 'idle' : 'bypassed');
	loadError = $state<string | null>(null);
	saving = $state(false);
	ownerId = $state<string | null>(null);
	private generation = 0;

	readonly needsOnboarding = $derived(
		this.status === 'missing' || (this.status === 'loaded' && !this.profile?.onboarding_completed)
	);

	isReadyFor(userId: string): boolean {
		return this.ownerId === userId && (this.status === 'loaded' || this.status === 'missing');
	}

	private isCurrent(userId: string, generation: number): boolean {
		return (
			this.generation === generation &&
			this.ownerId === userId &&
			authStore.status === 'signed-in' &&
			authStore.user?.id === userId
		);
	}

	private resetForOwner(ownerId: string | null): void {
		this.generation += 1;
		this.ownerId = ownerId;
		this.profile = null;
		this.loadError = null;
		this.saving = false;
		this.status = ownerId === null ? (supabaseConfigured ? 'idle' : 'bypassed') : 'idle';
	}

	private async selectOwnedProfile(ownerId: string): Promise<Profile | null | undefined> {
		if (!supabase) return undefined;
		try {
			const { data, error } = await supabase
				.from('profiles')
				.select(PROFILE_COLUMNS)
				.eq('id', ownerId)
				.maybeSingle();
			if (error) return undefined;
			return data ? (data as Profile) : null;
		} catch {
			return undefined;
		}
	}

	private async createOwnedProfile(userId: string): Promise<Profile | null> {
		if (!supabase) return null;
		const metadata = (authStore.user?.user_metadata ?? {}) as {
			first_name?: string;
			last_name?: string;
		};
		try {
			const { data, error } = await supabase
				.from('profiles')
				.insert({
					id: userId,
					first_name: metadata.first_name?.trim() || null,
					last_name: metadata.last_name?.trim() || null
				})
				.select(PROFILE_COLUMNS)
				.single();
			if (!error && data) return data as Profile;
		} catch {
			// A concurrent trigger or request can create this owner's row first.
		}

		const recovered = await this.selectOwnedProfile(userId);
		return recovered ?? null;
	}

	private async updateOwnedProfile(
		ownerId: string,
		patch: Partial<Pick<Profile, 'onboarding_step' | 'setup_path' | 'onboarding_completed'>>
	): Promise<Profile | null | undefined> {
		if (!supabase) return undefined;
		try {
			const { data, error } = await supabase
				.from('profiles')
				.update(patch)
				.eq('id', ownerId)
				.select(PROFILE_COLUMNS)
				.maybeSingle();
			if (error) return undefined;
			return data ? (data as Profile) : null;
		} catch {
			return undefined;
		}
	}

	// Callers: root layout once signed in; retry controls after a failure.
	// Stale requests are ignored when the authenticated owner changes.
	async load(): Promise<void> {
		if (!supabase || authStore.status !== 'signed-in' || !authStore.user) return;

		const userId = authStore.user.id;
		if (this.ownerId !== userId) this.resetForOwner(userId);
		if (this.status === 'loading') return;

		const generation = this.generation;
		this.status = 'loading';
		this.loadError = null;

		const existing = await this.selectOwnedProfile(userId);
		if (!this.isCurrent(userId, generation)) return;
		if (existing === undefined) {
			this.status = 'error';
			this.loadError = 'We could not load your setup. Check your connection and try again.';
			return;
		}
		if (existing) {
			this.profile = existing;
			this.status = 'loaded';
			return;
		}

		const created = await this.createOwnedProfile(userId);
		if (!this.isCurrent(userId, generation)) return;
		if (!created) {
			this.status = 'error';
			this.loadError = 'We could not prepare your setup record. Please retry.';
			return;
		}

		this.profile = created;
		this.status = 'loaded';
	}

	reset(): void {
		this.resetForOwner(null);
	}

	private async persist(
		patch: Partial<Pick<Profile, 'onboarding_step' | 'setup_path' | 'onboarding_completed'>>
	): Promise<boolean> {
		const userId = authStore.user?.id;
		if (
			!supabase ||
			authStore.status !== 'signed-in' ||
			!userId ||
			this.ownerId !== userId ||
			this.profile?.id !== userId ||
			this.status !== 'loaded'
		) {
			this.loadError = 'Your setup is not ready to save. Reload and try again.';
			return false;
		}
		if (this.saving) {
			this.loadError = 'Another setup change is still saving. Please wait.';
			return false;
		}

		const generation = this.generation;
		this.saving = true;
		this.loadError = null;
		try {
			let saved = await this.updateOwnedProfile(userId, patch);
			if (!this.isCurrent(userId, generation)) return false;

			if (saved === null) {
				const recovered = await this.createOwnedProfile(userId);
				if (!this.isCurrent(userId, generation)) return false;
				if (!recovered) {
					this.loadError = 'Your setup record could not be recovered. Please retry.';
					return false;
				}
				saved = await this.updateOwnedProfile(userId, patch);
				if (!this.isCurrent(userId, generation)) return false;
			}

			if (!saved) {
				this.loadError = 'We could not save your setup. Check your connection and try again.';
				return false;
			}

			this.profile = saved;
			return true;
		} catch {
			if (this.isCurrent(userId, generation)) {
				this.loadError = 'We could not save your setup. Check your connection and try again.';
			}
			return false;
		} finally {
			if (this.isCurrent(userId, generation)) this.saving = false;
		}
	}

	async updateStep(step: number): Promise<boolean> {
		return this.persist({ onboarding_step: step });
	}

	async setSetupPath(path: SetupPath): Promise<boolean> {
		return this.persist({ setup_path: path });
	}

	async completeSetup(path: SetupPath): Promise<boolean> {
		return this.persist({ setup_path: path, onboarding_completed: true });
	}
}

export const profileStore = new ProfileStore();
