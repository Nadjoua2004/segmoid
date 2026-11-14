# AstroDoc AI — Build Prompt (based on the AstroDoc AI System Overview)

How to use this file:
- Paste **PART A** (master spec) into your coding agent (Claude Code, Cursor, Windsurf…) once, and save it in the repo as `SPEC.md`.
- Then paste the **PART B** phase prompts one at a time. Test after each phase before moving on.
- **PART C** is the demo storyline the data must support.

---

# PART A — MASTER SPEC

You are a senior full-stack engineer. Build **AstroDoc AI**, a web app for the NASA Space Apps Challenge 2026 (48-hour hackathon). It monitors astronaut health during a space mission, ranks health risks, explains them through an AI medical assistant grounded in NASA Human Research Program (HRP) knowledge, forecasts trends, and escalates to the crew when an alert is ignored.

Read the whole spec before writing code. Follow the phase order in PART B.

## 1. System architecture — 4 layers

```
[ User / Wearable Input ]
          |
          v
[ Layer 1: Astronaut Daily Health Telemetry Ingestion ]
   - Manual daily metric check-in (form)
   - Simulated vitals stream instrumented with OpenTelemetry
          |
          v
[ Layer 2: Intelligence & Decision Engine ]
   1. Autonomous Spaceflight Triage & Hazard Scoring Engine
      (rules + classification model → Nominal / Warning / Critical)
   2. NASA HRP Knowledge Base (vector DB, RAG)
   3. Predictive Health Model (forecasts 7–30 days)
          |
          v
[ Layer 3: AstroDoc AI — Interactive Clinical Chatbot ]
   - Opens automatically on Warning/Critical results
   - Recommends immediate space countermeasures (protocols / diet / shielding)
   - Interactive Q&A for astronaut follow-ups, answered from the knowledge base
          |
          v
[ Layer 4: Dashboard, Alerts & Crew Safety ]
   - Real-time vitals & trend visualizer
   - Daily micro-check-in reminders
   - "Dead-Man's Switch" → Autonomous Intra-Crew Escalation Protocol
```

## 2. Tech stack

| Component | Tool |
|---|---|
| Frontend dashboard | Next.js (App Router) + React + TypeScript + Tailwind CSS |
| Charts | Recharts |
| Telemetry | OpenTelemetry Python SDK (metrics API) for the simulated vitals stream, with a console/in-memory exporter (OTLP exporter optional); a WebSocket forwards the stream to the dashboard |
| Backend / ML API | Python 3.11 + FastAPI + Uvicorn, SQLite (SQLModel) |
| Vector DB | ChromaDB (local, persistent) with `all-MiniLM-L6-v2` embeddings |
| Classifier | scikit-learn RandomForestClassifier (XGBoost optional) |
| Forecasting | Prophet (fallback: scikit-learn LinearRegression if Prophet install fails) |
| Chatbot & RAG | Open-source LLM via the Hugging Face Inference API (`huggingface_hub`; model from env `LLM_MODEL`, default `openai/gpt-oss-120b`, fallback `Qwen/Qwen3.8-27B`; token from `HF_TOKEN`); LangChain text splitters for RAG |

Monorepo:
```
astrodoc/
  backend/
    app/
      main.py                 # FastAPI routes + WebSocket
      models.py               # SQLModel tables
      ingestion/
        checkin.py            # daily form ingestion
        telemetry_stream.py   # OpenTelemetry-instrumented simulated vitals
      triage/
        rules.py              # threshold + baseline rules
        classifier.py         # RandomForest train/predict
        hazard_scoring.py     # hazard scores + ranking
      knowledge/
        ingest.py             # load NASA docs into Chroma
        retriever.py
      forecast/
        predictor.py          # Prophet 7–30 day forecasts + readiness index
      assistant/
        chain.py              # assistant loop (Hugging Face open-source LLM)
        prompts.py
        tools.py
        redflags.py
      crew_safety/
        escalation.py         # dead-man's switch
        reminders.py
      sim/
        mission_gen.py        # synthetic mission history + training data
    config/
      metrics.json            # thresholds, units, hazard mapping, texts
      countermeasures.json    # protocols / diet / shielding cards
      redflags.json
    data/
      docs/                   # NASA HRP PDFs/pages for RAG
      events/donki_sep_sample.json
      models/                 # saved classifier
  frontend/                   # Next.js app
  SPEC.md
  README.md
```

## 3. Crew and roles

