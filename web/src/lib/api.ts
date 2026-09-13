// Typed client for the Ginseng engine. Callers must handle three distinct
// outcomes explicitly — never coalesce them into a single boolean, and never
// substitute a fabricated or fixture number for a value the engine did not
// return.
import * as publicEnv from '$env/static/public';
import { supabase } from './supabase';
import { authStore } from './auth.svelte';
import type { HealthResponse, NessieSampleResponse, ScenarioRequest, ScenarioResponse } from './types';

const configuredEngineUrl = (
	'PUBLIC_ENGINE_URL' in publicEnv
		? (publicEnv as Record<string, string | undefined>).PUBLIC_ENGINE_URL
		: undefined
)?.trim();
const ENGINE_BASE_URL =
	configuredEngineUrl && configuredEngineUrl.length > 0
		? configuredEngineUrl.replace(/\/+$/, '')
		: import.meta.env.DEV
			? 'http://localhost:8000'
			: null;
const REQUEST_TIMEOUT_MS = 8000;

export type EngineResult<T> =
	| { status: 'ok'; data: T }
	// The engine process could not be reached at all (offline, wrong URL,
	// network failure, or the request timed out waiting for a connection).
	| { status: 'engine-unreachable'; message: string }
	// The engine responded, but with a non-2xx status or a body that could
	// not be parsed as the expected shape.
	| { status: 'engine-error'; message: string; http_status?: number };

export type HealthResult = EngineResult<HealthResponse>;
export type ScenarioResult = EngineResult<ScenarioResponse>;
export type NessieSampleResult = EngineResult<NessieSampleResponse>;
export type NessieStatusResult = EngineResult<{ configured: boolean }>;

interface EngineRequestOptions {
	requiresAuth?: boolean;
	timeoutMs?: number;
}

function fetchWithTimeout(url: string, init: RequestInit, timeoutMs: number): Promise<Response> {
	const timeout = AbortSignal.timeout(timeoutMs);
	// Keep the caller's cancellation signal as well as the request deadline.
	// https://developer.mozilla.org/en-US/docs/Web/API/AbortSignal/any_static
	const signal = init.signal ? AbortSignal.any([init.signal, timeout]) : timeout;
	return fetch(url, { ...init, signal });
}

export function describeNetworkError(error: unknown, timeoutMs: number): string {
	if (error instanceof DOMException && error.name === 'TimeoutError') {
		return `The engine did not respond within ${timeoutMs / 1000}s.`;
	}
	if (error instanceof DOMException && error.name === 'AbortError') return 'The request was cancelled.';
	return 'The engine is not reachable. Check the connection and try again.';
}

function sanitizedStatusMessage(status: number): string {
	if (status === 401) return 'Your session is invalid. Sign in again.';
	if (status === 409) return 'Workspace changed. Reload before saving.';
	if (status === 503) return 'The engine is temporarily unavailable. Try again shortly.';
	if (status === 422) return 'The request could not be completed. Review your input.';
	return `The engine returned HTTP ${status}.`;
}

async function responseDetail(response: Response): Promise<string | null> {
	try {
		const payload: unknown = await response.json();
		if (
			typeof payload === 'object' &&
			payload !== null &&
			'detail' in payload &&
			typeof payload.detail === 'string'
		) {
			return payload.detail;
		}
	} catch {
		// Malformed or non-JSON failures are never surfaced verbatim.
	}
	return null;
}

async function accessToken(): Promise<string | null> {
	const ownerId = authStore.user?.id;
	if (!supabase || !ownerId) return null;
	try {
		// getSession retrieves the current session and lets the Supabase client
		// refresh it when needed before we make the bearer-authenticated request.
		const { data, error } = await supabase.auth.getSession();
		// A refresh can outlive a sign-out/account switch. Never submit the
		// previous owner's draft using the next owner's credentials.
		if (error || data.session?.user.id !== ownerId || authStore.user?.id !== ownerId) return null;
		return data.session.access_token;
	} catch {
		return null;
	}
}

async function httpErrorResult(
	response: Response
): Promise<{ status: 'engine-error'; message: string; http_status: number }> {
	const detail = await responseDetail(response);
	return {
		status: 'engine-error',
		message: detail ?? sanitizedStatusMessage(response.status),
		http_status: response.status
	};
}

async function parseJsonResponse<T>(response: Response): Promise<EngineResult<T>> {
	if (!response.ok) return httpErrorResult(response);
	try {
		const data = (await response.json()) as T;
		return { status: 'ok', data };
	} catch (error) {
		if (error instanceof DOMException && (error.name === 'AbortError' || error.name === 'TimeoutError')) {
			throw error;
		}
		return { status: 'engine-error', message: 'Engine response was not valid JSON.' };
	}
}

