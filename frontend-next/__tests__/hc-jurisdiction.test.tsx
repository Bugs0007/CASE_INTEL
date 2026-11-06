import { fireEvent, render, screen } from "@testing-library/react";
import india from "@svg-maps/india";
import { describe, expect, it, vi } from "vitest";
import { IndiaMap } from "@/components/advocate-search/india-map";
import { COURT_OF_LOCATION, JURISDICTION, LOCATION_NAMES, SMALL_LOCATIONS, coverageOf } from "@/lib/hc-jurisdiction";
import type { HighCourtInfo } from "@/types";

// The twenty-five High Courts of the library registry (GET /api/cases/high-courts/).
// core/tests/test_hc_jurisdiction.py checks this list against the registry itself.
const REGISTRY = [
  "allahabad", "andhra", "bombay", "calcutta", "chhattisgarh", "delhi", "gauhati", "gujarat", "himachal", "jammu",
  "jharkhand", "karnataka", "kerala", "madras", "manipur", "meghalaya", "mp", "orissa", "patna", "punjab", "rajasthan",
  "sikkim", "telangana", "tripura", "uttarakhand",
];

const courts: HighCourtInfo[] = REGISTRY.map((code) => ({
  code,
  name: `${code[0].toUpperCase()}${code.slice(1)} High Court`,
  state_code: "0",
  registry_benches: [],
  supported: code !== "calcutta",
  support_note: code === "calcutta" ? "Not through this court library." : "",
}));

describe("jurisdiction table", () => {
  it("covers every High Court in the registry, once", () => {
    expect(Object.keys(JURISDICTION).sort()).toEqual([...REGISTRY].sort());
  });

  it("gives every location on the map to exactly one High Court", () => {
    const owners: Record<string, string[]> = {};
    for (const [court, ids] of Object.entries(JURISDICTION)) for (const id of ids) (owners[id] ??= []).push(court);
    for (const loc of india.locations) expect(owners[loc.id], `${loc.id} ${loc.name}`).toHaveLength(1);
    expect(Object.keys(owners).sort()).toEqual(india.locations.map((l) => l.id).sort()); // and names no location the map lacks
    expect(india.locations).toHaveLength(36);
  });

  it("names the locations as the map does", () => {
    for (const loc of india.locations) expect(LOCATION_NAMES[loc.id]).toBe(loc.name);
  });

  it("follows the arrangement the courts themselves have", () => {
    expect([...JURISDICTION.bombay].sort()).toEqual(["dd", "dn", "ga", "mh"]);
    expect([...JURISDICTION.gauhati].sort()).toEqual(["ar", "as", "mz", "nl"]);
    expect([...JURISDICTION.punjab].sort()).toEqual(["ch", "hr", "pb"]);
    expect(COURT_OF_LOCATION.ld).toBe("kerala");
    expect(COURT_OF_LOCATION.py).toBe("madras");
    expect(COURT_OF_LOCATION.an).toBe("calcutta");
    expect(COURT_OF_LOCATION.jk).toBe("jammu"); // Ladakh is not drawn separately
  });

  it("says which states a multi-state court covers", () => {
    expect(coverageOf("bombay")).toBe("Maharashtra, Goa, Dadra and Nagar Haveli and Daman and Diu");
    expect(coverageOf("telangana")).toBe("");
  });

  it("offers a button for every small state or territory", () => {
    for (const s of SMALL_LOCATIONS) for (const id of s.ids) expect(COURT_OF_LOCATION[id]).toBeTruthy();
  });
});

describe("IndiaMap", () => {
  it("draws every location, credits the map and says what it is for", () => {
    const { container } = render(<IndiaMap courts={courts} selected={null} onSelect={() => {}} />);
    expect(container.querySelectorAll("path[data-location]")).toHaveLength(36);
    expect(screen.getByText(/@svg-maps\/india, CC BY 4.0/)).toBeInTheDocument();
    expect(screen.getByText(/for choosing a court only/)).toBeInTheDocument();
  });

  it("selects a court from any of its states", () => {
    const onSelect = vi.fn();
    const { container } = render(<IndiaMap courts={courts} selected={null} onSelect={onSelect} />);
    for (const id of ["mh", "ga", "dn", "dd"]) fireEvent.click(container.querySelector(`path[data-location="${id}"]`)!);
    expect(onSelect.mock.calls.map((c) => c[0])).toEqual(["bombay", "bombay", "bombay", "bombay"]);
  });

  it("does not select a court that cannot be searched", () => {
    const onSelect = vi.fn();
    const { container } = render(<IndiaMap courts={courts} selected={null} onSelect={onSelect} />);
    const wb = container.querySelector('path[data-location="wb"]')!;
    expect(wb).toHaveAttribute("aria-disabled", "true");
    expect(wb).toHaveAttribute("tabindex", "-1");
    fireEvent.click(wb);
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("is a keyboard path: every usable state is a named stop that Enter and Space choose", () => {
    const onSelect = vi.fn();
    const { container } = render(<IndiaMap courts={courts} selected={null} onSelect={onSelect} />);
    const dl = container.querySelector('path[data-location="dl"]')!;
    expect(dl).toHaveAttribute("tabindex", "0");
    expect(dl).toHaveAttribute("aria-label", "Delhi: Delhi High Court");
    fireEvent.keyDown(dl, { key: "Enter" });
    fireEvent.keyDown(dl, { key: " " });
    expect(onSelect.mock.calls.map((c) => c[0])).toEqual(["delhi", "delhi"]);
  });

  it("marks the chosen court on every state it serves and in the pin column", () => {
    const { container } = render(<IndiaMap courts={courts} selected="bombay" onSelect={() => {}} />);
    for (const id of ["mh", "ga", "dn", "dd"]) expect(container.querySelector(`path[data-location="${id}"]`)).toHaveAttribute("aria-pressed", "true");
    expect(container.querySelector('path[data-location="kl"]')).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("button", { name: "Goa" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Delhi" })).toHaveAttribute("aria-pressed", "false");
  });

  it("lets the pin column choose the small states", () => {
    const onSelect = vi.fn();
    render(<IndiaMap courts={courts} selected={null} onSelect={onSelect} />);
    fireEvent.click(screen.getByRole("button", { name: "Lakshadweep" }));
    fireEvent.click(screen.getByRole("button", { name: "D&NH · Daman & Diu" }));
    expect(onSelect.mock.calls.map((c) => c[0])).toEqual(["kerala", "bombay"]);
  });
});
