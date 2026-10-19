import { useEffect, useMemo, useRef, useState } from "react";
import { MAP_ATTRIBUTION, buildMapView, markerKind } from "../../utils/stores";

const HEIGHT = 360;

/**
 * A map of the stores and the person's (rounded) position on OpenStreetMap tiles. It is a visual aid only: every fact is also in the
 * list, so a blocked or offline tile server leaves a usable page. Markers are numbered like the list and can be pressed to select a store.
 */
export default function StoreMap({ center, stores, selectedRef, onSelect, width: fixedWidth }) {
  const box = useRef(null);
  const [measured, setMeasured] = useState(fixedWidth || 640);

  useEffect(() => {
    if (fixedWidth || !box.current) return undefined;
    const node = box.current;
    const read = () => setMeasured(Math.max(280, Math.round(node.clientWidth)));
    read();
    if (typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver(read);
    observer.observe(node);
    return () => observer.disconnect();
  }, [fixedWidth]);

  const view = useMemo(() => {
    const points = [{ kind: "you", lat: center.lat, lon: center.lon }, ...stores.map((s, i) => ({ kind: "store", lat: s.lat, lon: s.lon, ref: s.store_id, name: s.name, number: i + 1, category: s.category }))];
    return buildMapView(points, measured, HEIGHT);
  }, [center, stores, measured]);

  return (
    <div className="store-map" ref={box} style={{ height: HEIGHT }} role="group" aria-label="Map of the stores listed below">
      {view.tiles.map((t) => <img key={t.key} className="store-map-tile" src={t.url} alt="" style={{ left: t.left, top: t.top }} draggable="false" loading="lazy" />)}
      {view.positions.map((p) => p.kind === "you" ? (
        <span key="you" className="store-pin is-you" style={{ left: p.x, top: p.y }} title="Your position (rounded to about 100 m)"><span className="sr-only">Your position</span></span>
      ) : (
        <button
          key={p.ref} type="button" className={`store-pin ${markerKind(p.category).className} ${selectedRef === p.ref ? "is-selected" : ""}`} style={{ left: p.x, top: p.y }}
          data-category={p.category} onClick={() => onSelect?.(p.ref)} aria-label={`Show ${p.name} (${markerKind(p.category).label}), number ${p.number} in the list`}
          aria-pressed={selectedRef === p.ref}
        >{p.number}</button>
      ))}
      <span className="store-map-attribution">{MAP_ATTRIBUTION}</span>
    </div>
  );
}
