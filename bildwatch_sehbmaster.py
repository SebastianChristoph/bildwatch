from bs4 import BeautifulSoup
import requests
import json
import os
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")

# ========= Konfiguration =========
URL = "https://www.bild.de/"
HEADERS = {
    "user-agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 12_3_1 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 "
        "Instagram 105.0.0.11.118 (iPhone11,8; iOS 12_3_1; en_US; en-US; scale=2.00; 828x1792; 165586599)"
    )
}

API_BASE = os.getenv("SEHBMASTER_API", "http://188.245.189.141:8000/api").rstrip("/")
API_KEY = os.getenv("SEHBMASTER_API_KEY", "dev-secret")
RASPBERRY_ID = os.getenv("RASPBERRY_ID", "z0")
TIMEOUT = 12  # Sekunden

# ========= HTTP-Helper =========
class ApiError(RuntimeError):
    pass

def _req(method: str, path: str, json_body: Optional[dict] = None) -> Any:
    url = f"{API_BASE}{path}"
    headers = {"Accept": "application/json"}
    if method in ("POST", "PATCH", "PUT", "DELETE"):
        headers["Content-Type"] = "application/json"
        headers["X-API-Key"] = API_KEY
    resp = None
    try:
        resp = requests.request(method, url, json=json_body, headers=headers, timeout=TIMEOUT)
        resp.raise_for_status()
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()
    except requests.HTTPError as e:
        text = resp.text[:500] if resp is not None else ""
        raise ApiError(f"{method} {url} -> HTTP {resp.status_code}: {text}") from e
    except Exception as e:
        raise ApiError(f"{method} {url} failed: {e}") from e

# ========= Zeit/Parsing-Helper =========
def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def iso_now_utc() -> str:
    return now_utc().replace(microsecond=0).isoformat()

def parse_iso_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    except Exception:
        return None

def hours_between(start: Optional[datetime], end: Optional[datetime]) -> Optional[float]:
    if not start or not end:
        return None
    return (end - start).total_seconds() / 3600.0


def fmt_berlin_time_and_date(dt_utc: datetime) -> tuple[str, str]:
    """Gibt ('HH:MM', 'DD.MM.YYYY') in Europe/Berlin zurück."""
    local = dt_utc.astimezone(BERLIN)
    return local.strftime("%H:%M"), local.strftime("%d.%m.%Y")


# ========= Backend-Calls =========
def send_log(message: str, ts_iso: Optional[str] = None):
    payload = {"message": message}
    if ts_iso:
        payload["timestamp"] = ts_iso
    try:
        return _req("POST", "/bild/logs", payload)
    except Exception as e:
        # Fallback: nicht crashen, wenn Logging scheitert
        print(f"[log-fallback] {message} ({e})")

def status_upsert(raspberry: str, status: str, message: Optional[str] = None):
    payload = {"raspberry": raspberry, "status": status, "message": message}
    return _req("POST", "/status", payload)  # dein /api/status upsert (on conflict)

def get_all_articles_from_sehbmaster() -> List[Dict[str, Any]]:
    return _req("GET", "/bild/articles") or []

def create_article_in_sehbmaster(scraped: Dict[str, Any]) -> Dict[str, Any]:
    payload = {
        "id": scraped["id"],
        "title": scraped["title"],
        "url": scraped["url"],
        "category": scraped.get("category"),
        "is_premium": bool(scraped.get("isPremium", False)),
        "converted": False,
        "published": iso_now_utc(),
        "converted_time": None,
        "converted_duration_hours": None,
    }
    return _req("POST", "/bild/articles", payload)

