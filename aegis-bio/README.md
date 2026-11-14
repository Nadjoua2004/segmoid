# AEGIS-BIO :: Autonomous Deep-Space Clinical Decision Support System

> **NASA Space Apps Challenge** | **Team Sigmoid**  
> *Autonomous Localized Medical Triage, Multi-Hazard Forecasting, and Intra-Crew Emergency Escalation for Deep-Space Exploration (Artemis Lunar Base & Mars Transit).*

---

## 🚀 1. Executive Summary & Problem Statement

During long-duration crewed exploration missions—such as deep-space transit to Mars or permanent surface operations at the **Artemis Lunar Base Alpha**—electromagnetic signal propagation introduces communication latencies of up to **24 minutes each way** (48 minutes round-trip). In an acute physiological crisis, **real-time telemedicine with Earth-based Mission Control Center (MCC Houston) is physically impossible**.

**Aegis-Bio** is an autonomous clinical flight surgeon system designed to run entirely locally onboard spacecraft hardware. It:
1. **Ingests Continuous Telemetry & Daily Self-Reports**: Real-time biometrics (HR, BP, SpO2, HRV, Core Temp) and subjective behavioral logs.
2. **Evaluates NASA's 5 Spaceflight Hazards**: Continuous multi-hazard scoring across Radiation, Microgravity, Isolation/Circadian Disruption, Distance from Earth, and Hostile Closed Environments.
3. **Projects 7-Day Physiological Trajectories**: Machine learning regression models predicting cardiovascular deconditioning acceleration and cognitive failure risks before symptoms become irreversible.
4. **Delivers RAG-Powered Autonomous Clinical Countermeasures**: Local vector database containing NASA Human Research Program (HRP) protocols, evidence reports, and flight rules.
5. **Executes Autonomous Intra-Crew Emergency Escalation**: Eliminates communication latency bottleneck by sounding intra-habitat alarms and guiding the Crew Medical Officer (CMO) through immediate life-saving interventions.

---

## 🛰️ 2. NASA 5 Spaceflight Hazards Addressed

| Hazard | Aerospace Threat | Aegis-Bio Clinical Engine | NASA Threshold / Rule |
| :--- | :--- | :--- | :--- |
| **1. Space Radiation** | Galactic Cosmic Rays (GCR) & Solar Particle Events (SPE) causing acute radiation sickness and DNA damage. | Automated dosimeter surveillance; storm shelter ingress directives; antioxidant pharmacotherapy. | `> 20 mSv/day`: Critical SPE trigger. Mandatory water-jacketed bunker retreat. |
| **2. Microgravity Fields** | Cephalad fluid shifts, baroreceptor reset, ~15% plasma volume loss, orthostatic intolerance. | Polynomial regression forecasting; Lower Body Negative Pressure (LBNP) suit protocol; electrolyte hydration loading. | Resting `HR > 115 BPM` or `BP > 140/90 mmHg`: Critical deconditioning alert. |
| **3. Isolation & Confinement** | Circadian misalignment, sleep architecture disruption, and psychomotor vigilance degradation. | Sleep-mood matrix analysis; solid-state dynamic blue light (460nm) therapy schedules; tactical pre-EVA nap protocols. | `Sleep < 4.5h` + `Mood <= 2`: High cognitive lapse probability. Mandatory mission stand-down. |
| **4. Distance from Earth** | Complete telemedical isolation due to 24-minute latency. | Fully offline-first RAG agent with local ChromaDB vector store; autonomous intra-crew emergency escalation. | Latency `> 10 min`: Clinical authority shifts autonomously to onboard CMO. |
| **5. Hostile Closed Environment** | Cabin ppCO2 elevation, toxic scrubber failure, life support system anomalies. | Pulse oximetry monitoring paired with environmental life support (ECLSS) lithium hydroxide scrubber purge directives. | `SpO2 < 93%`: Emergency supplemental medical oxygen protocol. |

---

## 🏗️ 3. System Architecture

Aegis-Bio is engineered as an ultra-reliable 2-Tier Monolith tailored for local edge execution onboard spacecraft computing clusters:

```
aegis-bio/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── metrics.py              # Ingestion & 30-day Artemis auto-seeder
│   │   │   ├── triage.py               # Rule-based 5-hazard triage & scoring engine
│   │   │   ├── predict.py              # 7-day polynomial regression forecasting
│   │   │   ├── emergency.py            # Intra-crew emergency escalation & ACK protocol
│   │   │   └── chat.py                 # RAG Clinical Flight Surgeon agent
│   │   ├── services/
│   │   │   ├── ai_agent.py             # ChromaDB vector store + NASA HRP prompt chain
│   │   │   ├── predictor.py            # Polynomial & linear trend regression logic
│   │   │   └── seeder.py               # Realistic 30-day Artemis mission telemetry generator
│   │   ├── config.py                   # App configuration & CORS definitions
│   │   ├── database.py                 # SQLite ORM session management
│   │   ├── models.py                   # SQLAlchemy schema models
│   │   ├── schemas.py                  # Pydantic validation schemas
│   │   └── main.py                     # FastAPI application entry point
│   ├── requirements.txt
│   └── run.py
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx              # Aerospace HUD dark layout
│   │   │   └── page.tsx                # Real-time mission dashboard
│   │   ├── components/
│   │   │   ├── TelemetryCard.tsx       # Reusable sparkline biometric cards
│   │   │   ├── VitalsChart.tsx         # Recharts historical & 7-day predictive curves
│   │   │   ├── DailyCheckInModal.tsx   # Astronaut biometric logging form
│   │   │   ├── ProactiveChatDrawer.tsx # Slide-over AI Flight Surgeon RAG interface
│   │   │   └── EmergencyBanner.tsx     # Intra-crew emergency alert banner
│   │   └── lib/
│   │       ├── api.ts                  # Typed client for backend communication
│   │       └── types.ts                # TypeScript interfaces
│   ├── package.json
│   ├── tailwind.config.js
│   └── tsconfig.json
```

---

## 🔬 4. NASA Data Citations & Clinical Evidence

Aegis-Bio's clinical guidelines, triage rules, and countermeasure protocols are strictly grounded in published NASA aerospace medical standards:
* **NASA-STD-3001**: *NASA Space Flight Human-System Standard, Volume 1 (Crew Health) & Volume 2 (Human Factors, Habitability, and Environmental Health)*.
* **NASA HRP-47053**: *Space Radiation Evidence Report – Human Research Program*.
* **NASA SP-2009-3405**: *Human Adaptation to Spaceflight: The Role of Nutrition and Exercise*.
* **NASA TM-2020-5008149**: *Spaceflight Lighting Protocols for Circadian Phase Shifting and Alertness*.
* **NASA ExMC-304**: *Exploration Medical Capability Autonomous Flight Operations Concept of Operations*.
* **NASA ECLSS Flight Rule Book Rev D**: *Environmental Control and Life Support System Toxic Gas and CO2 Flight Rules*.

---

## ⚡ 5. Quick Start & Installation

### Prerequisites
* **Python**: 3.10+
* **Node.js**: 18.x or 20.x

### 1. Launch Backend (FastAPI)
```bash
cd aegis-bio/backend

# Create and activate virtual environment
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start backend server
python run.py
```
> The backend automatically initializes SQLite and seeds 30 days of realistic Artemis mission telemetry on first boot.  
> Swagger Documentation: [http://localhost:8000/docs](http://localhost:8000/docs)

### 2. Launch Frontend (Next.js)
```bash
cd aegis-bio/frontend

# Install dependencies
npm install

# Start development server
npm run dev
```
> Mission Dashboard will be live at: [http://localhost:3000](http://localhost:3000)

---

## 🧪 6. Core Endpoints Summary

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/metrics/history` | Fetches 30-day mission telemetry (auto-seeded if empty). |
| `POST` | `/api/metrics/ingest` | Logs real-time sensor packet or astronaut daily check-in. |
| `GET` | `/api/triage/current` | Evaluates latest vitals against NASA 5-hazard matrix. |
| `POST` | `/api/triage/classify` | Custom rule-based multi-hazard classification and countermeasure prescription. |
| `POST` | `/api/predict/trajectory` | 7-day forward regression calculating strain indices & inflection points. |
| `GET` | `/api/emergency/status` | Returns active intra-crew emergency state. |
| `POST` | `/api/emergency/ack` | Logs Crew Medical Officer acknowledgment and silences alarms. |
| `POST` | `/api/chat/query` | RAG query interface to the local AI Flight Surgeon agent. |
| `POST` | `/api/chat/proactive` | Proactive clinical check-in dialogue triggered by adverse trends. |

---

## 👨‍🚀 Team Sigmoid
*Developed for the NASA Space Apps Challenge.*
*Bridging the deep-space telemedical latency gap through autonomous onboard intelligence.*
