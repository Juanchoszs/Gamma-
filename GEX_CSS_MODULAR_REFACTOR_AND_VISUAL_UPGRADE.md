# GEX Dashboard — CSS Modular Refactor + Visual Upgrade

## OBJETIVO

Reconstruir la arquitectura CSS del GEX Dashboard y, en una segunda etapa independiente, llevar su sistema visual a un nivel profesional de terminal de inteligencia de mercado.

NO quiero otro dashboard genérico.
NO quiero SaaS.
NO quiero gaming.
NO quiero neon.
NO quiero glassmorphism.
NO quiero gradients decorativos.
NO quiero glow permanente.
NO quiero emojis.

La interfaz debe transmitir: precisión, densidad informativa, jerarquía, estabilidad, lectura rápida y calidad institucional.

La secuencia obligatoria es:

AUDIT → ARCHITECTURE → MODULARIZATION → NORMALIZATION → VISUAL UPGRADE → RESPONSIVE → ACCESSIBILITY → REGRESSION → FINAL AUDIT

---

## 1. DIAGNÓSTICO DEL CSS ACTUAL

El CSS actual tiene 1684 líneas y presenta deuda estructural clara:

- dos bloques `:root`;
- múltiples redefiniciones del mismo selector;
- reglas que funcionan como overrides acumulativos;
- mezcla de dos sistemas visuales;
- restos de la estética neon original;
- colores hardcodeados;
- múltiples sistemas de segmented controls;
- tablas con patrones duplicados;
- varios sistemas de modal;
- múltiples media queries similares;
- animaciones decorativas;
- `!important` utilizado para compensar especificidad;
- módulos añadidos incrementalmente sin una arquitectura única.

Por ejemplo, el archivo define un primer sistema de tokens y posteriormente vuelve a definir `:root` con otro sistema. fileciteturn10file0L17-L63

También existen redefiniciones de `.topbar`, `.workspace-hero`, `.toolbar`, `.cards`, `.stat`, `.row`, `.daybar`, `.hint` y `.tabbar`. fileciteturn10file0L65-L124

El problema NO debe solucionarse agregando otra capa de overrides.

Debe solucionarse reorganizando el sistema.

---

# 2. REGLA ABSOLUTA: PRESERVAR FUNCIONALIDAD

Antes de editar CSS, inspeccionar el repositorio completo.

Inventariar:

- className usados desde Python/Dash;
- IDs de componentes;
- IDs de callbacks;
- clases utilizadas por callbacks o JS;
- tablas;
- charts;
- dropdowns;
- tabs;
- modals;
- estados dinámicos;
- componentes Dash;
- clases que puedan actuar como contratos implícitos.

NO modificar:

- callbacks;
- callback IDs;
- IDs de componentes;
- cálculos;
- providers;
- CBOE ingestion;
- storage;
- scheduler;
- modelos;
- generación de figuras;
- lógica de negocio.

Si una modificación visual requiere tocar Python, clasificarla como HIGH RISK y detener esa modificación.

---

# 3. ETAPA 1 — REESTRUCTURACIÓN

La primera etapa NO busca hacer la interfaz más bonita.

Busca hacer que el CSS sea arquitectónicamente correcto.

Crear, si el mecanismo de carga de Dash lo permite:

```text
gex/assets/css/
├── 00-reset.css
├── 01-tokens.css
├── 02-base.css
├── 03-layout.css
├── 04-navigation.css
├── 05-controls.css
├── 06-components.css
├── 07-data-display.css
├── 08-analytics.css
├── 09-heatmap.css
├── 10-positioning.css
├── 11-modals.css
├── 12-states.css
├── 13-responsive.css
└── 99-utilities.css
```

Mantener `style.css` como entrypoint si la aplicación depende de él.

No mover archivos sin comprobar primero cómo Dash carga assets.

---

# 4. 00-reset.css

Responsabilidades:

- box-sizing;
- body;
- headings;
- buttons;
- inputs;
- tables;
- links;
- focus;
- selection.

