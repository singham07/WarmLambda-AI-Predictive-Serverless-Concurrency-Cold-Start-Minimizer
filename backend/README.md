# WarmLambda AI Backend

The backend provides the FastAPI service and discrete-event simulation engine
for WarmLambda AI. It generates reproducible synthetic request traces, runs
warm-capacity policies against those traces, and returns simulation metrics and
capacity-plan data to the dashboard.

Results and costs are simulated estimates under the configured assumptions.
They are not real AWS measurements, billing invoices, or production guarantees.

## Requirements

- Python 3.10 or newer
- Dependencies from the repository-root `requirements.txt`
- Trained model artifacts in the repository-root `models/` directory when
  using `hgb`, `hgb_q90`, or `gru` forecasters

The repository includes the trained model artifacts. The API defaults to
`hgb_q90`; choose a statistical model such as `ewma` if you do not have the
trained artifacts available.

## Install

From the repository root, create and activate a virtual environment, then
install the project dependencies:

```bash
python -m venv .venv

# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# Linux or macOS
source .venv/bin/activate

pip install -r requirements.txt
```

## Run the API

Run Uvicorn from the repository root so the backend package, models, and
experiment results are available:

```bash
uvicorn backend.api.main:app --host 127.0.0.1 --port 8000 --reload
```

Useful URLs:

- API root: `http://localhost:8000`
- Interactive OpenAPI documentation: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- Health check: `http://localhost:8000/health`

When the frontend development server runs on port 5173, the API permits that
origin by default. Set `ALLOWED_ORIGINS` to a comma-separated list to allow
additional deployed frontend origins:

```bash
ALLOWED_ORIGINS="https://dashboard.example.com" uvicorn backend.api.main:app --host 0.0.0.0 --port 8000
```

## API Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Service status and simulation disclaimer |
| `GET` | `/scenarios` | Available synthetic traffic scenarios |
| `GET` | `/policies` | Available capacity policies and parameters |
| `POST` | `/run` | Run one scenario and policy |
| `POST` | `/compare` | Compare policies using the same generated request trace |
| `POST` | `/plan/export` | Export a policy capacity plan as CSV |
| `GET` | `/results/summary` | Aggregate committed benchmark results by scenario and policy |

Interactive request and response schemas are available at `/docs`.

### Example simulation request

```bash
curl -X POST http://localhost:8000/run \
  -H "Content-Type: application/json" \
  -d '{
    "scenario": "moderate",
    "policy": "wl_full",
    "model": "hgb_q90",
    "duration_s": 600,
    "seed": 42
  }'
```

Simulation requests default to 3600 seconds. Durations shorter than 600 seconds
are rejected unless `allow_short_runs` is set to `true` for diagnostic runs.
Scenario and policy names are validated; `GET /scenarios` and `GET /policies`
return the currently supported values.

`/run` and `/compare` responses include summary metrics, downsampled interval
data, capacity-plan data, and the simulation disclaimer. `/compare` reuses one
generated trace across all requested policies to keep the comparison consistent.

## Simulation Model

- Traffic scenarios are generated as non-homogeneous Poisson processes using
  Lewis-Shedler thinning.
- Request execution durations are sampled from a log-normal distribution.
- All simulation time values are in seconds. Seeds make trace generation
  reproducible for a given scenario and configuration.
- The engine models cold starts, warm idle instances, active execution,
  concurrency limits, queue timeouts, and idle instance eviction.
- Cost values use dimensionless simulation weights; they are not cloud provider
  prices.

The scenario registry includes `moderate`, `high_load`, `extreme`, `periodic`,
`scheduled_bursts`, and `daily_cycle`.

Supported policies include `no_warming`, `fixed`, `reactive`, `oracle`, and
WarmLambda forecast, correction, and hybrid variants. The `oracle` policy uses
future trace information and is an idealized upper bound, not an implementable
production policy.

Supported forecasters are `hgb`, `hgb_q90`, `ewma`, `ewma_trend`, `seasonal`,
`persistence`, and `gru`. The HGB and GRU options load their artifacts from the
repository-root `models/` directory. Train or regenerate those artifacts from
the repository root with:

```bash
python -m experiments.train_forecasters
```

## Production and Dashboard Hosting

The API serves the dashboard from `backend/api/static/` when built assets are
present there. Build the dashboard from the repository root with:

```bash
cd frontend
npm run build:api
cd ..
uvicorn backend.api.main:app --host 0.0.0.0 --port 8000
```

Alternatively, build and run the complete application using the repository
Dockerfile:

```bash
docker build -t warmlambda .
docker run --rm -p 8000:8000 warmlambda
```

For a separately hosted frontend, set `VITE_API_URL` when building the frontend
and configure the API's `ALLOWED_ORIGINS` with the frontend origin.

## Code Layout

```text
backend/
├── api/
│   ├── main.py             # FastAPI app, routes, CORS, and static dashboard
│   ├── schemas.py          # Pydantic request and response models
│   └── services.py         # Policy orchestration and result serialization
└── warmlambda/
    └── core/
        ├── policies/       # No-warming, fixed, reactive, oracle, and WarmLambda
        ├── capacity.py     # Capacity sizing helpers
        ├── config.py       # Validated immutable simulation configuration
        ├── forecaster.py   # Statistical forecasters
        ├── forecaster_registry.py
        ├── metrics.py      # Simulation metric calculations
        ├── ml_forecaster.py
        ├── simulator.py    # Discrete-event execution engine
        └── traffic.py      # Scenario rates and reproducible trace generation
```

Run tests from the repository root with:

```bash
pytest
```
