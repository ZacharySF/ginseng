import { requestEngine, type EngineResult } from './api';
import type { ScenarioResponse } from './types';
import type { CalibrationReport } from './analysis-types';
import type { CashAccount, CashBill, CashWorkspace } from './workspace';

export type { CashAccount, CashBill, CashWorkspace } from './workspace';

export type FinanceMode = 'scheduled' | 'assumptions' | 'history';
export type EventRecurrence = 'none' | 'weekly' | 'biweekly' | 'monthly' | 'yearly';
export type EventSettlementStatus = 'settled' | 'skipped';
export type TransactionCategory =
	| 'income_fixed'
	| 'income_variable'
	| 'expense_fixed'
	| 'expense_essential_variable'
	| 'expense_discretionary_variable'
	| 'expense_irregular'
	| 'transfer'
	| 'credit_purchase'
	| 'credit_payment'
	| 'investment_buy'
	| 'investment_sell';
export type HoldingAccount = 'taxable' | 'traditional' | 'roth' | 'retirement';
export type PlanningPriority =
	| 'avoid_interest_bearing_debt'
	| 'minimize_taxable_sales'
	| 'minimize_deferred_spending';
export type LotSelection = 'fifo' | 'hifo';
export type ForecastHorizonDays = 14 | 30 | 60;

export interface EventSettlement {
	due_date: string;
	status: EventSettlementStatus;
	settled_on: string | null;
}

export interface EventRule {
	event_id: string;
	recurrence: EventRecurrence;
	end_date: string | null;
	settlements: EventSettlement[];
}

export interface HistoricalTransaction {
	id: string;
	date: string;
	description: string;
	amount_cents: number;
	category: TransactionCategory;
	source_key: string | null;
}

export interface ModelAssumptions {
    income_payments_per_month: number;
	monthly_variable_income_cents: number;
	monthly_essential_spending_cents: number;
	monthly_discretionary_spending_cents: number;
	income_variability_pct: number;
	spending_variability_pct: number;
	persistence_days: number;
	income_spending_correlation: number;
	market_assumptions_enabled: boolean;
	expected_annual_return_pct: number;
	annual_return_volatility_pct: number;
	income_market_correlation: number;
}

export interface PersonalCreditAccount {
    cash_advance_limit_cents: number;
    cash_advance_apr: number;
    cash_advance_fee_pct: number;
	id: string;
	name: string;
	credit_limit_cents: number;
	current_balance_cents: number;
	purchase_apr: number;
	statement_close_day: number;
	payment_due_day: number;
	grace_period_eligible: boolean;
	minimum_payment_cents: number;
}

export interface PersonalTaxLot {
	id: string;
	quantity: number;
	cost_basis_per_share_cents: number;
	purchase_date: string;
}

export interface PersonalHolding {
	id: string;
	symbol: string;
	account: HoldingAccount;
	current_price_cents: number;
	tax_lots: PersonalTaxLot[];
}

export interface PortfolioReturn {
	date: string;
	return_decimal: number;
}

export interface PlanningPolicy {
	operating_buffer_cents: number;
	coverage_target: number;
	max_credit_utilization: number;
	priorities: PlanningPriority[];
	settlement_days: number;
	external_transfer_days: number;
	capital_gains_rate: number;
	overdraft_apr: number;
	buffer_tolerance_dollar_days: number | null;
	lot_selection: LotSelection;
}

// Every supplied override replaces that entire saved field; omitted fields keep
// the current saved input. Cash accounts, history, and holdings are intentionally
// not scenario-overridable in this release.
export interface ScenarioOverrides {
	bills?: CashBill[];
	income_events?: CashBill[];
	event_rules?: EventRule[];
	assumptions?: ModelAssumptions;
	policy?: PlanningPolicy;
	mode?: FinanceMode;
}

export interface NamedScenario {
	id: string;
	name: string;
	base_revision: number;
	overrides: ScenarioOverrides;
}

export interface AlertPreferences {
	enabled: boolean;
	shortfall_probability: number;
	stale_after_days: number;
}

export interface FinanceInputs {
    roth_contribution_basis_cents: number;
	mode: FinanceMode;
	income_events: CashBill[];
	event_rules: EventRule[];
	transactions: HistoricalTransaction[];
	history_start: string | null;
	history_end: string | null;
	history_complete: boolean;
	assumptions: ModelAssumptions;
	credit_accounts: PersonalCreditAccount[];
	holdings: PersonalHolding[];
	portfolio_returns: PortfolioReturn[];
	policy: PlanningPolicy;
	scenarios: NamedScenario[];
	alerts: AlertPreferences;
}

export interface FinanceWorkspace extends CashWorkspace {
	inputs: FinanceInputs;
}

