# AstroDoc AI (Layer 3): integration guide

This guide is for the backend and frontend developers. The chatbot layer is finished and tested on mock data. To connect it, the backend implements one Python interface, and the frontend calls six endpoints.

## What's in this layer

| Path | What it does |
|---|---|
| `backend/app/assistant/chain.py` | `AstroDocAssistant`: greeting, chat turn, red-flag fast path, offline fallback, LLM tool loop |
| `backend/app/assistant/tools.py` | The 7 tools from SPEC §7.2 (all read-only toward triage) |
| `backend/app/assistant/prompts.py` | System prompt (SPEC §7.3) and the per-turn `<turn_context>` block |
| `backend/app/assistant/redflags.py` + `config/redflags.json` | Emergency phrase detection, with negation handling ("no chest pain" is ignored) |
| `backend/app/assistant/countermeasures.py` + `config/countermeasures.json` | Protocol / Diet / Shielding cards, each with a source or a `demo protocol` tag |
| `backend/app/assistant/extract.py` | Pulls values out of chat text ("slept 5 hours, headache") when offline |
| `backend/app/assistant/data_provider.py` | **The interface the backend implements**, plus `MockDataProvider` and `HttpDataProvider` |
| `backend/app/assistant/router.py` | FastAPI routes |
| `backend/app/knowledge/ingest.py`, `retriever.py` | NASA HRP Knowledge Base: Chroma + all-MiniLM-L6-v2, with automatic TF-IDF fallback |
| `backend/app/assistant_app.py` | Standalone server on mock data, with a test chat page at `/` |

## Setup

```bash
cd astrodoc
python download_resources.py                  # NASA/CSA/JAXA docs, DONKI, PhysioNet
cd backend
python -m venv .venv && .venv/Scripts/pip install -r requirements-assistant.txt   # macOS/Linux: .venv/bin/pip
cp .env.example .env                          # add HF_TOKEN
.venv/Scripts/python -m app.knowledge.ingest  # builds data/kb (chunks.jsonl + Chroma)
.venv/Scripts/python -m uvicorn app.assistant_app:app --port 8001   # open http://localhost:8001
```

`python -m pytest tests` runs the chatbot tests (no network needed).

The first `ingest` run downloads the all-MiniLM-L6-v2 ONNX model (~80 MB) into `~/.cache/chroma`. Run it once with Wi-Fi on before the demo. After that, everything except the LLM call works offline.

## Backend: connect your data

Write a class with these 8 methods. They can call your triage, forecast and escalation code directly, so no HTTP is needed. Then mount the router in `main.py`:

```python
from app.assistant.router import create_assistant_router

class AstroDocData:                       # implements app.assistant.data_provider.AstroDataProvider
    def list_crew(self) -> list[Astronaut]: ...
    def get_context(self, astronaut_id) -> AstronautContext: ...   # name/role, mission day, check-in status, open alerts
    def get_triage(self, astronaut_id) -> Triage: ...              # latest triage record (§6.1 step 5)
    def get_metric_history(self, astronaut_id, metric, days) -> MetricHistory: ...
    def get_forecast(self, astronaut_id, target, horizon_days) -> Forecast: ...  # target = metric id or "readiness"
    def log_measurement(self, astronaut_id, metric, value, note=None, source="chat") -> LoggedMeasurement: ...
    def raise_alert(self, astronaut_id, level, reason, source="chat") -> AlertInfo: ...  # starts dead-man's switch
    def trigger_crew_alert(self, astronaut_id, reason) -> dict: ...  # escalate immediately (CMO, or commander if CMO affected)

app.include_router(create_assistant_router(AstroDocData()))
```

The data shapes are pydantic models in `app/assistant/contracts.py`. The most important one is `Triage`:

```python
Triage(astronaut_id="sara", mission_day=47, level="Warning",
       metric_levels=[MetricLevel(metric="rad_msv", level="Warning", value=0.62, unit="mSv",
                                  reason="Dosimeter reading 0.62 mSv today, 2.4 times your mission average.")],
       ranked_risks=[RankedRisk(hazard="Radiation", level="Warning", score=68, reason="...", top_factors=["..."])],
       reasons=["..."], top_factors=[TopFactor(feature="rad_z", label="dosimeter +2.4σ", importance=0.38)],
       model_probabilities={"Nominal": 0.18, "Warning": 0.71, "Critical": 0.11})
```

Notes:
- `reason` strings are shown to the astronaut word for word. Write them as full sentences, like the example.
- `hazard` must be one of `Radiation`, `Isolation`, `Distance`, `Gravity`, `Hostile environment`.
- Metric ids are those of SPEC §4: `bp_sys bp_dia hr spo2 sleep_h glucose temp_c rad_msv mood hrv_ms`. From chat, the bot can also log `metric="symptom"` with `value=None` and `note="headache"`. Your Measurement table needs a nullable `note` column, or you can drop symptoms.
- **Running as a separate service instead?** `HttpDataProvider(base_url)` calls the SPEC §10 endpoints, plus `GET /api/crew`, `GET /api/checkin/status/{id}`, `POST /api/measurements`, `POST /api/alerts` and `POST /api/escalations`.

