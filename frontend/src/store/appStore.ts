import { create } from "zustand";
import { persist } from "zustand/middleware";
import { formatISO, subDays, addHours } from "date-fns";
import type {
  CommunityRequest,
  CommunitySignalReport,
  IncidentSignalCluster,
  Incident,
  MissionOrder,
  Organization,
  PriceReport,
  RequestAssignment,
  LogisticsAssignment,
  ProofOfDelivery,
  ScenarioRun,
  TriggerEvent,
  UserRole,
  RequestStatus,
  AuditLogEntry,
  AuditActionType,
  SourceHealth,
  Recommendation,
  RecHorizon,
} from "@/types/foodready";
import { generateReference, COMPONENT_WEIGHTS, computeTotalScore, triggerForScore } from "@/lib/risk";
import { IOWA_COUNTIES, SAMPLE_COUNTIES, ALL_COUNTIES } from "@/data/counties";
import {
  getCountyFPIDetail,
  getStateFPIDetail,
  syntheticCountiesForState,
} from "@/data/baseline";
import { clusterReports } from "@/lib/confidence";
import { US_STATES, STATE_CENTROIDS } from "@/data/states";

const now = () => new Date().toISOString();

// ---------- Seeds ----------
const seedRequests = (): CommunityRequest[] => {
  const items: Omit<CommunityRequest, "id" | "reference" | "createdAt" | "updatedAt">[] = [
    { stateAbbr: "IA", countyFips: "19007", city: "Centerville", zip: "52544", type: "household_food_shortage", urgency: "urgent_24h", householdSize: 5, description: "Family of 5, no groceries after flooding closed our road.", status: "submitted" },
    { stateAbbr: "IA", countyFips: "19179", city: "Ottumwa", zip: "52501", type: "pantry_low_stock", urgency: "moderate_week", householdSize: 0, description: "Pantry serving 200 families is down to <3 days of stock.", status: "verified" },
    { stateAbbr: "IA", countyFips: "19029", city: "Atlantic", zip: "50022", type: "transportation_access_issue", urgency: "moderate_week", householdSize: 3, description: "Elderly couple cannot reach pantry due to closed bridge.", status: "submitted" },
    { stateAbbr: "IA", countyFips: "19047", city: "Denison", zip: "51442", type: "market_price_spike", urgency: "low_general", householdSize: 0, description: "Eggs +60% in two weeks at local stores.", status: "closed", resolutionNote: "Verified, escalated to state monitor." },
    { stateAbbr: "IA", countyFips: "19153", city: "Des Moines", zip: "50309", type: "household_food_shortage", urgency: "moderate_week", householdSize: 4, description: "Lost SNAP benefits temporarily, need bridge support.", status: "assigned" },
    { stateAbbr: "IA", countyFips: "19127", city: "Marshalltown", zip: "50158", type: "pantry_low_stock", urgency: "urgent_24h", householdSize: 0, description: "Mobile pantry truck broken, distribution paused.", status: "screening" },
    { stateAbbr: "TX", countyFips: "48201", city: "Houston", zip: "77002", type: "responder_capacity_gap", urgency: "urgent_24h", householdSize: 0, description: "Hurricane-impacted ZIP, food bank at 30% capacity.", status: "escalated" },
    { stateAbbr: "LA", countyFips: "22071", city: "New Orleans", zip: "70112", type: "household_food_shortage", urgency: "urgent_24h", householdSize: 6, description: "Power outage, no refrigeration for 4 days.", status: "in_transit" },
    { stateAbbr: "CA", countyFips: "06019", city: "Fresno", zip: "93721", type: "market_price_spike", urgency: "low_general", householdSize: 0, description: "Produce prices doubled at corner stores.", status: "submitted" },
    { stateAbbr: "FL", countyFips: "12086", city: "Miami", zip: "33101", type: "transportation_access_issue", urgency: "moderate_week", householdSize: 2, description: "Storm-flooded streets blocking pantry access.", status: "submitted" },
  ];
  return items.map((r, i) => ({
    ...r, id: `req-${i + 1}`, reference: generateReference(),
    createdAt: subDays(new Date(), Math.floor(Math.random() * 10)).toISOString(),
    updatedAt: now(),
  }));
};

