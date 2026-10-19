import { useRef, useState } from "react";
import { LocateFixed, Search } from "lucide-react";
import Page from "../components/Page";
import StoreResults from "../components/stores/StoreResults";
import { ErrorState, LoadingState } from "../components/ui/States";
import { findNearbyStores, findPlace } from "../api/prescriptionApi";
import { getErrorMessage } from "../api/getErrorMessage";
import { SCOPE_OPTIONS, geolocationMessage, roundCoordinate, storeDomId } from "../utils/stores";

const RADII = [2, 5, 10, 25];

/**
 * Medical stores and Jan Aushadhi Kendras near me. An independent, location-only page: it knows nothing about medicines, stock or prices.
 * The browser's location is requested ONLY when the person presses the button; they can instead type an area or PIN code. Nothing is
 * shown that the listing source does not say.
 */
export default function StoreFinder() {
  const [place, setPlace] = useState(null);                       // { lat, lon, label }, already rounded
  const [locating, setLocating] = useState(false);
  const [locationError, setLocationError] = useState("");
  const [typed, setTyped] = useState("");
  const [choices, setChoices] = useState({ status: "idle" });
  const [radius, setRadius] = useState(5);
  const [scope, setScope] = useState("all");
  const [state, setState] = useState({ status: "idle" });
  const [selectedRef, setSelectedRef] = useState(null);
  const latest = useRef(0);                                       // only the newest search may update the screen

  // One search, started by something the person did (choosing a place, or changing the distance or the filter).
  function search(nextPlace, nextRadius, nextScope) {
    const mine = ++latest.current;
    setState({ status: "loading" });
    setSelectedRef(null);
    findNearbyStores({ lat: nextPlace.lat, lon: nextPlace.lon, radiusKm: nextRadius, scope: nextScope })
      .then((res) => { if (mine === latest.current) setState({ status: "ready", result: res.data }); })
      .catch((err) => { if (mine === latest.current) setState({ status: "error", message: getErrorMessage(err) }); });
  }

  function choosePlace(next) {
    setLocationError("");
    setPlace(next);
    search(next, radius, scope);
  }

  function changeRadius(value) {
    setRadius(value);
    if (place) search(place, value, scope);
  }

  function changeScope(value) {
    setScope(value);
    if (place) search(place, radius, value);
  }

  function useMyLocation() {
    setLocationError("");
    if (!("geolocation" in navigator)) { setLocationError("This browser cannot share a location. Type your area or PIN code below."); return; }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLocating(false);
        choosePlace({ lat: roundCoordinate(pos.coords.latitude), lon: roundCoordinate(pos.coords.longitude), label: "Your current location" });
      },
      (err) => { setLocating(false); setLocationError(geolocationMessage(err)); },
      { enableHighAccuracy: false, timeout: 15000, maximumAge: 300000 },
    );
  }

  async function submitPlace(event) {
    event.preventDefault();
    const text = typed.trim();
    if (text.length < 3) { setChoices({ status: "error", message: "Type at least 3 characters: an area, a town or a PIN code." }); return; }
    setChoices({ status: "loading" });
    try {
      const res = await findPlace(text);
      setChoices({ status: "ready", places: res.data.places, attribution: res.data.attribution });
    } catch (err) {
      setChoices({ status: "error", message: getErrorMessage(err) });
    }
  }

  function select(ref) {
    setSelectedRef(ref);
    document.getElementById(storeDomId(ref))?.scrollIntoView?.({ block: "nearest", behavior: "smooth" });
  }

  return (
    <Page
      crumbs={[{ label: "Dashboard", to: "/dashboard" }, { label: "Stores" }]}
      eyebrow="Near you"
      title="Find medical stores near me"
      subtitle="Medical stores and Jan Aushadhi Kendras around you, with distance, directions and contact details where they are listed."
    >
      <section className="panel rise d1" style={{ display: "grid", gap: "var(--s-4)" }}>
        <div className="row" style={{ flexWrap: "wrap", gap: "var(--s-3)" }}>
          <button type="button" className="btn btn-primary" onClick={useMyLocation} disabled={locating}>
            <LocateFixed size={16} /> {locating ? "Waiting for your browser…" : "Use my current location"}
          </button>
          <span className="tiny subtle">Your browser will ask first. Your position is rounded to about 100 m, used only for this search, and not stored.</span>
        </div>
        {locationError && <div className="alert alert-warn" role="alert"><div>{locationError}</div></div>}

        <form onSubmit={submitPlace} className="store-place-form">
          <div className="field" style={{ marginBottom: 0, flex: 1 }}>
            <label htmlFor="store-place">Or type an area, town or PIN code</label>
            <input id="store-place" type="search" value={typed} onChange={(e) => setTyped(e.target.value)} placeholder="e.g. Connaught Place or 110001" autoComplete="off" />
          </div>
          <button type="submit" className="btn btn-ghost" disabled={choices.status === "loading"}><Search size={15} /> Find place</button>
        </form>
        {choices.status === "error" && <p className="field-error" role="alert">{choices.message}</p>}
        {choices.status === "ready" && (
          choices.places.length === 0 ? <p className="small muted">No place matched that. Try the town name or a PIN code.</p> : (
            <div>
              <p className="small" style={{ margin: "0 0 var(--s-2)" }}>Which one do you mean?</p>
              <ul className="store-options is-static">
                {choices.places.map((p) => (
                  <li key={`${p.lat},${p.lon},${p.label}`}>
                    <button type="button" onClick={() => { choosePlace({ lat: p.lat, lon: p.lon, label: p.label }); setChoices({ status: "idle" }); }}>{p.label}</button>
                  </li>
                ))}
              </ul>
              <p className="tiny subtle">{choices.attribution}</p>
            </div>
          )
        )}

        <div className="store-filters">
          <div className="field" style={{ marginBottom: 0 }}>
            <label htmlFor="store-radius">Distance</label>
            <select id="store-radius" value={radius} onChange={(e) => changeRadius(Number(e.target.value))}>
              {RADII.map((r) => <option key={r} value={r}>Within {r} km</option>)}
            </select>
          </div>
          <div className="field" style={{ marginBottom: 0 }}>
            <label htmlFor="store-scope">Show</label>
            <select id="store-scope" value={scope} onChange={(e) => changeScope(e.target.value)}>
              {SCOPE_OPTIONS.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
            </select>
          </div>
        </div>
      </section>

      {state.status === "loading" && <section className="panel" style={{ marginTop: "var(--s-5)" }}><LoadingState title="Looking for stores" message="Asking OpenStreetMap for stores near this place." /></section>}
      {state.status === "error" && <section className="panel" style={{ marginTop: "var(--s-5)" }}><ErrorState message={state.message} /></section>}
      {state.status === "ready" && (
        <section className="panel rise" style={{ marginTop: "var(--s-5)" }}>
          {place && <p className="small muted" style={{ marginTop: 0 }}>Around: {place.label}</p>}
          <StoreResults result={state.result} selectedRef={selectedRef} onSelect={select} />
        </section>
      )}
    </Page>
  );
}