No utilizar un reset agresivo que pueda romper Dash.

---

# 5. 01-tokens.css

Crear UNA sola fuente de verdad.

## Surfaces

```css
--color-bg
--color-surface-1
--color-surface-2
--color-surface-3
--color-surface-hover
--color-surface-active
```

## Typography

```css
--color-text-primary
--color-text-secondary
--color-text-muted
--color-text-disabled
```

## Borders

```css
--color-border
--color-border-subtle
--color-border-strong
--color-border-focus
```

## Semantic states

```css
--color-positive
--color-negative
--color-warning
--color-info
--color-success
```

## Market semantics

```css
--market-call
--market-put
--market-gex-positive
--market-gex-negative
--market-spot
--market-flip
--market-call-wall
--market-put-wall
--market-hvl
--market-volume
--market-open-interest
--market-iv
--market-delta
```

El color debe comunicar información. No decoración.

---

# 6. ELIMINAR LA ESTÉTICA NEON

La primera versión del CSS utiliza explícitamente cyan/magenta neon, glows y gradients. fileciteturn10file0L11-L39

Eliminar del chrome de la aplicación:

- `#00f0ff` como color dominante;
- magenta neon;
- text-shadow decorativo;
- glowing borders;
- box-shadow luminoso;
- gradients RGB;
- botones luminosos;
- superficies glassmorphic;
- blur utilizado sólo como decoración.

El diseño debe conseguir profundidad mediante:

- contraste;
- tipografía;
- spacing;
- borders;
- superficies;
- jerarquía.

NO mediante iluminación artificial.

---

# 7. SPACING SYSTEM

Crear escala:

```css
--space-1: 4px;
--space-2: 6px;
--space-3: 8px;
--space-4: 12px;
--space-5: 16px;
--space-6: 20px;
--space-7: 24px;
--space-8: 32px;
--space-9: 40px;
```

Evitar valores arbitrarios.

No introducir 11px, 13px, 17px, etc. salvo justificación real.

---

# 8. TYPOGRAPHY

Mantener:

- sans para UI;
- monospace para datos.

Crear:

```css
--font-ui
--font-data
```

Definir escala tipográfica.

Los números deben utilizar:

```css
font-variant-numeric: tabular-nums;
```

Los valores financieros deben ser fáciles de comparar visualmente.

---

# 9. RADII

Reducir la variedad.

```css
--radius-sm
--radius-md
--radius-lg
```

Evitar mezclar arbitrariamente 4/5/6/7/8/10/12/14/16px.

---

# 10. SHADOWS

Sólo:

```css
--shadow-sm
--shadow-md
--shadow-lg
```

Las sombras deben representar profundidad.

No iluminación.

---

# 11. 02-base.css

Centralizar:

- html;
- body;
- anchors;
- buttons;
- inputs;
- selection;
- disabled;
- focus-visible;
- typography base;
- numeric defaults.

El body actualmente aparece definido en más de un punto y debe quedar consolidado. fileciteturn10file0L64-L70 fileciteturn10file0L126-L135

---

# 12. 03-layout.css

Crear un sistema de layout único.

Debe cubrir:

- app shell;
- content container;
- page;
- rows;
- columns;
- sections;
- chart regions;
- spacing;
- max-width.

Modelo:

```text
Application
├── Header
│   ├── Brand
│   ├── Instrument
│   ├── Controls
│   └── Status
└── Main
    ├── Workspace Header
    ├── Navigation
    └── Page
        ├── Section
        ├── Data
        └── Charts
```

No resolver layout mediante margins arbitrarios.

---

# 13. 04-navigation.css

Refactorizar:

- `.topbar`;
- `.brand`;
- `.brand-mark`;
- `.brand-sub`;
- `.toolbar`;
- `.tabbar`;
- `.tab-item`;
- selected state;
- symbol selector.

El header debe ser compacto.

Jerarquía:

```text
identity → instrument → controls → status → navigation
```

No convertirlo en hero decorativo.

---

# 14. 05-controls.css

Crear primitives reutilizables para:

- segmented controls;
- checkbox;
- button;
- dropdown;
- input;
- selector.

Actualmente existen implementaciones similares para `.seg`, `.check`, `.symbol-seg`, `.pos-seg` y `.heat-seg`. fileciteturn10file0L305-L386 fileciteturn11file0L481-L514

Crear una base:

```text
control
├── default
├── compact
├── active
├── disabled
└── danger
```

Las variantes deben modificar sólo lo necesario.

---

# 15. ESTADOS DE CONTROLES

Todo elemento interactivo debe contemplar:

- default;
- hover;
- active;
- focus-visible;
- selected;
- disabled;
- loading;
- error.

No depender únicamente del color.

---

# 16. 06-components.css

Crear primitives:

- panel;
- stat;
- badge;
- chip;
- section header;
- divider;
- action;
- status;
- empty state.

El `.stat` actual combina background, border, shadow, hover y accent bar y debe convertirse en una primitive coherente. fileciteturn10file0L388-L438

Las stats NO deben parecer cards de SaaS.

---

# 17. 07-data-display.css

Crear lenguaje visual para:

- price;
- GEX;
- DEX;
- volume;
- OI;
- IV;
- delta;
- gamma;
- timestamps;
- status;
- metadata.

Los datos son protagonistas.

Orden de prioridad:

```text
DATA > CHART > CONTAINER > DECORATION
```

---

# 18. TABLAS

Unificar visualmente:

- Tape;
- Whale Tracker;
- GEX Levels.

Actualmente existen estructuras repetidas para headers, rows, numeric alignment y hover. fileciteturn10file0L795-L822 fileciteturn11file0L332-L454

Crear:

```text
.data-table
.data-table__header
.data-table__row
.data-table__cell
.data-table__numeric
.data-table__muted
```

Luego crear variantes semánticas.

Las tablas deben ser densas, legibles y técnicas.

No convertir cada fila en una card.

---

# 19. GEX LEVELS

Diferenciar claramente:

- Call;
- Put;
- strongest levels;
- Spot;
- Flip;
- HVL;
- Call Wall;
- Put Wall.

No depender únicamente del color.

Usar:

- posición;
- peso tipográfico;
- label;
- contraste;
- accent mínimo.

No inventar significado financiero mediante decoración.

---

# 20. P/C GAUGE

Debe ser una visualización informativa.

Eliminar glow.

Mantener separación clara entre:

```text
Call
Put
```

La información debe seguir siendo entendible sin color.

---

# 21. REGIME / MARKET STATE

El regime banner debe sentirse como estado del sistema.

No como marketing.

Usar:

- label;
- estado;
- explicación;
- disclaimer;
- accent lateral discreto.

Sin gradient.

Sin glow.

---

# 22. CHIPS

Los chips sólo deben utilizarse para unidades compactas de información.

Deben parecer elementos de terminal, no tags SaaS.

Mantener:

- monospace;
- densidad;
- metadata;
- alineación.

Eliminar decoración innecesaria.

---

# 23. REAL-TIME / DATA QUALITY

Unificar estados:

```text
LIVE
RECENT
STALE
MISSING
INVALID
DEGRADED
DISCONNECTED
```

No depender solamente de un punto de color.

Cada estado debe tener:

- texto;
- indicador;
- color semántico;
- tratamiento consistente.

Debe funcionar en:

- header;
- charts;
- tables;
- analytics;
- empty states.

---

# 24. EMPTY STATES

Nunca mostrar únicamente:

```text
No data
```

El estado debe explicar por qué.

Ejemplos:

```text
No intraday history available
Waiting for the first valid snapshot
Selected window contains no observations
```

Usar el idioma real de la aplicación.

NO usar emojis.

---

# 25. 08-analytics.css

Unificar:

- analytics;
- whale tracker;
- levels;
- volume;
- expiry.

