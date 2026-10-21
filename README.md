# ApplyFlow v5 — postulaciones ChileTrabajos en 2 comandos

Sistema liviano que busca ofertas, las puntúa, filtra las publicadas en los últimos
14 días, abre las mejores y **rellena** los formularios con tu perfil. **Nunca envía**:
tú revisas y haces clic en Enviar.

> 📖 **Guía completa de uso con `/ir30` y todos los comandos**: [GUIA-DE-USO.md](GUIA-DE-USO.md)

## Requisitos

- Windows + Google Chrome
- Python 3.9 o superior en el PATH
- La extensión `extension_v2` cargada una vez en Chrome

## Instalación (una sola vez)

1. Ejecuta `1-preparar-sesion.bat` (o `.\1-preparar-sesion.ps1`).
2. En `chrome://extensions` activa **Modo de desarrollador** → **Cargar descomprimida** → elige la carpeta `extension_v2`.
3. Inicia sesión en ChileTrabajos. Cuando veas tu nombre, la sesión está lista.

> Cada vez que se actualicen archivos de la extensión, pulsa el botón de recarga (↻)
> en `chrome://extensions`.

## Uso diario

```powershell
# 1) Solo si la sesión expiró
.\1-preparar-sesion.ps1

# 2) Todo el flujo: buscar → rankear → abrir → rellenar
.\2-arrancar-postulaciones.ps1
```

El comando 2 pide el nombre del perfil (Enter = `Jorge`) y arranca. Además, si el
receiver v5 (127.0.0.1:8766) no está corriendo, **lo levanta solo** en background.
Al terminar deja las pestañas abiertas y rellenadas. Revisa cada una, ajusta la
renta si quieres, adjunta el CV y envía manualmente.

## Opciones útiles

```powershell
.\2-arrancar-postulaciones.ps1 -DryRun              # solo genera plan/cartas/sueldos, no abre pestañas
.\2-arrancar-postulaciones.ps1 -Objetivo 100 -Dias 14
.\2-arrancar-postulaciones.ps1 -NoBuscar            # usa el histórico, no consulta portales
.\2-arrancar-postulaciones.ps1 -Rapido              # 4 keywords por cluster (más rápido)
.\2-arrancar-postulaciones.ps1 -Refill              # incluye ofertas ya rellenadas antes
.\2-arrancar-postulaciones.ps1 -MinScore 60
```

## Sueldo (dato sensible)

- Si defines `OPENAI_API_KEY`, `OPENROUTER_API_KEY` o `LLM_API_KEY` + `LLM_BASE_URL`,
  el sistema hace **una llamada en lote** al LLM y propone una renta por oferta.
- Sin API key usa una tabla de mercado Chile 2026 por cluster/ciudad.
- El valor queda en el formulario para que lo revises antes de enviar.

## Qué hace exactamente

1. Lee `perfiles/<nombre>/profile.json` y el CV PDF de esa carpeta.
2. Ejecuta `apply_copilot/job_hunter.py` con 5 clusters ampliados:
   gestión de proyectos, ITO/calidad, mecánica/mantenimiento, piping/montaje y agua/riles.
3. Filtra ofertas de los últimos 14 días, elimina ya rellenadas y ordena por **fecha**
   y luego por **score**.
4. Genera carta personalizada por oferta (título del cargo) y sueldo estimado.
5. Abre las pestañas en lotes de 10. La extensión detecta cada formulario y lo rellena
   automáticamente al cargar.
6. Cierra las expiradas, cuenta los rellenos y se detiene al llegar al objetivo (100).
7. Deja el detalle en `apply_copilot/data/last_run.json` y actualiza el dashboard.

## Estructura

```
1-preparar-sesion.ps1 / .bat
2-arrancar-postulaciones.ps1 / .bat
orquestador.py
extension_v2/                 # extensión Chrome (autofill)
perfiles/Jorge/               # profile.json + CV
apply_copilot/
  job_hunter.py               # búsqueda, scoring, dashboard
  config/settings.json
  data/
    jobs_database.json        # histórico de ofertas
    site_answers.json         # respuestas base
    offer_answers.json        # carta + sueldo por oferta (generado)
    apply_plan.json           # plan de la corrida (generado)
    salaries.json             # detalle de sueldos (generado)
    last_run.json             # resultado de la última corrida
  tools/
    receiver.py               # API local v5 (127.0.0.1:8766) — /api/fill-registry incl.
    selfcheck.py              # 10 validaciones (~9s)
    acceptance.py             # gate 1-comando: selfcheck + autotest + humos de search/rank
    btw.py                    # tick/repair/history/similar del loop /btw
    match_engine.py           # ranking v2 → data/apply_queue.json (+dedupe reposts)
    search_offers.py          # búsqueda por sinónimos + --similar <id> + --duplicados
    corpus_common.py          # loaders compartidos (corpus y jobs_database)
    eval_ranker.py            # comparación v2 vs legacy (precision@10)
    market_analysis.py        # informe de mercado y expansión de clusters
    apply_state.py            # puente /progress (sync/summary/mark)
    salary.py                 # sueldos (tabla Chile 2026; --autotest)
    profile_wizard.py         # modo entrenamiento breve
```

## Seguridad

- El receiver escucha solo en `127.0.0.1`.
- `auto_submit` está en `false`; no hay ningún clic en Enviar/Postular.
- RUT, LinkedIn y datos bancarios quedan fuera del autofill.

## Operar con agentes (OpenCode)

También puedes operar por comandos conversacionales (definidos en `.opencode/`):

| Comando | Qué hace |
|---|---|
| `/search <texto>` | Busca ofertas por sinónimos (`tools/search_offers.py`). |
| `/rank` | Recalcula el orden v2 (`tools/match_engine.py rank` → `data/apply_queue.json`). |
| `/next <n>` | Prepara el siguiente lote de postulaciones. |
| `/audit` | Audita pestañas abiertas (carta, sueldo estimado, cero submit). |
| `/mark <ids>` | Registra postulaciones que TÚ enviaste (`apply_copilot.py mark`). |
| `/progress` | Avance por estado (`tools/apply_state.py sync|summary`). |
| `/eval` | Compara ranking v2 vs legacy (`tools/eval_ranker.py`). |
| `/market` | Informe de mercado y expansión (`tools/market_analysis.py`). |
| `/check` | Self-check de 10 validaciones en ~9s (`tools/selfcheck.py`). |
| `/ir30 <n>` | **Un solo comando**: sesión ChileTrabajos + top N ofertas rellenadas + reporte con tiempos. |
| `/btw <n>` | Mantenimiento autónomo: N ticks de selfcheck + 1 mejora del backlog por tick + compresión de sesión. |

Estados del pipeline: RANKED → QUEUED → OPENED → FILLED → READY → APPLIED (o EXPIRED).
Ningún comando envía postulaciones.
