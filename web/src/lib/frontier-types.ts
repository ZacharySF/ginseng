export interface FrontierMetrics {
	mean_return: number;
	volatility: number;
	pressure_cvar: number;
}
export interface FrontierPoint {
	id: string;
	label: string;
	weights: number[];
	source: 'sampled' | 'optimized' | 'anchor';
	pareto: boolean;
	discovery: FrontierMetrics;
	evaluation: FrontierMetrics;
}
export interface FrontierReady {
	status: 'ready';
	symbols: string[];
	points: FrontierPoint[];
	pressure: {
		discovery_count: number; evaluation_count: number;
		discovery_probability: number; evaluation_probability: number;
		discovery_tail_mass_count: number; evaluation_tail_mass_count: number;
	};
	metadata: Record<string, unknown>;
}
export type FrontierReport = FrontierReady | { status: 'unavailable'; message?: string; reason?: string; pressure?: Partial<FrontierReady['pressure']>; metadata?: Record<string, unknown> };
