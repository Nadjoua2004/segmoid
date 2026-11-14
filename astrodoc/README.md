# AstroDoc AI

NASA Space Apps Challenge 2026. AstroDoc AI monitors astronaut health during a mission, ranks health risks against the five NASA HRP hazards, and explains them through an AI medical assistant grounded in NASA Human Research Program knowledge. The full specification is in [SPEC.md](SPEC.md).

| Layer | Owner | Status |
|---|---|---|
| 1. Astronaut Daily Health Telemetry Ingestion | backend team | to do |
| 2. Triage & Hazard Scoring Engine, forecasts | backend team | to do |
| **3. AstroDoc AI: Interactive Clinical Chatbot + NASA HRP Knowledge Base** | **AI** | **done, tested on mock data** |
| 4. Dashboard, alerts, crew safety | frontend team | to do |

Integration guide for the chatbot (provider interface, endpoints, response format): [docs/ASSISTANT_INTEGRATION.md](docs/ASSISTANT_INTEGRATION.md).

## Quick start (chatbot only)

```bash
python download_resources.py                                  # NASA / CSA / JAXA docs, DONKI, PhysioNet
cd backend
python -m venv .venv && .venv/Scripts/pip install -r requirements-assistant.txt
cp .env.example .env                                          # add HF_TOKEN (free Hugging Face token)
.venv/Scripts/python -m app.knowledge.ingest                  # build the knowledge base
.venv/Scripts/python -m uvicorn app.assistant_app:app --port 8001   # open http://localhost:8001
```

Other commands:
- `python -m pytest tests` runs the tests. They need no network.
- `python -m app.assistant.cli --astronaut sara --day 47` chats in the terminal.
- `python scripts/smoke_llm.py` runs the live check against the Hugging Face model (needs `HF_TOKEN`).

## Data sources

- NASA: *The Human Body in Space*; HRP *5 Hazards of Human Spaceflight*; *Astronaut Exercise*.
- NASA-STD-3001 technical briefs: Radiation Protection, Carbon Dioxide, Bone Loss.
- Peer-reviewed papers: Effects of exercise countermeasures in long-duration spaceflight (npj Microgravity 2023); SANS mechanical countermeasures (2025); *Red risks for a journey to the red planet* (2020).
- CSA: effects of space on the body (radiation, bones, muscles, decompression). JAXA: health management for astronauts.
- NASA DONKI: solar particle events of May 2024. The day 120 scenario uses `2024-05-09T13:59:00-SEP-001`.
- PhysioNet: Apple Watch sleep heart-rate data (ODC-BY), for the simulator.

The nature.com PDF of the 2023 exercise paper is blocked for scripts. `backend/data/docs/08_*.txt` holds the same open-access article, taken from Europe PMC (PMC9898566).

## Limitations

- This is decision support, not diagnosis. Every forecast is a projection if current trends continue.
- Countermeasure cards tagged `demo protocol` are team-written placeholders that the cited source supports only in general terms.
- Individual astronaut medical data is private, so all vitals and training data are synthetic.
- Without a Hugging Face token, or with Wi-Fi off, the chatbot answers with the triage assessment, the countermeasure cards and the top knowledge-base passages instead of AI wording.
