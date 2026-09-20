# Job Scout — sistema visual de descubrimiento

Referencia: la página pública de vacantes de Startups Argentina, inspeccionada como flujo y contenido. La adaptación conserva la jerarquía (navegación contenida, pregunta principal, compositor conversacional, ejemplos y oportunidades recientes), sin copiar logo, textos de marca ni assets ajenos.

## Fundamentos

- **Tono:** editorial, cálido y práctico. El producto se siente como una mesa de búsqueda personal, no como un dashboard corporativo.
- **Paleta:** fondo hueso `#f7f5ef`, superficies `#fffdf8`, tinta verde-negra `#16221d`, líneas `#d8d4c7` y un acento coral `#e85d36` para la acción principal.
- **Tipografía:** `Avenir Next`/`Helvetica Neue` para lectura; titulares muy pesados, apretados y de dos líneas cuando el ancho lo permite.
- **Escala:** 4, 8, 12, 16, 24, 32, 48 y 72 px. El ancho de lectura del hero está limitado para que la pregunta sea la protagonista.

## Componentes

- **Navegación:** barra fina, sticky y translúcida; enlaces discretos y estado activo con contraste pleno.
- **Compositor:** superficie elevada con borde suave, textarea sin borde interior y pie que separa la pista de teclado de la CTA coral.
- **Sugerencias:** cápsulas de texto compactas, sin iconos decorativos; hover con un cambio de superficie nítido.
- **Tarjetas:** borde de 1 px, radio de 16 px, metadatos compactos y elevación mínima al hover. Las empresas se representan con datos propios del posting, no logos de terceros.

## Layout y responsive

- Contenedor máximo 1152 px con 16 px laterales en móvil y 24 px desde tablet.
- Desktop (≥1024): hero en dos columnas; ejemplos y resultados debajo.
- Tablet (768–1023): hero y compositor se apilan con aire de 24 px.
- Mobile (<640): título a 38–44 px, CTA de ancho completo y filtros detrás de una acción explícita.
- Movimiento: 180–240 ms, sólo para foco, hover y aparición; se elimina con `prefers-reduced-motion`.
