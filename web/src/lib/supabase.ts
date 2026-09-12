// Supabase browser client for Ginseng auth.
//
// PUBLIC_SUPABASE_URL and PUBLIC_SUPABASE_PUBLISHABLE_KEY are SvelteKit
// public env vars: they are inlined into the static bundle at build time,
// which is safe because the publishable (anon) key is designed to be
// exposed to browsers — access control happens through Row Level Security
// in Postgres, not through hiding this key.
// Source: https://supabase.com/docs/guides/auth/server-side/sveltekit
import { createClient } from '@supabase/supabase-js';
import type { SupabaseClient } from '@supabase/supabase-js';

const supabaseUrl = import.meta.env.PUBLIC_SUPABASE_URL as string | undefined;
const supabasePublishableKey = import.meta.env.PUBLIC_SUPABASE_PUBLISHABLE_KEY as
	| string
	| undefined;

export const supabase: SupabaseClient | null =
	supabaseUrl && supabasePublishableKey
		? createClient(supabaseUrl, supabasePublishableKey)
		: null;

export const supabaseConfigured = supabase !== null;