interface Transported {
	response: Response;
	ownerId: string | undefined;
}

// Shared by requestEngine and requestEngineStream so both JSON and streaming
// callers authenticate and race the same request deadline exactly once.
async function transport(
	path: string,
	init: RequestInit,
	options: EngineRequestOptions
): Promise<EngineResult<Transported>> {
	if (ENGINE_BASE_URL === null) {
		return {
			status: 'engine-error',
			message: 'Ginseng engine URL is not configured for this build.',
			http_status: 503
		};
	}
	const headers = new Headers(init.headers);
	const ownerId = authStore.user?.id;
	if (options.requiresAuth) {
		const token = await accessToken();
		if (!token || authStore.user?.id !== ownerId) {
			return {
				status: 'engine-error', message: 'Sign in to use Ginseng.', http_status: 401
			};
		}
		headers.set('authorization', `Bearer ${token}`);
	}
	const timeoutMs = options.timeoutMs ?? REQUEST_TIMEOUT_MS;
	try {
		const response = await fetchWithTimeout(`${ENGINE_BASE_URL}${path}`, { ...init, headers }, timeoutMs);
		return { status: 'ok', data: { response, ownerId } };
	} catch (error) {
		return { status: 'engine-unreachable', message: describeNetworkError(error, timeoutMs) };
	}
}

export async function requestEngine<T>(
	path: string,
	init: RequestInit,
	options: EngineRequestOptions = {}
): Promise<EngineResult<T>> {
	const transported = await transport(path, init, options);
	if (transported.status !== 'ok') return transported;
	const { response, ownerId } = transported.data;
	const timeoutMs = options.timeoutMs ?? REQUEST_TIMEOUT_MS;
	try {
		const result = await parseJsonResponse<T>(response);
		if (options.requiresAuth && authStore.user?.id !== ownerId) {
			return { status: 'engine-error', message: 'Your account changed. Try again.', http_status: 401 };
		}
		return result;
	} catch (error) {
		return { status: 'engine-unreachable', message: describeNetworkError(error, timeoutMs) };
	}
}

// A streamed engine response handed to callers that consume the body
// incrementally (e.g. NDJSON chat deltas) instead of parsing it as a single
// JSON document. `isOwnerCurrent` lets the consumer re-check the signed-in
// owner before acting on every frame, not only once at connect time.
export interface EngineStream {
	response: Response;
	isOwnerCurrent: () => boolean;
}

export async function requestEngineStream(
	path: string,
	init: RequestInit,
	options: EngineRequestOptions = {}
): Promise<EngineResult<EngineStream>> {
	const transported = await transport(path, init, options);
	if (transported.status !== 'ok') return transported;
	const { response, ownerId } = transported.data;
	if (options.requiresAuth && authStore.user?.id !== ownerId) {
		await response.body?.cancel().catch(() => {});
		return { status: 'engine-error', message: 'Your account changed. Try again.', http_status: 401 };
	}
	if (!response.ok) {
		// Preserve normal JSON HTTP error handling for failures that occur
		// before any streaming begins (401/422/429/503/504, ...).
		return httpErrorResult(response);
	}
	const contentType = response.headers.get('content-type') ?? '';
	if (contentType.split(';', 1)[0].trim().toLowerCase() !== 'application/x-ndjson') {
		await response.body?.cancel().catch(() => {});
		return { status: 'engine-error', message: 'Engine response was not a valid stream.' };
	}
	const isOwnerCurrent = () => !options.requiresAuth || authStore.user?.id === ownerId;
	return { status: 'ok', data: { response, isOwnerCurrent } };
}

export function getHealth(): Promise<HealthResult> {
	return requestEngine<HealthResponse>('/health', { method: 'GET' });
}

export function postScenario(request: ScenarioRequest): Promise<ScenarioResult> {
	return requestEngine<ScenarioResponse>(
		'/scenario',
		{
			method: 'POST',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify(request)
		},
		{ requiresAuth: true }
	);
}

// Nessie is a deliberately simulated demo provider; its API key never enters
// this bundle, and all access still requires the user's own session.
export function getNessieStatus(): Promise<NessieStatusResult> {
	return requestEngine<{ configured: boolean }>('/providers/nessie/status', { method: 'GET' }, { requiresAuth: true });
}

export function getNessieSample(): Promise<NessieSampleResult> {
	return requestEngine<NessieSampleResponse>('/providers/nessie/sample', { method: 'GET' }, { requiresAuth: true });
}
