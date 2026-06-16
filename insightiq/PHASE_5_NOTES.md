# InsightIQ v2 — Phase 5 Notes

## What was built

### Prompt Studio backend
- **Models**: `PromptTemplate`, `PromptVersion`, `PromptRun`
- **Migration**: `0006_prompt_studio`
- **Jinja2 renderer** (`core/prompts/renderer.py`) for `{{ variable }}` templates
- **LLM-as-judge** heuristic scorecard (`core/prompts/judge.py`) — faithfulness, relevancy, overall
- **`prompt` card refresher** for live dashboard cards

### API
| Endpoint | Purpose |
|---|---|
| `POST /prompt-studio/templates` | Create template + v1 |
| `GET /prompt-studio/templates` | Library (owned + shared) |
| `POST /prompt-studio/templates/{id}/versions` | New version |
| `GET /prompt-studio/templates/{id}/versions` | Version history |
| `POST /prompt-studio/templates/{id}/run` | Render + LLM + judge |
| `GET /prompt-studio/templates/{id}/runs` | Run history |
| `PATCH /prompt-studio/templates/{id}/share` | Toggle library sharing |
| `POST /prompt-studio/runs/{runId}/pin` | Pin run output to dashboard |

### Frontend
- **Prompt Studio** (`/prompt-studio`): template library, Jinja editor, JSON variables, run + eval scores, pin to dashboard
- **Response renderer** supports `explanation` type
- Home nav link added

## Run

```bash
cd insightiq/backend
uv run alembic upgrade head   # 0006_prompt_studio
```

## Assumptions
- Bindings (`bindings_json`) stored on template for future datasource/document wiring (Phase 5 UI shows variables JSON only)
- Judge uses heuristic dev scorer; real judge model deferred to Phase 6
- Pin creates dashboard card with `source_type=prompt` for live refresh

## TODO(phase6)
- Real LLM-as-judge via `ILLMProvider`
- Bindings UI: attach Postgres datasource or document collection
- Team/tenant sharing enforcement
