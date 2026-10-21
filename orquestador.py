#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ApplyFlow v5 — orquestador de postulaciones (ChileTrabajos).

Hace toda la cadena:
  1. perfil + CV
  2. búsqueda por 5 clusters ampliados
  3. filtro últimas 2 semanas + dedupe + ranking fecha→score
  4. estimación de sueldo en lote (LLM o tabla local)
  5. cartas personalizadas por oferta
  6. apertura de pestañas en lotes
  7. autofill vía extensión Chrome (nunca envía)

Uso:
    python orquestador.py --perfil Jorge
    python orquestador.py --perfil Jorge --dry-run
    python orquestador.py --perfil Jorge --objetivo 100 --dias 14 --min-score 70
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

ROOT = Path(__file__).resolve().parent
AC = ROOT / "apply_copilot"
DATA = AC / "data"
TOOLS = AC / "tools"
PROFILES = ROOT / "perfiles"
JOB_HUNTER = AC / "job_hunter.py"
RECEIVER = TOOLS / "receiver.py"

sys.path.insert(0, str(TOOLS))
import ac_common as ac  # noqa: E402
import salary as salary_mod  # noqa: E402


class LoginRequired(RuntimeError):
    pass


# Clusters de versiones anteriores → clusters nuevos (para ofertas ya guardadas).
CLUSTER_RENAME = {
    "C3_OPERACIONES": ("C3_MECANICA", "Mecánica, Maestranza & Mantenimiento"),
    "C4_MANTENIMIENTO": ("C3_MECANICA", "Mecánica, Maestranza & Mantenimiento"),
    "C5_ESPECIALISTA": ("C4_PIPING", "Piping, Montaje & Estructuras"),
}


# --------------------------------------------------------------------------- utilidades
def read_json(path: Path, default: Any) -> Any:
    try:
        return ac.read_json(path)
    except (ValueError, OSError):
        return default


def write_json(path: Path, obj: Any) -> None:
    ac.atomic_write_json(path, obj)


def now_iso() -> str:
    return dt.datetime.now().replace(microsecond=0).isoformat()


def parse_date(value: Any) -> Optional[dt.date]:
    text = str(value or "")[:10]
    try:
        return dt.date.fromisoformat(text)
    except ValueError:
        return None


def apply_url_for(url: str) -> Optional[str]:
    """URL de postulación de ChileTrabajos a partir del slug de la oferta."""
    m = re.search(r"-(\d{4,})(?:[/?#].*)?$", url or "")
    if not m:
        m = re.search(r"/(\d{4,})(?:[/?#].*)?$", url or "")
    return f"https://www.chiletrabajos.cl/trabajo/postular/{m.group(1)}" if m else None


def numeric_id(url: str) -> Optional[str]:
    m = re.search(r"-(\d{4,})(?:[/?#].*)?$", url or "") or re.search(r"/(\d{4,})(?:[/?#].*)?$", url or "")
    return m.group(1) if m else None


def chrome_path() -> Optional[Path]:
    candidates = [
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("LocalAppData", "")) / "Google/Chrome/Application/chrome.exe",
    ]
    return next((p for p in candidates if p.exists()), None)