Demo crew of 4 (no login, a switcher in the top bar):
- **Sara Okafor** — Commander
- **Lin Wei** — Flight Engineer
- **Tomás Rivera** — Mission Specialist
- **Amina Diallo** — Mission Specialist / Crew Medical Officer (receives escalations)

Each astronaut has a pre-flight **baseline** (mean and standard deviation per metric), generated in the simulator.

## 4. Health metrics (`config/metrics.json`)

The daily check-in collects exactly these 8 metrics. The simulated stream also provides HR, SpO₂, HRV, body temperature and dosimeter readings.

| id | Metric (unit) | NASA hazard | Warning | Critical | Source |
|---|---|---|---|---|---|
| `bp_sys` / `bp_dia` | Blood pressure (mmHg) | Gravity (fluid shift) | sys ≥140 or ≤90 | sys ≥160 or ≤80 | demo value |
| `hr` | Heart rate (bpm) | Gravity | <45 or >100, or baseline z>2 | <40 or >120, or baseline z>3 | demo value |
| `spo2` | SpO₂ (%) | Hostile/closed environment | <94 | <90 | demo value |
| `sleep_h` | Sleep duration (h) | Isolation & confinement | <6 h, or irregular (bedtime shift >2 h for 2 nights) | <4 h | demo value |
| `glucose` | Blood glucose (mg/dL) | Distance (limited food supply) | <70 or >180 | <54 or >250 | demo value |
| `temp_c` | Body temperature (°C) | Hostile environment | ≥38.0 or <35.5 | ≥39.5 or <35.0 | demo value |
| `rad_msv` | Radiation exposure (mSv: daily and cumulative) | Radiation | daily dose >2× the astronaut's mission average, or cumulative ≥80% of mission allocation | active solar particle event alert, or acute spike | NASA-STD-3001: career limit 600 mSv; solar-particle-event short-term limit 250 mSv |
| `mood` | Mood (1–5) | Isolation & confinement | ≤2 | 1 for 2 days in a row | demo value |
| `hrv_ms` | Heart-rate variability, RMSSD (ms) — stream only | Isolation / fatigue | drop >20% vs baseline | drop >35% vs baseline | demo value |

Every metric entry in the config has: `id, name, unit, hazard, warning, critical, baseline {method:"zscore", warningZ:2, criticalZ:3}, howToMeasure[], whyItMatters, source, isDemoValue`. Values marked `isDemoValue: true` show a small "demo value" tag in the UI.

## 5. Layer 1 — Astronaut Daily Health Telemetry Ingestion

### 5.1 Daily check-in form
- Fields for the 8 metrics above, with sliders/number inputs and units; mood as 5 emoji-free labeled buttons (1 Very low … 5 Very good).
- A **"Mock-sync from sensors"** button fills HR, SpO₂, temperature and dosimeter values from the latest stream reading.
- Each value saved as a Measurement (astronaut, metric, value, timestamp, source = `form` | `sensor` | `chat`, mission_day).
- Submitting runs Layer 2 immediately.

### 5.2 Simulated vitals stream (OpenTelemetry)
- `telemetry_stream.py` runs a background loop every 3 s per astronaut, generating HR, SpO₂, HRV, body temperature and dosimeter rate = baseline + realistic noise + scenario offsets.
- Record each value with the OpenTelemetry metrics API (one instrument per metric, attributes `astronaut_id`, `mission_day`), using a console or in-memory exporter.
- Forward the same values over `WS /ws/telemetry` to the dashboard.
- Scenarios (dev panel): `radiation_spike`, `solar_particle_event`, `low_spo2`, `high_hr`, `fever`, `poor_sleep`.

## 6. Layer 2 — Intelligence & Decision Engine

### 6.1 Autonomous Spaceflight Triage & Hazard Scoring Engine
Three levels: **Nominal (Green)**, **Warning (Yellow)**, **Critical (Red)**.
- *Nominal:* everything logged, trends steady.
- *Warning:* a moderate hazard, e.g. elevated dosimeter reading + irregular sleep.
- *Critical:* e.g. acute radiation spike or signs of cardiovascular distress.

