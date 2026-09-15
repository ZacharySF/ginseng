// Types for the POST /scenario contract and its model diagnostics.
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
	tail_deficit_limit?: number | null;
	drought_view?: { probability: number; window_days?: number; income_fraction?: number } | null;
}

export interface Severity {
	cash_shortfall_probability: number;
	avg_cash_deficit_when_short: number;
	expected_max_cash_deficit: number;
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
	probabilities?: number[];
}

// Funding plans (spec sections 38-45, 60), serialized by
// `ginseng.policy.to_contract`. Field names match the engine's JSON exactly.
export interface Plan {
    meets_policy?: boolean;
    policy_reason?: string | null;
    buffer_breach_probability?: number;
    dollar_days_below_buffer?: number;
    tail_deficit?: number;
	id: string;
	label: string;
	evaluation_horizon_days: number;
	evaluation_draw_id: string;
	cash_shortfall_probability: number;
	avg_cash_deficit_when_short: number;
	new_debt: number;
	interest_exposure: number;
	investment_sold: number;
	withdrawal_tax_reserve?: number;
	withdrawal_penalty_reserve?: number;
	withdrawal_net_cash?: number;
	withdrawal_accounts?: AccountWithdrawal[];
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
    meets_policy?: boolean;
    policy_reason?: string | null;
    buffer_coverage_target?: number | null;
    lot_selection?: string;
	credit_draw: number;
	liquidation_amount: number;
	deferral_fraction: number;
	cvar_cost: number;
	var_cost: number;
	expected_cost: number;
	cash_shortfall_probability: number;
	implied_liquidity_price: number | null;
	// Whether this plan's evaluated costs vary across the simulated futures.
	cost_is_path_dependent: boolean;
	solver_status: string;
	solver_method?: 'clarabel' | 'highs_constraint_generation';
	evaluation_horizon_days: number;
	evaluation_draw_id: string;
	evaluation_paths: number;
	cost_coverage_target: number;
	buffer_breach_probability: number;
	dollar_days_below_buffer: number;
	buffer_tolerance_dollar_days: number;
	buffer_constraint_binding: boolean;
	evaluation_weight_hash: string;
	tail_deficit: number;
	tail_deficit_limit: number | null;
	implied_credit_price: number | null;
	credit_constraint_binding: boolean;
	objective_kind: 'cvar' | 'expected';
	withdrawal_accounts?: AccountWithdrawal[];
	withdrawal_allocations?: { key: string; gross: number }[];
	withdrawal_net_cash?: number;
	withdrawal_tax_reserve?: number;
	withdrawal_penalty_reserve?: number;
}

export interface AccountWithdrawal {
	account_type: 'taxable' | 'traditional' | 'roth';
	gross: number;
	tax_reserve: number;
	penalty_reserve: number;
	net_cash: number;
}

export interface AccountLiquidity {
	accounts: (AccountWithdrawal & { balance: number; excluded_balance: number })[];
	total_net_accessible: number;
	roth_contribution_basis: number;
	unclassified_retirement_balance: number;
	assumptions_version: string;
	availability_delay_days: number;
	assumptions: { label: string; value: string; source: string; url: string | null }[];
	scope: string;
	tie_break: string;
}

export interface OptimizerStatus {
	code: 'optimal' | 'optimal_inaccurate' | 'not_needed' | 'invalid_input'
		| 'no_funding_levers' | 'resource_limit' | 'cvxpy_unavailable' | 'solver_unavailable'
		| 'solver_timeout' | 'solver_limit' | 'solver_error' | 'infeasible' | 'unbounded' | 'invalid_solution';
	message: string;
	paths: number;
	time_limit_seconds: number;
}

export interface ScenarioResponse {
	funding_evaluation_horizon_days?: number;
	funding_policy?: Record<string, unknown>;
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
	optimizer_status: OptimizerStatus;
	provenance: Record<string, string>;
	model_card: ModelCard;
	stress: StressReport;
	baseline_summary: ScenarioSummary;
	unstressed_summary: ScenarioSummary;
	immediate_cash_coverage_ratio: number | null;
	recommendation_status: string;
	excluded_obligations: string[];
	account_liquidity?: AccountLiquidity;
}

export interface ScenarioSummary {
	required_liquidity_reserve: number;
	funding_gap: number;
	severity: Severity;
	coverage_at_current_funding: number;
}

export interface StressReport {
	status: 'inactive' | 'active' | 'unsupported';
	label: string;
	message?: string;
	definition?: string;
	baseline_probability?: number;
	target_probability?: number;
	achieved_probability?: number;
	constraint_residual?: number;
	ens_overall: number;
	ens_tail: number;
	max_weight: number;
	recommendation_supported: boolean;
	support_policy: string;
}

export interface ModelCard {
	version: string;
	evidence_statement: string;
	source: string;
	history_start: string;
	history_end: string;
	history_days: number;
	simulation_paths: number;
	purpose: string;
	target: string;
	prohibited_uses: string[];
	assumptions: Record<string, unknown>;
	limitations: string[];
	recommendation_gates: string[];
	guidance: { name: string; url: string; use: string };
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
