# Ginseng

You can have money invested and still be short on rent next week. Ginseng is a cash-planning app for people with uneven income, built at HackRice 16.

## Using it

Start in **Data** (`/data`) with the opening date and settled checking or savings balances. The same workspace stores classified transaction history, credit terms, investments and tax lots, modeling assumptions, reserve policy, and in-app alert preferences. CSV imports are reviewed before saving and never rewrite opening cash. Data also provides an explicit JSON export of the saved workspace.

**Overview** (`/`) charts the next 14, 30, or 60 days. Choose the evidence in Data: **Scheduled** uses known income and bills without probability bands; **Assumptions** uses the monthly amounts and variability you enter; **History** resamples a declared complete transaction window. Missing inputs produce an explanation, not synthetic personal data.

**Events** (`/future`) handles bills, scheduled income, recurrence, and paid, received, or skipped occurrences. Changes are an unsaved what-if until you commit them. A paid occurrence uses its settlement date once; a payment before the opening snapshot is already reflected in that balance. Overdue one-time bills must be reconciled, not silently moved to today.

**Reserve** (`/liquidity`) shows the coverage curve, buffer tradeoffs, downside distribution, and persistence sensitivity when the chosen model supports them. **Funding** (`/plans`) compares cash, credit, taxable sales, and spending deferral while keeping restricted capital separate. A covered reserve is shown as covered, not as a missing funding calculation.

Save named scenarios and compare them from any personal forecast screen. Scenarios retain events, assumptions, and policy; they use the current saved balances, credit, and holdings rather than pretending to be historical account snapshots. History mode also offers a walk-forward backtest against held-out variable cash flows, using only earlier records to train each forecast.

The Gemini assistant can explain the active forecast and unsaved what-if, or prepare account and bill additions. You review and explicitly approve every save. Additions show a known-schedule preview, not a probabilistic reserve, and do not commit another active what-if. Unsubmitted Data form edits are never included in chat.

**Try an example** opens the separate synthetic workspace at `/demo`, with events, reserves, and funding comparisons beneath that route. It runs 2,000 possible cash paths by default. Example changes never alter personal records.

## About the numbers

History mode and the demo resample stretches of income, spending, and available market returns together. Keeping those stretches together matters: a slow week tends to contain more than one slow day. Assumptions mode instead generates prospective paths from your explicit cash-flow and optional market parameters. For each path, the engine checks the cash needed at its worst point, not just the ending balance.

A 95% coverage target means choosing enough cash to stay above the selected buffer in roughly 95% of those simulated paths. It isn't a promise about what will happen to your money.

Funding comparisons reuse the same paths so a plan doesn't look better just because it got a luckier simulation. The CVaR optimizer minimizes average cost across the worst simulated outcomes under an average buffer-erosion limit. That is not the same constraint as the reserve's coverage target or a hard shortfall-probability cap; the interface shows the optimizer's remaining shortfall risk. Taxable sales use the selected FIFO or HIFO lots, and losses do not create an immediate tax-credit cash inflow. Unusable or oversized solves return no optimized plan.

Ginseng doesn't move money or connect to a live bank account. The optional Capital One Nessie integration uses simulated data too. This is a hackathon project, not financial advice.

## Run locally with hosted Supabase

You'll need [uv](https://docs.astral.sh/uv/getting-started/installation/) and [Bun](https://bun.sh/). The frontend and Python engine run on your machine; authentication and saved workspace data use the online Supabase project. You don't need Docker or `supabase start` for this setup.

From the root of a fresh checkout:

```sh
uv sync --locked --extra dev
bun install --cwd web --frozen-lockfile
cp .env.example .env.local
cp web/.env.example web/.env
```

Only copy the example files if you don't already have environment files; don't overwrite existing keys. The examples contain local-development defaults, so replace the settings below before starting either server. Both files are ignored by Git and aren't included when you clone the repository.

In `.env.local`:

```dotenv
SUPABASE_URL=https://eqzvleafpdldevmrhjtx.supabase.co
SUPABASE_PUBLISHABLE_KEY=<hosted project publishable key>
GINSENG_ALLOWED_ORIGINS=http://127.0.0.1:5174,http://localhost:5174
```

In `web/.env`:

```dotenv
PUBLIC_SUPABASE_URL=https://eqzvleafpdldevmrhjtx.supabase.co
PUBLIC_SUPABASE_PUBLISHABLE_KEY=<same hosted project publishable key>
PUBLIC_ENGINE_URL=http://127.0.0.1:8000
```

Get the publishable key from the hosted project's Supabase dashboard, or copy it from your existing configured `web/.env`. Use the same project URL and key in both files. Never use a service-role key here or commit your environment files.

To use the assistant, also set `GEMINI_API_KEY` in `.env.local`. Leave it blank if you only want the workspace and demo. Keep that key on the server; it does not belong in `web/.env` or a `PUBLIC_` variable.

Start the engine in one terminal:

```sh
uv run --env-file .env.local uvicorn ginseng.api:app --app-dir engine --host 127.0.0.1 --port 8000
```

Start the web app in another:

```sh
bun run --cwd web dev --host 127.0.0.1 --port 5174 --strictPort
```

Open [127.0.0.1:5174](http://127.0.0.1:5174) and sign in with an account from the hosted project. Local Supabase accounts are separate and won't work here. Save an account and bill, then reload to check persistence. Restart both servers after changing environment settings.

The database needs migrations `0001` (onboarding), `0002` (cash workspace), and `0003` (complete financial inputs). The current RPCs are `get_finance_workspace` and `save_finance_workspace`; the cash-only additions writer preserves supplemental data and uses the same validation and revision check. Back up hosted data and reconcile migration history before applying missing migrations in order. Do not replay existing migrations or reset hosted data. Migration `0003` does not rewrite existing cash or profile rows.

### Optional isolated local database

For database development and tests, use a separate local stack with a running Docker-compatible container runtime:

```sh
bunx supabase start
bunx supabase migration up --local
bunx supabase status
```

With Podman, first export `DOCKER_HOST="unix://$XDG_RUNTIME_DIR/podman/podman.sock"` after enabling its API socket. Supabase applies the migrations on first startup; `migration up --local` applies later changes.

Replace both Supabase URLs above with `http://127.0.0.1:54321` and both publishable keys with the local key from `supabase status`. Keep the engine URL and allowed origins unchanged, restart both servers, and create a local account. Local data and identities are separate from the hosted project.

## Working on the code

- `web/` contains the SvelteKit frontend. Personal and synthetic views share chart, reserve, and funding components. The personal controller owns revisioned forecasts and scenarios; Data owns the input draft, while Events is the sole editor for scheduled cash events.
- `engine/ginseng/` contains the FastAPI app, schedule calculations, simulation, and funding models. NumPy handles the paths; CVXPY solves the optimization problem.
- `supabase/` contains local configuration, database migrations, and ownership checks enforced through row-level security.

`GET /finance` reads the authenticated workspace; `PUT /finance` saves the complete snapshot with an expected revision. `POST /finance/forecast` evaluates saved inputs and optional scenario overrides without writing. `POST /finance/backtest` runs read-only historical evaluation. The assistant's `PUT /workspace` additions path preserves supplemental inputs through the same database validation. Stale revisions and uncertain save acknowledgments require an explicit reload and reconciliation before another write. Restart the Python engine after updating its code.

Run the engine tests and frontend checks from the repository root:

```sh
uv run pytest -q
bun run --cwd web check
bun run --cwd web build
```

Database tests run against the local stack:

```sh
bunx supabase test db
```

## A note about chat

Sending a message shares your question, recent conversation, and relevant financial context, including the active forecast and unsaved scenario—with Google Gemini. Unsubmitted Data form edits are excluded. Review proposed changes before saving them, and don't send information you're uncomfortable sharing with the model provider.