El usuario debe sentir que todos pertenecen al mismo producto.

El CSS actual tiene reglas específicas y animaciones propias para analytics. fileciteturn11file0L304-L479

Eliminar diferencias arbitrarias.

---

# 26. 09-heatmap.css

El heatmap es analítico.

No decorativo.

Los controles deben ocupar poco espacio.

El gráfico debe dominar visualmente.

Eliminar:

- glow de selección;
- gradients decorativos;
- blur innecesario;
- sombras fuertes.

El color del heatmap pertenece al lenguaje de datos, no al chrome general.

---

# 27. 10-positioning.css

Unificar:

- selector;
- metric cards;
- controls;
- chart;
- panes.

Reutilizar primitives.

No duplicar componentes completos.

---

# 28. 11-modals.css

Actualmente existen familias independientes de modal para CFD, Tastytrade y native overlay. fileciteturn11file0L39-L302

Crear primitive:

```text
modal
├── backdrop
├── container
├── header
├── body
├── status
├── fields
└── actions
```

Las variantes deben ser semánticas.

No copiar todo el CSS tres veces.

---

# 29. LEGACY TASTYTRADE

Antes de conservar las reglas Tastytrade:

1. comprobar si siguen siendo usadas;
2. comprobar consumidores;
3. determinar si son legacy;
4. eliminar si están muertas;
5. si siguen activas, migrarlas al sistema nuevo.

No tocar lógica funcional.

---

# 30. EMOJIS — CERO TOLERANCIA

La UI final debe contener CERO emojis.

Buscar en:

- HTML;
- Python-generated text;
- labels;
- buttons;
- empty states;
- tooltips;
- banners;
- tables;
- titles;
- status;
- messages.

No sustituir un emoji por otro emoji.

Si el emoji cumple una función informativa:

- reemplazar por texto;
- CSS;
- iconografía funcional existente.

No añadir una librería de iconos sólo para decorar.

Realizar un check automático.

Resultado esperado:

```text
UI emoji count = 0
```

---

# 31. NO DISEÑO GENÉRICO DE IA

Está prohibido introducir:

- hero gigantes;
- cards enormes;
- gradients;
- glassmorphism;
- blobs;
- neon;
- glowing borders;
- pill badges excesivos;
- iconos gigantes;
- métricas gigantes;
- whitespace excesivo;
- copywriting de marketing;
- fondos abstractos.

El producto debe parecer una herramienta especializada para análisis de mercado.

---

# 32. DENSIDAD

Objetivo:

```text
high information density
+
strong hierarchy
+
low visual noise
```

No aumentar spacing para que "se vea moderno".

La modernización debe venir de:

- consistencia;
- precisión;
- alineación;
- contraste;
- jerarquía.

---

# 33. CHART CONTAINERS

Los gráficos son protagonistas.

Los containers deben ser casi invisibles cuando sea posible.

Evitar:

```text
card
  card
    chart
```

Preferir:

```text
section
  chart
```

con separación mínima y borde funcional.

No tocar cálculos de Plotly.

---

# 34. PLOTLY

Separar responsabilidades:

```text
CSS
→ application chrome

Plotly configuration
→ chart internals
```

No intentar controlar todos los elementos de Plotly mediante CSS.

Si existe un helper común para layouts de Plotly, conservarlo y reutilizar su lenguaje visual.

No modificar:

- fórmulas;
- series;
- datos;
- callbacks;
- cálculos.

---

# 35. RESPONSIVE

Consolidar breakpoints.

Validar:

```text
1440
1280
1024
768
480
```

Desktop es prioritario, pero mobile no puede romperse.

No crear media queries duplicadas.

---

# 36. ACCESSIBILITY

Implementar:

```css
:focus-visible
```

y:

```css
@media (prefers-reduced-motion: reduce) {
    /* disable non-essential motion */
}
```

No depender únicamente del color.

Mantener targets razonables.

Garantizar contraste suficiente.