Pipeline for every new check-in or stream window:
1. **Rules** (`rules.py`): absolute thresholds from `metrics.json` + personal baseline z-scores → a rule level per metric, each with a plain reason sentence (e.g. "Heart rate 118 bpm, 31% above your baseline").
2. **Classification model** (`classifier.py`): a RandomForestClassifier predicts Nominal/Warning/Critical from a feature vector: all 8 metrics + HRV, deltas from baseline (z-scores), 3-day trends, and combination features (e.g. `dosimeter_z × sleep_irregularity`). It catches combined moderate signals that no single rule flags.
   - Training data: generated by `mission_gen.py` (thousands of labeled synthetic astronaut-days, labels from documented scenario logic). Save the model to `data/models/`.
   - Show **feature importances** for each prediction in the UI ("Main factors: dosimeter +2.4σ, sleep 5.1 h").
3. **Final level = the more severe of the rule level and the model level.** The model can raise severity, never lower a rule result (safety floor).
4. **Hazard scoring and ranking** (`hazard_scoring.py`): compute a 0–100 score per NASA hazard (Radiation, Isolation, Distance, Gravity, Hostile environment) from the metrics mapped to it, and return a **ranked list of risks** for the astronaut (highest first), each with level, score, reason and top factors.
5. Save a Triage record: astronaut, overall level, per-metric levels, ranked risks, reasons, model probabilities, timestamp.

Unit tests: rules, the safety-floor merge, and hazard ranking.

### 6.2 NASA HRP Knowledge Base (RAG)
- `ingest.py` loads `.pdf`, `.txt`, `.md` files from `data/docs/`, splits them (~800 tokens, 100 overlap) with LangChain text splitters, embeds them and stores them in Chroma with metadata `title`, `url`, `page`.
- Seed documents (the team downloads them): NASA "The Human Body in Space", NASA HRP five hazards page, NASA-STD-3001 technical briefs (radiation protection, carbon dioxide, bone loss, habitable atmosphere), NASA astronaut exercise page, spaceflight countermeasure papers, CSA and JAXA space medicine pages.
- `countermeasures.json` is also embedded, so protocol, diet and shielding actions are retrievable.

### 6.3 Predictive Health Model (7–30 day forecasts)
- `predictor.py` fits Prophet per metric per astronaut on the mission history and forecasts 7, 14 and 30 days, with uncertainty intervals.
- For each forecast, compute **"days until Warning / Critical threshold if the trend continues"** (null if never).
- **Readiness Index (0–100):** a composite of sleep, mood, HRV and recent radiation dose, documented as a simple weighted formula in the code and UI. Forecast it the same way. Show messages in this form: "Based on current sleep and radiation trends, your Readiness Index is projected to fall from 78 to 52 within 5 days if untreated."
- Label everything as "projection if current trends continue". Never present a forecast as a certainty or a diagnosis.

## 7. Layer 3 — AstroDoc AI (Interactive Clinical Chatbot)

### 7.1 Behavior
- **Opens proactively** (slide-in panel + sound) when a triage result is Warning or Critical.
- **Greets with an immediate, plain-language assessment** built from the triage reasons and the ranked risks, e.g. *"Commander, your dosimeter reading today is 2.4 times your mission average and your HRV is down 25%. This combination is flagged Warning for radiation and fatigue. Here's what to do now."*
- **Recommends immediate space countermeasures** retrieved from the knowledge base and `countermeasures.json`, grouped as **Protocols / Diet / Shielding**, each with its source.
- **Interactive Q&A:** the astronaut asks follow-ups (e.g. "Can I still do the EVA tomorrow?", "What shielding steps should I take in module B?"). Answers use RAG over the HRP knowledge base and the astronaut's own data, without fine-tuning.
- **Data from chat:** if the astronaut mentions values ("slept 5 hours, headache"), the bot logs them as measurements (source = `chat`) and shows a small "Logged: sleep 5 h" chip.
- Panel also has a **Text input + microphone** (Web Speech API) and a "Read aloud" toggle.

### 7.2 Implementation
- Open-source LLM via Hugging Face Inference Providers, using tool calling. Tools:
  - `get_triage(astronaut_id)` → current level, per-metric levels, ranked risks, reasons, top factors.
  - `get_metric_history(astronaut_id, metric, days)` → values + baseline.
  - `get_forecast(astronaut_id, metric_or_readiness, horizon_days)`.
  - `search_hrp_knowledge(query)` → chunks with titles and URLs.
  - `get_countermeasures(hazard, level)` → protocol / diet / shielding cards.
  - `log_measurement(astronaut_id, metric, value)`.
  - `trigger_crew_alert(astronaut_id, reason)` → starts the Intra-Crew Escalation Protocol immediately.
