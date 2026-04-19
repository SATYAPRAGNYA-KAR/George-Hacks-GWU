// Core domain types for FoodReady (refactored)
// Frontend-only mock — no Cloud yet. Loose where useful.

// ---------- Roles ----------
export type UserRole =
  | "public"
  | "community"
  | "responder"        // legacy alias = organization
  | "organization"
  | "coordinator"
  | "government"
  | "logistics"
  | "admin";

// ---------- Geo ----------
export interface USState {
  code: string;
  abbr: string;
  name: string;
  fips: string;
}

export interface County {
  fips: string;
  stateAbbr: string;
  name: string;
  population: number;
  seedRich: boolean;
}

// ---------- Trigger bands ----------
export type TriggerLevel = "prepared" | "watch" | "warning" | "action" | "critical";

// ---------- Data coverage / freshness ----------
export type CoverageLevel =
  | "live"               // real adapter connected
  | "delayed"            // adapter exists, data > 24h
  | "baseline"           // generated baseline only
  | "partial"            // partial local adapter
  | "none";              // nothing for this state/county

export type SourceFreshness = "live" | "fresh" | "stale" | "very_stale" | "baseline";

export interface MetricValue {
  value: number;          // 0-100 normalized risk
  source: string;         // e.g. "NWS", "ACS", "baseline", "community"
  freshness: SourceFreshness;
  asOf: string;           // ISO
  notes?: string;
}

// ---------- County FPI components ----------
export interface ComponentScores {
  shockExposure: number;
  vulnerability: number;
  supplyCapacity: number;       // higher = worse
  responseReadiness: number;    // higher = worse
}

export interface CountyFPIDetail {
  countyFips: string;
  total: number;
  trigger: TriggerLevel;
  components: ComponentScores;
  metrics: {
    // shock
    alertCount: MetricValue;
    alertSeverity: MetricValue;
    fema: MetricValue;
    drought: MetricValue;
    // vulnerability
    poverty: MetricValue;
    noVehicle: MetricValue;
    svi: MetricValue;
    foodInsecurity: MetricValue;
    childFoodInsecurity: MetricValue;
    // supply
    foodAccess: MetricValue;
    retailerScarcity: MetricValue;
    // readiness
    stockShortfall: MetricValue;
    voucherShortfall: MetricValue;
  };
  coverage: CoverageLevel;
  communityAdjustment: number; // capped +/- influence from confidence engine
  asOf: string;
}

// ---------- State FPI (separate from county avg) ----------
export interface StateFPIDetail {
  stateAbbr: string;
  total: number;
  trigger: TriggerLevel;
  components: {
    hotspotPressure: number;       // pop-weighted high-risk counties
    pctCountiesWarningPlus: number;
    hazardBurden: number;
    logisticsDisruption: number;
    responseCapacity: number;      // higher = worse
    openIncidentPressure: number;
    communitySignalSurge: number;
  };
  coverage: CoverageLevel;
  asOf: string;
}

// ---------- Signals (legacy) ----------
export interface SignalDriver {
  label: string;
  value: number;
  category: "shock" | "vulnerability" | "supply" | "readiness";
  sourceMock: boolean;
}

// ---------- Daily score ----------
export interface CountyDailyScore {
  countyFips: string;
  date: string;
  totalScore: number;
  components: ComponentScores;
  triggerLevel: TriggerLevel;
  topDrivers: SignalDriver[];
  updatedAt: string;
}

// ---------- Community requests ----------
export type RequestType =
  | "household_food_shortage"
  | "pantry_low_stock"
  | "market_price_spike"
  | "responder_capacity_gap"
  | "transportation_access_issue"
  | "shelter_supply_shortage";

export type Urgency = "urgent_24h" | "moderate_week" | "low_general";

// Full status machine (19 statuses)
export type RequestStatus =
  | "submitted"
  | "screening"
  | "verified"
  | "needs_follow_up"
  | "duplicate"
  | "out_of_scope"
  | "assigned"
  | "accepted"
  | "declined"
  | "scheduled"
  | "picked_up"
  | "in_transit"
  | "delivered"
  | "pending_confirmation"
  | "closed"
  | "reopened"
  | "escalated"
  | "failed_delivery"
  // legacy compatibility (treated as submitted/closed)
  | "open"
  | "claimed"
  | "resolved";

export interface CommunityRequest {
  id: string;
  reference: string;
  stateAbbr: string;
  countyFips: string;
  city: string;
  zip: string;
  type: RequestType;
  urgency: Urgency;
  householdSize: number;
  description: string;
  contact?: string;
  accessLimitations?: string;
  preferredFulfillment?: "delivery" | "pickup" | "either";
  photoUrl?: string;
  status: RequestStatus;
  // legacy
  claimedBy?: string;
  resolutionNote?: string;
  // workflow refs
  assignmentId?: string;
  incidentId?: string;
  duplicateOfId?: string;
  beneficiaryConfirmed?: boolean;
  beneficiaryRejected?: boolean;
  failedReason?: string;
  slaBreachedAt?: string;
  createdAt: string;
  updatedAt: string;
}

