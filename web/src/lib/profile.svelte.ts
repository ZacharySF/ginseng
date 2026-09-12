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

	// `bypassed` is the no-Supabase offline demo; `error` fails open to
	// the app rather than trapping the user in a gate whose persistence
	// is broken — the onboarding page surfaces write errors instead.
	readonly needsOnboarding = $derived(
		this.status === 'bypassed' || this.status === 'error'
			? false
			: this.status === 'missing' || (this.status === 'loaded' && !this.profile?.onboarding_completed)
	);

	// Callers: root layout once signed in; onboarding page on changes.
	// Throws nothing — inspect `status`/`loadError` instead.
	async load(): Promise<void> {
		if (!supabase || authStore.status !== 'signed-in' || this.status === 'loading') return;

		const user = authStore.user;
		if (!user) return;

		this.status = 'loading';
		this.loadError = null;

		const { data, error } = await supabase.from('profiles').select(PROFILE_COLUMNS).eq('id', user.id).maybeSingle();

		if (error) {
			this.status = 'error';
			this.loadError = error.message;
			return;
		}

		if (data) {
			this.profile = data as Profile;
			this.status = 'loaded';
			return;
		}

		// No row yet (pre-trigger signup whose backfill raced). Self-heal
		// by inserting from user metadata; the insert policy allows the
		// owner to create their own row.
		const meta = (user.user_metadata ?? {}) as { first_name?: string; last_name?: string };
		const { data: inserted, error: insertError } = await supabase
			.from('profiles')
			.insert({
				id: user.id,
				first_name: meta.first_name?.trim() || null,
				last_name: meta.last_name?.trim() || null
			})
			.select(PROFILE_COLUMNS)
			.single();

		if (insertError) {
			this.status = 'error';
			this.loadError = insertError.message;
			return;
		}

		this.profile = inserted as Profile;
		this.status = 'loaded';
	}

	reset(): void {
		this.profile = null;
		this.loadError = null;
		this.status = supabaseConfigured ? 'idle' : 'bypassed';
	}

	// Advance the persisted step so a reload resumes where the user left
	// off. PostgREST upsert updates only the columns present in the
	// payload, so this never clobbers setup_path or completion.
	// Source: https://supabase.com/docs/reference/javascript/upsert
	async updateStep(step: number): Promise<boolean> {
		if (!supabase || !this.profile) return false;
		const { error } = await supabase.from('profiles').upsert({
			id: this.profile.id,
			onboarding_step: step
		});
		if (error) {
			this.loadError = error.message;
			return false;
		}
		this.profile = { ...this.profile, onboarding_step: step };
		return true;
	}

	// Persisted as soon as the user picks it so a reload mid-onboarding
	// restores the chosen path, not just the step number.
	async setSetupPath(path: SetupPath): Promise<boolean> {
		if (!supabase || !this.profile) return false;
		const { error } = await supabase.from('profiles').upsert({
			id: this.profile.id,
			setup_path: path
		});
		if (error) {
			this.loadError = error.message;
			return false;
		}
		this.profile = { ...this.profile, setup_path: path };
		return true;
	}

	async completeSetup(path: SetupPath): Promise<boolean> {
		if (!supabase || !this.profile) return false;
		const { error } = await supabase.from('profiles').upsert({
			id: this.profile.id,
			setup_path: path,
			onboarding_completed: true
		});
		if (error) {
			this.loadError = error.message;
			return false;
		}
		this.profile = { ...this.profile, setup_path: path, onboarding_completed: true };
		return true;
	}
}

export const profileStore = new ProfileStore();
