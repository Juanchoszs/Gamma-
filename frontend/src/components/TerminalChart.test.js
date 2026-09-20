import { describe, expect, it } from "vitest";
import { cleanPrices } from "./TerminalChart";

describe("cleanPrices", () => {
  it("keeps the latest real OHLC row for a duplicate timestamp", () => {
    const rows = [
      { timestamp: "2026-09-19T10:00:00Z", open: 100, high: 102, low: 99, close: 101 },
      { timestamp: "2026-09-19T10:00:00Z", open: 101, high: 103, low: 100, close: 102 },
      { timestamp: "2026-09-19T10:05:00Z", open: 102, high: 104, low: 101, close: 103 },
    ];

    expect(cleanPrices(rows)).toEqual([
      { time: 1789812000, open: 101, high: 103, low: 100, close: 102 },
      { time: 1789812300, open: 102, high: 104, low: 101, close: 103 },
    ]);
  });
});
