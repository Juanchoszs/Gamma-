import { describe, expect, it } from "vitest";
import { localizePlotlyFigure } from "./plotlyI18n";

describe("localizePlotlyFigure", () => {
  const figure = {
    data: [{ name: "Call GEX", hovertemplate: "Price: %{y}<br>Volume: %{x}", text: ["CALL WALL", "PUT WALL"] }],
    layout: {
      title: { text: "SPY exposure by strike" },
      xaxis: { title: "Gamma exposure" },
      yaxis: { title: { text: "Price" } },
      annotations: [{ text: "CALL WALL 80/100" }],
    },
  };

  it("keeps English figures unchanged", () => {
    expect(localizePlotlyFigure(figure, "en")).toBe(figure);
  });

  it("localizes presentation strings without changing values", () => {
    const localized = localizePlotlyFigure(figure, "es");
    expect(localized.layout.title.text).toBe("SPY exposicion por strike");
    expect(localized.layout.xaxis.title).toBe("Exposicion gamma");
    expect(localized.layout.yaxis.title.text).toBe("Precio");
    expect(localized.layout.annotations[0].text).toBe("MURO CALL 80/100");
    expect(localized.data[0].name).toBe("GEX Call");
    expect(localized.data[0].hovertemplate).toContain("Precio");
    expect(localized.data[0].text).toEqual(["MURO CALL", "MURO PUT"]);
  });
});
