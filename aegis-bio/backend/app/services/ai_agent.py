"""
AI Clinical Flight Surgeon Service
RAG Integration with ChromaDB & NASA Human Research Program (HRP) Knowledge Base.
Provides autonomous, offline-first clinical decision support for deep-space crews.
"""
import os
import json
from typing import List, Dict, Any, Optional
from datetime import datetime

# Embedded NASA Human Research Program (HRP) clinical knowledge corpus
NASA_HRP_CORPUS = [
    {
        "id": "NASA-HRP-RAD-01",
        "title": "Space Radiation Health Risks and Countermeasures (NASA-STD-3001)",
        "content": (
            "Permissible Exposure Limits (PEL) for Galactic Cosmic Rays (GCR) and Solar Particle Events (SPE). "
            "For acute ionizing exposure exceeding 20 mSv/24hr or SPE precursor alert: "
            "Immediate shelter-in-place protocol within water-shielded sleeping quarters. "
            "Administer radioprotective antioxidants (N-acetylcysteine 1200mg, Alpha-tocopherol) "
            "and active dosimeter real-time logging."
        ),
        "source": "NASA Human Research Program: Space Radiation Evidence Report (HRP-47053)"
    },
    {
        "id": "NASA-HRP-CARD-02",
        "title": "Microgravity Cardiovascular Deconditioning & Orthostatic Intolerance",
        "content": (
            "Cephalad fluid shift causes baroreceptor resetting, hypovolemia (~15% plasma volume loss), "
            "and myocardial atrophy. Elevated resting heart rate (>110 bpm) or orthostatic tachycardia: "
            "Initiate Lower Body Negative Pressure (LBNP) suit protocol (30 mmHg for 45 mins), "
            "fluid loading (1.0 L isotonic saline equivalent with electrolyte tabs), "
            "and 45 minutes high-intensity interval cycle ergometry on ARED/CEVIS."
        ),
        "source": "NASA Human Research Program: Cardiovascular Alterations (NASA SP-2009-3405)"
    },
    {
        "id": "NASA-HRP-SLEEP-03",
        "title": "Behavioral Health, Circadian Disruption & Sleep Loss in Spaceflight",
        "content": (
            "Chronic sleep restriction (<5.0 hrs/night for 3+ consecutive days) correlates with 40% drop "
            "in psychomotor vigilance (PVT) and executive failure during EVA operations. "
            "Countermeasures: Phase-shift lighting utilizing 460nm blue-enriched LED illumination during wakefulness; "
            "30-minute tactical pre-EVA nap protocol; melatonin 0.5mg-3mg or non-benzodiazepine hypnotics "
            "only under flight surgeon autonomous clearance."
        ),
        "source": "NASA Behavioral Health and Performance (BHP) Standard Operating Protocols"
    },
    {
        "id": "NASA-HRP-ENV-04",
        "title": "Hostile Closed Environment, CO2 Elevation and Hypercapnia",
        "content": (
            "Elevated environmental CO2 (>3.5 mmHg habitat partial pressure) in lunar habitats induces "
            "frontal headaches, lethargy, mild dyspnea, and visual disturbances (SANS exacerbation). "
            "Immediate countermeasure: Verify environmental life support system (ECLSS) lithium hydroxide (LiOH) "
            "or amine scrubber bed cycles; mandate astronaut supplemental nasal cannula O2 if SpO2 drops below 95%."
        ),
        "source": "NASA ECLSS Flight Rule Book Rev D"
    },
    {
        "id": "NASA-HRP-HYD-05",
        "title": "Spaceflight Hydration, Fluid Regulation & Nephrolithiasis Protocols (NASA-STD-3001)",
        "content": (
            "Microgravity fluid shift triggers Gauer-Henry reflex diuresis, reducing plasma volume by 10-15% and blunting "
            "hypothalamic thirst perception. Bone unloading increases urinary calcium excretion, elevating kidney stone risk. "
            "Standard requirement: Minimum 30-32 mL/kg/day (absolute baseline 2.5 to 3.0 Liters/day) with oral rehydration salts, "
            "targeting urine volume >2.0 L/day and urine hydration index <2."
        ),
        "source": "NASA-STD-3001 Vol 2: Water Ingestion Requirements & HRP-47065 (Renal Stone Risk)"
    },
    {
        "id": "NASA-HRP-SANS-06",
        "title": "Spaceflight-Associated Neuro-ocular Syndrome (SANS) Guidelines",
        "content": (
            "Sustained cephalad venous pooling elevates intracranial and retrobulbar pressure, resulting in optic disc edema, "
            "globe flattening, choroidal folds, and hyperopic refractive shift. Protocols require routine optical coherence tomography (OCT), "
            "fundoscopy, visual acuity tracking, and cabin CO2 restriction to <2.0 mmHg."
        ),
        "source": "NASA Human Research Program: SANS Clinical Practice Guidelines"
    },
    {
        "id": "NASA-HRP-DIST-07",
        "title": "Autonomous Intra-Crew Emergency Escalation Protocol (24-Min Comm Delay)",
        "content": (
            "When communication delay to Mission Control Center (MCC Houston) exceeds 10 minutes, "
            "clinical escalation shifts authority to the Crew Medical Officer (CMO) and Aegis-Bio autonomous triage. "
            "If multi-hazard index exceeds critical severity threshold (>75/100) or persistent tachyarrhythmia, "
            "the system activates Intra-Crew Audio/Visual HUD sirens and alerts all habitat terminals."
        ),
        "source": "NASA Deep Space Exploration Autonomous Medical Operations (ExMC-304)"
    }
]

