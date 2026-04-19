# George-Hacks-GWU
Developed Solution for George Hacks organized at George Washington University, Washington DC

A real-time community early warning system for food insecurity. It monitors crop health via satellite imagery, tracks supply chain disruptions (disasters, road closures, freight issues), and combines both into a risk score that tells communities in southern their food supply is at risk — weeks before shortages hit shelves.

What Is This?
FoodReady is an anticipatory food insecurity platform for the United States. Rather than reacting to food crises after they happen, it predicts where food access is about to break down — at the county level, across all 50 states — so that responders, coordinators, and government agencies can act before people go hungry.
The core idea: combine real-time weather data, drought monitoring, FEMA disaster declarations, satellite fire detection, and AI-generated risk weights into a single Food Pressure Index (FPI) score for every county in America, updated continuously.

Technology Stack
Frontend
React 18 + TypeScript, built with Vite
Routing: React Router v6 (/, /dashboard, /state/:stateAbbr, /community, /responder, etc.)
State management: Zustand (persistent store for requests, alerts, organizations, incidents)
Server state / API caching: TanStack React Query (5-minute stale time, automatic background refresh)
Maps: React-Leaflet with CartoDB light tile layer — interactive circle markers for all 50 states and county-level drill-down
Charts: Recharts (bar charts, trend lines)
UI: shadcn/ui components + Tailwind CSS
Forms: React Hook Form + Zod validation
Backend
Python 3.11, FastAPI, served via Uvicorn
Deployed on Render (free tier, Ohio region)
Database: MongoDB (via db.py) for persistent community requests, user registrations, and signal reports
AI: Google Gemini API for dynamic risk weight generation
Weather: NASA, NOAA, and USDA APIs

Data Sources & APIs
1. NOAA National Weather Service (NWS)
Fetches active weather alerts for every state: flood watches, tornado warnings, extreme heat advisories, etc.
Each alert has a severity rank (1–5). Alerts feed directly into the shock score.
Endpoint pattern: api.weather.gov/alerts/active?area={state}
2. NOAA/USDA Drought Monitor
Weekly drought classification data for every county in the US
Classifications: D0 (Abnormally Dry) through D4 (Exceptional Drought)
The system tracks what percentage of a state's area falls into each drought class
D2+ coverage (Extreme Drought) is the key threshold used in risk scoring
3. NASA FIRMS (Fire Information for Resource Management System)
Satellite thermal anomaly detection — identifies active wildfires and burn areas
Used to detect agricultural disruption from fires near farmland
Anomaly count feeds into the shock exposure component of FPI
4. NASA Earthdata / NDVI
Normalized Difference Vegetation Index — a satellite measure of crop health
Compares current greenness against historical baselines
A large negative deviation signals crop stress or failure before it's visible on the ground
Requires EARTHDATA_TOKEN credential
5. FEMA Disaster Declarations
Count of active federal disaster declarations per state
Each declaration adds weight to the vulnerability and readiness components
6. Google Gemini AI
The most novel data source in the system
Given a state's raw metrics (drought %, active storms, FEMA declarations, NDVI deviation, poverty rate, food insecurity rate, SVI score), Gemini generates dynamic risk weights — how much each factor should count toward the final FPI score for this specific state right now
Also generates: a plain-English reasoning paragraph, recommended actions for coordinators, and a dominant driver label
Falls back to deterministic baseline weights if the API is unavailable or rate-limited
Model used: gemini-pro via the gemini_scorer.py module

The Food Pressure Index (FPI) — How It's Calculated
The FPI is a 0–100 score. Higher = more at risk. Every county and state gets one.
Four components:
Component
What It Measures
Shock Exposure (0–100)
Immediate external stressors: active weather alerts, drought severity, wildfire proximity, NDVI crop deviation
Vulnerability (0–100)
Population susceptibility: poverty rate, food insecurity rate, % households with no vehicle, CDC Social Vulnerability Index (SVI)
Supply Capacity (0–100)
Food system resilience: food bank density, pantry coverage, grocery store access, supply corridor health
Response Readiness (0–100)
Institutional capacity: FEMA declarations, responder org coverage, open incident count

Baseline formula (deterministic):
FPI = (ShockExposure × w1) + (Vulnerability × w2) + (SupplyCapacity × w3) + (ResponseReadiness × w4)
Default weights: w1=0.35, w2=0.30, w3=0.20, w4=0.15
With Gemini (live mode): Gemini replaces the fixed weights with contextually appropriate ones. For example, during an active hurricane, it might push w1 (shock) to 0.55 and lower w3 (supply) because supply disruption is already captured in the shock signal. The weights always sum to 1.0.

