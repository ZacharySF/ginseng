// Supabase browser client for Ginseng auth.
//
// `$env/static/public` is SvelteKit's documented channel for client-side
// env vars — it statically replaces `PUBLIC_`-prefixed values at build
// time. Bare `import.meta.env.PUBLIC_*` is a Vite convention SvelteKit
// does not guarantee (its public prefix is funneled through this module
// specifically, not through Vite's `envPrefix`).
// Source: https://svelte.dev/docs/kit/$env-static-public
//
// The publishable (anon) key is designed to be exposed to browsers —
// access control happens through Row Level Security in Postgres, not
// through hiding this key.
import { createClient } from '@supabase/supabase-js';
import type { SupabaseClient } from '@supabase/supabase-js';
import { PUBLIC_SUPABASE_URL, PUBLIC_SUPABASE_PUBLISHABLE_KEY } from '$env/static/public';

export const supabase: SupabaseClient | null =
	PUBLIC_SUPABASE_URL && PUBLIC_SUPABASE_PUBLISHABLE_KEY
		? createClient(PUBLIC_SUPABASE_URL, PUBLIC_SUPABASE_PUBLISHABLE_KEY)
		: null;

export const supabaseConfigured = supabase !== null;