---

# 37. ANIMATIONS

Las animaciones sólo se justifican si comunican:

- transición;
- cambio de estado;
- loading;
- feedback;
- apertura/cierre.

Eliminar animaciones decorativas permanentes.

El `.live-pulse` actual utiliza animación y text-shadow y debe evaluarse críticamente. fileciteturn10file0L247-L272

---

# 38. !IMPORTANT

No eliminar `!important` a ciegas.

Para cada uno:

1. determinar por qué existe;
2. comprobar especificidad Dash;
3. crear regla correcta;
4. eliminar override sólo cuando sea seguro.

Objetivo: reducir `!important`, no simplemente sustituirlo.

---

# 39. HARDCODED COLORS

Después de crear tokens, buscar:

```text
#...
rgb(...)
rgba(...)
hsl(...)
hsla(...)
```

Clasificar cada resultado:

```text
TOKEN
PLOTLY
SEMANTIC
OVERLAY
LEGACY
ACCIDENTAL
```

El chrome de UI no debe contener colores arbitrarios.

---

# 40. PROHIBICIÓN DE OVERRIDE PILE

Nunca hacer:

```css
.selector { ... }
.selector { ... }
.selector { ... }
```

para resolver un problema que debería solucionarse en arquitectura.

Si existe conflicto:

- corregir especificidad;
- corregir orden modular;
- consolidar;
- crear variante;
- eliminar regla vieja.

---

# 41. FASE 2 — VISUAL UPGRADE

Sólo comenzar cuando la Fase 1 esté terminada.

Dirección:

```text
Institutional Market Intelligence Terminal
```

Características:

- dark;
- restrained;
- technical;
- precise;
- dense;
- information-first;
- low-noise;
- high-legibility.

No buscar "wow" mediante efectos.

Buscar calidad mediante precisión.

---

# 42. JERARQUÍA FINAL

La interfaz debe comunicar:

```text
GLOBAL CONTEXT
↓
INSTRUMENT / SESSION
↓
MARKET STATE
↓
KEY LEVELS
↓
PRIMARY CHART
↓
SECONDARY ANALYTICS
↓
RAW / EXPLORATORY DATA
```

No todos los componentes tienen el mismo peso.

---

# 43. SUPERFICIES

Máximo tres niveles:

```text
background
surface
elevated / overlay
```

Evitar card nesting.

---

# 44. BORDERS

Los borders deben:

- separar;
- contener;
- indicar focus;
- indicar estado.

No decorar.

---

# 45. COLOR SEMÁNTICO

El color siempre debe tener significado.

Ejemplo:

```text
positive → positive market/system state
negative → negative market/system state
warning → caution/degraded
info → informational
```

Nunca:

```text
cyan = bonito
magenta = bonito
yellow = bonito
```

---

# 46. MICROINTERACCIONES

Sólo:

- hover;
- focus;
- active;
- selected;
- loading;
- update.

Transiciones rápidas y discretas.

---

# 47. VALIDACIÓN

Después de cada módulo:

1. levantar aplicación;
2. revisar consola;
3. revisar errores;
4. abrir cada tab;
5. cambiar instrumento;
6. probar dropdowns;
7. probar modals;
8. probar tablas;
9. probar charts;
10. probar responsive.

"Compila" NO significa "terminado".

---

# 48. REGRESSION CHECKLIST

Validar:

- Dashboard;
- Analytics;
- Heatmap;
- Positioning;
- Tape;
- Whale Tracker;
- GEX Levels;
- modals;
- dropdowns;
- segmented controls;
- checkboxes;
- buttons;
- symbol selector;
- empty states;
- status states;
- charts;
- responsive.

También validar los instrumentos realmente soportados por el backend.

---

# 49. AUTOMATED CSS AUDIT

Crear o ejecutar checks para:

- duplicate selectors;
- duplicate `:root`;
- hardcoded colors;
- obsolete selectors;
- emoji;
- excessive `!important`;
- duplicate media queries;
- unused animations;
- conflicting declarations.