Geographic Coverage
Iowa — the fully seeded pilot state with 25 real counties, each having:
Real FIPS codes, population figures, centroids
Hand-tuned component scores reflecting actual risk profiles
Named signal drivers (e.g. "Persistent rural poverty", "NWS flood watch active")
Rich county-level detail panel with trend data
Seeded sample states with real county data: Texas (3 counties), California (3), Florida (2), Louisiana (2), Mississippi, Kentucky, West Virginia, Oklahoma, North Dakota, Arizona, New York, Michigan — covering the highest-risk regions in each
All remaining states — synthetic baseline counties generated deterministically from a seeded random function (rngFor) using the state's centroid coordinates. Between 5–8 counties per state using real county names from a hardcoded lookup table (REAL_COUNTY_NAMES). These get full FPI scores via the baseline engine.
Total monitored: All 50 states, ~400+ counties depending on synthetic generation

The Gemini Prompt (What We Actually Ask the AI)
The gemini_scorer.py module constructs a structured prompt that includes:
State name and current date
Raw metric values: drought percentages by class, active NWS alert count and max severity, FIRMS fire anomaly count, NDVI deviation, poverty rate, food insecurity rate, SVI score, FEMA declaration count
Instructions to return a JSON object with: weights (four floats summing to 1.0), risk_score (0–100), trigger (one of five levels), dominant_driver, reasoning (2–3 sentences), recommended_actions (list of strings)
This means the AI isn't just decorating a fixed number — it's making the weighting decision itself based on current conditions, then explaining its reasoning in plain English that shows up directly in the UI.

Supply Corridor Monitoring
The system tracks 12 named food supply corridors — physical routes that move agricultural produce from source regions to dependent communities. Each corridor has:
Source region and crop types (e.g. Terrebonne Basin → crawfish, rice, sugarcane, soybeans)
Named waypoints with state and county
Destination communities with a dependency_weight (0–1) indicating how reliant that community is on this specific corridor
Primary and backup routes (highway designations)
Corridor status is computed from the weather shock score:
0–34: Operational
35–54: At Risk
55–74: Degraded
75–100: Blocked
Communities with dependency_weight ≥ 0.7 are flagged as high-risk when a corridor degrades or blocks — these appear as warnings in the UI.

User Roles & Workflow
The platform has six roles with different views and capabilities:
Public — can submit household food shortage requests, track their request status via reference number
Community — food bank coordinators who see requests in their area and manage pantry stock signals
Responder — emergency responders who see the full request queue, update statuses, assign organizations
Coordinator — regional coordinators who see cross-county resource allocation and logistics assignments
Government — state/federal officials who see the national dashboard and FPI trend data
Admin — full access including the admin panel, source health monitoring, and scenario simulation

Community Request Lifecycle
When someone submits a food request it goes through a tracked pipeline stored in MongoDB:
submitted → screening → verified → assigned → in_transit → resolved
With side exits to escalated or closed at any stage. Each status change is logged with a timestamp, note, and optionally an assigned organization. Responders see the full queue filterable by state, county, urgency (urgent_24h, moderate_week, low_general), and status. Every request gets a unique reference number (FR-XXXX-XXXX) for public lookup.

Burn Rate Engine
For each responder organization covering a county, the system computes a burn rate — how fast they're consuming food stock relative to capacity:
Inputs: current food stock in lbs, open request count, estimated household size (3.5 default), whether an active incident (surge) is ongoing
USDA baseline: 4.5 lbs of food per household per day
Surge multiplier: 1.4× during active incidents
Output: estimated days of supply remaining, daily lbs consumed, status (normal / warning / critical)
This feeds the "Responder capacity" widget in the county detail panel.

Cold Chain Tracking
Organizations can be flagged as having cold chain capability. The coldChain.ts module tracks temperature-sensitive food (produce, dairy, meat) separately from shelf-stable goods, with labels indicating cold chain status that appear as badges on organization cards.

Scenario Simulator
A what-if tool where users can adjust shock parameters (drought severity, storm intensity, supply disruption level) for any state and see in real time how the FPI score and trigger level would change. Used for emergency planning and pre-positioning decisions.

Key Architectural Decisions
Why Zustand + React Query together? Zustand holds the application's own data (requests, incidents, organizations, user role) which is seeded and mutated locally. React Query handles all external API calls with caching, background refresh, and loading/error states. They don't overlap.
Why baseline + live hybrid? The backend may be offline (free Render tier sleeps after inactivity). The frontend always has deterministic baseline scores so the app is never broken — it just shows a "Baseline data" badge instead of "Live · Gemini · NOAA". When the backend comes back, React Query seamlessly upgrades to live data.
Why county-level granularity? State-level food insecurity data already exists (USDA publishes it annually). The insight gap is at the county level in real time — a hurricane hitting two counties in Louisiana doesn't affect the other 62. County granularity is what makes anticipatory response possible.
Why anticipatory rather than reactive? By the time a food crisis is visible (pantries empty, news coverage), it's too late to pre-position. The FPI is designed to cross trigger thresholds 48–72 hours before a crisis becomes acute, giving responders time to act.