// ---------- Community ground-truth signals ----------
export type SignalCategory =
  | "flood"
  | "road_blockage"
  | "bridge_closure"
  | "store_closure"
  | "pantry_closure"
  | "power_outage"
  | "water_issue"
  | "delivery_access"
  | "neighborhood_shortage"
  | "empty_shelves"
  | "severe_price_spike"
  | "unsafe_travel";

export type SignalSeverity = "low" | "moderate" | "high" | "severe";

export type SignalConfidence =
  | "unverified"
  | "probable"
  | "coordinator_verified"
  | "officially_corroborated";

export interface CommunitySignalReport {
  id: string;
  stateAbbr: string;
  countyFips: string;
  zip: string;
  category: SignalCategory;
  severity: SignalSeverity;
  description: string;
  imageUrl?: string;
  householdsAffectedEstimate?: number;
  reporterFingerprint: string; // pseudo-uniqueness for confidence scoring
  createdAt: string;
}

export interface IncidentSignalCluster {
  id: string;
  countyFips: string;
  category: SignalCategory;
  reportIds: string[];
  uniqueReporters: number;
  geoClusterScore: number;     // 0-1
  timeClusterScore: number;    // 0-1
  evidenceScore: number;       // 0-1
  consistencyScore: number;    // 0-1
  officialCorroboration: boolean;
  confidence: SignalConfidence;
  confidenceScore: number;     // 0-100
  fpiAdjustment: number;       // capped +/- delta applied to county FPI
  firstReportAt: string;
  lastReportAt: string;
}

// ---------- Price reports ----------
export interface PriceReport {
  id: string;
  stateAbbr: string;
  countyFips: string;
  storeName: string;
  date: string;
  item: string;
  price: number;
  packageSize: string;
  note?: string;
  createdAt: string;
}

// ---------- Organizations ----------
export type OrgType =
  | "food_bank"
  | "ngo"
  | "pantry_network"
  | "local_agency"
  | "faith_based"
  | "county_agency";

export type OrgVerificationStatus =
  | "pending"
  | "provisionally_verified"
  | "verified"
  | "restricted"
  | "suspended";

export interface Organization {
  id: string;
  name: string;
  type: OrgType;
  verified: boolean;                       // legacy
  verificationStatus: OrgVerificationStatus;
  contactEmail?: string;
  officialEmailDomain?: string;
  einPlaceholder?: string;
  statesCovered: string[];
  countiesCovered: string[];
  foodStockLbs: number;
  voucherCapacityUsd: number;
  transportTrucks: number;
  coldChain: boolean;
  voucherCapability: boolean;
  municipalAffiliation?: string;
  emergencyContact?: string;
  documentsPlaceholder?: string[];
  notes?: string;
  // performance
  perfResponseTimeMin?: number;
  perfAcceptanceRate?: number;
  perfCompletionRate?: number;
  perfFailedDeliveryRate?: number;
  perfBeneficiaryConfirmRate?: number;
  lastUpdated: string;
}

// ---------- Trigger events ----------
export interface TriggerEvent {
  id: string;
  stateAbbr: string;
  countyFips: string;
  previousScore: number;
  newScore: number;
  thresholdCrossed: TriggerLevel;
  timestamp: string;
  recommendedAction: string;
  actionStatus: "pending" | "in_progress" | "completed" | "escalated";
  notes?: string;
}

// ---------- Recommendations ----------
export type RecHorizon = "immediate" | "short_term" | "structural";

export interface Recommendation {
  id: string;
  countyFips: string;
  text: string;
  reason: string;
  urgency: TriggerLevel;
  horizon: RecHorizon;
  timeline: string;
  confidence: "low" | "medium" | "high";
  signalsUsed: string[];
  staleDataFlag?: boolean;
  createdAt: string;
}

// ---------- Scenarios ----------
export interface ScenarioRun {
  id: string;
  stateAbbr: string;
  scenario: string;
  inputs: Record<string, number>;
  beforeAvg: number;
  afterAvg: number;
  affectedCounties: { fips: string; before: number; after: number; level: TriggerLevel }[];
  createdAt: string;
}

// ---------- Data sources ----------
export interface DataSource {
  name: string;
  category: string;
  geographicLevel: "national" | "state" | "county";
  description: string;
  updateFrequency: string;
  status: "mock" | "live" | "planned";
  lastSync: string;
}