Para emojis usar una detección Unicode equivalente a:

```text
[🌀-🫿]
```

Resultado obligatorio:

```text
0 emojis in UI
```

---

# 50. DEFINITION OF DONE

## Arquitectura

- [ ] CSS modularizado
- [ ] single source of truth para tokens
- [ ] duplicate `:root` eliminado
- [ ] duplicate selectors consolidados
- [ ] overrides innecesarios eliminados
- [ ] legacy CSS auditado
- [ ] módulos claramente separados

## Visual

- [ ] neon eliminado
- [ ] gradients decorativos eliminados
- [ ] glow decorativo eliminado
- [ ] glassmorphism eliminado
- [ ] spacing normalizado
- [ ] typography normalizada
- [ ] radius normalizado
- [ ] shadows normalizadas
- [ ] controls unificados
- [ ] tables unificadas
- [ ] modals unificados
- [ ] states unificados
- [ ] charts visualmente priorizados

## UI

- [ ] 0 emojis
- [ ] empty states profesionales
- [ ] LIVE/RECENT/STALE/MISSING/INVALID coherentes
- [ ] focus-visible
- [ ] reduced-motion
- [ ] responsive

## Seguridad funcional

- [ ] callbacks intactos
- [ ] callback IDs intactos
- [ ] component IDs intactos
- [ ] cálculos intactos
- [ ] providers intactos
- [ ] CBOE intacto
- [ ] storage intacto
- [ ] scheduler intacto
- [ ] Plotly data intacta

## Validación

- [ ] todas las tabs probadas
- [ ] todos los modals probados
- [ ] todos los controles probados
- [ ] symbol switching probado
- [ ] charts probados
- [ ] responsive probado
- [ ] final CSS audit ejecutado
- [ ] aplicación levantada sin errores

---

# 51. ORQUESTACIÓN PARA AGENTE / IDE

Antes de modificar:

1. leer este documento;
2. leer `AGENTS.md` si existe;
3. leer el master plan del proyecto;
4. revisar `gex/ui/app.py`;
5. revisar `gex/assets/style.css`;
6. revisar cualquier helper de Plotly;
7. identificar contratos.

Si existen agentes especializados:

```text
repo-auditor
architecture-reviewer
data-auditor
quant-guardian
```

usarlos para auditoría antes de modificar.

No utilizar `data-auditor` o `quant-guardian` para cambiar lógica financiera.

Su función aquí es detectar riesgos de regresión.

---

# 52. PROTOCOLO DE IMPLEMENTACIÓN

## Paso 1

Auditar.

No modificar.

Crear:

```text
CSS_AUDIT.md
```

## Paso 2

Diseñar arquitectura modular.

## Paso 3

Migrar reglas.

## Paso 4

Eliminar duplicados.

## Paso 5

Normalizar tokens.

## Paso 6

Validar que el producto sigue funcionando.

## Paso 7

Comenzar visual upgrade.

## Paso 8

Validar cada módulo.

## Paso 9

Auditoría final.

---

# 53. INSTRUCCIÓN FINAL

No trates este documento como una colección de sugerencias estéticas.

Trátalo como una migración arquitectónica del sistema visual.

Primero:

```text
UNDERSTAND
```

Después:

```text
AUDIT
```

Después:

```text
CLASSIFY
```

Después:

```text
MODULARIZE
```

Después:

```text
NORMALIZE
```

Después:

```text
REDESIGN
```

Después:

```text
VALIDATE
```

Nunca mezclar las dos etapas sin control.

Si encuentras una modificación que pueda afectar lógica, datos, callbacks, IDs, providers o cálculos:

```text
STOP
CLASSIFY AS HIGH RISK
DO NOT CHANGE
```

El resultado final no debe ser simplemente un CSS más bonito.

Debe ser un sistema visual profesional, coherente, mantenible y preparado para evolucionar junto al GEX Dashboard.
