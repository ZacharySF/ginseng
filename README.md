# Ginseng

You can have money invested and still be short on rent next week. Ginseng is a cash-planning app for people with uneven income, built at HackRice 16.

## Using it

Enter your checking and savings balances, choose the date those balances reflect, and add upcoming bills. The personal workspace lays out the next 14, 30, or 60 days so you can see when cash would run short. It only knows about the amounts and dates you save; it doesn't predict your next paycheck.

If you'd rather type a sentence than fill out each row, the Gemini assistant can prepare several accounts and bills in one go. You review the additions and their effect on your cash before approving the save. The cash preview comes from the Python engine. Closing the chat or discarding a proposal doesn't approve it.

There's also a separate demo with synthetic financial history. It runs 2,000 possible cash paths by default. Add a bill, move its due date, or change how much cash you want to keep available, then compare ways to cover the gap. Your saved personal balances don't feed this simulation.

## About the numbers

The demo resamples stretches of income, spending, and market returns together. Keeping those stretches together matters: a slow week tends to contain more than one slow day. For each simulated path, the engine checks the cash needed at its worst point, not just the balance at the end of the month.

A 95% coverage target means choosing enough cash to stay above the selected buffer in roughly 95% of those simulated paths. It isn't a promise about what will happen to your money.

Funding comparisons reuse the same paths so a plan doesn't look better just because it got a luckier simulation. The CVaR optimizer chooses a funding mix by minimizing average cost across the worst simulated outcomes. If it can't return a usable solution, the API leaves that result empty.

Ginseng doesn't move money or connect to a live bank account. The optional Capital One Nessie integration uses simulated data too. This is a hackathon project, not financial advice.

## Run it locally

You'll need [uv](https://docs.astral.sh/uv/getting-started/installation/), [Bun](https://bun.sh/), and a running Docker-compatible container runtime for local Supabase.

From the root of a fresh checkout:

```sh
uv sync --locked --extra dev
bun install --cwd web --frozen-lockfile
bunx supabase start
bunx supabase status
cp .env.example .env.local
cp web/.env.example web/.env
```

Use the local API URL and publishable key from `supabase status` in both files. The engine and browser must point to the same Supabase project.

In `.env.local`:

```dotenv
SUPABASE_URL=http://127.0.0.1:54321
SUPABASE_PUBLISHABLE_KEY=<local publishable key>
```

In `web/.env`:

```dotenv
PUBLIC_SUPABASE_URL=http://127.0.0.1:54321
PUBLIC_SUPABASE_PUBLISHABLE_KEY=<same local publishable key>
PUBLIC_ENGINE_URL=http://127.0.0.1:8000
```

To use the assistant, also set `GEMINI_API_KEY` in `.env.local`. Leave it blank if you only want the workspace and demo. Keep that key on the server; it does not belong in `web/.env` or a `PUBLIC_` variable.

Start the engine in one terminal:

```sh
uv run --env-file .env.local uvicorn ginseng.api:app --app-dir engine --host 127.0.0.1 --port 8000
```

Start the web app in another:

```sh
bun run --cwd web dev --host 127.0.0.1 --port 5173 --strictPort
```

Open [localhost:5173](http://127.0.0.1:5173), create a local account, and sign in. Supabase applies the migrations in `supabase/migrations/` when the local stack starts. For later migration changes, run `bunx supabase migration up --local`.

Use a separate local or staging Supabase project for development. Don't reset a hosted database to try the demo.

## Working on the code

- `web/` contains the SvelteKit frontend, including the personal ledger and assistant UI.
- `engine/ginseng/` contains the FastAPI app, schedule calculations, simulation, and funding models. NumPy handles the paths; CVXPY solves the optimization problem.
- `supabase/` contains local configuration, database migrations, and ownership checks enforced through row-level security.

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

Sending a message shares your question, recent conversation, and relevant saved financial context with Google Gemini. Unsaved form edits aren't part of that context. Review proposed changes before saving them, and don't send information you're uncomfortable sharing with the model provider.
