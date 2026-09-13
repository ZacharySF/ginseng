// Types for the frozen POST /scenario contract (Ginseng spec section 20-34).
// Field names are snake_case and must match the engine's JSON exactly —
// the frontend never renames, derives, or computes a financial number.

export interface Obligation {
	id: string;
	label: string;
	amount: number;
	due_in_days: number;
}

export interface ScenarioRequest {
	seed: number;
	horizon_days: number;
	coverage_target: number;
	operating_buffer: number;
	paths: number;
	mean_block_length: number | null;
	obligations: Obligation[];
	overdraft_apr?: number;
	buffer_tolerance_dollar_days?: number | null;
	capital_gains_rate?: number;
}

export interface Severity {
	cash_shortfall_probability: number;
	avg_cash_deficit_when_short: number;
	dollar_days_below_buffer: number;
}
export interface EstimateBand {
	low: number;
	high: number;
}

export interface CoverageCurvePoint {
	funding: number;
	coverage: number;
}

export interface ReserveBufferCurvePoint {
	operating_buffer: number;
	required_liquidity_reserve: number;
}

export interface CashPaths {
	days: number[];
	p10: number[];
	p50: number[];
	p90: number[];
	known_income: number[];
	known_obligations: number[];
}

export interface ShortfallDistribution {
	bin_edges: number[];
	counts: number[];
}

// Funding plans (spec sections 38-45, 60), serialized by
// `ginseng.policy.to_contract`. Field names match the engine's JSON exactly.
export interface Plan {
	id: string;
	label: string;
	cash_shortfall_probability: number;
	avg_cash_deficit_when_short: number;
	new_debt: number;
	interest_exposure: number;
	investment_sold: number;
	realized_gain_loss: number;
	deferred_spending: number;
	feasible: boolean;
	infeasible_reason: string | null;
	dominated: boolean;
	dominated_by: string | null;
	recommended: boolean;
	explanation: string;
}

export interface Recommendation {
	plan_id: string;
	explanation: string;
}

// One row of the spec section 18 persistence-sensitivity table.
export interface SensitivityRow {
	block_label: string;
	mean_block_length: number;
	was_clipped: boolean;
	required_liquidity_reserve: number;
	is_estimated: boolean;
}

export interface WrongWayRisk {
	fraction_forced_to_sell: number;
	portfolio_return_all_paths: number;
	portfolio_return_when_forced: number | null;
	wrong_way_risk_present: boolean;
}

export interface OptimalPlan {
	credit_draw: number;
	liquidation_amount: number;
	deferral_fraction: number;
	cvar_cost: number;
	var_cost: number;
	expected_cost: number;
	cash_shortfall_probability: number;
	implied_liquidity_price: number | null;
	cost_is_path_dependent: boolean;
	solver_status: string;
}

export interface ScenarioResponse {
	as_of: string;
	seed: number;
	bootstrap_draw_id: string;
	mean_block_length: number;
	mean_block_length_was_clipped: boolean;
	immediate_funding: number;
	marketable_backup_capital: number;
	restricted_capital: number;
	coverage_target: number;
	operating_buffer: number;
	required_liquidity_reserve: number;
	funding_gap: number;
	coverage_at_current_funding: number;
	severity: Severity;
	estimate_band: EstimateBand | null;
	coverage_curve: CoverageCurvePoint[];
	reserve_buffer_curve: ReserveBufferCurvePoint[];
	cash_paths: CashPaths;
	shortfall_distribution: ShortfallDistribution;
	plans: Plan[];
	recommendation: Recommendation | null;
	sensitivity: SensitivityRow[];
	sensitivity_verdict: string | null;
	wrong_way_risk: WrongWayRisk | null;
	optimal_plan: OptimalPlan | null;
}


export interface HealthResponse {
	status: string;
	seed_default: number;
}

// Provider scaffolding — sample workspace payloads normalized by the
// engine (see ginseng/providers/nessie.py). `simulated: true` marks the
// whole payload as demo data; the UI must never present it as the
// user's real finances.
export interface SampleCustomer {
	external_id: string;
	first_name: string | null;
	last_name: string | null;
}

export interface SampleAccount {
	source: 'nessie';
	external_id: string;
	kind: 'checking' | 'savings' | 'credit';
	name: string;
	balance: number;
}

export interface SampleTransaction {
	source: 'nessie';
	external_id: string;
	account_external_id: string;
	date: string;
	amount: number;
	description: string | null;
}

export interface SampleBill {
	source: 'nessie';
	external_id: string;
	account_external_id: string;
	payee: string;
	amount: number;
	payment_date: string;
	recurring: boolean;
}

export interface NessieSampleResponse {
	label: 'sample';
	simulated: true;
	customer: SampleCustomer;
	accounts: SampleAccount[];
	transactions: SampleTransaction[];
	bills: SampleBill[];
}