- Tools only READ triage results; no tool can change a triage level.
- Every answer that explains health or recommends an action cites at least one knowledge-base source (title + link) shown under the message.
- **Red-flag fast path** (`redflags.py`): before calling the LLM, detect phrases like "chest pain", "can't breathe", "passed out", "can't see", "severe headache", "confused". Respond instantly with Critical guidance from `countermeasures.json`, offer "Alert crew now", and start the escalation timer.
- **Offline fallback:** if the API key is missing or the API fails, the chatbot shows the triage assessment and the countermeasure cards without LLM wording, and Q&A returns the top 3 knowledge-base passages directly.

### 7.3 System prompt (`prompts.py`)
```
You are AstroDoc AI, the onboard health assistant of a space mission crew.
You speak calmly and clearly, like an experienced crewmate with medical training.

Each turn you receive: the astronaut's name and role, mission day, the latest triage result
(level, ranked risks, reasons, top factors), active alerts and today's check-in status.

Rules:
- The triage engine decides Nominal / Warning / Critical. Always report its level exactly; never change or downplay it.
- Base every number on a tool result. Base every health explanation and countermeasure on search_hrp_knowledge
  or get_countermeasures, and cite the source title.
- Describe findings, not diagnoses: say "this combination is flagged for radiation and fatigue risk",
  not "you have radiation sickness". A daily dose of tens of mSv is elevated but far below acute radiation
  sickness levels; never call it acute radiation sickness.
- Recommend countermeasures in three groups when relevant: Protocols, Diet, Shielding.
  Never give medication names with doses; say "medication only per the onboard medical checklist or flight surgeon".
- For go/no-go questions (EVA, exercise, duty), give the relevant data and countermeasures, and say the final
  decision belongs to the flight surgeon / mission control.
- If the astronaut mentions values or symptoms, log them with log_measurement.
- Keep replies to 2–5 sentences plus one clear next step.
- On Critical: give the first actions immediately, then call trigger_crew_alert if the astronaut has not acknowledged.
```

### 7.4 Countermeasure cards (`config/countermeasures.json`)
Each card: `id, hazard, level, group (protocol|diet|shielding), title, steps[], source`. Minimum set:
- **Radiation — Warning:** Protocol: limit time in low-shielding modules, log dosimeter every 2 h. Shielding: move sleep station to the most shielded area, use water/stowage walls as extra shielding. Diet: maintain antioxidant-rich food and hydration per mission nutrition plan.
- **Radiation — Critical (solar particle event):** Shielding: go to the designated storm shelter now, stay until all-clear. Protocol: crew headcount, dosimeter readings every 30 min.
- **Fatigue / sleep — Warning:** Protocol: protect the next sleep window, light schedule, reduce workload. Diet: no caffeine within 6 h of sleep.
- **Cardiovascular — Warning/Critical:** Protocol: rest, re-measure HR/BP sitting and lying, hydration; Critical: stop activity, notify crew medical officer.
- **Low SpO₂:** Protocol: rest, re-measure, check cabin air (CO₂/O₂) readings; Critical: notify crew medical officer, follow onboard oxygen protocol.
- **Glucose low/high:** Diet: fast-acting carbohydrate for low per mission nutrition plan; re-measure in 15 min; notify CMO if Critical.
- **Fever:** Protocol: re-measure, hydrate, isolate shared items, notify CMO.
- **Low mood:** Protocol: private conference with the ground psychologist (optional), crew contact, schedule a recovery activity.
Sources for each card come from the knowledge-base documents; mark any unsourced card "demo protocol".

## 8. Layer 4 — Dashboard, Alerts & Crew Safety

### 8.1 Dashboard (Next.js)
Dark "mission control" theme, high contrast, large touch targets. Status colors: Nominal `#22c55e`, Warning `#eab308`, Critical `#ef4444`, always with a label and icon.
- **Top bar:** astronaut switcher, mission day, overall triage badge, check-in status ("Due in 2 h" / "Done" / "Overdue"), offline-mode toggle, demo-speed toggle (×60).
- **Real-time vitals panel:** live Recharts line charts from the WebSocket (HR, SpO₂, HRV, temperature, dosimeter rate) with Warning/Critical bands.
- **Ranked risk list:** the Hazard Scoring Engine output, highest first, each with level, score, reason and "Ask AstroDoc" button.
- **Trend visualizer:** per-metric history over the mission with baseline line and threshold bands; mission-day slider (1–180) to replay the mission.
- **Predictive Horizon panel:** forecast charts (7/14/30-day toggle) with uncertainty band, "days until Warning" labels and the Readiness Index forecast with its message.
- **Countermeasure cards** for active risks (Protocols / Diet / Shielding).
- **AstroDoc AI chat panel** docked right (auto-opens on Warning/Critical).
- **Crew view:** all 4 astronauts' triage levels, check-in status and active alerts, sorted by severity.