def patch_article_in_sehbmaster(article_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    clean = {k: v for k, v in updates.items() if v is not None or k in ("converted", "is_premium")}
    return _req("PATCH", f"/bild/articles/{article_id}", clean)

def post_metrics(ts_hour_iso: str, snapshot_total: int, snapshot_premium: int,
                 new_count: int, new_premium_count: int):
    pct = round((snapshot_premium / snapshot_total * 100.0), 2) if snapshot_total else 0.0
    payload = {
        "ts_hour": ts_hour_iso,
        "snapshot_total": snapshot_total,
        "snapshot_premium": snapshot_premium,
        "snapshot_premium_pct": pct,
        "new_count": new_count,
        "new_premium_count": new_premium_count,
    }
    return _req("POST", "/bild/metrics", payload)

# ========= Scraping =========
def get_all_articles_from_bild() -> List[Dict[str, Any]]:
    source = requests.get(URL, headers=HEADERS, timeout=TIMEOUT).text
    soup = BeautifulSoup(source, "html.parser")
    script_tag = soup.find("script", {"id": "pageContext", "type": "application/json"})
    articles = []
    if not script_tag:
        send_log("WARN: Kein <script id='pageContext'> gefunden.", iso_now_utc())
        return articles

    try:
        data = json.loads(script_tag.string or "{}")
        blocks = data["CLIENT_STORE_INITIAL_STATE"]["pageAggregation"]["curation"]["page"]["blocks"]
        for block in blocks:
            for layout in block.get("children", []):
                for child in layout.get("children", []):
                    if child.get("type") == "ARTICLE":
                        props = child.get("props", {}) or {}
                        url = props.get("url") or ""
                        category = url.split("/")[1] if url else None
                        articles.append({
                            "id": props.get("id"),
                            "title": props.get("title"),
                            "url": url,
                            "category": category,
                            "isPremium": bool(props.get("isPremium", False)),
                        })
    except Exception as e:
        send_log(f"Fehler beim Parsen: {e}", iso_now_utc())

    send_log(f"Anzahl gefundener Bild-Artikel: {len(articles)}", iso_now_utc())
    return [a for a in articles if a.get("id") and a.get("title") and a.get("url")]

# ========= Sync-Logik =========
def sync_bildwatch():
    start_ts = now_utc()
    time_str, date_str = fmt_berlin_time_and_date(start_ts)
    msg_start = f"Start scraping BILD at {time_str}, {date_str}"


    try:
        status_upsert(RASPBERRY_ID, "working", msg_start)
    except Exception as e:
        send_log(f"Status-Start fehlgeschlagen: {e}", iso_now_utc())

    send_log(msg_start, start_ts.replace(microsecond=0).isoformat())

    try:
        # 1) DB → alle Articles
        db_rows = get_all_articles_from_sehbmaster()
        db_by_id = {row["id"]: row for row in db_rows}

        # 2) Scrape die Startseite
        scraped = get_all_articles_from_bild()
        scraped_by_id = {row["id"]: row for row in scraped}

        created = 0
        created_premium = 0
        patched = 0

        # 3) Neue Artikel anlegen
        for sid, srow in scraped_by_id.items():
            if sid not in db_by_id:
                try:
                    create_article_in_sehbmaster(srow)
                    created += 1
                    if srow.get("isPremium"):
                        created_premium += 1
                    send_log(f"CREATE {sid} – {srow.get('title')!r}", iso_now_utc())
                except Exception as e:
                    send_log(f"ERR create {sid}: {e}", iso_now_utc())

        # 4) isPremium-Änderungen: True -> False
        now = now_utc()
        for sid, srow in scraped_by_id.items():
            db_row = db_by_id.get(sid)
            if not db_row:
                continue
            was_premium = bool(db_row.get("is_premium"))
            is_premium_now = bool(srow.get("isPremium", False))
            if was_premium and not is_premium_now:
                published_dt = parse_iso_dt(db_row.get("published"))
                duration = hours_between(published_dt, now)
                try:
                    patch_article_in_sehbmaster(
                        sid,
                        {
                            "is_premium": False,
                            "converted": True,
                            "converted_time": iso_now_utc(),
                            "converted_duration_hours": round(duration, 4) if duration is not None else None,
                        },
                    )
                    patched += 1
                    send_log(f"PATCH {sid} – is_premium False, converted=True, hours={duration}", iso_now_utc())
                except Exception as e:
                    send_log(f"ERR patch {sid}: {e}", iso_now_utc())

        # 5) Metrics posten (Snapshot + Zuwachs)
        snapshot_total = len(scraped)
        snapshot_premium = sum(1 for a in scraped if a.get("isPremium"))
        ts_hour = now.replace(minute=0, second=0, microsecond=0)
        try:
            post_metrics(
                ts_hour_iso=ts_hour.isoformat(),
                snapshot_total=snapshot_total,
                snapshot_premium=snapshot_premium,
                new_count=created,
                new_premium_count=created_premium,
            )
            send_log(
                f"METRICS {ts_hour.isoformat()} [snapshot: total={snapshot_total}, premium={snapshot_premium}] "
                f"[new: total={created}, premium={created_premium}]",
                iso_now_utc(),
            )
        except Exception as e:
            send_log(f"ERR metrics: {e}", iso_now_utc())

        send_log(
            f"Fertig. Neu: {created}, Gepatcht: {patched}, Bekannte DB: {len(db_rows)}, Gesehen: {len(scraped)}",
            iso_now_utc(),
        )

        end_ts = now_utc()
        mins = round((end_ts - start_ts).total_seconds() / 60.0, 2)
        time_str, date_str = fmt_berlin_time_and_date(end_ts)
        mins_str = f"{mins:.2f}".rstrip("0").rstrip(".")  # "0.10" -> "0.1", "2.00" -> "2"

        idle_msg = f"finished bild scraping at {time_str}, {date_str} after {mins_str}min"
        try:
            status_upsert(RASPBERRY_ID, "idle", idle_msg)
        except Exception as e:
            send_log(f"Status-Ende (idle) fehlgeschlagen: {e}", iso_now_utc())

        # optional zusätzlich ins Log mit Abschlusszeit (UTC-TS ist ok)
        send_log(idle_msg, end_ts.replace(microsecond=0).isoformat())

    except Exception as e:
        end_ts = now_utc()
        mins = round((end_ts - start_ts).total_seconds() / 60.0, 2)
        time_str, date_str = fmt_berlin_time_and_date(end_ts)
        mins_str = f"{mins:.2f}".rstrip("0").rstrip(".")

        err_msg = f"SCRAPER ERROR at {time_str}, {date_str} after {mins_str}min: {e}"
        send_log(err_msg, end_ts.replace(microsecond=0).isoformat())
        try:
            status_upsert(RASPBERRY_ID, "error", err_msg)
        except Exception as e2:
            send_log(f"Status-Update (error) fehlgeschlagen: {e2}", iso_now_utc())


# ========= Run =========
if __name__ == "__main__":
    sync_bildwatch()
