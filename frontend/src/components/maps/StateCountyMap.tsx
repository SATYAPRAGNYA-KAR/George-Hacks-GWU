import { MapContainer, TileLayer, CircleMarker, Tooltip } from "react-leaflet";
import { STATE_CENTROIDS } from "@/data/states";
import { getCountiesForState, countyScore } from "@/store/appStore";
import { colorForScore, TRIGGER_META, triggerForScore } from "@/lib/risk";

export const StateCountyMap = ({
  stateAbbr, selectedFips, onSelect, height = 460,
}: { stateAbbr: string; selectedFips?: string; onSelect?: (fips: string) => void; height?: number }) => {
  const counties = getCountiesForState(stateAbbr);
  const center = STATE_CENTROIDS[stateAbbr] ?? [39.5, -98.35];
  // const zoom = stateAbbr === "IA" ? 7 : 6;
  const STATE_ZOOM: Record<string, number> = {
    AK: 4, HI: 6, TX: 5, CA: 5, MT: 5, NM: 5, AZ: 5, NV: 5, CO: 5, OR: 5, WY: 5, ID: 5,
    WA: 6, UT: 6, KS: 6, NE: 6, SD: 6, ND: 6, OK: 6, MO: 6, IA: 7, MN: 6, WI: 6,
    LA: 6, MS: 6, AL: 6, GA: 6, FL: 6, NC: 6, TN: 6, KY: 6, VA: 6, AR: 6, IL: 6,
    IN: 7, OH: 7, MI: 6, PA: 7, NY: 6, WV: 7, SC: 7,
    ME: 6, VT: 7, NH: 7, MA: 7, CT: 8, RI: 8, DE: 8, NJ: 7, MD: 7, DC: 10,
  };
  const zoom = STATE_ZOOM[stateAbbr] ?? 6;

  return (
    <div className="overflow-hidden rounded-xl border bg-card shadow-smooth">
      <MapContainer center={center} zoom={zoom} scrollWheelZoom={false} style={{ height, width: "100%" }} attributionControl={false}>
        <TileLayer url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png" />
        {counties.map((c) => {
          const cs = countyScore(c.fips);
          if (!cs) return null;
          const color = colorForScore(cs.total);
          const isSel = selectedFips === c.fips;
          return (
            <CircleMarker
              key={c.fips}
              center={(c as any).centroid}
              radius={isSel ? 16 : Math.max(7, Math.min(18, 7 + cs.total / 8))}
              pathOptions={{
                color,
                fillColor: color,
                fillOpacity: isSel ? 0.85 : 0.55,
                weight: isSel ? 3 : 2,
              }}
              eventHandlers={{ click: () => onSelect?.(c.fips) }}
            >
              <Tooltip direction="top">
                <div className="text-xs">
                  <div className="font-semibold">{c.name} County</div>
                  <div>Risk: <strong>{cs.total}</strong> · {TRIGGER_META[triggerForScore(cs.total)].label}</div>
                  <div className="text-muted-foreground">Pop. {c.population.toLocaleString()}</div>
                </div>
              </Tooltip>
            </CircleMarker>
          );
        })}
      </MapContainer>
    </div>
  );
};
