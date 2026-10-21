# 📖 Guía de uso — ApplyFlow v5

Sistema que busca ofertas en ChileTrabajos, las puntúa, abre las mejores en Chrome y
**rellena los formularios con tu perfil**. Regla de oro: **NUNCA envía nada** — tú
revisas cada formulario, ajustas la renta si quieres, adjuntas el CV y haces clic en
**Enviar** tú mismo.

Esta guía explica el flujo diario con `/ir30` y documenta **todos los comandos**.
Para el resumen técnico de arquitectura, ve al [README](README.md).

---

## 1. Instalación (una sola vez)

Requisitos: **Windows + Google Chrome + Python 3.9+** en el PATH.

1. **Crea tu perfil** desde la plantilla:
   ```powershell
   Copy-Item apply_copilot\config\profile.example.json perfiles\<TuNombre>\profile.json
   ```
   Edítalo con tus datos (nombre, contacto, skills, logros). Pon también tu CV en PDF
   en esa misma carpeta: `perfiles\<TuNombre>\CV2026_<tu-nombre>.pdf`
   ⚠️ `profile.json` contiene tu contacto y RUT → está en `.gitignore`, **nunca se sube**.

2. **Prepara la sesión de ChileTrabajos**:
   ```powershell
   .\1-preparar-sesion.bat
   ```
   Se abre Chrome en la página de login. Ingresa con tu cuenta. Cuando veas tu nombre,
   la sesión está lista (queda viva mientras no cierres esa ventana de Chrome).

3. **Carga la extensión** en Chrome:
   - Ve a `chrome://extensions`
   - Activa **Modo de desarrollador** (esquina superior derecha)
   - **Cargar descomprimida** → elige la carpeta `extension_v2` del repo

4. **Verifica que todo esté sano**:
   ```powershell
   python apply_copilot\tools\selfcheck.py --silencioso
   ```
   Debe responder `10/10 ok`.

> 🔁 Si más adelante actualizo archivos de la extensión (o clonas cambios), pulsa ↻
> en `chrome://extensions` para recargarla.

---

## 2. El flujo diario: `/ir30 <n>`

`/ir30` es el **comando único**: hace todo el ciclo y te entrega el reporte.
(El `30` es el objetivo de rellenados; si no pasas número, usa 30.)

Se usa **dentro de OpenCode** (la terminal conversacional con agentes). Simplemente escribe:

```
/ir30 30
```

y el agente (rol `apply-orchestrator`) ejecuta esta secuencia **sin preguntarte nada**:

| Paso | Qué hace | Detalle |
|---|---|---|
| 1. Quick check | `selfcheck.py --silencioso` (~9s) | Si algo falla, se detiene y te lo muestra |
| 2. Sesión | Si la corrida anterior terminó con `EXIT 3` (sesión expirada), abre `1-preparar-sesion.ps1` | Ingresa a ChileTrabajos y el flujo sigue solo |
| 3. Ciclo completo | `2-arrancar-postulaciones.ps1 -Objetivo <n> -MinScore 65` | Buscar → rankear → abrir pestañas → rellenar (1–5 min) |
| 4. Reporte | Lee `data/last_run.json` | Rellenadas, sin reporte, expiradas, tiempos, mediana de sueldos |

**Qué verás en Chrome**: pestañas nuevas con los formularios de postulación **ya
rellenados** (carta generada + renta estimada + respuestas de tu perfil).

**Qué haces tú** (el único paso manual, por diseño):
1. Revisa cada pestaña a tu ritmo.
2. Ajusta la renta si lo estimado no te convence.
3. Adjunta el CV si el formulario no lo trajo.
4. **Envía** con el botón de ChileTrabajos.
5. (Opcional) `/mark <ids>` para registrar las que enviaste, o botón del popup
   **"Cerrar pestañas ya rellenadas"** para cerrar de una las ya revisadas.

---

## 3. Flujo sin OpenCode (solo Windows)

Si no quieres usar la terminal conversacional, el equivalente directo es:

```powershell
.\2-arrancar-postulaciones.bat
```

