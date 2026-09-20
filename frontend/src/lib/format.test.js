import { describe, expect, it } from "vitest";
import { displayLabel, formatMoney, formatPercent, formatPrice, translateLabel } from "./format";

describe("terminal formatters", () => {
  it("formats financial magnitudes without throwing on missing values", () => {
    expect(formatMoney(1_250_000)).toBe("$1.25M");
    expect(formatMoney(null)).toBe("--");
    expect(formatPrice(761.69)).toBe("761.69");
  });

  it("keeps signed percentage context visible", () => {
    expect(formatPercent(0.17)).toBe("+0.17%");
    expect(formatPercent(-1.2)).toBe("-1.20%");
  });

  it("turns engine enum labels into readable UI text", () => {
    expect(displayLabel("NEGATIVE_GAMMA")).toBe("NEGATIVE GAMMA");
    expect(displayLabel(null)).toBe("--");
    expect(translateLabel("CALL_WALL", (key, fallback) => key === "value.callWall" ? "MURO CALL" : fallback)).toBe("MURO CALL");
  });
});