def open_url(url: str) -> None:
    chrome = chrome_path()
    try:
        if chrome:
            subprocess.Popen([str(chrome), url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            webbrowser.open(url)
    except Exception:
        webbrowser.open(url)


def receiver_url(port: int, path: str) -> str:
    return f"http://127.0.0.1:{port}{path}"


def receiver_health(port: int) -> Optional[Dict[str, Any]]:
    try:
        with urllib.request.urlopen(receiver_url(port, "/health"), timeout=2) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return None


def start_receiver(port: int) -> None:
    health = receiver_health(port)
    if health and health.get("version") == "v5":
        print(f"✔ Receiver v5 activo en 127.0.0.1:{port}")
        return
    if health:
        raise SystemExit(
            f"Hay un receptor que no es v5 en el puerto {port}. "
            "Cierra ese proceso (o reinicia el PC) y vuelve a intentar."
        )

    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    proc = subprocess.Popen(
        [sys.executable, str(RECEIVER), "--port", str(port)],
        cwd=str(AC),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )
    for _ in range(50):
        health = receiver_health(port)
        if health and health.get("version") == "v5":
            print(f"✔ Receiver v5 iniciado en 127.0.0.1:{port}")
            return
        if proc.poll() is not None:
            break
        time.sleep(0.2)
    raise SystemExit(
        f"No pude iniciar el receiver en 127.0.0.1:{port}. "
        f"Prueba manual: python \"{RECEIVER}\" --port {port}"
    )


# --------------------------------------------------------------------------- perfil
def load_profile(name: str, entrenar: bool) -> tuple[Dict[str, Any], Optional[Path], Path]:
    folder = PROFILES / name
    if not folder.is_dir():
        raise SystemExit(
            f"No existe el perfil '{name}' en {PROFILES}.\n"
            f"Crea la carpeta con tu CV y vuelve a ejecutar, o usa --entrenar."
        )

    profile_path = folder / "profile.json"
    if not profile_path.exists() and entrenar:
        subprocess.run([sys.executable, str(TOOLS / "profile_wizard.py"),
                        "--perfil", name, "--dir", str(folder)], check=False)
    if not profile_path.exists():
        profile_path = AC / "config" / "profile.json"
    profile = read_json(profile_path, {})
    if not isinstance(profile, dict) or not profile:
        raise SystemExit(f"No pude leer el perfil en {profile_path}. Ejecuta --entrenar.")

    cvs = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".pdf")
    cv = cvs[0] if cvs else None
    return profile, cv, folder


# --------------------------------------------------------------------------- búsqueda + selección
def run_search(args: argparse.Namespace) -> None:
    if args.no_buscar:
        print("🔎 Búsqueda omitida (--no-buscar): uso el histórico.")
        return
    queries = 4 if args.rapido else args.queries
    cmd = [
        sys.executable, str(JOB_HUNTER),
        "--sources", args.sources,
        "--queries-per-cluster", str(queries),
        "--max-per-query", str(args.max_per_query),
        "--min-score", "55",
        "--days", "30",
        "--no-open",
        "--no-browser",
    ]
    print(f"🔎 Buscando en {args.sources} ({queries} keywords por cluster)...")
    started = time.time()
    result = subprocess.run(cmd, cwd=str(AC))
    elapsed = time.time() - started
    if result.returncode != 0:
        print(f"⚠ El buscador terminó con código {result.returncode}; sigo con el histórico.")
    print(f"   Búsqueda terminada en {elapsed:.0f}s.")


def offer_state(offer: Dict[str, Any], registry: Dict[str, Any], oid: str) -> str:
    entry = registry.get(oid)
    if isinstance(entry, dict):
        return str(entry.get("estado") or offer.get("estado") or "PENDING").upper()
    return str(offer.get("estado") or "PENDING").upper()


def select_offers(db: Dict[str, Any], registry: Dict[str, Any], fills: Dict[str, Any],
                  args: argparse.Namespace) -> List[Dict[str, Any]]:
    today = dt.date.today()
    cutoff = today - dt.timedelta(days=max(1, args.dias))

    def collect(min_score: int) -> List[Dict[str, Any]]:
        by_num: Dict[str, Dict[str, Any]] = {}
        for oid, offer in db.items():
            if not isinstance(offer, dict):
                continue
            if str(offer.get("portal") or "") != "ChileTrabajos":
                continue
            if offer_state(offer, registry, oid) != "PENDING":
                continue
            apply_url = apply_url_for(str(offer.get("url") or ""))
            num_id = numeric_id(str(offer.get("url") or ""))
            if not apply_url or not num_id:
                continue
            if not args.refill:
                filled = fills.get(num_id)
                if isinstance(filled, dict) and filled.get("status") == "filled":
                    continue
            published = parse_date(offer.get("fecha_publicacion")) or parse_date(offer.get("fecha_deteccion"))
            if not published or published < cutoff or published > today + dt.timedelta(days=1):
                continue
            score = int(offer.get("score") or 0)
            if score < min_score:
                continue

            cluster_id = str(offer.get("cluster_id") or "")
            cluster_name = str(offer.get("cluster_name") or "")
            if cluster_id in CLUSTER_RENAME:
                cluster_id, cluster_name = CLUSTER_RENAME[cluster_id]

            candidate = {
                "id": oid,
                "num_id": num_id,
                "titulo": str(offer.get("titulo") or "").strip(),
                "empresa": str(offer.get("empresa") or "").strip(),
                "ubicacion": str(offer.get("ubicacion") or "").strip(),
                "cluster_id": cluster_id,
                "cluster_name": cluster_name,
                "score": score,
                "fecha": published.isoformat(),
                "fecha_fiable": bool(offer.get("fecha_publicacion")),
                "url": str(offer.get("url") or ""),
                "apply_url": apply_url,
            }
            previous = by_num.get(num_id)
            if previous is None or (candidate["fecha"], candidate["score"]) > (previous["fecha"], previous["score"]):
                by_num[num_id] = candidate
        return list(by_num.values())

    thresholds = []
    for value in (args.min_score, max(60, args.min_score - 10), 55):
        if value not in thresholds:
            thresholds.append(value)

    chosen: List[Dict[str, Any]] = []
    used_threshold = args.min_score
    for threshold in thresholds:
        chosen = collect(threshold)
        used_threshold = threshold
        if len(chosen) >= args.objetivo:
            break

    chosen.sort(key=lambda o: (o["fecha"], o["score"]), reverse=True)
    chosen = chosen[: args.objetivo + args.buffer]
    args._used_threshold = used_threshold
    return chosen


def print_plan(plan: List[Dict[str, Any]], args: argparse.Namespace) -> None:
    print("\n" + "=" * 78)
    print(f"PLAN: {len(plan)} ofertas · últimas {args.dias} días · score ≥ {getattr(args, '_used_threshold', args.min_score)}")
    print("=" * 78)
    print(f"{'Fecha':<12}{'Score':>6}  {'Cluster':<34}Cargo")
    print("-" * 78)
    for o in plan[:15]:
        cargo = o["titulo"][:52]
        print(f"{o['fecha']:<12}{o['score']:>6}  {o['cluster_name'][:33]:<34}{cargo}")
    if len(plan) > 15:
        print(f"... y {len(plan) - 15} más")
    by_cluster: Dict[str, int] = {}
    for o in plan:
        by_cluster[o["cluster_name"]] = by_cluster.get(o["cluster_name"], 0) + 1
    print("\nPor cluster:")
    for name, count in sorted(by_cluster.items(), key=lambda kv: -kv[1]):
        print(f"  {count:>3}  {name}")
    print()


# --------------------------------------------------------------------------- cartas + sueldo
def build_answers(plan: List[Dict[str, Any]], profile: Dict[str, Any],
                  use_llm: bool) -> tuple[Dict[str, Any], Dict[str, Any]]:
    salaries = salary_mod.estimate(plan, profile, use_llm=use_llm)
    templates = profile.get("templates") or {}
    motivation = str(templates.get("motivation") or
                     "Me interesa la vacante de {cargo} porque calza con mi experiencia y formación.")
    full_name = str(profile.get("full_name") or "")
    current_role = str(profile.get("current_role") or "")
    employer = str(profile.get("current_employer") or "")

    answers: Dict[str, Any] = {}
    salary_detail: Dict[str, Any] = {}
    for offer in plan:
        oid = offer["num_id"]
        salary = salaries.get(oid) or {}
        clp = int(salary.get("clp") or 0)
        display = salary_mod.format_clp(clp) if clp else ""

        letter = motivation.replace("{cargo}", offer["titulo"])
        extra = []
        if current_role:
            extra.append(f"Actualmente me desempeño como {current_role}" +
                         (f" en {employer}." if employer else "."))

        body = letter.rstrip()
        if extra:
            body += "\n\n" + " ".join(extra)
        if full_name:
            body += f"\n\nSaludos cordiales,\n{full_name}"

        answers[oid] = {
            "app_letter": body,
            "salary": clp,
            "salary_display": display,
            "title": offer["titulo"],
            "cluster_id": offer["cluster_id"],
            "cluster_name": offer["cluster_name"],
            "generated_at": now_iso(),
        }
        salary_detail[oid] = {
            "clp": clp,
            "display": display,
            "nota": salary.get("nota", ""),
            "source": salary.get("source", ""),
            "title": offer["titulo"],
        }

    write_json(DATA / "offer_answers.json", answers)
    write_json(DATA / "salaries.json", salary_detail)
    write_json(DATA / "apply_plan.json", plan)
    return answers, salary_detail


# --------------------------------------------------------------------------- corrida
def write_run_state(active: bool, run_id: str, objetivo: int, port: int) -> None:
    previous = read_json(DATA / "current_run.json", {})
    state = {
        "active": active,
        "run_id": run_id,
        "objetivo": objetivo,
        "port": port,
        "started_at": previous.get("started_at") if isinstance(previous, dict) else None,
        "updated_at": now_iso(),
    }
    if active and not state["started_at"]:
        state["started_at"] = state["updated_at"]
    if not active:
        state["finished_at"] = state["updated_at"]
    write_json(DATA / "current_run.json", state)


def read_reports(run_id: str) -> List[Dict[str, Any]]:
    path = DATA / "fill_reports.jsonl"
    if not path.exists():
        return []
    reports = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    report = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if str(report.get("run_id") or "") == run_id:
                    reports.append(report)
    except OSError:
        return []
    return reports


def wait_for_batch(run_id: str, batch_ids: Set[str], timeout: float) -> Dict[str, Dict[str, Any]]:
    deadline = time.time() + max(5.0, timeout)
    seen: Dict[str, Dict[str, Any]] = {}
    while time.time() < deadline:
        for report in read_reports(run_id):
            if str(report.get("status")) == "login":
                raise LoginRequired()
            oid = str(report.get("offer_id") or "")
            if oid in batch_ids and oid not in seen:
                seen[oid] = report
        if len(seen) >= len(batch_ids):
            break
        time.sleep(1.0)
    return seen


def open_tabs(plan: List[Dict[str, Any]], args: argparse.Namespace, run_id: str, port: int) -> Dict[str, Any]:
    results: Dict[str, Dict[str, Any]] = {}
    opened_ids: Set[str] = set()
    pending = list(plan)
    login_required = False
    no_report_batches = 0
    started = time.time()

    while pending:
        filled = sum(1 for r in results.values() if r.get("status") == "filled" and int(r.get("filled") or 0) > 0)
        if filled >= args.objetivo:
            break

        batch = pending[: args.batch_size]
        pending = pending[args.batch_size:]
        batch_ids = {o["num_id"] for o in batch}

        print(f"\n▶ Abriendo lote de {len(batch)} pestañas (rellenadas: {filled}/{args.objetivo})...", flush=True)
        for offer in batch:
            opened_ids.add(offer["num_id"])
            open_url(offer["apply_url"])
            time.sleep(max(0.0, args.tab_delay))

        try:
            reports = wait_for_batch(run_id, batch_ids, args.timeout)
        except LoginRequired:
            login_required = True
            print("\n✖ ChileTrabajos pidió login. La sesión expiró.", flush=True)
            print("  Ejecuta 1-preparar-sesion.ps1, inicia sesión y vuelve a correr el comando 2.", flush=True)
            break

        for oid, report in reports.items():
            results[oid] = report

        if not reports:
            no_report_batches += 1
            print("  ⚠ Este lote no reportó nada. ¿La extensión está cargada y recargada (↻)?", flush=True)
            if no_report_batches >= 2:
                print("  ✖ Dos lotes sin reportes: aborto para no abrir pestañas en vano.", flush=True)
                break
        else:
            no_report_batches = 0
            ok = sum(1 for r in reports.values() if r.get("status") == "filled")
            print(f"  ✔ Reportes: {ok} rellenadas, "
                  f"{sum(1 for r in reports.values() if r.get('status') == 'expired')} expiradas, "
                  f"{sum(1 for r in reports.values() if r.get('status') == 'no_form')} sin formulario.",
                  flush=True)

    # Barrido final: con muchas pestañas abiertas, algunos reportes llegan tarde.
    if opened_ids and len(results) < len(opened_ids):
        time.sleep(8)
        for report in read_reports(run_id):
            oid = str(report.get("offer_id") or "")
            if oid in opened_ids and oid not in results:
                results[oid] = report

    elapsed = time.time() - started
    filled_reports = {oid: r for oid, r in results.items()
                      if r.get("status") == "filled" and int(r.get("filled") or 0) > 0}
    expired = [oid for oid, r in results.items() if r.get("status") == "expired"]
    no_form = [oid for oid, r in results.items() if r.get("status") == "no_form"]
    errors = [oid for oid, r in results.items() if r.get("status") == "error"]
    unreported = [oid for oid in opened_ids if oid not in results]
    not_opened = [o["num_id"] for o in plan if o["num_id"] not in opened_ids]

    return {
        "run_id": run_id,
        "started_at": dt.datetime.fromtimestamp(started).replace(microsecond=0).isoformat(),
        "elapsed_seconds": round(elapsed, 1),
        "objetivo": args.objetivo,
        "filled": len(filled_reports),
        "expired": len(expired),
        "no_form": len(no_form),
        "errors": len(errors),
        "unreported": len(unreported),
        "not_opened": len(not_opened),
        "login_required": login_required,
        "filled_ids": sorted(filled_reports),
        "expired_ids": sorted(expired),
        "no_form_ids": sorted(no_form),
        "unreported_ids": sorted(unreported),
        "not_opened_ids": sorted(not_opened),
        "details": results,
    }


# --------------------------------------------------------------------------- main
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="ApplyFlow v5 — orquestador de postulaciones.")
    p.add_argument("--perfil", default="Jorge", help="Nombre de la carpeta en perfiles/")
    p.add_argument("--objetivo", type=int, default=100, help="Pestañas rellenadas objetivo (default 100)")
    p.add_argument("--dias", type=int, default=14, help="Solo ofertas publicadas en los últimos N días")
    p.add_argument("--min-score", type=int, default=70, help="Score mínimo (default 70)")
    p.add_argument("--buffer", type=int, default=40, help="Ofertas extra en el plan por expiradas/fallos")
    p.add_argument("--batch-size", type=int, default=10, help="Pestañas por lote (default 10)")
    p.add_argument("--timeout", type=float, default=50, help="Segundos de espera por lote")
    p.add_argument("--tab-delay", type=float, default=0.8, help="Segundos entre pestañas")
    p.add_argument("--queries", type=int, default=12, help="Keywords por cluster (default 12)")
    p.add_argument("--max-per-query", type=int, default=8)
    p.add_argument("--sources", default="ChileTrabajos")
    p.add_argument("--rapido", action="store_true", help="4 keywords por cluster")
    p.add_argument("--no-buscar", action="store_true", help="Usar solo el histórico")
    p.add_argument("--refill", action="store_true", help="Incluir ofertas ya rellenadas antes")
    p.add_argument("--sin-llm", action="store_true", help="No llamar al LLM; tabla local")
    p.add_argument("--entrenar", action="store_true", help="Crear perfil si falta")
    p.add_argument("--dry-run", action="store_true", help="Preparar plan sin abrir pestañas")
    p.add_argument("--abrir-dashboard", action="store_true", help="Abrir el dashboard al terminar")
    return p


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    args = build_parser().parse_args(argv)
    settings = ac.load_settings(ac.get_paths(AC))
    port = int((settings.get("receiver") or {}).get("port") or 8766)

    print("=" * 78)
    print("ApplyFlow v5 — postulaciones ChileTrabajos")
    print("=" * 78)
    print(f"Perfil: {args.perfil} · objetivo: {args.objetivo} · últimos {args.dias} días · "
          f"score ≥ {args.min_score}")
    print("Este flujo NUNCA envía postulaciones. Solo rellena para tu revisión.\n")

    profile, cv, profile_dir = load_profile(args.perfil, args.entrenar)
    print(f"👤 {profile.get('full_name', args.perfil)}")
    print(f"📄 CV: {cv if cv else '⚠ no encontré PDF en ' + str(profile_dir)}")

    run_search(args)

    db = read_json(DATA / "jobs_database.json", {})
    registry = read_json(DATA / "applied_registry.json", {})
    fills = read_json(DATA / "fill_registry.json", {})
    if not isinstance(db, dict):
        db = {}
    if not isinstance(registry, dict):
        registry = {}
    if not isinstance(fills, dict):
        fills = {}

    plan = select_offers(db, registry, fills, args)
    if not plan:
        print("\n✖ No hay ofertas nuevas que cumplan el filtro.")
        print(f"  Prueba: --dias 21 --min-score 60, o corre sin --no-buscar.")
        return 2

    print_plan(plan, args)
    answers, salary_detail = build_answers(plan, profile, use_llm=not args.sin_llm)

    if args.dry_run:
        print("🧪 Dry-run: plan, cartas y sueldos generados. No se abrió ninguna pestaña.")
        print(f"   Plan:    {DATA / 'apply_plan.json'}")
        print(f"   Cartas:  {DATA / 'offer_answers.json'}")
        print(f"   Sueldos: {DATA / 'salaries.json'}")
        sample = next(iter(answers.values()), {})
        if sample:
            print("\nMuestra de carta:\n" + "-" * 78)
            print(sample.get("app_letter", "")[:700])
            print("-" * 78)
            print(f"Sueldo propuesto: {sample.get('salary_display', '—')}")
        return 0

    run_id = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    write_run_state(True, run_id, args.objetivo, port)
    start_receiver(port)

    print(f"\n🚀 Corrida {run_id}: abre {len(plan)} pestañas en lotes de {args.batch_size}.")
    print("   La extensión debe estar cargada en Chrome (extension_v2) y recargada con ↻.")
    print("   No toques las pestañas hasta que termine.\n")

    try:
        summary = open_tabs(plan, args, run_id, port)
    finally:
        write_run_state(False, run_id, args.objetivo, port)

    summary.update({
        "profile": args.perfil,
        "cv": str(cv) if cv else "",
        "plan_size": len(plan),
        "finished_at": now_iso(),
        "salary_mode": next(iter(salary_detail.values()), {}).get("source", ""),
    })
    write_json(DATA / "last_run.json", summary)

    print("\n" + "=" * 78)
    print("RESULTADO")
    print("=" * 78)
    print(f"  Rellenadas:       {summary['filled']} / {args.objetivo}")
    print(f"  Expiradas:        {summary['expired']}")
    print(f"  Sin formulario:   {summary['no_form']}")
    print(f"  Errores:          {summary['errors']}")
    print(f"  Sin reporte:      {summary['unreported']}")
    print(f"  No abiertas:      {summary.get('not_opened', 0)}")
    print(f"  Tiempo:           {summary['elapsed_seconds']}s")
    if summary["filled"]:
        print(f"\n  Revisa cada pestaña. Ajusta renta si hace falta, adjunta tu CV y envía TÚ.")
        print(f"  CV: {cv}")
    if summary["login_required"]:
        print("\n  ⚠ La sesión expiró. Corre 1-preparar-sesion.ps1 y vuelve a intentar.")
    print(f"\n  Detalle: {DATA / 'last_run.json'}")
    print(f"  Dashboard: {AC / 'dashboard_interactivo.html'}")
    print("  NINGUNA postulación fue enviada automáticamente.")

    if args.abrir_dashboard:
        try:
            open_url((AC / "dashboard_interactivo.html").resolve().as_uri())
        except Exception:
            pass

    return 0 if not summary["login_required"] else 3


if __name__ == "__main__":
    sys.exit(main())