const seedOrgs: Organization[] = [
  { id: "org-iowafoodbank", name: "Food Bank of Iowa", type: "food_bank", verified: true, verificationStatus: "verified", statesCovered: ["IA"], countiesCovered: ["19007", "19179", "19029", "19047", "19153", "19127"], foodStockLbs: 480000, voucherCapacityUsd: 65000, transportTrucks: 12, coldChain: true, voucherCapability: true, contactEmail: "ops@iowafoodbank.org", officialEmailDomain: "iowafoodbank.org", einPlaceholder: "EIN-XX-1234567", emergencyContact: "+1-515-555-0101", perfResponseTimeMin: 42, perfAcceptanceRate: 0.92, perfCompletionRate: 0.95, perfFailedDeliveryRate: 0.03, perfBeneficiaryConfirmRate: 0.78, lastUpdated: now() },
  { id: "org-dmrescue", name: "Des Moines Area Religious Council", type: "faith_based", verified: true, verificationStatus: "verified", statesCovered: ["IA"], countiesCovered: ["19153"], foodStockLbs: 95000, voucherCapacityUsd: 22000, transportTrucks: 4, coldChain: true, voucherCapability: true, perfResponseTimeMin: 65, perfAcceptanceRate: 0.85, perfCompletionRate: 0.90, perfFailedDeliveryRate: 0.05, perfBeneficiaryConfirmRate: 0.71, lastUpdated: now() },
  { id: "org-secondharvest", name: "Second Harvest Food Bank", type: "food_bank", verified: true, verificationStatus: "verified", statesCovered: ["LA", "MS"], countiesCovered: ["22071", "22051", "28049"], foodStockLbs: 320000, voucherCapacityUsd: 45000, transportTrucks: 9, coldChain: true, voucherCapability: true, perfResponseTimeMin: 55, perfAcceptanceRate: 0.88, perfCompletionRate: 0.91, perfFailedDeliveryRate: 0.06, perfBeneficiaryConfirmRate: 0.72, lastUpdated: now() },
  { id: "org-feedingtx", name: "Feeding Texas", type: "pantry_network", verified: true, verificationStatus: "verified", statesCovered: ["TX"], countiesCovered: ["48201", "48029", "48141"], foodStockLbs: 720000, voucherCapacityUsd: 110000, transportTrucks: 18, coldChain: true, voucherCapability: true, perfResponseTimeMin: 38, perfAcceptanceRate: 0.94, perfCompletionRate: 0.96, perfFailedDeliveryRate: 0.02, perfBeneficiaryConfirmRate: 0.80, lastUpdated: now() },
  { id: "org-cafoodbank", name: "California Association of Food Banks", type: "food_bank", verified: true, verificationStatus: "verified", statesCovered: ["CA"], countiesCovered: ["06037", "06019", "06107"], foodStockLbs: 1100000, voucherCapacityUsd: 180000, transportTrucks: 24, coldChain: true, voucherCapability: true, perfResponseTimeMin: 47, perfAcceptanceRate: 0.91, perfCompletionRate: 0.94, perfFailedDeliveryRate: 0.04, perfBeneficiaryConfirmRate: 0.76, lastUpdated: now() },
  { id: "org-cassrural", name: "Cass County Rural Outreach", type: "local_agency", verified: false, verificationStatus: "pending", statesCovered: ["IA"], countiesCovered: ["19029"], foodStockLbs: 8500, voucherCapacityUsd: 2000, transportTrucks: 1, coldChain: false, voucherCapability: false, notes: "Awaiting verification. EIN and 501(c)(3) docs pending review.", lastUpdated: now() },
  { id: "org-iowagov-fleet", name: "Iowa Municipal Fleet Pool", type: "county_agency", verified: true, verificationStatus: "verified", statesCovered: ["IA"], countiesCovered: ["19153", "19113", "19127"], foodStockLbs: 0, voucherCapacityUsd: 0, transportTrucks: 8, coldChain: false, voucherCapability: false, municipalAffiliation: "Iowa State Emergency Mgmt", notes: "Logistics-only; transport assets.", perfResponseTimeMin: 30, perfAcceptanceRate: 0.97, perfCompletionRate: 0.96, perfFailedDeliveryRate: 0.02, perfBeneficiaryConfirmRate: 0.0, lastUpdated: now() },
];

const seedPrices: PriceReport[] = [
  { id: "p1", stateAbbr: "IA", countyFips: "19047", storeName: "Family Mart", date: "2025-04-12", item: "Eggs", price: 6.49, packageSize: "dozen", note: "Up from $3.99 two weeks ago.", createdAt: now() },
  { id: "p2", stateAbbr: "IA", countyFips: "19179", storeName: "Hy-Vee", date: "2025-04-14", item: "Milk", price: 5.29, packageSize: "gallon", createdAt: now() },
  { id: "p3", stateAbbr: "IA", countyFips: "19007", storeName: "Country Mart", date: "2025-04-15", item: "Ground beef", price: 7.99, packageSize: "1 lb", createdAt: now() },
  { id: "p4", stateAbbr: "CA", countyFips: "06019", storeName: "Local Market", date: "2025-04-13", item: "Tomatoes", price: 4.99, packageSize: "1 lb", note: "Doubled in 3 weeks.", createdAt: now() },
  { id: "p5", stateAbbr: "TX", countyFips: "48201", storeName: "Corner Grocery", date: "2025-04-14", item: "Bread", price: 4.49, packageSize: "loaf", createdAt: now() },
];

const seedTriggers: TriggerEvent[] = [
  { id: "t1", stateAbbr: "IA", countyFips: "19007", previousScore: 68, newScore: 76, thresholdCrossed: "action", timestamp: subDays(new Date(), 2).toISOString(), recommendedAction: "Activate voucher workflow; deploy mobile pantry.", actionStatus: "in_progress" },
  { id: "t2", stateAbbr: "IA", countyFips: "19179", previousScore: 58, newScore: 64, thresholdCrossed: "warning", timestamp: subDays(new Date(), 4).toISOString(), recommendedAction: "Pre-position shelf-stable food; activate responder review.", actionStatus: "completed" },
  { id: "t3", stateAbbr: "LA", countyFips: "22071", previousScore: 72, newScore: 81, thresholdCrossed: "action", timestamp: subDays(new Date(), 1).toISOString(), recommendedAction: "Open emergency food reserves; deploy responders.", actionStatus: "in_progress" },
  { id: "t4", stateAbbr: "TX", countyFips: "48201", previousScore: 55, newScore: 62, thresholdCrossed: "warning", timestamp: subDays(new Date(), 3).toISOString(), recommendedAction: "Pre-position food stocks for hurricane-affected ZIPs.", actionStatus: "pending" },
];