### 8.2 Daily micro-check-in reminders
- Each astronaut has a daily check-in due time (default 08:00 mission time). Reminders show on the dashboard at due time and every 30 min after (banner + sound).
- Overdue check-ins count toward the dead-man's switch.

### 8.3 "Dead-Man's Switch" — Autonomous Intra-Crew Escalation Protocol
- Every Warning/Critical triage creates an Alert that the astronaut must acknowledge ("I'm OK – acknowledged").
- **Safety windows** (configurable; demo values): Critical 15 min, Warning 2 h, missed daily check-in 2 h after due time. With demo speed ×60, 15 min passes in 15 s.
- If the window expires, the system automatically triggers an **Internal Crew Emergency Alert** to another crew member (the crew medical officer first; if she is the one affected, the commander): full-screen red banner + sound on their dashboard, with the affected astronaut's latest triage and vitals, and an "I'm responding" button.
- If nobody responds within a second window (Critical: 5 min), alert all crew.
- All escalations are logged in an **Escalation Log** (who, when, why, response time).
- A background task checks windows every 5 s.

## 9. Synthetic mission data (`sim/mission_gen.py`)

Seeded and reproducible: `python -m app.sim.mission_gen --days 180 --seed 42`.
- 30 days of pre-flight data per astronaut → baseline mean/sd.
- 180 mission days with realistic daily noise (if PhysioNet heart-rate CSVs are placed in `data/physionet/`, sample daily heart-rate patterns from them).
- Spaceflight effects: small HR/BP shift in week 1, HRV decline with poor sleep, slowly rising cumulative radiation.
- **Planted scenarios:**
  - Days 40–47 (Sara): rising dosimeter readings + irregular sleep + HRV down ~25% → Warning on day 47 (combination caught by the classifier).
  - Day 120 (all crew): **solar particle event** using a real event from `data/events/donki_sep_sample.json` (saved from NASA DONKI; fallback hard-coded sample) → Critical radiation, storm shelter countermeasures.
  - Day 121 (Tomás): misses his check-in → dead-man's switch fires → Amina (CMO) is alerted.
- Also generate the **classifier training set** (≥5,000 labeled astronaut-days covering Nominal/Warning/Critical cases) and train + save the model.

## 10. API (FastAPI)

- `POST /api/checkin` (8 metrics) → triage result
- `GET /api/triage/{astronaut_id}?day=` · `GET /api/risks/{astronaut_id}?day=`
- `GET /api/metrics/{astronaut_id}/{metric}?from_day&to_day`
- `GET /api/forecast/{astronaut_id}/{metric}?horizon=7|14|30` · `GET /api/readiness/{astronaut_id}?horizon=`
- `POST /api/chat` → `{reply, citations[], logged[], countermeasures[]}`
- `GET /api/countermeasures?hazard&level`
- `GET /api/alerts?astronaut_id` · `POST /api/alerts/{id}/ack` · `GET /api/escalations`
- `POST /api/sim/scenario` · `POST /api/sim/reset` · `WS /ws/telemetry` · `WS /ws/alerts`

## 11. Acceptance criteria

1. Submitting a check-in returns a triage level, per-metric reasons and a ranked risk list in under 2 s.
2. A combination of moderately elevated dosimeter + irregular sleep (each below its own rule threshold) is flagged **Warning** by the classifier, with feature importances shown.
3. A Warning/Critical result opens AstroDoc AI automatically with a plain-language assessment and Protocol / Diet / Shielding countermeasures, each with a source.
4. Asking "Can I still do the EVA tomorrow?" returns the relevant data and countermeasures and states that the flight surgeon / mission control makes the final call.
5. Typing "I have chest pain" triggers the red-flag fast path instantly.
6. The Predictive Horizon shows 7/14/30-day forecasts, days-until-threshold and the Readiness Index message.
7. Ignoring a Critical alert with demo speed on triggers the Intra-Crew Emergency Alert on the CMO's screen within ~15 s; it appears in the Escalation Log.
8. Missing a daily check-in triggers reminders, then the dead-man's switch.
9. Scrubbing to day 120 shows the solar particle event: Critical radiation for all crew + shelter countermeasures.
10. With no API key (offline mode), triage, countermeasures, alerts and knowledge-base passages still work.

