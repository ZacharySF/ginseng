// Reactive session store backed by Supabase Auth.
//
// `onAuthStateChange` fires an `INITIAL_SESSION` event immediately on
// subscription with whatever session is already in local storage, so a
// separate `getSession()` call on startup is redundant.
// Source: https://supabase.com/docs/reference/javascript/auth-onauthstatechange
import { supabase, supabaseConfigured } from './supabase';
import { isAuthError, isAuthRetryableFetchError, type Session, type User } from '@supabase/supabase-js';

export type AuthStatus = 'loading' | 'signed-out' | 'signed-in' | 'unconfigured';

// Provider codes distinguish credentials from delivery, quota, and database failures.
// https://supabase.com/docs/guides/auth/debugging/error-codes
function authFailure(error: unknown, action: 'sign-in' | 'sign-up'): Error {
	if (isAuthRetryableFetchError(error) || error instanceof TypeError) {
		return new Error('Could not reach the account service. Check your connection and try again.');
	}
	if (isAuthError(error)) {
		switch (error.code) {
			case 'email_not_confirmed':
				return new Error('Confirm your email using the signup link before signing in.');
			case 'weak_password':
				return new Error('Use a stronger password with at least 8 characters.');
			case 'user_already_exists':
			case 'email_exists':
				return new Error('An account already exists for this email. Choose Sign in instead.');
			case 'over_request_rate_limit':
			case 'over_email_send_rate_limit':
				return new Error('Too many account requests. Wait a few minutes before trying again.');
			case 'email_address_not_authorized':
				return new Error('The account service could not send the confirmation email. Contact the app administrator.');
			case 'signup_disabled':
			case 'email_provider_disabled':
				return new Error('Account registration is currently disabled.');
		}
		if ((error.status ?? 0) >= 500) {
			return new Error('The account service could not complete the request. Try again later; your password may be correct.');
		}
	}
	return new Error(action === 'sign-in'
		? 'Could not sign in. Check your email and password, and use the same app address where you signed up.'
		: 'Could not create your account. Check your details and try again.');
}

class AuthStore {
	session = $state<Session | null>(null);
	status = $state<AuthStatus>(supabaseConfigured ? 'loading' : 'unconfigured');

	readonly user = $derived<User | null>(this.session?.user ?? null);

	// Names are seeded in user metadata during sign-up, before the database
	// trigger creates the owned profile row.
	// Source: https://supabase.com/docs/reference/javascript/auth-signup
	error = $state<string | null>(null);

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
			if (session) this.error = null;
		});
	}

	// Login failures are intentionally normalized before they reach the UI.
	// Source: https://supabase.com/docs/reference/javascript/auth-signinwithpassword
	async signInWithPassword(email: string, password: string): Promise<void> {
		if (!supabase) throw new Error('Sign-in is unavailable because Ginseng is not configured.');
		try {
			const { data, error } = await supabase.auth.signInWithPassword({ email, password });
			if (error) throw error;
			if (data.session && data.user && data.session.user.id === data.user.id) return;
		} catch (error) {
			throw authFailure(error, 'sign-in');
		}
		throw new Error('The account service did not establish a session. Try signing in again.');
	}

	// Hosted Supabase projects require email confirmation by default, so a
	// fresh sign-up returns no session until the user clicks the emailed
	// link — the caller must render that pending state honestly rather than
	// assuming sign-up always lands the user in the app immediately.
	// `options.data` seeds user metadata. The profile trigger copies these
	// names into the owned profile row created for the new user.
	// Source: https://supabase.com/docs/guides/auth/passwords#signing-up-with-an-email-and-password
	async signUp(
		email: string,
		password: string,
		firstName: string,
		lastName: string
	): Promise<{ needsEmailConfirmation: boolean }> {
		if (!supabase) throw new Error('Sign-up is unavailable because Ginseng is not configured.');
		try {
			const { data, error } = await supabase.auth.signUp({
				email,
				password,
				options: { data: { first_name: firstName, last_name: lastName } }
			});
			if (error) throw error;
			if (data.user && (!data.session || data.session.user.id === data.user.id)) {
				return { needsEmailConfirmation: data.session === null };
			}
		} catch (error) {
			throw authFailure(error, 'sign-up');
		}
		throw new Error('The account service did not confirm registration. Try again.');

	}

	async signOut(): Promise<boolean> {
		if (!supabase) return true;
		this.error = null;
		try {
			const { error } = await supabase.auth.signOut();
			if (!error) return true;
		} catch {
			// The actionable message below is intentionally stable; provider
			// failures can contain implementation details that do not help here.
		}
		this.error = 'Could not sign out. Check your connection and try again.';
		return false;
	}
}

export const authStore = new AuthStore();
