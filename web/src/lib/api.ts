// Typed client for the Ginseng engine. Callers must handle three distinct
// outcomes explicitly — never coalesce them into a single boolean, and never
// substitute a fabricated or fixture number for a value the engine did not
// return.
import type { HealthResponse, ScenarioRequest, ScenarioResponse } from './types';

const ENGINE_BASE_URL = 'http://localhost:8000';
const REQUEST_TIMEOUT_MS = 8000;

export type EngineResult<T> =
	| { status: 'ok'; data: T }
	// The engine process could not be reached at all (offline, wrong port,
	// network failure, or the request timed out waiting for a connection).
	| { status: 'engine-unreachable'; message: string }
	// The engine responded, but with a non-2xx status or a body that could
	// not be parsed as the expected shape.
	| { status: 'engine-error'; message: string; http_status?: number };

export type HealthResult = EngineResult<HealthResponse>;
export type ScenarioResult = EngineResult<ScenarioResponse>;

function fetchWithTimeout(url: string, init: RequestInit): Promise<Response> {
	return fetch(url, { ...init, signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS) });
}

function describeNetworkError(error: unknown): string {
	if (error instanceof DOMException && error.name === 'AbortError') {
		return `The engine did not respond within ${REQUEST_TIMEOUT_MS / 1000}s.`;
	}
	return `The engine is not reachable at ${ENGINE_BASE_URL}.`;
}

async function safeReadText(response: Response): Promise<string> {
	try {
		return await response.text();
	} catch {
		return '';
	}
}

async function parseJsonResponse<T>(response: Response): Promise<EngineResult<T>> {
	if (!response.ok) {
		const detail = await safeReadText(response);
		return {
			status: 'engine-error',
			message: detail || `Engine returned HTTP ${response.status}.`,
			http_status: response.status
		};
	}
	try {
		const data = (await response.json()) as T;
		return { status: 'ok', data };
	} catch {
		return { status: 'engine-error', message: 'Engine response was not valid JSON.' };
	}
}

export async function getHealth(): Promise<HealthResult> {
	let response: Response;
	try {
		response = await fetchWithTimeout(`${ENGINE_BASE_URL}/health`, { method: 'GET' });
	} catch (error) {
		return { status: 'engine-unreachable', message: describeNetworkError(error) };
	}
	return parseJsonResponse<HealthResponse>(response);
}

export async function postScenario(request: ScenarioRequest): Promise<ScenarioResult> {
	let response: Response;
	try {
		response = await fetchWithTimeout(`${ENGINE_BASE_URL}/scenario`, {
			method: 'POST',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify(request)
		});
	} catch (error) {
		return { status: 'engine-unreachable', message: describeNetworkError(error) };
	}
	return parseJsonResponse<ScenarioResponse>(response);
}