## Frontend: endpoints

| Call | When |
|---|---|
| `POST /api/chat/greet` `{astronaut_id, use_llm?: false, offline?}` | When a triage comes back Warning/Critical: open the panel and play the sound. It returns instantly; it doesn't call the LLM unless `use_llm` is set. |
| `POST /api/chat` `{astronaut_id, message, history: [{role, content}], offline?}` | Each message. Send the earlier turns of the panel as `history`. |
| `POST /api/chat/voice` (multipart: `audio` file, `astronaut_id`, `history` as JSON string, `offline`) | Voice message. Whisper (open-source, on Groq) transcribes it, then it goes through the same path as `/api/chat`: red flags, knowledge base, logging. The response is a `ChatResponse` with `transcript` set; show it as the user's bubble. Errors: 422 (no speech detected), 413 (over 10 MB), 503 (speech service unavailable, so offer typing). |
| `POST /api/transcribe` (multipart `audio`) | Speech to text only, e.g. to fill the daily check-in form by voice. Returns `{text}`. |
| `POST /api/chat/alert-crew` `{astronaut_id, reason?}` | "Alert crew now" button |
| `GET /api/countermeasures?hazard=&topic=&level=` | Countermeasure cards for the dashboard |
| `GET /api/knowledge/search?q=&k=` | Optional: browse the knowledge base |
| `GET /api/assistant/status` | Is the LLM on, retriever type, number of chunks |

Both chat calls return a `ChatResponse`:

```ts
interface ChatResponse {
  reply: string;                       // contains [S1]-style markers matching citations[].id
  mode: "llm" | "offline" | "redflag" | "template";
  level: "Nominal" | "Warning" | "Critical" | null;   // always the triage engine's level
  citations: { id: string; title: string; url: string; page: number | null; snippet: string }[];
  logged: { metric: string; value: number | null; note: string | null; source: "chat"; label: string }[];  // show label as a chip
  countermeasures: Record<"protocol" | "diet" | "shielding", {
    id: string; topic: string; hazard: string; level: string; group: string; title: string;
    steps: string[]; source_title: string; source_url: string; demo_protocol: boolean }[]>;
  actions: { id: "alert_crew" | "acknowledge"; label: string }[];
  red_flag: { id: string; label: string; matched: string } | null;
  crew_alert_triggered: boolean;
  notice: string | null;               // e.g. "AI wording unavailable - offline mode."
  transcript: string | null;           // voice messages only: what Whisper heard
}
```

How to render it:
- Show `logged[].label` as small chips under the message ("Logged: sleep 5 h").
- Show a "demo protocol" tag on cards where `demo_protocol` is true.
- When `red_flag` is set, use the red styling and put the "Alert crew now" action first.
- The `acknowledge` action should call your `POST /api/alerts/{id}/ack`.
- Microphone: record with `MediaRecorder` (webm/opus in Chrome and Edge, ogg in Firefox) and POST it to `/api/chat/voice`. When `GET /api/assistant/status` returns `stt_available: false`, fall back to the browser's Web Speech API. Read-aloud uses `speechSynthesis`; remove `[S1]` markers before reading.
- `backend/app/assistant/static/chat_dev.html` is a working reference for all of the above.

## Behavior summary

1. **Red-flag fast path**: chest pain, can't breathe, passed out, can't see, severe headache or confusion triggers an instant Critical reply with no LLM call. It logs the symptom, calls `raise_alert(..., "Critical")` to start the escalation timer, and offers "Alert crew now".
2. **LLM**: an open-source model through the Hugging Face Inference API (`app/assistant/llm.py`). The default is `openai/gpt-oss-120b` (Apache-2.0), with `Qwen/Qwen3.8-27B` as fallback; change them with `LLM_MODEL` and `LLM_FALLBACK_MODELS`. Before each call the bot pre-loads the countermeasure cards, the matching knowledge-base passages and any values typed in the message, so citations and logging work even when the model skips its tools. Tools still serve history, forecasts, extra searches and crew alerts. Go/no-go questions always end with the flight surgeon / mission control line.
3. **Offline fallback**: used when there's no `HF_TOKEN`, `offline: true`, `ASTRODOC_OFFLINE=1`, or an API error. The bot returns the triage assessment, the countermeasure cards and the top 3 knowledge-base passages. After a network failure it stays offline for 60 s, so the UI doesn't hang.

## Mock storyline (standalone server)

`POST /api/mock/day {day}` switches the mock data to a given mission day:
- **47**: Sara gets a Warning (dosimeter 2.4× her average, HRV down 25%, irregular sleep). Her Readiness Index is projected to fall from 78 to 52 in 5 days.
- **120**: solar particle event (real NASA DONKI event `2024-05-09T13:59:00-SEP-001`). All crew go Critical, and the storm shelter cards appear.
- **121**: Tomás's check-in is Overdue.