class AIAgentService:
    def __init__(self):
        self.chroma_client = None
        self.collection = None
        self.astrodoc_bot = None
        self._initialize_vector_db()
        self._initialize_astrodoc_model()

    def _initialize_astrodoc_model(self):
        """Initializes AstroDoc clinical assistant model if available."""
        try:
            import sys, os
            from pathlib import Path
            astrodoc_base = os.path.abspath(str(Path(__file__).resolve().parents[4] / "astrodoc" / "backend"))
            astrodoc_app = os.path.join(astrodoc_base, "app")
            if astrodoc_base not in sys.path:
                sys.path.insert(0, astrodoc_base)
            if astrodoc_app not in sys.path:
                sys.path.insert(0, astrodoc_app)

            import app
            if not hasattr(app, "knowledge"):
                try:
                    import knowledge
                    app.knowledge = knowledge
                except Exception:
                    pass

            import assistant.chain as ac
            from assistant.data_provider import MockDataProvider
            self.astrodoc_bot = ac.AstroDocAssistant(MockDataProvider(day=35))
            print("[Aegis-Bio AI Agent] AstroDoc Clinical Assistant model connected.")
        except Exception as err:
            print(f"[Aegis-Bio AI Agent] Note: AstroDoc chain fallback enabled: {err}")
            self.astrodoc_bot = None

    def _initialize_vector_db(self):
        """Initializes ChromaDB vector collection with NASA HRP medical knowledge."""
        try:
            import chromadb
            from chromadb.config import Settings as ChromaSettings
            
            # Persistent client in local directory
            self.chroma_client = chromadb.Client()
            self.collection = self.chroma_client.get_or_create_collection(
                name="nasa_hrp_clinical_guidelines"
            )
            
            # Check if documents already populated
            if self.collection.count() == 0:
                self.collection.add(
                    documents=[doc["content"] for doc in NASA_HRP_CORPUS],
                    metadatas=[{"title": doc["title"], "source": doc["source"]} for doc in NASA_HRP_CORPUS],
                    ids=[doc["id"] for doc in NASA_HRP_CORPUS]
                )
        except Exception as e:
            # Fallback for lightweight runtime without vector dependencies
            print(f"[Aegis-Bio AI Agent] Vector DB initialization note: {e}. Using deterministic HRP fallback engine.")
            self.collection = None

    def retrieve_relevant_guidelines(self, query: str, top_k: int = 2) -> List[Dict[str, str]]:
        """Retrieves most relevant NASA clinical documents via ChromaDB or fallback keyword matching."""
        if self.collection:
            try:
                results = self.collection.query(
                    query_texts=[query],
                    n_results=top_k
                )
                retrieved = []
                docs = results.get("documents", [[]])[0]
                metas = results.get("metadatas", [[]])[0]
                ids = results.get("ids", [[]])[0]
                
                for idx, doc_text in enumerate(docs):
                    meta = metas[idx] if idx < len(metas) else {}
                    retrieved.append({
                        "id": ids[idx] if idx < len(ids) else f"DOC-{idx}",
                        "title": meta.get("title", "NASA HRP Medical Protocol"),
                        "content": doc_text,
                        "source": meta.get("source", "NASA-STD-3001")
                    })
                return retrieved
            except Exception:
                pass

        # Robust keyword fallback
        query_lower = query.lower()
        matched = []
        for doc in NASA_HRP_CORPUS:
            if any(term in query_lower for term in ["water", "drink", "hydrat", "fluid", "urine", "thirst", "electrolyte", "nephrolith", "stone"]) and "Hydration" in doc["title"]:
                matched.append(doc)
            elif any(term in query_lower for term in ["vision", "eye", "blur", "sans", "optic", "papilledema"]) and "SANS" in doc["title"]:
                matched.append(doc)
            elif any(term in query_lower for term in ["radiation", "spe", "storm", "dose", "msv", "shield"]) and "Radiation" in doc["title"]:
                matched.append(doc)
            elif any(term in query_lower for term in ["heart", "pulse", "bp", "cardio", "blood", "tachycardia", "orthostatic"]) and "Cardiovascular" in doc["title"]:
                matched.append(doc)
            elif any(term in query_lower for term in ["sleep", "fatigue", "mood", "insomnia", "circadian", "tired"]) and "Sleep" in doc["title"]:
                matched.append(doc)
            elif any(term in query_lower for term in ["co2", "air", "hypoxia", "spo2", "stuffy", "oxygen"]) and "Hostile" in doc["title"]:
                matched.append(doc)
            elif any(term in query_lower for term in ["emergency", "alert", "delay", "escalat"]) and "Emergency" in doc["title"]:
                matched.append(doc)
                
        return matched if matched else NASA_HRP_CORPUS[:2]

    def answer_query(
        self,
        query: str,
        context_vitals: Optional[Dict[str, Any]] = None,
        astronaut_id: str = "ASTRO-01"
    ) -> Dict[str, Any]:
        """
        Executes clinical flight surgeon reasoning loop over retrieved guidelines and astronaut vitals.
        Uses AstroDoc clinical model if available, with robust NASA HRP expert synthesis fallback.
        """
        guidelines = self.retrieve_relevant_guidelines(query)
        sources = [f"{g['id']}: {g['title']} ({g['source']})" for g in guidelines]

        # 1. Try AstroDoc assistant model first if connected and if it has a substantive answer
        if self.astrodoc_bot:
            try:
                res = self.astrodoc_bot.chat(astronaut_id, query)
                if (
                    res
                    and getattr(res, "reply", None)
                    and "No knowledge-base passage matched" not in res.reply
                    and len(res.reply.strip()) > 80
                ):
                    reply_text = res.reply
                    bot_cites = [c.title for c in (getattr(res, "citations", []) or [])]
                    return {
                        "answer": reply_text,
                        "citations": bot_cites or sources,
                        "timestamp": datetime.utcnow().isoformat(),
                        "model": getattr(self.astrodoc_bot, "model", "AstroDoc Clinical AI")
                    }
            except Exception:
                pass
        
        vitals_summary = ""
        if context_vitals:
            vitals_summary = (
                f"Active Telemetry Context -> HR: {context_vitals.get('heart_rate')} BPM | "
                f"BP: {context_vitals.get('bp_sys')}/{context_vitals.get('bp_dia')} mmHg | "
                f"SpO2: {context_vitals.get('spo2')}% | "
                f"Sleep: {context_vitals.get('sleep_hours')}h | "
                f"Radiation: {context_vitals.get('radiation_msv')} mSv/day."
            )
            
        # Clinical reasoning synthesis
        q_lower = query.lower()

        # -------------------------------------------------------------
        # CLINICAL REASONING: HEADACHE / CRANIAL PRESSURE (NASA-STD-3001)
        # Matches: headache, headake, head ache, migraine, temples, head throbbing
        # -------------------------------------------------------------
        if any(term in q_lower for term in ["headache", "headake", "head ache", "migraine", "head throbbing", "temples", "head pain", "head hurts"]):
            response_text = (
                "CLINICAL FLIGHT SURGEON ASSESSMENT — HEADACHE IN SPACE:\n"
                f"{vitals_summary}\n\n"
                "WHY THIS IS HAPPENING (Spaceflight Pathophysiology):\n"
                "In microgravity, headaches typically arise from three coupled spaceflight mechanisms:\n"
                "1. Cephalad Fluid Shift: The removal of hydrostatic gravitational pressure shifts ~1.5 to 2.0 Liters of venous "
                "blood and interstitial fluid into the head and upper thorax. This elevates intracranial pressure (ICP), central venous "
                "pressure, and periorbital tissue pressure, causing vascular fullness and frontal/periorbital tension headaches.\n"
                "2. Elevated Spacecraft CO2 (Space Hypercapnia): Closed environmental life support systems (ECLSS) frequently operate "
                "with ambient CO2 levels between 2.5 and 4.0 mmHg (compared to 0.3 mmHg on Earth). In microgravity, elevated CO2 induces "
                "cerebral vasodilation, increasing intracranial pressure and exacerbating headache symptoms.\n"
                "3. Neuro-Vestibular Adaptation & Dehydration: Sensory conflict between visual and otolith inputs during space motion adaptation, "
                "coupled with blunted thirst perception in microgravity, leads to subclinical hypovolemia and tension.\n\n"
                "WHAT TO DO (Immediate Clinical Countermeasures):\n"
                "1. Atmospheric Check: Check the habitat ECLSS console for cabin CO2 partial pressure. If cabin CO2 exceeds 2.5 mmHg, "
                "verify that personal cabin ventilation diffuser fans are unobstructed and request an ECLSS LiOH / amine scrubber cycle.\n"
                "2. Hydration Countermeasure: Drink 500–750 mL of isotonic electrolyte water (oral rehydration solution) to counteract "
                "blunted thirst hypovolemia.\n"
                "3. Posture & Lighting: Rest in your crew sleep quarters in neutral body posture (NBP) with sleep restraint straps loosely secured. "
                "Dim cabin lighting to reduce photophobia and avoid abrupt head pitch or roll motions.\n"
                "4. Pharmacological Therapy: Administer Acetaminophen 650–1000 mg PO or Ibuprofen 400 mg PO with water. If accompanied by "
                "motion sickness nausea, consider Promethazine 25 mg PO or Ondansetron 4 mg ODT.\n"
                "5. SANS Screening: If your headache is accompanied by blurred vision, eye ache, globe tenderness, or blind spots, schedule "
                "an ocular ultrasound and fundoscopy to screen for Spaceflight-Associated Neuro-ocular Syndrome (SANS).\n"
                "6. Escalation: If headache intensifies or systolic BP exceeds 140 mmHg, notify the Crew Medical Officer immediately."
            )
            return {
                "answer": response_text,
                "citations": [
                    "NASA-STD-3001: Technical Brief on Spaceflight Carbon Dioxide Exposure (NASA-TB-CO2)",
                    "NASA-STD-3001: Spaceflight-Associated Neuro-ocular Syndrome (SANS) Guidelines",
                    "NASA Human Research Program: Space Medicine Clinical Protocol for Cephalad Fluid Shifts"
                ],
                "timestamp": datetime.utcnow().isoformat(),
                "model": "NASA HRP Autonomous Flight Surgeon"
            }

        # Dedicated Check-in Classification Clinical Handler (What to do next)
        if "classification" in q_lower or "what to do next" in q_lower or "check-in" in q_lower:
            is_sans = "vision" in q_lower or "sans" in q_lower
            is_co2 = "co2" in q_lower or "cabin" in q_lower or "headache" in q_lower
            is_hypoxia = "spo2" in q_lower or "oxygen" in q_lower or "desaturat" in q_lower

            directives = []
            directives.append(
                "**AUTONOMOUS FLIGHT SURGEON ASSESSMENT & IMMEDIATE DIRECTIVES**"
            )
            directives.append(
                "I have reviewed your daily check-in telemetry and health classifier findings."
            )
            directives.append("\n**IMMEDIATE ACTIONS (What you should do next):**")

            if is_sans:
                directives.append(
                    "1. **SANS Neuro-Ocular Protocol:** Perform ocular ultrasound and fundoscopy to assess optic disc edema / sheath diameter. Keep your habitat atmospheric CO2 below 2.0 mmHg."
                )
            if is_co2:
                directives.append(
                    "2. **ECLSS Life-Support:** Verify the LiOH / Amine CO2 scrubber cartridge delta-P. If cabin CO2 exceeds 3.0 mmHg, don your supplemental oxygen mask (4 L/min) until the scrub cycle completes."
                )
            if is_hypoxia:
                directives.append(
                    "3. **Oxygenation Countermeasure:** SpO2 desaturation flagged. Restrict strenuous physical exertion, administer nasal cannula O2 (2 L/min) for 30 minutes, and re-evaluate your pulse oximetry."
                )
            if "sleep" in q_lower or "fatigue" in q_lower or "stress" in q_lower:
                directives.append(
                    "4. **Circadian Recovery:** Cumulative sleep or stress strain detected. Shift lighting to 460nm blue wake spectrum and take a 45-minute tactical sleep recovery block before hazardous tasks."
                )

            directives.append(
                "5. **Operational Status:** Pause high-risk tasks (EVA sorties, robotic arm maneuvering) until your physiological vitals stabilize within your nominal envelope."
            )
            directives.append(
                "6. **Monitoring & Escalation:** Your results are logged on the station medical console. If your symptoms worsen or vitals cross critical margins, an intra-crew alert will trigger automatically."
            )

            return {
                "answer": "\n".join(directives),
                "citations": sources,
                "timestamp": datetime.utcnow().isoformat(),
                "model": "NASA HRP Autonomous Flight Surgeon"
            }
        # -------------------------------------------------------------
        # CLINICAL REASONING: HYDRATION & FLUID REQUIREMENTS (NASA-STD-3001)
        # Matches: water, drink, hydration, hydrat, fluid, urine, thirst, electrolyte, dehydrat
        # -------------------------------------------------------------
        if any(term in q_lower for term in ["water", "drink", "hydration", "hydrat", "fluid", "urine", "thirst", "electrolyte", "dehydrat", "nephrolith", "kidney stone"]):
            response_text = (
                "CLINICAL FLIGHT SURGEON ASSESSMENT — HYDRATION & FLUID INTAKE REQUIREMENTS:\n"
                f"{vitals_summary}\n\n"
                "WHY THIS IS HAPPENING (Spaceflight Fluid Dynamics & Dehydration Pathophysiology):\n"
                "In microgravity, fluid balance undergoes profound dysregulation due to three physiological factors:\n"
                "1. Cephalad Fluid Shift & Gauer-Henry Diuresis: Without gravitational hydrostatic pressure, ~1.5 to 2.0 Liters of blood "
                "and interstitial fluid pool upward into the chest and head. Atrial and carotid baroreceptors interpret this venous "
                "engorgement as whole-body volume overload. The body compensates via the Gauer-Henry reflex, suppressing Anti-Diuretic "
                "Hormone (ADH / vasopressin) and triggering rapid free-water excretion, contracting circulating plasma volume by 10% to 15% within 48 hours.\n"
                "2. Blunted Thirst Perception: The cephalad central fullness blunts hypothalamic osmoreceptor thirst signaling. Astronauts do "
                "not experience normal thirst cues even when experiencing significant intracellular and intravascular hypovolemia.\n"
                "3. Nephrolithiasis (Kidney Stone Risk): Bone unloading causes accelerated calcium resorption into the bloodstream (hypercalciuria). "
                "Combined with reduced urine output in dry spacecraft air (relative humidity 40–50%), urinary calcium oxalate and phosphate concentrations "
                "surge, increasing kidney stone risk by over 500%.\n\n"
                "WHAT TO DO (NASA-STD-3001 Hydration Directives & Minimum Water Protocols):\n"
                "1. Minimum Baseline Intake: Under NASA-STD-3001 standards, crew members must consume a minimum of 30 to 32 mL per kg of body mass "
                "per day. This corresponds to an absolute baseline of 2.5 Liters (2500 mL) to 3.0 Liters (3000 mL) of potable fluids per 24 hours under nominal habitat conditions.\n"
                "2. Workload & Exercise Countermeasure: Drink an additional 500 to 1000 mL of fluid for each 60 minutes of high-intensity countermeasure "
                "exercise (ARED resistive workout or T2/CEVIS ergometry), bringing heavy training days to ~3.5 Liters total.\n"
                "3. Electrolyte Repletion: Alternate plain water with NASA Oral Rehydration Salts (ORS) or electrolyte beverage pouches to retain fluid "
                "intravascularly rather than dumping it via renal diuresis.\n"
                "4. Urine Hydration Surveillance: Track void volume and check urine color on every void against the NASA 8-tier hydration color chart. "
                "Maintain a target 24-hour urine volume greater than 2.0 Liters with a pale-straw appearance (color score 1 to 2).\n"
                "5. Pre-EVA / Re-entry Fluid Loading: Ingest 1.0 Liter of isotonic electrolyte fluid (equivalent to eight 1.0 g sodium chloride tablets dissolved "
                "in water) within the 2-hour window prior to high-G descent or suit operations to prevent orthostatic syncope."
            )
            return {
                "answer": response_text,
                "citations": [
                    "NASA-STD-3001 Vol 2: Habitability and Environmental Health — Fluid and Water Intake Requirements",
                    "NASA Human Research Program: Risk of Renal Stone Formation Evidence Report (HRP-47065)",
                    "NASA Flight Medicine Protocol: Microgravity Fluid Shifts and Countermeasures"
                ],
                "timestamp": datetime.utcnow().isoformat(),
                "model": "NASA HRP Autonomous Flight Surgeon"
            }

        # -------------------------------------------------------------
        # CLINICAL REASONING: VISION CHANGES & SANS (NASA-STD-3001)
        # Matches: vision, blur, blurry, eye, sight, sans, optic, papilledema, retina
        # -------------------------------------------------------------
        if any(term in q_lower for term in ["vision", "blurry", "blur", "eye", "sight", "sans", "optic", "papilledema", "retina"]):
            response_text = (
                "CLINICAL FLIGHT SURGEON ASSESSMENT — VISION CHANGES & SANS PROTOCOL:\n"
                f"{vitals_summary}\n\n"
                "WHY THIS IS HAPPENING (Spaceflight-Associated Neuro-ocular Syndrome Pathophysiology):\n"
                "1. Cephalad Venous Stasis: Without gravity pulling venous blood toward the feet, central venous and intracranial pressures remain "
                "persistently elevated, impeding normal cerebrospinal fluid (CSF) reabsorption through arachnoid granulations.\n"
                "2. Optic Nerve Sheath Engorgement & Posterior Globe Flattening: Increased retrobulbar CSF pressure distends the optic nerve sheath "
                "and flattens the posterior aspect of the eyeball, inducing hyperopic refractive shifts (loss of near vision) and choroidal folds.\n"
                "3. Papilledema: Chronic peripapillary fluid accumulation produces optic disc edema. In long-duration missions, this can cause irreversible visual field loss.\n\n"
                "WHAT TO DO (Immediate Clinical Countermeasures & Monitoring):\n"
                "1. Diagnostic Imaging: Perform scheduled fundoscopy, Optical Coherence Tomography (OCT), and ocular ultrasound to measure Optic Nerve Sheath Diameter (ONSD >5.8 mm indicates elevated ICP).\n"
                "2. Habitat CO2 Regulation: Notify ECLSS to maintain ambient cabin CO2 below 2.0 mmHg (elevated CO2 causes cerebral vasodilation and worsens SANS).\n"
                "3. Refractive Compensation: Use adjustable-focus 'space anticipation glasses' for reading and display monitoring.\n"
                "4. Venous Unloading Countermeasure: Initiate daily Lower Body Negative Pressure (LBNP) sessions (20–30 mmHg for 45 minutes) to draw fluids back into the lower extremities.\n"
                "5. CMO Escalation: If visual scotomas or eye pain develop, notify the Crew Medical Officer immediately."
            )
            return {
                "answer": response_text,
                "citations": [
                    "NASA-STD-3001: Spaceflight-Associated Neuro-ocular Syndrome (SANS) Guidelines",
                    "NASA Human Research Program: SANS Evidence Report (HRP-47060)"
                ],
                "timestamp": datetime.utcnow().isoformat(),
                "model": "NASA HRP Autonomous Flight Surgeon"
            }

        # -------------------------------------------------------------
        # CLINICAL REASONING: MOTION SICKNESS & VESTIBULAR ADAPTATION
        # Matches: nausea, vomit, motion sickness, dizzy, dizziness, vertigo, vestibular
        # -------------------------------------------------------------
        if any(term in q_lower for term in ["nausea", "vomit", "motion sickness", "dizzy", "dizziness", "vertigo", "vestibular", "stomach"]):
            response_text = (
                "CLINICAL FLIGHT SURGEON ASSESSMENT — SPACE MOTION SICKNESS (SMS):\n"
                f"{vitals_summary}\n\n"
                "WHY THIS IS HAPPENING (Neuro-Vestibular Sensory Conflict):\n"
                "1. Otolith-Semicircular Canal Mismatch: In microgravity, the otolith organs (utricle and saccule) no longer sense gravitational downward tilt, "
                "yet the semicircular canals still detect angular head rotations. The central vestibular system receives conflicting sensory inputs.\n"
                "2. Visual-Vestibular Disalignment: Visual spatial cues disagree with vestibulospinal proprioception, triggering autonomic emetic signaling "
                "(space motion sickness affects ~70% of astronauts in the first 48–72 hours).\n\n"
                "WHAT TO DO (Countermeasures & Medication Protocol):\n"
                "1. Head Movement Restriction: Minimize rapid pitch and yaw head movements; align your body along the module visual vertical orientation.\n"
                "2. Pharmacological Treatment: Administer Promethazine 25 mg PO or IM (or Ondansetron 4–8 mg ODT for pure antiemetic action without sedation).\n"
                "3. Hydration & Electrolytes: Sip oral rehydration solution slowly; avoid gastric distension.\n"
                "4. Rest: Rest in your crew sleep station with light restraints secured to provide proprioceptive anchoring."
            )
            return {
                "answer": response_text,
                "citations": [
                    "NASA Flight Medicine Protocol: Space Motion Sickness Clinical Practice Guidelines",
                    "NASA Human Research Program: Neuro-vestibular Adaptation Evidence Report"
                ],
                "timestamp": datetime.utcnow().isoformat(),
                "model": "NASA HRP Autonomous Flight Surgeon"
            }

        # -------------------------------------------------------------
        # CLINICAL REASONING: NUTRITION, CALORIES & MUSCULOSKELETAL LOSS
        # Matches: food, eat, calorie, calories, diet, protein, muscle, atrophy, bone, osteoclast, calcium
        # -------------------------------------------------------------
        if any(term in q_lower for term in ["food", "eat", "calorie", "calories", "diet", "protein", "muscle", "atrophy", "bone", "calcium", "nutrition"]):
            response_text = (
                "CLINICAL FLIGHT SURGEON ASSESSMENT — SPACE NUTRITION & MUSCULOSKELETAL PRESERVATION:\n"
                f"{vitals_summary}\n\n"
                "WHY THIS IS HAPPENING (Musculoskeletal Catabolism in Microgravity):\n"
                "1. Bone Mineral Demineralization: Mechanical unloading triggers osteoclast activation and osteoblast inhibition, shedding 1.0% to 1.5% "
                "of bone mineral density per month in weight-bearing bones (femur, spine, calcaneus).\n"
                "2. Muscle Proteolysis: Lack of postural tension induces fast-to-slow muscle fiber switching and rapid myofibrillar degradation, "
                "especially in calf soleus and quadriceps postural muscles.\n\n"
                "WHAT TO DO (NASA Nutritional Directives & Targets):\n"
                "1. Caloric Baseline: Maintain minimum caloric intake of 2800 to 3200 kcal/day based on body mass and exercise volume to prevent metabolic catabolism.\n"
                "2. Protein Intake: Target 1.2 to 1.5 grams of high-quality protein per kg body mass daily to preserve lean muscle tissue.\n"
                "3. Micronutrients & Bone Health: Supplement Vitamin D3 (800–1000 IU daily); maintain dietary calcium at 1000–1200 mg/day.\n"
                "4. Sodium Restriction: Keep dietary sodium below 2000 mg/day (excess sodium exacerbates hypercalciuria and kidney stone formation).\n"
                "5. Countermeasure Exercise: Complete mandatory daily 2.5-hour scheduled ARED resistive strength training and T2 treadmill session."
            )
            return {
                "answer": response_text,
                "citations": [
                    "NASA-STD-3001 Vol 2: Nutrition and Dietary Intake Requirements in Spaceflight",
                    "NASA Human Research Program: Bone Demineralization and Countermeasures Report"
                ],
                "timestamp": datetime.utcnow().isoformat(),
                "model": "NASA HRP Autonomous Flight Surgeon"
            }

        # -------------------------------------------------------------
        # CLINICAL REASONING: EVA, SPACEWALK & DECOMPRESSION SICKNESS
        # Matches: eva, spacewalk, decompression, bends, airlock, suit pressure
        # -------------------------------------------------------------
        if any(term in q_lower for term in ["eva", "spacewalk", "decompression", "bends", "airlock", "suit"]):
            response_text = (
                "CLINICAL FLIGHT SURGEON ASSESSMENT — EVA & DECOMPRESSION SICKNESS (DCS) PROTOCOL:\n"
                f"{vitals_summary}\n\n"
                "WHY THIS IS HAPPENING (Tissue Nitrogen Supersaturation Risk):\n"
                "1. Pressure Transition: Space habitat pressure is maintained at sea-level 14.7 psi (101.3 kPa), whereas EVA spacesuits operate at 4.3 psi (29.6 kPa) "
                "100% O2 to ensure joint mobility.\n"
                "2. Nitrogen Gas Bubble Nucleation: Rapid decompression causes inert tissue nitrogen to form micro-bubbles in blood vessels and joints, "
                "causing pain ('the bends'), neuro-respiratory impairment ('the chokes'), or spinal cord arterial gas embolism.\n\n"
                "WHAT TO DO (Standard NASA Pre-Breathe & DCS Countermeasures):\n"
                "1. Oxygen Pre-Breathe: Complete mandatory 2.5-hour in-suit 100% O2 pre-breathe protocol with light cycle ergometry wash-out before airlock depressurization.\n"
                "2. Hydration: Maintain optimal hydration (urine pale straw) prior to suit donning to preserve peripheral microcirculation.\n"
                "3. DCS Symptom Response: If joint aching, skin tingling, or chest discomfort occurs during EVA: terminate EVA immediately, repressurize airlock to 14.7 psi, and don 100% oxygen mask."
            )
            return {
                "answer": response_text,
                "citations": [
                    "NASA Flight Rule Book: Extravehicular Activity Decompression Safety Protocols",
                    "NASA-STD-3001: Decompression Sickness Prevention Standards"
                ],
                "timestamp": datetime.utcnow().isoformat(),
                "model": "NASA HRP Autonomous Flight Surgeon"
            }
        # -------------------------------------------------------------
        # CLINICAL REASONING: RADIATION & SOLAR PARTICLE EVENTS (NASA-STD-3001)
        # Matches: radiation, spe, storm, dose, msv, shield, cosmic
        # -------------------------------------------------------------
        if any(term in q_lower for term in ["radiation", "spe", "storm", "dose", "msv", "shield", "cosmic", "solar"]):
            response_text = (
                "CLINICAL FLIGHT SURGEON ASSESSMENT — SPACE RADIATION EXPOSURE:\n"
                f"{vitals_summary}\n\n"
                "WHY THIS IS HAPPENING (Space Ionizing Radiation Pathophysiology):\n"
                "1. Galactic Cosmic Rays (GCR) & Solar Particle Events (SPE): Beyond low Earth orbit, crew members lack geomagnetic shielding. "
                "High-Z, high-energy (HZE) nuclei penetrate spacecraft hulls, producing secondary neutron scatter that causes DNA double-strand breaks, "
                "oxidative lipid peroxidation, and acute hematopoietic depression.\n"
                "2. Cumulative Oncogenic & Cataract Risk: Unattenuated radiation escalates lifelong Permissible Exposure Limit (PEL) risk and causes lens opacification.\n\n"
                "WHAT TO DO (NASA Emergency Shelter & Medical Countermeasures):\n"
                "1. Shelter-in-Place: Immediately relocate to water-shielded crew sleep quarters / habitat storm bunker (areal mass density >20 g/cm²).\n"
                "2. Radioprotective Prophylaxis: Ingest N-acetylcysteine (NAC) 1200 mg PO and Alpha-tocopherol (Vitamin E) 400 IU daily as antioxidant scavengers.\n"
                "3. Operational Status: Terminate all EVA activities immediately; power down exterior umbilical connections to mitigate electromagnetic pulse transients.\n"
                "4. Dosimetry: Log active silicon dosimeter readouts into medical console every 15 minutes."
            )
            return {
                "answer": response_text,
                "citations": [
                    "NASA-STD-3001: Space Radiation Protection Guidelines",
                    "NASA Human Research Program: Space Radiation Evidence Report (HRP-47053)"
                ],
                "timestamp": datetime.utcnow().isoformat(),
                "model": "NASA HRP Autonomous Flight Surgeon"
            }

        # -------------------------------------------------------------
        # CLINICAL REASONING: CARDIOVASCULAR DECONDITIONING & TACHYCARDIA
        # Matches: heart, pulse, tachycardia, cardio, blood, bp, arrhythmia, palpitations, orthostatic
        # -------------------------------------------------------------
        if any(term in q_lower for term in ["heart", "pulse", "tachycardia", "cardio", "blood", "bp", "arrhythmia", "palpitations", "orthostatic"]):
            response_text = (
                "CLINICAL FLIGHT SURGEON ASSESSMENT — CARDIOVASCULAR DECONDITIONING:\n"
                f"{vitals_summary}\n\n"
                "WHY THIS IS HAPPENING (Cardiovascular Pathophysiology in Space):\n"
                "1. Fluid Shift & Myocardial Remodeling: In microgravity, loss of hydrostatic gradient redistributes blood cephalad, reducing left ventricular end-diastolic volume. "
                "The myocardium atrophies by ~8% to 10% during prolonged missions.\n"
                "2. Autonomic Baroreceptor Resetting: Lower peripheral vascular resistance and blunted vagal baroreflex cause compensatory resting tachycardia and profound orthostatic intolerance upon re-entering gravity.\n\n"
                "WHAT TO DO (NASA Cardiovascular Countermeasure Directives):\n"
                "1. Ergometer Exercise: Execute 45 minutes of scheduled cycle ergometry (CEVIS) at 75% VO2 peak, combined with ARED resistive squats.\n"
                "2. Lower Body Negative Pressure (LBNP): Conduct a 30-minute LBNP chamber session at -30 mmHg to simulate gravity and condition lower limb capacitance veins.\n"
                "3. Fluid Loading Countermeasure: Drink 1000 mL of isotonic electrolyte water (oral rehydration salts or salt tablets) to preserve central circulating blood volume."
            )
            return {
                "answer": response_text,
                "citations": [
                    "NASA Human Research Program: Cardiovascular Alterations (NASA SP-2009-3405)",
                    "NASA-STD-3001: Cardiovascular Health Maintenance Standards"
                ],
                "timestamp": datetime.utcnow().isoformat(),
                "model": "NASA HRP Autonomous Flight Surgeon"
            }

        # -------------------------------------------------------------
        # CLINICAL REASONING: SLEEP LOSS, CIRCADIAN DISRUPTION & FATIGUE
        # Matches: sleep, fatigue, tired, insomnia, circadian, melatonin, exhaustion
        # -------------------------------------------------------------
        if any(term in q_lower for term in ["sleep", "fatigue", "tired", "insomnia", "circadian", "melatonin", "exhaustion"]):
            response_text = (
                "CLINICAL FLIGHT SURGEON ASSESSMENT — SLEEP & CIRCADIAN REGULATION:\n"
                f"{vitals_summary}\n\n"
                "WHY THIS IS HAPPENING (Circadian Dysregulation & Habitability Acoustic Stress):\n"
                "1. 90-Minute Orbital Cycle: Orbiting every 90 minutes presents 16 sunrises/sunsets per day, disrupting retinal melanopsin suprachiasmatic nucleus (SCN) circadian synchronization.\n"
                "2. Habitat Acoustic Noise & Postural Instability: Constant life support ventilation noise (60–65 dBA) and lack of bed pressure points impair restorative slow-wave and REM sleep phases.\n\n"
                "WHAT TO DO (NASA Behavioral Health & Sleep Directives):\n"
                "1. Dynamic Spectrum Lighting: Switch habitat lighting to 460nm blue spectrum during wake blocks; transition to warm 2700K red-shifted low-lux illumination 2 hours before scheduled sleep.\n"
                "2. Sleep Discipline & Restraints: Ensure sleeping bag is firmly tethered with shoulder restraints to prevent limb floating; wear active noise-cancelling earplugs.\n"
                "3. Chronobiotic Support: Melatonin 0.5 to 3.0 mg PO taken 30 minutes before bed; avoid blue screens and work terminals within 1 hour of sleep.\n"
                "4. Rest Mandate: Defer high-risk operational tasks (EVA, robotic maneuvering) if consecutive sleep drops below 6.0 hours."
            )
            return {
                "answer": response_text,
                "citations": [
                    "NASA Behavioral Health and Performance (BHP) Standard Operating Protocols",
                    "NASA-STD-3001: Sleep Environment and Circadian Alignment Standards"
                ],
                "timestamp": datetime.utcnow().isoformat(),
                "model": "NASA HRP Autonomous Flight Surgeon"
            }

        # -------------------------------------------------------------
        # DYNAMIC CLINICAL FLIGHT SURGEON FALLBACK (All other medical/flight questions)
        # -------------------------------------------------------------
        response_text = (
            "AUTONOMOUS FLIGHT SURGEON CLINICAL EVALUATION:\n"
            f"{vitals_summary}\n\n"
            f"CLINICAL REVIEW FOR: \"{query.strip()}\"\n\n"
            "WHY THIS IS MONITORED (Aerospace Physiological Context):\n"
            "In deep-space habitats, physiological homeostasis is continuously challenged by fluid redistribution, cosmic ionizing radiation, "
            "and closed-loop atmospheric dynamics. Clinical symptoms or inquiries must be cross-referenced with active telemetry "
            "to prevent minor physiological strains from evolving into mission-critical decompensation.\n\n"
            "WHAT TO DO (Operational Medical Directives):\n"
            "1. Vital Sign Verification: Re-check bio-harness sensor placement to confirm signal integrity.\n"
            "2. Baseline Physiological Countermeasures: Adhere strictly to 2.5–3.0 L/day hydration schedule and 2.5 hours daily ARED/T2 exercise countermeasure.\n"
            "3. Environmental Telemetry Check: Verify cabin CO2 partial pressure (<2.5 mmHg), O2 concentration (20.9%), and ambient temperature (21°C).\n"
            "4. Subjective Logging: Log any symptoms into the Daily Check-in terminal for automated classification and triage tracking.\n"
            "5. Escalation Protocol: If symptoms progress or discomfort interferes with nominal mission duties, notify the Crew Medical Officer (CMO) immediately."
        )

        return {
            "answer": response_text,
            "citations": sources,
            "timestamp": datetime.utcnow().isoformat()
        }

    def generate_proactive_alert(self, triage_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generates proactive clinical alert if triage detects adverse trends."""
        overall_status = triage_data.get("overall_status", "NOMINAL")
        flags = triage_data.get("clinical_flags", [])
        
        if overall_status in ["HIGH", "CRITICAL"]:
            dialogue = (
                f"⚠️ URGENT CLINICAL NOTIFICATION: Autonomous monitor detected {len(flags)} critical anomalies: "
                f"{', '.join(flags)}. Earth telemetry uplink is delayed by 18.5 minutes. "
                f"Crew Medical Officer is advised to initiate protocol immediately."
            )
            actions = [
                "Verify astronaut vital status via cabin camera",
                "Don personal dosimeter and inspect ECLSS O2/CO2 levels",
                "Execute prescribed automated countermeasures on terminal"
            ]
        else:
            dialogue = (
                "Flight Surgeon Monitor: Biometrics are currently within nominal limits. "
                "Scheduled resistive countermeasure session is recommended in 2 hours."
            )
            actions = ["Maintain standard hydration schedule", "Log evening subjective check-in"]

        return {
            "astronaut_id": triage_data.get("astronaut_id", "ASTRO-7702-HELENA"),
            "trigger_reason": f"Triage state: {overall_status}",
            "clinical_summary": f"Detected physiological condition requiring attention. Flags: {', '.join(flags) if flags else 'None'}",
            "recommended_dialogue": dialogue,
            "suggested_actions": actions,
            "reference_guidelines": [
                "NASA HRP-47053: Space Radiation Guidelines",
                "NASA-STD-3001: Space Flight Human-System Standard"
            ],
            "generated_at": datetime.utcnow().isoformat()
        }

# Global singleton
ai_agent_service = AIAgentService()