Ese script hace lo mismo que el paso 3 de `/ir30` (y además levanta el receiver solo).
Pide el nombre del perfil y arranca. Al terminar: revisa las pestañas y envía.

---

## 4. Guía de comandos

### 4.1 Comandos de Windows (raíz del repo)

| Comando | Qué hace |
|---|---|
| `1-preparar-sesion.bat` | Abre Chrome en el login de ChileTrabajos (`chtlogin`) y espera tu ingreso. |
| `2-arrancar-postulaciones.bat` | Ciclo completo: buscar → rankear → abrir → rellenar. Detiene al llegar al objetivo. |

**Parámetros de `2-arrancar-postulaciones.ps1`:**

| Parámetro | Default | Qué hace |
|---|---|---|
| `-Perfil <nombre>` | `Jorge` | Carpeta de `perfiles/` a usar. |
| `-Objetivo <n>` | `100` | Cuántas ofertas rellenar en esta corrida. |
| `-Dias <n>` | `14` | Solo ofertas publicadas en los últimos N días. |
| `-MinScore <n>` | `70` | Puntaje mínimo para abrir la oferta. |
| `-DryRun` | — | Genera plan/carta/sueldos **sin abrir ninguna pestaña** (prueba segura). |
| `-NoBuscar` | — | Salta la búsqueda en portales; usa el histórico local (más rápido). |
| `-Refill` | — | Incluye ofertas ya rellenadas antes (re-rellena desde respuestas locales). |
| `-Rapido` | — | 4 keywords por cluster en vez de 5 (búsqueda más rápida). |
| `-SinLLM` | — | Fuerza sueldos por tabla local aunque haya API key. |
| `-Entrenar` | — | Crea/completa el perfil paso a paso (wizard). |
| `-AbrirDashboard` | — | Abre el dashboard al terminar. |

### 4.2 Comandos conversacionales (OpenCode, definidos en `.opencode/commands/`)

| Comando | Qué hace |
|---|---|
| `/ir30 <n>` | **El de uso diario**: sesión + top N rellenadas + reporte con tiempos. |
| `/search <texto>` | Busca ofertas por sinónimos. Acepta `--similar <offer_id>` para ver parecidas a una dada. |
| `/rank` | Recalcula el ranking v2 y la cola (`data/apply_queue.json`). |
| `/next <n>` | Prepara el siguiente lote de postulaciones. |
| `/mark <ids>` | Registra las que TÚ enviaste manualmente. |
| `/progress` | Avance por estado: RANKED/QUEUED/OPENED/FILLED/READY/APPLIED. |
| `/check` | Self-check de 10 validaciones (~9s). |
| `/eval` | Comparación ranking v2 vs legacy (precision@10). |
| `/market` | Informe de mercado por cluster y expansión de búsqueda. |
| `/audit` | Audita las pestañas abiertas (carta, sueldo, cero submit). |
| `/btw <n>` | Mantenimiento autónomo: N ticks de selfcheck + mejoras del backlog. |

### 4.3 Herramientas CLI (`apply_copilot/tools/`, con Python directo)

```powershell
# Verificación
python tools\selfcheck.py --silencioso      # 10 validaciones en ~9s
python tools\acceptance.py                  # gate completo: 6 checks (selfcheck + autotest + humos)

# Búsqueda y similitud
python tools\search_offers.py "bodeguero"                     # búsqueda por texto
python tools\search_offers.py --similar ch_abc123 --limit 10  # ofertas parecidas a una dada
python tools\search_offers.py --duplicados                    # grupos de reposts detectados

# Ranking y evaluación
python tools\match_engine.py rank            # recalcular cola v2 (dedupe reposts incluido)
python tools\eval_ranker.py                  # precision@10 v2 vs legacy

# Estado y progreso
python tools\apply_state.py sync             # refresca estado desde data/
python tools\apply_state.py summary          # resumen de avance
python tools\apply_state.py mark <ID> READY --nota "enviada a mano"

# Mantenimiento (/btw)
python tools\btw.py tick --reparar --etiqueta "texto"   # 1 tick: selfcheck + mejora
python tools\btw.py history -n 10                       # últimos 10 ticks
python tools\btw.py similar ch_abc123                   # similares en 1 línea
python tools\btw.py repair                              # reparos mecánicos (receiver abajo, cachés)

# Sueldos
python tools\salary.py --autotest          # autotest determinista del estimador
```

