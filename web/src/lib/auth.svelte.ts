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
	// Source: https://supabase.com/docs/guides/auth/passwords#signing-up-with-an-email-and-password
	async signUp(email: string, password: string): Promise<{ needsEmailConfirmation: boolean }> {
		if (!supabase) throw new Error('Supabase is not configured.');
		const { data, error } = await supabase.auth.signUp({ email, password });
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
