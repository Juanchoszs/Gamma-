const SPANISH_REPLACEMENTS = [
  ["No market-map rows are available.", "No hay filas disponibles para el mapa de mercado."],
  ["No unified levels are available.", "No hay niveles unificados disponibles."],
  ["No saved level history for this session.", "No hay historico de niveles guardado para esta sesion."],
  ["Net Gamma Exposure", "Exposicion gamma neta"],
  ["Deterministic strength", "Fuerza deterministica"],
  ["Liquidity & Absorption", "Liquidez y absorcion"],
  ["Delta & Absorption", "Delta y absorcion"],
  ["Volume Profile", "Perfil de volumen"],
  ["Gamma exposure", "Exposicion gamma"],
  ["exposure by strike", "exposicion por strike"],
  ["Unified levels", "Niveles unificados"],
  ["unified levels", "niveles unificados"],
  ["Level history", "Historico de niveles"],
  ["Call GEX", "GEX Call"],
  ["Put GEX", "GEX Put"],
  ["Call Wall", "Muro Call"],
  ["Put Support", "Soporte Put"],
  ["CALL WALL", "MURO CALL"],
  ["PUT WALL", "MURO PUT"],
  ["GEX WALL", "MURO GEX"],
  ["HIGH GAMMA", "GAMMA ALTA"],
  ["LOW GAMMA", "GAMMA BAJA"],
  ["VOLUME NODE", "NODO DE VOLUMEN"],
  ["OI NODE", "NODO DE OI"],
  ["Ask / Venta", "Oferta / Venta"],
  ["Bid / Compra", "Demanda / Compra"],
  ["Net Open Interest", "Interes abierto neto"],
  ["Open Interest", "Interes abierto"],
  ["Open_interest", "interes abierto"],
  ["Put / Call Ratio", "Ratio Put/Call"],
  ["Bullish", "Alcista"],
  ["Bearish", "Bajista"],
  ["Expiry", "Vencimiento"],
  ["Strength", "Fuerza"],
  ["Distance", "Distancia"],
  ["Source", "Fuente"],
  ["Session", "Sesion"],
  ["Status", "Estado"],
  ["Volume", "Volumen"],
  ["Price", "Precio"],
  ["Time", "Hora"],
];

function translateText(value, language) {
  if (language !== "es" || typeof value !== "string") return value;
  return SPANISH_REPLACEMENTS.reduce((text, [source, translated]) => text.replaceAll(source, translated), value);
}

function translateTitle(title, language) {
  if (typeof title === "string") return translateText(title, language);
  if (!title || typeof title !== "object") return title;
  return { ...title, text: translateText(title.text, language) };
}

function translateAxis(axis, language) {
  if (!axis || typeof axis !== "object") return axis;
  return { ...axis, title: translateTitle(axis.title, language) };
}

function translateTrace(trace, language) {
  const text = Array.isArray(trace.text)
    ? trace.text.map((item) => translateText(item, language))
    : translateText(trace.text, language);
  return {
    ...trace,
    name: translateText(trace.name, language),
    hovertemplate: translateText(trace.hovertemplate, language),
    text,
    texttemplate: translateText(trace.texttemplate, language),
  };
}

export function localizePlotlyFigure(figure, language = "en") {
  if (!figure || language !== "es") return figure;
  const layout = { ...(figure.layout || {}) };
  Object.keys(layout).forEach((key) => {
    if (/^(xaxis|yaxis)\d*$/.test(key)) layout[key] = translateAxis(layout[key], language);
  });
  Object.keys(layout).forEach((key) => {
    if (/^coloraxis\d*$/.test(key) && layout[key]?.colorbar) {
      layout[key] = { ...layout[key], colorbar: { ...layout[key].colorbar, title: translateTitle(layout[key].colorbar.title, language) } };
    }
  });
  layout.title = translateTitle(layout.title, language);
  layout.annotations = (layout.annotations || []).map((annotation) => ({ ...annotation, text: translateText(annotation.text, language) }));
  return { ...figure, data: (figure.data || []).map((trace) => translateTrace(trace, language)), layout };
}