const seedSignalReports = (): CommunitySignalReport[] => {
  const mk = (
    countyFips: string,
    stateAbbr: string,
    zip: string,
    category: any,
    severity: any,
    description: string,
    fingerprint: string,
    hoursAgo: number,
    extras: Partial<CommunitySignalReport> = {},
  ): CommunitySignalReport => ({
    id: `sig-${countyFips}-${fingerprint}-${hoursAgo}`,
    stateAbbr,
    countyFips,
    zip,
    category,
    severity,
    description,
    reporterFingerprint: fingerprint,
    createdAt: addHours(new Date(), -hoursAgo).toISOString(),
    ...extras,
  });
  return [
    // Cluster: Appanoose flood — multiple reporters, tight time, evidence
    mk("19007", "IA", "52544", "flood", "high", "Water over Hwy 5, can't get to town.", "fp-aa", 6, { householdsAffectedEstimate: 30, imageUrl: "placeholder://flood1.jpg" }),
    mk("19007", "IA", "52544", "flood", "severe", "Bridge underwater, pantry inaccessible.", "fp-bb", 5),
    mk("19007", "IA", "52544", "flood", "high", "Neighbors stranded, no road out.", "fp-cc", 4, { householdsAffectedEstimate: 18 }),
    mk("19007", "IA", "52544", "road_blockage", "high", "County Rd J18 closed, debris.", "fp-bb", 3),
    // Cluster: Wapello empty shelves — 2 reporters
    mk("19179", "IA", "52501", "empty_shelves", "moderate", "Hy-Vee bread aisle empty all weekend.", "fp-dd", 14),
    mk("19179", "IA", "52501", "empty_shelves", "moderate", "No milk at any store on the south side.", "fp-ee", 10),
    // Single reports (low confidence)
    mk("48201", "TX", "77002", "power_outage", "high", "Block-wide outage, fridge food spoiling.", "fp-tx1", 8),
    mk("22071", "LA", "70112", "delivery_access", "severe", "Truck can't reach 7th ward, water too high.", "fp-la1", 5, { imageUrl: "placeholder://water.jpg" }),
  ];
};

// ---------- Audit log helpers ----------
const ROLE_LABEL: Record<UserRole, string> = {
  public: "Public (mock)",
  community: "Community (mock)",
  responder: "Organization (mock)",
  organization: "Organization (mock)",
  coordinator: "Coordinator (mock)",
  government: "Government (mock)",
  logistics: "Logistics partner (mock)",
  admin: "Admin (mock)",
};

interface AppState {
  // role & settings
  role: UserRole;
  setRole: (r: UserRole) => void;
  weights: typeof COMPONENT_WEIGHTS;
  setWeights: (w: typeof COMPONENT_WEIGHTS) => void;
  thresholds: { watch: number; warning: number; action: number; critical: number };
  setThresholds: (t: AppState["thresholds"]) => void;
  slaMinutes: { acceptanceUrgent: number; acceptanceModerate: number; deliveryUrgent: number };
  setSlaMinutes: (s: AppState["slaMinutes"]) => void;

  // requests + workflow
  requests: CommunityRequest[];
  addRequest: (r: Omit<CommunityRequest, "id" | "reference" | "createdAt" | "updatedAt" | "status">) => CommunityRequest;
  screenRequest: (id: string, decision: { newStatus: RequestStatus; note?: string; duplicateOfId?: string }) => void;
  assignRequest: (id: string, organizationId: string) => RequestAssignment;
  respondAssignment: (assignmentId: string, accept: boolean, reason?: string) => void;
  updateRequestStatus: (id: string, status: RequestStatus, note?: string) => void;
  beneficiaryConfirm: (id: string, confirmed: boolean, note?: string) => void;
  reopenRequest: (id: string, note?: string) => void;
  escalateRequest: (id: string, note?: string) => void;
  closeRequest: (id: string, note?: string) => void;

  // legacy claim/resolve (kept for backwards compat with some pages)
  claimRequest: (id: string, orgId: string) => void;
  resolveRequest: (id: string, note: string) => void;

  // assignments + logistics
  assignments: RequestAssignment[];
  logistics: LogisticsAssignment[];
  proofs: ProofOfDelivery[];
  createLogistics: (l: Omit<LogisticsAssignment, "id" | "createdAt" | "updatedAt" | "status"> & { status?: LogisticsAssignment["status"] }) => LogisticsAssignment;
  updateLogisticsStatus: (id: string, status: LogisticsAssignment["status"], note?: string) => void;
  uploadProof: (logisticsAssignmentId: string, type: ProofOfDelivery["type"], notes?: string) => ProofOfDelivery;

  // organizations
  organizations: Organization[];
  upsertOrgCapacity: (o: Organization) => void;
  setOrgVerificationStatus: (id: string, status: Organization["verificationStatus"]) => void;
  verifyOrg: (id: string) => void;

  // signals
  signalReports: CommunitySignalReport[];
  addSignalReport: (s: Omit<CommunitySignalReport, "id" | "createdAt" | "reporterFingerprint"> & { reporterFingerprint?: string }) => CommunitySignalReport;
  coordinatorVerifyCluster: (clusterId: string) => void;
  officialCorroboratedKeys: string[]; // keys "fips::category"
  toggleOfficialCorroboration: (countyFips: string, category: string, on: boolean) => void;