## 12. Presentation terminology (use in UI labels and README)

| Generic | NASA-aligned label |
|---|---|
| Form where user enters metrics | Astronaut Daily Health Telemetry Ingestion |
| Classifier | Autonomous Spaceflight Triage & Hazard Scoring Engine |
| Vector DB with documents | NASA Human Research Program (HRP) Knowledge Base |
| Emergency message to teammate | Autonomous Intra-Crew Escalation Protocol |

## 13. Non-functional

- `make demo` resets the database, regenerates the mission (seed 42), retrains the classifier, re-ingests the knowledge base and starts at mission day 47 with Sara selected.
- README: setup in ≤5 commands, architecture diagram (the 4 layers), data sources (NASA-STD-3001 technical briefs, NASA HRP pages, NASA DONKI, PhysioNet, CSA/JAXA pages), limitations ("decision support, not diagnosis; demo values are placeholders; individual astronaut medical data is private, so vitals and training data are synthetic").
- `.env.example` with `HF_TOKEN`, `LLM_MODEL`. No secrets in the repo.
- Unit tests for rules, the classifier pipeline (loads and predicts), the safety-floor merge, hazard ranking, forecast output shape, red-flag detection and the dead-man's switch timer.

---

# PART B — PHASE PROMPTS (paste one at a time)

### Phase 0 — Setup (hours 0–3)
> Read SPEC.md. Scaffold the monorepo from §2. Create the FastAPI app, the SQLite models, and the config files `metrics.json`, `countermeasures.json` and `redflags.json` with full content from §4 and §7.4. Create the Next.js + Tailwind frontend with a dark mission-control layout and empty panels for every dashboard section in §8.1. Add `.env.example` and a README skeleton. Done when both servers start and the layout shows.

### Phase 1 — Layer 1 + rules + crew safety (hours 3–16)
> Implement the daily check-in form with mock-sync (§5.1), the OpenTelemetry-instrumented simulated stream and `WS /ws/telemetry` (§5.2), the rules part of the triage engine with reasons (§6.1 steps 1 and 5), the real-time vitals panel, daily reminders (§8.2) and the dead-man's switch with demo speed and Escalation Log (§8.3). Done when acceptance criteria 1 (rules only), 7 and 8 pass.

### Phase 2 — Layer 2 intelligence (hours 16–28)
> Implement the synthetic mission generator and classifier training (§9), the RandomForest classifier with the safety-floor merge and feature importances, hazard scoring and the ranked risk list (§6.1), the Prophet forecasts, days-until-threshold and Readiness Index (§6.3), the trend visualizer with the mission-day slider and the Predictive Horizon panel. Done when acceptance criteria 1, 2, 6 and 9 pass.

### Phase 3 — Layer 3 AstroDoc AI (hours 28–40)
> Implement the HRP Knowledge Base ingestion and retriever (§6.2), the Hugging Face open-source LLM assistant with tools, system prompt, citations, chat logging, red-flag fast path, voice and offline fallback (§7), the auto-open on Warning/Critical, countermeasure cards and the crew view. Done when acceptance criteria 3, 4, 5 and 10 pass.

### Phase 4 — Freeze and polish (hours 40–48)
> No new features. Check all acceptance criteria in §11, implement `make demo`, apply the NASA-aligned labels from §12 across the UI, finish the README with data sources and limitations, and verify everything works with Wi-Fi off in offline mode.

---

# PART C — DEMO STORYLINE

1. **Day 47, Sara (Commander).** She submits her check-in. No single value is alarming, but the dosimeter is elevated, her sleep is irregular and HRV is down 25%. The Hazard Scoring Engine flags **Warning**, with radiation and fatigue ranked at the top.
2. **AstroDoc AI opens by itself:** "Commander, your dosimeter reading is 2.4 times your mission average and your HRV is down 25%…" It gives Protocol / Diet / Shielding countermeasures with NASA sources.
3. **Sara asks:** "Can I still do the EVA tomorrow?" The bot shows her data and countermeasures and says the final go/no-go is the flight surgeon's call.
4. **Predictive Horizon:** "Readiness Index projected to fall from 78 to 52 within 5 days if untreated."
5. **Scrub to day 120:** a real solar particle event from NASA DONKI. Critical radiation for all crew, storm shelter instructions.
6. **Day 121:** Tomás misses his check-in and ignores the alert. The dead-man's switch fires, and Amina (CMO) gets the Intra-Crew Emergency Alert.
