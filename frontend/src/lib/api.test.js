import { describe, expect, it } from "vitest";
import { apiPath, bucketParam, normalizeOverlay } from "./api";

describe("terminal API contracts", () => {
  it("builds encoded deep API paths", () => {
    expect(apiPath("SPX RT", "/market/state", { bucket: "Tout", empty: "" })).toBe("/api/v1/SPX%20RT/market/state?bucket=Tout");
  });

  it("maps UI expiration values to the Python contract", () => {
    expect(bucketParam("ALL")).toBe("Tout");
    expect(bucketParam("WEEKLY")).toBe("Semaine");
    expect(bucketParam("MONTHLY")).toBe("Mois");
    expect(bucketParam("0DTE")).toBe("0DTE");
  });

  it("normalizes missing overlay collections without fabricating values", () => {
    const result = normalizeOverlay({ current_price: null, gex_levels: undefined, flow_bubbles: null });
    expect(result.currentPrice).toBeNull();
    expect(result.levels).toEqual([]);
    expect(result.bubbles).toEqual([]);
    expect(result.priceSeries).toEqual([]);
  });
});