### 4.4 Estados del pipeline

```
RANKED → QUEUED → OPENED → FILLED → READY → APPLIED
                                  ↘ EXPIRED (la oferta venció y se cierra sola)
```

- **FILLED**: el sistema rellenó el formulario. Esperando tu revisión y envío.
- **APPLIED**: TÚ enviaste la postulación (registrado con `/mark` o `apply_state.py mark`).
- **EXPIRED**: la oferta ya no acepta postulaciones; la pestaña se cierra automáticamente.

---

## 5. Seguridad y privacidad

**Lo que el sistema nunca hace:**
- No hay clic en Enviar/Postular: `auto_submit: false` está forzado en `config/settings.json`.
- No rellena RUT, LinkedIn ni datos bancarios (bloqueados por `block_sensitive_autofill`).
- El receiver solo escucha en `127.0.0.1` (loopback, no red).
- No inventa experiencia: el LLM solo puede usar lo que dice tu `profile.json`.

**Lo que NO está en este repositorio** (protegido por `.gitignore`):
- `perfiles/` — tu CV, tu perfil con contacto/RUT y tus historiales privados.
- `apply_copilot/config/profile.json` — el perfil activo.
- `apply_copilot/data/` — registro de rellenados, respuestas de formularios, cartas,
  sueldos, evidencias (capturas), logs y bases de búsqueda.
- `dashboard_interactivo.html` — dashboard generado con tus datos.

Para tu propio uso tras clonar: copia `config/profile.example.json` a
`perfiles/<TuNombre>/profile.json` y complétalo.

---

## 6. Troubleshooting

| Síntoma | Causa | Solución |
|---|---|---|
| La corrida termina con `EXIT 3` | Sesión de ChileTrabajos expiró | `.\1-preparar-sesion.bat` → ingresa → vuelve a correr `/ir30` (reanuda solo) |
| Formularios no se rellenan | Extensión desactualizada o receiver abajo | ↻ en `chrome://extensions`; verifica receiver: `curl http://127.0.0.1:8766/health` |
| `0/10 ok` en selfcheck | Varias | Lee el check fallido; para fallos mecánicos: `python tools\btw.py repair` |
| El botón del popup no responde | Receiver no está en 8766 | `python apply_copilot\tools\receiver.py` (o corre `2-arrancar-postulaciones.bat`, lo levanta solo) |
| Sueldos muy bajos/altos | Tabla local conservadora | Edita `tools/salary.py` (`BASE_BY_CLUSTER`) o define una API key de LLM |
| Ofertas repetidas en el plan | — | Ya mitigado: dedupe por registro + reposts; revisa con `--duplicados` |
| `No existe el perfil 'X'` | Falta la carpeta | Créala con `--entrenar` o copia `profile.example.json` |

---

## 7. Estructura del repositorio

```
1-preparar-sesion.bat/.ps1      # sesión de ChileTrabajos
2-arrancar-postulaciones.bat/.ps1  # el ciclo completo (UN comando)
orquestador.py                  # orquesta: buscar → plan → abrir
extension_v2/                   # extensión Chrome (autofill + popup)
perfiles/                       # (gitignored) TU perfil + CV
apply_copilot/
  job_hunter.py                 # búsqueda en portales, scoring, dashboard
  apply_copilot.py              # CLI de estado (mark, check...)
  config/settings.json          # límites y seguridad (auto_submit false)
  config/profile.example.json   # plantilla para tu perfil
  data/                         # (gitignored) estado generado
  tools/                        # receiver, selfcheck, acceptance, btw, ranking,
                                # search_offers, salary, market_analysis, etc.
.opencode/                      # agentes + comandos + skills (interfaz conversacional)
```

**Después de clonar**: crea tu perfil (paso 1 de instalación) → `1-preparar-sesion.bat`
→ carga `extension_v2` en Chrome → `/ir30 30` o `2-arrancar-postulaciones.bat`. 🚀