export interface SourceHealth {
  sourceName: string;
  coverage: CoverageLevel;
  syncHealth: "ok" | "degraded" | "failing" | "offline";
  lastSync: string;
  staleWarning: boolean;
  failedJobs24h: number;
  notes?: string;
}

// ---------- Workflow: assignments, logistics, deliveries ----------
export type AssignmentStatus =
  | "proposed"
  | "accepted"
  | "declined"
  | "expired"
  | "completed"
  | "cancelled";

export interface RequestAssignment {
  id: string;
  requestId: string;
  organizationId: string;
  proposedBy: string;             // coordinator / gov user id
  proposedAt: string;
  respondBy: string;              // SLA deadline
  status: AssignmentStatus;
  acceptedAt?: string;
  declinedReason?: string;
  notes?: string;
}

export type SupplySourceType =
  | "food_bank_stock"
  | "pantry_stock"
  | "municipal_reserve"
  | "retailer_support"
  | "voucher_cash";

export type StagingSiteType =
  | "warehouse"
  | "pantry"
  | "community_center"
  | "school"
  | "church"
  | "municipal_depot"
  | "temporary_site";

export type TransportProviderType =
  | "supplier_truck"
  | "municipal_fleet"
  | "logistics_partner"
  | "volunteer_driver"
  | "recipient_pickup";

export type DeliveryMode =
  | "home_delivery"
  | "pantry_pickup"
  | "community_distribution"
  | "shelter_delivery"
  | "voucher_cash";

export type LogisticsStatus =
  | "allocated"
  | "packed"
  | "ready_for_pickup"
  | "picked_up"
  | "in_transit"
  | "delivered_to_site"
  | "delivered_to_household"
  | "delivery_failed"
  | "confirmed";

export interface LogisticsAssignment {
  id: string;
  requestId?: string;
  incidentId?: string;
  missionOrderId?: string;
  supplySource: SupplySourceType;
  supplyOrgId?: string;
  stagingSite: StagingSiteType;
  stagingSiteName?: string;
  transportProvider: TransportProviderType;
  transportOrgId?: string;
  deliveryMode: DeliveryMode;
  status: LogisticsStatus;
  scheduledFor?: string;
  notes?: string;
  createdAt: string;
  updatedAt: string;
}

export interface ProofOfDelivery {
  id: string;
  logisticsAssignmentId: string;
  uploadedBy: string;
  type: "photo" | "signature" | "sms_confirmation" | "coordinator_attestation";
  fileNamePlaceholder?: string;
  notes?: string;
  createdAt: string;
}

// ---------- Incidents & mission orders ----------
export type IncidentStatus = "open" | "active" | "stabilizing" | "closed";

export interface Incident {
  id: string;
  stateAbbr: string;
  countyFips: string;
  title: string;
  description: string;
  hazardType: SignalCategory | "other";
  status: IncidentStatus;
  estHouseholdsAffected: number;
  openedBy: string;
  openedAt: string;
  closedAt?: string;
  signalClusterIds: string[];
  missionOrderIds: string[];
  requestIds: string[];
}

export type MissionOrderStatus = "draft" | "issued" | "in_progress" | "fulfilled" | "cancelled";

export interface MissionOrder {
  id: string;
  incidentId: string;
  issuedBy: string;          // gov user id
  issuedAt: string;
  status: MissionOrderStatus;
  title: string;
  instructions: string;
  reservedStockLbs?: number;
  voucherBudgetUsd?: number;
  assignedOrgIds: string[];
  assignedLogisticsIds: string[];
  bypassNormalRouting: boolean;
  notes?: string;
}

// ---------- Audit log ----------
export type AuditActionType =
  | "request_submitted"
  | "request_screened"
  | "request_verified"
  | "request_marked_duplicate"
  | "request_assigned"
  | "assignment_accepted"
  | "assignment_declined"
  | "logistics_created"
  | "logistics_updated"
  | "proof_uploaded"
  | "beneficiary_confirmed"
  | "beneficiary_rejected"
  | "request_closed"
  | "request_reopened"
  | "request_escalated"
  | "incident_opened"
  | "mission_order_issued"
  | "org_verified"
  | "org_status_changed"
  | "signal_reported"
  | "signal_confidence_updated"
  | "scenario_run"
  | "settings_changed"
  | "gov_override";

export interface AuditLogEntry {
  id: string;
  timestamp: string;
  actorRole: UserRole;
  actorLabel: string;     // "Coordinator (mock)" etc.
  action: AuditActionType;
  subjectType: "request" | "organization" | "incident" | "mission_order" | "logistics" | "signal" | "system";
  subjectId: string;
  summary: string;
  metadata?: Record<string, any>;
}
