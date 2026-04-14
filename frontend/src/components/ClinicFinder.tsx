"use client";

import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useFacilities } from "@/hooks/useApi";
import { cacheFacilities, getAllFacilities } from "@/lib/offlineDb";
import { MapPinIcon, PhoneIcon } from "./Icons";

interface ClinicFinderProps {
  onClose: () => void;
}

interface Facility {
  name: string;
  level: string;
  district: string;
  latitude?: number;
  longitude?: number;
  phone?: string;
  services?: string[];
  distance_km?: number;
  _distance?: number;
}

const DISTRICTS = [
  "Kampala", "Wakiso", "Mukono", "Jinja", "Mbarara",
  "Gulu", "Lira", "Mbale", "Fort Portal", "Masaka",
  "Soroti", "Hoima", "Arua", "Kabale", "Moroto",
];

function haversineKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 6371;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

export default memo(function ClinicFinder({ onClose }: ClinicFinderProps) {
  const [district, setDistrict] = useState<string>("");
  const [userLat, setUserLat] = useState<number | null>(null);
  const [userLon, setUserLon] = useState<number | null>(null);
  const [geoStatus, setGeoStatus] = useState<"idle" | "loading" | "granted" | "denied">("idle");
  const [selectedFacility, setSelectedFacility] = useState<Facility | null>(null);
  const mapRef = useRef<HTMLIFrameElement>(null);

  // Fetch from API with GPS params
  const apiParams = userLat != null && userLon != null
    ? `?lat=${userLat}&lon=${userLon}&radius_km=50&limit=20${district ? `&district=${encodeURIComponent(district)}` : ""}`
    : district ? `?district=${encodeURIComponent(district)}` : "";

  const { data: rawFacilities, isLoading } = useFacilities(
    // Pass district for non-geo filtering, or pass nothing to get all
    district || undefined
  );

  // Request geolocation
  const requestLocation = useCallback(() => {
    if (!("geolocation" in navigator)) {
      setGeoStatus("denied");
      return;
    }
    setGeoStatus("loading");
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setUserLat(pos.coords.latitude);
        setUserLon(pos.coords.longitude);
        setGeoStatus("granted");
      },
      () => setGeoStatus("denied"),
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 300000 }
    );
  }, []);

  // Auto-request on mount
  useEffect(() => {
    requestLocation();
  }, [requestLocation]);

  // Cache facilities offline when loaded
  useEffect(() => {
    if (rawFacilities && rawFacilities.length > 0) {
      cacheFacilities(rawFacilities).catch(() => {});
    }
  }, [rawFacilities]);

  // Compute distances client-side and sort — memoized to avoid recalc on every render
  const facilities = useMemo(() => {
    const list: Facility[] = (rawFacilities || []).map((f: Facility) => {
      if (userLat != null && userLon != null && f.latitude && f.longitude) {
        return { ...f, _distance: f.distance_km ?? haversineKm(userLat, userLon, f.latitude, f.longitude) };
      }
      return f;
    });
    if (userLat != null) {
      list.sort((a, b) => (a._distance ?? 999) - (b._distance ?? 999));
    }
    return list;
  }, [rawFacilities, userLat, userLon]);

  // Map center
  const mapLat = selectedFacility?.latitude ?? userLat ?? 0.3476;
  const mapLon = selectedFacility?.longitude ?? userLon ?? 32.5825;
  const mapZoom = selectedFacility ? 15 : userLat ? 12 : 7;

  // Build OpenStreetMap embed URL with marker
  const mapUrl = selectedFacility?.latitude
    ? `https://www.openstreetmap.org/export/embed.html?bbox=${mapLon - 0.01},${mapLat - 0.01},${mapLon + 0.01},${mapLat + 0.01}&layer=mapnik&marker=${mapLat},${mapLon}`
    : `https://www.openstreetmap.org/export/embed.html?bbox=${mapLon - 0.15},${mapLat - 0.1},${mapLon + 0.15},${mapLat + 0.1}&layer=mapnik${userLat ? `&marker=${userLat},${userLon}` : ""}`;

  return (
    <div className="panel clinic-finder" role="dialog" aria-label="Find nearest clinic">
      <div className="panel-header">
        <h2>
          <MapPinIcon width={18} height={18} />
          Nearest Health Facilities
        </h2>
        <button className="panel-close" onClick={onClose} aria-label="Close">
          &times;
        </button>
      </div>

      <div className="panel-body">
        {/* Embedded map */}
        <div className="map-container">
          <iframe
            ref={mapRef}
            className="map-embed"
            src={mapUrl}
            title="Health facility map"
            loading="lazy"
            allowFullScreen
          />
          {selectedFacility && (
            <div className="map-overlay">
              <strong>{selectedFacility.name}</strong>
              <span>{selectedFacility.level}</span>
            </div>
          )}
        </div>

        {/* Geolocation status */}
        {geoStatus === "loading" && (
          <p className="geo-status">Detecting your location...</p>
        )}
        {geoStatus === "granted" && (
          <p className="geo-status geo-success">
            Location found — showing nearest facilities first
          </p>
        )}
        {geoStatus === "denied" && (
          <p className="geo-status geo-denied">
            Location unavailable —{" "}
            <button className="geo-retry" onClick={requestLocation}>
              try again
            </button>
          </p>
        )}

        <label htmlFor="district-select" className="field-label">
          Filter by district:
        </label>
        <select
          id="district-select"
          className="select-input"
          value={district}
          onChange={(e) => setDistrict(e.target.value)}
        >
          <option value="">All districts</option>
          {DISTRICTS.map((d) => (
            <option key={d} value={d}>{d}</option>
          ))}
        </select>

        {isLoading && <p className="panel-loading">Loading facilities...</p>}

        <ul className="facility-list">
          {facilities.map((f, i) => (
            <li
              key={i}
              className={`facility-card ${selectedFacility?.name === f.name ? "selected" : ""}`}
              onClick={() => setSelectedFacility(f)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), setSelectedFacility(f))}
            >
              <div className="facility-header">
                <strong>{f.name}</strong>
                <span className="facility-level">{f.level}</span>
              </div>
              <div className="facility-meta">
                <span className="facility-district">{f.district}</span>
                {(f._distance ?? f.distance_km) != null && (
                  <span className="facility-distance">
                    {(f._distance ?? f.distance_km)! < 1
                      ? `${Math.round((f._distance ?? f.distance_km)! * 1000)} m`
                      : `${(f._distance ?? f.distance_km)!.toFixed(1)} km`}
                  </span>
                )}
              </div>
              {f.services && f.services.length > 0 && (
                <div className="facility-services">
                  {f.services.slice(0, 4).map((s, j) => (
                    <span key={j} className="service-tag">{s}</span>
                  ))}
                </div>
              )}
              <div className="facility-actions">
                {f.phone && (
                  <a
                    href={`tel:${f.phone}`}
                    className="facility-phone"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <PhoneIcon width={14} height={14} />
                    Call
                  </a>
                )}
                {f.latitude && f.longitude && (
                  <a
                    href={`https://www.google.com/maps/dir/?api=1&destination=${f.latitude},${f.longitude}${userLat ? `&origin=${userLat},${userLon}` : ""}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="facility-directions"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <MapPinIcon width={14} height={14} />
                    Directions
                  </a>
                )}
              </div>
            </li>
          ))}
          {facilities.length === 0 && !isLoading && (
            <li className="facility-empty">No facilities found. Try a different district.</li>
          )}
        </ul>
      </div>
    </div>
  );
});
