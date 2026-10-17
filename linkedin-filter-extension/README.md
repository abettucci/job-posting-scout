# Scout Lens — extensión local para LinkedIn Jobs

Extensión **personal y local** que agrega filtros sobre una búsqueda abierta de LinkedIn Jobs. No se conecta a Job Scout, no usa CV, no inicia sesión en ningún backend y no envía datos fuera del navegador.

> Advertencia: LinkedIn prohíbe en sus términos los plugins que scrapean/copien datos y los overlays que modifiquen la apariencia del sitio. Esta carpeta está pensada únicamente para experimentación local; no la publiques en Chrome Web Store ni la uses para eludir controles de LinkedIn. Si LinkedIn muestra un checkpoint o verificación, Scout Lens se pausa y no intenta evitarlo.

## Instalar localmente

1. Abrí `chrome://extensions`.
2. Activá **Developer mode**.
3. Elegí **Load unpacked** y seleccioná esta carpeta `linkedin-filter-extension`.
4. Abrí una búsqueda en `linkedin.com/jobs/search`.

El panel aparece arriba a la derecha. Desde allí se configuran años máximos, seniorities, tecnologías incluidas/excluidas y tamaño de empresa. También muestra, en modo solo lectura, las keywords y ubicación que ya aplicaste en LinkedIn.

## Cómo opera

- Observa tarjetas que LinkedIn ya cargó durante el scroll.
- Abre detalles de jobs y páginas `About` de empresas en pestañas inactivas, de a una, para calcular campos locales.
- Mantiene solo metadata normalizada en `chrome.storage.local` por 30 días; no guarda descripciones completas.
- Conserva visible cualquier oferta cuyo año, tecnología o tamaño no se pueda determinar.
- Limita cada ventana de 10 minutos a 12 detalles de jobs y 8 páginas de empresa. Si llega al límite, las ofertas restantes quedan visibles como desconocidas.

## Desarrollo y pruebas

No requiere dependencias ni build. Para probar las reglas de extracción:

```bash
node --test tests/rules.test.js
```

Tras modificar archivos de la extensión, usá el botón **Reload** de `chrome://extensions` y recargá la pestaña de LinkedIn.