  // incidents + mission orders
  incidents: Incident[];
  openIncident: (i: Omit<Incident, "id" | "openedAt" | "status" | "missionOrderIds" | "requestIds">) => Incident;
  closeIncident: (id: string, note?: string) => void;
  missionOrders: MissionOrder[];
  issueMissionOrder: (m: Omit<MissionOrder, "id" | "issuedAt" | "status">) => MissionOrder;
  updateMissionOrderStatus: (id: string, status: MissionOrder["status"]) => void;

  // prices + triggers + scenarios
  priceReports: PriceReport[];
  addPriceReport: (p: Omit<PriceReport, "id" | "createdAt">) => PriceReport;
  triggers: TriggerEvent[];
  scenarios: ScenarioRun[];
  addScenario: (s: Omit<ScenarioRun, "id" | "createdAt">) => ScenarioRun;

  // audit log + source health
  auditLog: AuditLogEntry[];
  appendAudit: (entry: Omit<AuditLogEntry, "id" | "timestamp" | "actorRole" | "actorLabel">) => void;
  sourceHealth: SourceHealth[];
}

// ---------- Source health seed ----------
const seedSourceHealth: SourceHealth[] = [
  { sourceName: "NWS alerts", coverage: "partial", syncHealth: "ok", lastSync: now(), staleWarning: false, failedJobs24h: 0, notes: "Adapter stub: returns baseline values for non-IA states." },
  { sourceName: "FEMA disaster declarations", coverage: "baseline", syncHealth: "degraded", lastSync: subDays(new Date(), 2).toISOString(), staleWarning: true, failedJobs24h: 1 },
  { sourceName: "USDA Food Access Atlas", coverage: "baseline", syncHealth: "ok", lastSync: subDays(new Date(), 30).toISOString(), staleWarning: true, failedJobs24h: 0, notes: "Updates ~annual; baseline only." },
  { sourceName: "ACS poverty / no-vehicle", coverage: "baseline", syncHealth: "ok", lastSync: subDays(new Date(), 90).toISOString(), staleWarning: false, failedJobs24h: 0 },
  { sourceName: "CDC SVI", coverage: "baseline", syncHealth: "ok", lastSync: subDays(new Date(), 60).toISOString(), staleWarning: false, failedJobs24h: 0 },
  { sourceName: "USDA SNAP retailer density", coverage: "baseline", syncHealth: "ok", lastSync: subDays(new Date(), 14).toISOString(), staleWarning: false, failedJobs24h: 0 },
  { sourceName: "US Drought Monitor", coverage: "baseline", syncHealth: "failing", lastSync: subDays(new Date(), 5).toISOString(), staleWarning: true, failedJobs24h: 3, notes: "Adapter not yet wired." },
  { sourceName: "Community signal reports", coverage: "live", syncHealth: "ok", lastSync: now(), staleWarning: false, failedJobs24h: 0, notes: "User-submitted; confidence-scored." },
];

// ---------- Seed: incidents + clusters wiring is derived; only one seeded incident for demo ----------
const seedIncidents = (): Incident[] => [
  {
    id: "inc-ia-app-flood",
    stateAbbr: "IA",
    countyFips: "19007",
    title: "Appanoose County flooding",
    description: "Heavy rainfall flooding rural roads; multiple community reports plus NWS flood watch.",
    hazardType: "flood",
    status: "active",
    estHouseholdsAffected: 250,
    openedBy: "coordinator-mock",
    openedAt: subDays(new Date(), 1).toISOString(),
    signalClusterIds: ["cluster-19007::flood"],
    missionOrderIds: ["mo-ia-app-1"],
    requestIds: ["req-1"],
  },
];

const seedMissionOrders = (): MissionOrder[] => [
  {
    id: "mo-ia-app-1",
    incidentId: "inc-ia-app-flood",
    issuedBy: "gov-mock",
    issuedAt: subDays(new Date(), 1).toISOString(),
    status: "in_progress",
    title: "Mobile pantry deployment — Centerville",
    instructions: "Deploy mobile pantry to Centerville staging site; prioritize households west of Hwy 5.",
    reservedStockLbs: 12000,
    voucherBudgetUsd: 5000,
    assignedOrgIds: ["org-iowafoodbank"],
    assignedLogisticsIds: ["log-seed-1"],
    bypassNormalRouting: false,
  },
];

const seedLogistics = (): LogisticsAssignment[] => [
  {
    id: "log-seed-1",
    requestId: "req-1",
    incidentId: "inc-ia-app-flood",
    missionOrderId: "mo-ia-app-1",
    supplySource: "food_bank_stock",
    supplyOrgId: "org-iowafoodbank",
    stagingSite: "community_center",
    stagingSiteName: "Centerville Community Center",
    transportProvider: "supplier_truck",
    transportOrgId: "org-iowafoodbank",
    deliveryMode: "community_distribution",
    status: "in_transit",
    scheduledFor: addHours(new Date(), 4).toISOString(),
    createdAt: subDays(new Date(), 1).toISOString(),
    updatedAt: now(),
  },
  {
    id: "log-seed-2",
    requestId: "req-8",
    supplySource: "food_bank_stock",
    supplyOrgId: "org-secondharvest",
    stagingSite: "warehouse",
    stagingSiteName: "Second Harvest NOLA Warehouse",
    transportProvider: "logistics_partner",
    deliveryMode: "home_delivery",
    status: "picked_up",
    scheduledFor: addHours(new Date(), 2).toISOString(),
    createdAt: subDays(new Date(), 1).toISOString(),
    updatedAt: now(),
  },
];

