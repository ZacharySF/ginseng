// Reactive session store backed by Supabase Auth.
//
// `onAuthStateChange` fires an `INITIAL_SESSION` event immediately on
// subscription with whatever session is already in local storage, so a
// separate `getSession()` call on startup is redundant.
// Source: https://supabase.com/docs/reference/javascript/auth-onauthstatechange
import { supabase, supabaseConfigured } from './supabase';
import type { Session, User } from '@supabase/supabase-js';

export type AuthStatus = 'loading' | 'signed-out' | 'signed-in' | 'unconfigured';

class AuthStore {
	session = $state<Session | null>(null);
	status = $state<AuthStatus>(supabaseConfigured ? 'loading' : 'unconfigured');

	readonly user = $derived<User | null>(this.session?.user ?? null);

	// `user_metadata` is Supabase's raw_user_meta_data JSON column — the
	// standard place for profile fields that don't need their own table.
	readonly displayName = $derived<string | null>(
		(() => {
			const meta = this.user?.user_metadata as { first_name?: string; last_name?: string } | undefined;
			const name = [meta?.first_name, meta?.last_name].filter(Boolean).join(' ').trim();
			return name.length > 0 ? name : null;
		})()
	);

	constructor() {
		if (!supabase) return;
		supabase.auth.onAuthStateChange((_event, session) => {
			this.session = session;
			this.status = session ? 'signed-in' : 'signed-out';
		});
	}

	// Throws the Supabase AuthError on failure; callers render `error.message`.
	// Source: https://supabase.com/docs/reference/javascript/auth-signinwithpassword
	async signInWithPassword(email: string, password: string): Promise<void> {
		if (!supabase) throw new Error('Supabase is not configured.');
		const { error } = await supabase.auth.signInWithPassword({ email, password });
		if (error) throw error;
	}

	// Hosted Supabase projects require email confirmation by default, so a
	// fresh sign-up returns no session until the user clicks the emailed
	// link — the caller must render that pending state honestly rather than
	// assuming sign-up always lands the user in the app immediately.
	// `options.data` becomes `user_metadata` on the created user; Ginseng
	// has no `profiles` table, so first/last name live there rather than
	// as unused schema.
	// Source: https://supabase.com/docs/guides/auth/passwords#signing-up-with-an-email-and-password
	async signUp(
		email: string,
		password: string,
		firstName: string,
		lastName: string
	): Promise<{ needsEmailConfirmation: boolean }> {
		if (!supabase) throw new Error('Supabase is not configured.');
		const { data, error } = await supabase.auth.signUp({
			email,
			password,
			options: { data: { first_name: firstName, last_name: lastName } }
		});
		if (error) throw error;
		return { needsEmailConfirmation: data.session === null };
	}

	async signOut(): Promise<void> {
		if (!supabase) return;
		const { error } = await supabase.auth.signOut();
		if (error) throw error;
	}
}

export const authStore = new AuthStore();
