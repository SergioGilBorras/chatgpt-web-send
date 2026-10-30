# Cambios / Changelog

## 0.1.3 — 2026-10-30

- Se habilita el sandbox de Chromium/Chrome/Edge explícitamente (`chromium_sandbox=True`) para que Playwright no inicie Edge con `--no-sandbox` de forma predeterminada.
- Pruebas automáticas de configuración en Chromium y Edge, y smoke test Windows de Edge real con comprobación de la línea de comandos.
- **No** se oculta la automatización ni se cambian User-Agent, perfiles o medidas de acceso. El cambio no pretende resolver CAPTCHAs.

## 0.1.2 — 2026-10-30

- `chatgpt-web-send open`: abre ChatGPT directamente en el **navegador personal predeterminado**, usando la sesión habitual y sin control automatizado (envío manual).
- `chatgpt-web-send doctor --browser-channel msedge|chrome`: diagnóstico verificable del navegador real, User-Agent, perfil y descargas.
- Automatización con ventana de tamaño **nativo** (`no_viewport=True`) en lugar de viewport fijo 1280 × 900.
- Descargas habilitadas; los archivos aceptados se guardan permanentemente en `~/Downloads` o `--downloads-dir`, con nombres seguros que no sobrescriben archivos existentes.
- Protección del directorio personal de perfiles predeterminados Chrome/Edge para evitar corrupción o bloqueos.
- Pruebas de apertura manual sin Playwright, guardado de descargas, selección de navegador, diagnóstico y protección de perfiles.
- **No incluye bypass de CAPTCHA, User-Agent falsificado ni camuflaje de Playwright.**

## 0.1.1

- Selección de Edge/Chrome reales y perfiles separados.
- Diagnóstico de verificación humana, sin reintentos automáticos.

## 0.1.0

- Primer envío a conversaciones existentes y perfil Chromium persistente.