// ---------- Store ----------
export const useAppStore = create<AppState>()(
  persist(
    (set, get) => {
      const appendAudit = (entry: Omit<AuditLogEntry, "id" | "timestamp" | "actorRole" | "actorLabel">) => {
        const role = get().role;
        const log: AuditLogEntry = {
          ...entry,
          id: `audit-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
          timestamp: now(),
          actorRole: role,
          actorLabel: ROLE_LABEL[role],
        };
        set({ auditLog: [log, ...get().auditLog].slice(0, 500) });
      };

      return {
        role: "public",
        setRole: (r) => set({ role: r }),
        weights: COMPONENT_WEIGHTS,
        setWeights: (w) => set({ weights: w }),
        thresholds: { watch: 40, warning: 60, action: 75, critical: 90 },
        setThresholds: (t) => set({ thresholds: t }),
        slaMinutes: { acceptanceUrgent: 60, acceptanceModerate: 240, deliveryUrgent: 360 },
        setSlaMinutes: (s) => set({ slaMinutes: s }),

        // requests
        requests: seedRequests(),
        addRequest: (r) => {
          const req: CommunityRequest = {
            ...r, id: `req-${Date.now()}`, reference: generateReference(),
            status: "submitted", createdAt: now(), updatedAt: now(),
          };
          set({ requests: [req, ...get().requests] });
          appendAudit({ action: "request_submitted", subjectType: "request", subjectId: req.id, summary: `Submitted: ${req.type} (${req.urgency})` });
          return req;
        },
        screenRequest: (id, decision) =>
          set((state) => {
            const next = state.requests.map((r) =>
              r.id === id
                ? { ...r, status: decision.newStatus, duplicateOfId: decision.duplicateOfId, updatedAt: now() }
                : r,
            );
            return { requests: next };
          }),
        assignRequest: (id, organizationId) => {
          const sla = get().slaMinutes;
          const req = get().requests.find((r) => r.id === id);
          const respondMins = req?.urgency === "urgent_24h" ? sla.acceptanceUrgent : sla.acceptanceModerate;
          const a: RequestAssignment = {
            id: `asn-${Date.now()}`,
            requestId: id,
            organizationId,
            proposedBy: "coordinator-mock",
            proposedAt: now(),
            respondBy: addHours(new Date(), respondMins / 60).toISOString(),
            status: "proposed",
          };
          set({
            assignments: [a, ...get().assignments],
            requests: get().requests.map((r) =>
              r.id === id ? { ...r, status: "assigned", assignmentId: a.id, updatedAt: now() } : r,
            ),
          });
          appendAudit({ action: "request_assigned", subjectType: "request", subjectId: id, summary: `Assigned to ${organizationId}`, metadata: { organizationId } });
          return a;
        },
        respondAssignment: (assignmentId, accept, reason) => {
          const a = get().assignments.find((x) => x.id === assignmentId);
          if (!a) return;
          set({
            assignments: get().assignments.map((x) =>
              x.id === assignmentId
                ? { ...x, status: accept ? "accepted" : "declined", acceptedAt: accept ? now() : undefined, declinedReason: !accept ? reason : undefined }
                : x,
            ),
            requests: get().requests.map((r) =>
              r.id === a.requestId
                ? { ...r, status: accept ? "accepted" : "declined", updatedAt: now() }
                : r,
            ),
          });
          appendAudit({
            action: accept ? "assignment_accepted" : "assignment_declined",
            subjectType: "request",
            subjectId: a.requestId,
            summary: accept ? `Org ${a.organizationId} accepted` : `Org ${a.organizationId} declined: ${reason ?? "no reason"}`,
          });
        },
        updateRequestStatus: (id, status, note) => {
          set({
            requests: get().requests.map((r) =>
              r.id === id ? { ...r, status, updatedAt: now() } : r,
            ),
          });
          appendAudit({ action: "request_screened", subjectType: "request", subjectId: id, summary: `Status → ${status}${note ? `: ${note}` : ""}` });
        },
        beneficiaryConfirm: (id, confirmed, note) => {
          set({
            requests: get().requests.map((r) =>
              r.id === id
                ? {
                    ...r,
                    beneficiaryConfirmed: confirmed,
                    beneficiaryRejected: !confirmed,
                    status: confirmed ? "closed" : "reopened",
                    resolutionNote: note,
                    updatedAt: now(),
                  }
                : r,
            ),
          });
          appendAudit({
            action: confirmed ? "beneficiary_confirmed" : "beneficiary_rejected",
            subjectType: "request",
            subjectId: id,
            summary: confirmed ? `Beneficiary confirmed delivery${note ? `: ${note}` : ""}` : `Beneficiary rejected: ${note ?? "no note"}`,
          });
        },
        reopenRequest: (id, note) => {
          set({
            requests: get().requests.map((r) =>
              r.id === id ? { ...r, status: "reopened", resolutionNote: note, updatedAt: now() } : r,
            ),
          });
          appendAudit({ action: "request_reopened", subjectType: "request", subjectId: id, summary: note ?? "Reopened" });
        },
        escalateRequest: (id, note) => {
          set({
            requests: get().requests.map((r) =>
              r.id === id ? { ...r, status: "escalated", updatedAt: now() } : r,
            ),
          });
          appendAudit({ action: "request_escalated", subjectType: "request", subjectId: id, summary: note ?? "Escalated to state coordination" });
        },
        closeRequest: (id, note) => {
          set({
            requests: get().requests.map((r) =>
              r.id === id ? { ...r, status: "closed", resolutionNote: note, updatedAt: now() } : r,
            ),
          });
          appendAudit({ action: "request_closed", subjectType: "request", subjectId: id, summary: note ?? "Closed" });
        },

        // legacy compat
        claimRequest: (id, orgId) => {
          set({
            requests: get().requests.map((r) =>
              r.id === id ? { ...r, status: "accepted", claimedBy: orgId, updatedAt: now() } : r,
            ),
          });
        },
        resolveRequest: (id, note) => {
          set({
            requests: get().requests.map((r) =>
              r.id === id ? { ...r, status: "closed", resolutionNote: note, updatedAt: now() } : r,
            ),
          });
        },

        // assignments + logistics
        assignments: [],
        logistics: seedLogistics(),
        proofs: [],
        createLogistics: (l) => {
          const log: LogisticsAssignment = {
            ...l,
            id: `log-${Date.now()}`,
            status: l.status ?? "allocated",
            createdAt: now(),
            updatedAt: now(),
          };
          set({ logistics: [log, ...get().logistics] });
          appendAudit({ action: "logistics_created", subjectType: "logistics", subjectId: log.id, summary: `${log.supplySource} → ${log.deliveryMode}` });
          return log;
        },
        updateLogisticsStatus: (id, status, note) => {
          set({
            logistics: get().logistics.map((l) =>
              l.id === id ? { ...l, status, notes: note ?? l.notes, updatedAt: now() } : l,
            ),
          });
          appendAudit({ action: "logistics_updated", subjectType: "logistics", subjectId: id, summary: `Status → ${status}${note ? `: ${note}` : ""}` });
        },
        uploadProof: (logisticsAssignmentId, type, notes) => {
          const proof: ProofOfDelivery = {
            id: `proof-${Date.now()}`,
            logisticsAssignmentId,
            uploadedBy: get().role,
            type,
            notes,
            createdAt: now(),
          };
          set({ proofs: [proof, ...get().proofs] });
          appendAudit({ action: "proof_uploaded", subjectType: "logistics", subjectId: logisticsAssignmentId, summary: `Proof: ${type}${notes ? ` — ${notes}` : ""}` });
          return proof;
        },

        // orgs
        organizations: seedOrgs,
        upsertOrgCapacity: (o) => {
          const exists = get().organizations.find((x) => x.id === o.id);
          if (exists) {
            set({ organizations: get().organizations.map((x) => (x.id === o.id ? { ...o, lastUpdated: now() } : x)) });
          } else {
            set({ organizations: [{ ...o, lastUpdated: now() }, ...get().organizations] });
          }
        },
        setOrgVerificationStatus: (id, status) => {
          set({
            organizations: get().organizations.map((o) =>
              o.id === id ? { ...o, verificationStatus: status, verified: status === "verified" || status === "provisionally_verified", lastUpdated: now() } : o,
            ),
          });
          appendAudit({ action: "org_status_changed", subjectType: "organization", subjectId: id, summary: `Status → ${status}` });
        },
        verifyOrg: (id) => {
          set({
            organizations: get().organizations.map((o) =>
              o.id === id ? { ...o, verified: true, verificationStatus: "verified", lastUpdated: now() } : o,
            ),
          });
          appendAudit({ action: "org_verified", subjectType: "organization", subjectId: id, summary: `Organization verified` });
        },

        // signals
        signalReports: seedSignalReports(),
        addSignalReport: (s) => {
          const report: CommunitySignalReport = {
            ...s,
            id: `sig-${Date.now()}`,
            reporterFingerprint: s.reporterFingerprint ?? `anon-${Math.random().toString(36).slice(2, 8)}`,
            createdAt: now(),
          };
          set({ signalReports: [report, ...get().signalReports] });
          appendAudit({ action: "signal_reported", subjectType: "signal", subjectId: report.id, summary: `${report.category} (${report.severity}) in ${report.countyFips}` });
          return report;
        },
        coordinatorVerifyCluster: (clusterId) => {
          appendAudit({ action: "signal_confidence_updated", subjectType: "signal", subjectId: clusterId, summary: "Coordinator-verified cluster" });
          // confidence is computed live; we mark via official corroboration toggle for UI
          // (simple impl — coordinator verify auto-toggles official corroboration on)
          const parts = clusterId.replace("cluster-", "").split("::");
          if (parts.length === 2) {
            const key = `${parts[0]}::${parts[1]}`;
            if (!get().officialCorroboratedKeys.includes(key)) {
              set({ officialCorroboratedKeys: [...get().officialCorroboratedKeys, key] });
            }
          }
        },
        officialCorroboratedKeys: ["19007::flood"],
        toggleOfficialCorroboration: (countyFips, category, on) => {
          const key = `${countyFips}::${category}`;
          const cur = get().officialCorroboratedKeys;
          set({
            officialCorroboratedKeys: on
              ? Array.from(new Set([...cur, key]))
              : cur.filter((k) => k !== key),
          });
        },

        // incidents + mission orders
        incidents: seedIncidents(),
        openIncident: (i) => {
          const inc: Incident = {
            ...i,
            id: `inc-${Date.now()}`,
            status: "open",
            openedAt: now(),
            missionOrderIds: [],
            requestIds: [],
          };
          set({ incidents: [inc, ...get().incidents] });
          appendAudit({ action: "incident_opened", subjectType: "incident", subjectId: inc.id, summary: inc.title });
          return inc;
        },
        closeIncident: (id, note) => {
          set({
            incidents: get().incidents.map((i) =>
              i.id === id ? { ...i, status: "closed", closedAt: now() } : i,
            ),
          });
          appendAudit({ action: "request_closed", subjectType: "incident", subjectId: id, summary: note ?? "Incident closed" });
        },
        missionOrders: seedMissionOrders(),
        issueMissionOrder: (m) => {
          const mo: MissionOrder = {
            ...m,
            id: `mo-${Date.now()}`,
            issuedAt: now(),
            status: "issued",
          };
          set({
            missionOrders: [mo, ...get().missionOrders],
            incidents: get().incidents.map((i) =>
              i.id === m.incidentId ? { ...i, missionOrderIds: [...i.missionOrderIds, mo.id] } : i,
            ),
          });
          appendAudit({ action: "mission_order_issued", subjectType: "mission_order", subjectId: mo.id, summary: mo.title, metadata: { bypass: m.bypassNormalRouting } });
          if (m.bypassNormalRouting) {
            appendAudit({ action: "gov_override", subjectType: "mission_order", subjectId: mo.id, summary: "Government bypass of normal routing", metadata: { incidentId: m.incidentId } });
          }
          return mo;
        },
        updateMissionOrderStatus: (id, status) => {
          set({
            missionOrders: get().missionOrders.map((m) =>
              m.id === id ? { ...m, status } : m,
            ),
          });
        },

        // prices, triggers, scenarios
        priceReports: seedPrices,
        addPriceReport: (p) => {
          const pr: PriceReport = { ...p, id: `pr-${Date.now()}`, createdAt: now() };
          set({ priceReports: [pr, ...get().priceReports] });
          return pr;
        },
        triggers: seedTriggers,
        scenarios: [],
        addScenario: (s) => {
          const sr: ScenarioRun = { ...s, id: `sc-${Date.now()}`, createdAt: now() };
          set({ scenarios: [sr, ...get().scenarios] });
          appendAudit({ action: "scenario_run", subjectType: "system", subjectId: sr.id, summary: `Scenario: ${s.scenario}` });
          return sr;
        },

        // audit + source health
        auditLog: [],
        appendAudit,
        sourceHealth: seedSourceHealth,
      };
    },
    { name: "foodready-store-v2" },
  ),
);

// ---------- Derived helpers ----------
export function getCountyByFips(fips: string) {
  return ALL_COUNTIES.find((c) => c.fips === fips);
}

/** Returns seeded counties for a state, or generates synthetic baseline counties so no state is blank. */
export function getCountiesForState(abbr: string) {
  if (abbr === "IA") return IOWA_COUNTIES;
  const seeded = SAMPLE_COUNTIES.filter((c) => c.stateAbbr === abbr);
  if (seeded.length > 0) return seeded;
  return syntheticCountiesForState(abbr).map((c) => ({
    ...c,
    seedRich: false,
    components: { shockExposure: 0, vulnerability: 0, supplyCapacity: 0, responseReadiness: 0 },
  })) as any;
}

export function countyScore(fips: string, weights = COMPONENT_WEIGHTS) {
  const c = getCountyByFips(fips);
  if (!c) {
    // fall back to baseline detail (works for synthetic counties)
    const stateAbbr = US_STATES.find((s) => fips.startsWith(s.fips))?.abbr ?? "";
    if (!stateAbbr) return null;
    const detail = getCountyFPIDetail(fips, stateAbbr);
    return { total: detail.total, level: detail.trigger, components: detail.components };
  }
  if ((c as any).components) {
    const total = computeTotalScore((c as any).components, weights);
    return { total, level: triggerForScore(total), components: (c as any).components };
  }
  const detail = getCountyFPIDetail(fips, c.stateAbbr);
  return { total: detail.total, level: detail.trigger, components: detail.components };
}

export function countyFPI(fips: string) {
  const c = getCountyByFips(fips);
  const stateAbbr = c?.stateAbbr ?? US_STATES.find((s) => fips.startsWith(s.fips))?.abbr ?? "";
  // apply community adjustment from clustered signals
  const clusters = getClustersForCounty(fips);
  const adj = clusters.reduce((a, c) => a + c.fpiAdjustment, 0);
  return getCountyFPIDetail(fips, stateAbbr, Math.min(5, adj));
}

export function stateAverageScore(abbr: string, weights = COMPONENT_WEIGHTS): number | null {
  const counties = getCountiesForState(abbr);
  if (!counties.length) return null;
  const sum = counties.reduce((acc, c: any) => {
    const score = c.components ? computeTotalScore(c.components, weights) : countyScore(c.fips, weights)?.total ?? 0;
    return acc + score;
  }, 0);
  return Math.round((sum / counties.length) * 10) / 10;
}

export function stateFPI(abbr: string) {
  const counties = getCountiesForState(abbr);
  const countyFPIs = counties.map((c: any) => {
    const sc = countyScore(c.fips);
    return {
      fips: c.fips,
      total: sc?.total ?? 0,
      trigger: sc?.level ?? "prepared",
      population: c.population ?? 50000,
    };
  });
  const store = useAppStore.getState();
  const openIncidents = store.incidents.filter((i) => i.stateAbbr === abbr && i.status !== "closed").length;
  const recentSignals = store.signalReports.filter(
    (s) => s.stateAbbr === abbr && new Date(s.createdAt).getTime() > Date.now() - 24 * 3_600_000,
  ).length;
  // return getStateFPIDetail(abbr, countyFPIs, { openIncidents, communitySignals24h: recentSignals });
  return getStateFPIDetail(abbr);
}

export function generateTrend(fips: string, days = 14): { date: string; score: number }[] {
  const cs = countyScore(fips);
  if (!cs) return [];
  const seed = parseInt(fips.slice(-3), 10);
  const out: { date: string; score: number }[] = [];
  for (let i = days - 1; i >= 0; i--) {
    const noise = Math.sin((seed + i) * 0.7) * 6 + Math.cos((seed + i) * 0.3) * 3;
    const drift = (days - i) * 0.4;
    const score = Math.max(0, Math.min(100, Math.round(cs.total - drift + noise)));
    out.push({ date: formatISO(subDays(new Date(), i), { representation: "date" }), score });
  }
  return out;
}

export function generateNationalTrend(days = 30): { date: string; score: number; alerts: number }[] {
  const out: { date: string; score: number; alerts: number }[] = [];
  for (let i = days - 1; i >= 0; i--) {
    const wobble = Math.sin(i * 0.4) * 4;
    out.push({
      date: formatISO(subDays(new Date(), i), { representation: "date" }),
      score: Math.round(48 + wobble + (i < 7 ? 3 : 0)),
      alerts: Math.round(12 + Math.abs(Math.sin(i * 0.6)) * 8),
    });
  }
  return out;
}

// ---------- Confidence cluster helpers ----------
export function getAllClusters(): IncidentSignalCluster[] {
  const store = useAppStore.getState();
  return clusterReports(store.signalReports, new Set(store.officialCorroboratedKeys));
}

export function getClustersForCounty(fips: string): IncidentSignalCluster[] {
  return getAllClusters().filter((c) => c.countyFips === fips);
}

// ---------- Recommendation engine (rules-based, horizon-tagged) ----------
export function recommendationsForCounty(fips: string, weights = COMPONENT_WEIGHTS): Recommendation[] {
  const detail = countyFPI(fips);
  const recs: Recommendation[] = [];
  const base = (
    text: string,
    reason: string,
    urgency: any,
    horizon: RecHorizon,
    timeline: string,
    confidence: any,
    signalsUsed: string[],
    staleDataFlag = false,
  ): Recommendation => ({
    id: `rec-${fips}-${recs.length}`,
    countyFips: fips,
    text,
    reason,
    urgency,
    horizon,
    timeline,
    confidence,
    signalsUsed,
    staleDataFlag,
    createdAt: now(),
  });

  const c = detail.components;
  const stale = detail.coverage === "baseline" || detail.coverage === "delayed";

  // Immediate (24-72h)
  if (detail.trigger === "critical" || detail.trigger === "action") {
    recs.push(base("Activate voucher/cash workflow if local markets functional.", "Composite FPI in Action/Critical band.", detail.trigger, "immediate", "within 24h", "high", ["composite_score"], stale));
  }
  if (c.shockExposure >= 60) {
    recs.push(base("Pre-position shelf-stable food in affected ZIPs.", "Elevated shock exposure (alerts/FEMA/drought).", "warning", "immediate", "within 48h", stale ? "low" : "medium", ["shock_exposure"], stale));
  }
  if (c.responseReadiness >= 60) {
    recs.push(base("Escalate to state coordination — local readiness limited.", "High readiness risk (stock/voucher shortfalls).", "action", "immediate", "within 24h", "high", ["response_readiness"], stale));
  }

  // Short-term (7-30d)
  if (c.vulnerability >= 60) {
    recs.push(base("Prioritize cash/voucher support over physical distribution where markets function.", "High vulnerability (poverty, food insecurity).", "warning", "short_term", "within 7-14 days", "medium", ["vulnerability"], stale));
  }
  if (c.supplyCapacity >= 60) {
    recs.push(base("Recruit additional pantry partners; expand mobile distribution routes.", "Limited pantry/retailer density.", "warning", "short_term", "within 14-30 days", "medium", ["supply_capacity"], stale));
  }

  // Structural
  if (c.vulnerability >= 50 || c.supplyCapacity >= 50) {
    recs.push(base("Improve permanent food access infrastructure (transit, retail, cold storage).", "Persistent structural risk in vulnerability/supply.", "watch", "structural", "6-24 months", "low", ["vulnerability", "supply_capacity"], stale));
  }

  if (recs.length === 0) {
    recs.push(base("Continue routine daily monitoring.", "All component scores below action thresholds.", "prepared", "immediate", "ongoing", "high", ["composite_score"], stale));
  }
  return recs;
}