// PUT /finance is a complete replacement guarded by the cash-workspace CAS
// revision. `as_of` remains the opening-of-day date represented by all balances.
export interface FinanceDraft {
	expected_revision: number;
	as_of: string;
	accounts: CashAccount[];
	bills: CashBill[];
	inputs: FinanceInputs;
}

export interface ForecastRequest {
	expected_revision: number;
	horizon_days: ForecastHorizonDays;
	overrides?: ScenarioOverrides;
	seed?: number;
	paths?: number;
}

export interface DataRequirement {
	code: string;
	label: string;
	section: 'cash' | 'income' | 'history' | 'assumptions' | 'credit' | 'investments' | 'policy';
}

export interface ForecastAlert {
	id: string;
	severity: 'info' | 'warning' | 'critical';
	title: string;
	detail: string;
}

export interface ForecastRun {
	status: 'ready' | 'needs-input';
	model_mode: FinanceMode;
	input_revision: number;
	horizon_days: ForecastHorizonDays;
	as_of: string | null;
	result: ScenarioResponse | null;
	requirements: DataRequirement[];
	warnings: string[];
	alerts: ForecastAlert[];
	accuracy: BacktestSummary | null;
}

export interface ScenarioChange {
	label: string;
	before: string;
	after: string;
}

export interface ForecastResponse {
	baseline: ForecastRun;
	preview: ForecastRun | null;
	changes: ScenarioChange[];
}

export interface BacktestWindow {
	start_date: string;
	end_date: string;
	realized_required_cents: number;
	predicted_reserve_cents: number;
	covered: boolean;
}

export interface BacktestSummary {
    information_timing?: 'retrospective_current_records';
	periods: number;
	observed_coverage: number;
	calibration: CalibrationReport;
	mean_absolute_error_cents: number;
	windows: BacktestWindow[];
	warning: string | null;
}

export interface BacktestRequest {
	expected_revision: number;
	horizon_days: ForecastHorizonDays;
	policy?: PlanningPolicy;
}

export function defaultFinanceInputs(): FinanceInputs {
	return {
		mode: 'scheduled',
        roth_contribution_basis_cents: 0,
		income_events: [],
		event_rules: [],
		transactions: [],
		history_start: null,
		history_end: null,
		history_complete: false,
		assumptions: {
            income_payments_per_month: 2,
			monthly_variable_income_cents: 0,
			monthly_essential_spending_cents: 0,
			monthly_discretionary_spending_cents: 0,
			income_variability_pct: 0,
			spending_variability_pct: 0,
			persistence_days: 7,
			income_spending_correlation: 0,
			market_assumptions_enabled: false,
			expected_annual_return_pct: 0,
			annual_return_volatility_pct: 0,
			income_market_correlation: 0
		},
		credit_accounts: [],
		holdings: [],
		portfolio_returns: [],
		policy: {
			operating_buffer_cents: 0,
			coverage_target: 0.95,
			max_credit_utilization: 0.3,
			priorities: [
				'avoid_interest_bearing_debt',
				'minimize_taxable_sales',
				'minimize_deferred_spending'
			],
			settlement_days: 1,
			external_transfer_days: 2,
			capital_gains_rate: 0.15,
			overdraft_apr: 0.18,
			buffer_tolerance_dollar_days: null,
			lot_selection: 'fifo'
		},
		scenarios: [],
		alerts: {
			enabled: true,
			shortfall_probability: 0.05,
			stale_after_days: 30
		}
	};
}

export function getFinanceWorkspace(): Promise<EngineResult<FinanceWorkspace>> {
	return requestEngine<FinanceWorkspace>('/finance', { method: 'GET' }, { requiresAuth: true });
}

export function saveFinanceWorkspace(draft: FinanceDraft): Promise<EngineResult<FinanceWorkspace>> {
	return requestEngine<FinanceWorkspace>(
		'/finance',
		{
			method: 'PUT',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify(draft)
		},
		{ requiresAuth: true }
	);
}

export function forecastFinance(request: ForecastRequest): Promise<EngineResult<ForecastResponse>> {
	return requestEngine<ForecastResponse>(
		'/finance/forecast',
		{
			method: 'POST',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify(request)
		},
		{ requiresAuth: true, timeoutMs: 45000 }
	);
}

export function runBacktest(request: BacktestRequest): Promise<EngineResult<BacktestSummary>> {
	return requestEngine<BacktestSummary>(
		'/finance/backtest',
		{
			method: 'POST',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify(request)
		},
		{ requiresAuth: true, timeoutMs: 60000 }
	);
}

// Export intentionally reads the same authenticated canonical snapshot. The UI
// chooses whether and when to turn that data into a downloaded file.
export function exportFinanceWorkspace(): Promise<EngineResult<FinanceWorkspace>> {
	return getFinanceWorkspace();
}
