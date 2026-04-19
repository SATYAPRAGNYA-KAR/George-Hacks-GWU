import { useNavigate } from "react-router-dom";
import { MapContainer, TileLayer, CircleMarker, Tooltip } from "react-leaflet";
import { US_STATES, STATE_CENTROIDS } from "@/data/states";
import { stateAverageScore } from "@/store/appStore";
import { colorForScore, triggerForScore, TRIGGER_META } from "@/lib/risk";
import type { StateFPISummary } from "@/lib/api";

interface USMapProps {
  height?: number;
  /** Live FPI data from backend — keyed by state_abbr */
  liveFPIMap?: Record<string, StateFPISummary>;
}

const WEATHER_STATUS_LABELS: Record<string, string> = {
  clear: "No active weather disruptions",
  impaired: "⚠ Weather disruptions active",
  blocked: "🚨 Severe weather disruptions",
};

export const USMap = ({ height = 480, liveFPIMap = {} }: USMapProps) => {
  const navigate = useNavigate();

  return (
    <div className="overflow-hidden rounded-xl border bg-card shadow-smooth">
      <MapContainer
        center={[39.5, -98.35]}
        zoom={4}
        scrollWheelZoom={false}
        style={{ height, width: "100%" }}
        attributionControl={false}
      >
        <TileLayer url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png" />
        {US_STATES.map((s) => {
          const center = STATE_CENTROIDS[s.abbr];
          if (!center) return null;

          const live = liveFPIMap[s.abbr];
          const baselineAvg = stateAverageScore(s.abbr);

          // Prefer live backend score; fall back to baseline; then use 30 as neutral
          const score  = live?.risk_score ?? baselineAvg ?? 30;
          const isLive = !!live;
          const trigger = live?.trigger ?? triggerForScore(score ?? 30);
          const color  = colorForScore(score ?? 30);
          const radius = Math.max(7, Math.min(22, 7 + (score ?? 30) / 6));

          return (
            <CircleMarker
              key={s.abbr}
              center={center}
              radius={radius}
              pathOptions={{
                color,
                fillColor: color,
                fillOpacity: isLive ? 0.65 : 0.25,
                weight: isLive ? 2 : 1,
              }}
              eventHandlers={{ click: () => navigate(`/state/${s.abbr}`) }}
            >
              <Tooltip direction="top">
                <div className="text-xs min-w-[160px]">
                  <div className="font-semibold">{s.name}</div>
                  <div className="flex items-center gap-1 mt-0.5">
                    <span>Risk: <strong>{Math.round(score ?? 30)}</strong></span>
                    <span>·</span>
                    <span>{TRIGGER_META[trigger as keyof typeof TRIGGER_META]?.label ?? trigger}</span>
                    {isLive && (
                      <span className="ml-1 rounded-full bg-emerald-100 px-1.5 text-[9px] text-emerald-700">Live</span>
                    )}
                  </div>
                  {live?.dominant_driver && (
                    <div className="text-muted-foreground capitalize mt-0.5">
                      Driver: {live.dominant_driver.replace(/_/g, " ")}
                    </div>
                  )}
                  {live?.weather_status && (
                    <div className="mt-0.5 text-muted-foreground">
                      {WEATHER_STATUS_LABELS[live.weather_status] ?? live.weather_status}
                    </div>
                  )}
                  {!isLive && (
                    <div className="text-muted-foreground mt-0.5">Baseline estimate · click to analyze</div>
                  )}
                  <div className="mt-1 text-muted-foreground text-[10px]">Click to drill into counties →</div>
                </div>
              </Tooltip>
            </CircleMarker>
          );
        })}
      </MapContainer>
    </div>
  );
};