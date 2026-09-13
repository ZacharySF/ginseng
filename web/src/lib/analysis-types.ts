import type { OptimalPlan } from './types';

export interface CalibrationSample {
	spacing_days: number; overlapping: boolean; windows: number; covered: number;
	observed_coverage: number | null; interval: { low: number; high: number } | null;
	mean_pinball_loss: number | null; mean_crps: number | null;
}
export interface CalibrationReport {
	status: string; source: string; target: string; excluded: string;
	history_days: number; training_days_minimum: number; horizon_days: number;
	paths_per_forecast: number; nominal_coverage: number; primary: CalibrationSample;
	spacing_results: CalibrationSample[]; expected_tail_failures: number; interval_note: string;
	formal_tests: Record<string, { status: string; reason?: string; statistic?: number; p_value?: number; caveat?: string }>;
	pit: { counts: number[]; edges: number[]; method: string };
	windows: { training_cutoff: string; start: string; end: string; predicted_reserve: number;
		realized_required: number; covered: boolean; pit: number; in_primary_sample: boolean }[];
	descriptive_windows: number;
}
export interface LossMetrics {
	expected_cost: number; cvar_cost: number; var_cost: number; tail_deficit: number;
	cash_shortfall_probability: number; buffer_breach_probability: number; dollar_days_below_buffer: number;
}
export type FundingAnalysis = FundingAnalysisReport | { status: 'unavailable'; reason: string };
export interface FundingAnalysisReport {
	status: string; reason?: string; evaluation_horizon_days: number; evaluation_draw_id: string;
	evaluation_weight_hash: string; paths: number;
	anchors: (LossMetrics & { id: string; label: string; feasible: boolean })[];
	frontier: { limit: number; status: string; plan: OptimalPlan | null }[];
	base?: OptimalPlan;
	holdout: (LossMetrics & { status: 'ready'; label: string; paths: number;
		within_mean_buffer_limit: boolean; within_tail_deficit_limit: boolean | null })
		| { status: 'unavailable'; message: string } | null;
	shadow_checks: { resource: string; solver_dual: number | null; stable: boolean;
		range: { low: number; high: number } | null;
		checks: { bump: number; value_per_unit: number | null; status: string }[] }[];
	loss_definition: string; risk_definition: string; budget_exhausted?: boolean;
}
export interface PortfolioRisk {
	remaining_value: number; daily_volatility: number; conditional_underperformance: number | null;
}
export interface PortfolioReport {
	status: string; message?: string; source: string; history_days: number; shrinkage: number;
	before: PortfolioRisk; cash_pressure_probability: number; target_proceeds: number;
	tax_assumptions: { long_term_rate: number; short_term_rate: number; label: string };
	assets: { symbol: string; value: number; risk_contribution: number;
		return_all_paths: number; return_under_cash_pressure: number | null }[];
	variants: { label: string; proceeds: number; realized_gain_loss: number;
		estimated_positive_gain_tax: number; after: PortfolioRisk;
		lots: { lot_id: string; symbol: string; dollars: number; shares: number; realized_gain_loss: number }[] }[];
}
