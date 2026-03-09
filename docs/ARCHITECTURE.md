# Architektur – #TeamMinigolf

## Überblick

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Browser    │────▶│  Django/     │────▶│  MariaDB 11  │
│  (Bootstrap) │◀────│  Gunicorn    │◀────│  (InnoDB)    │
└──────────────┘     └──────────────┘     └──────────────┘
       :8000              web                   db
```

## Stack-Entscheidungen

| Komponente | Wahl | Begründung |
|---|---|---|
| Framework | **Django 5** | Batteries-included (Auth, Admin, ORM, Migrations), ideal für Server-rendered UI mit kleinem Team |
| DB | **MariaDB 11** | Stabile, performante relationale DB mit InnoDB; bewährt für Webapps |
| UI | **Server-rendered (Django Templates + Bootstrap 5)** | Einfach, schnell, kein Build-Step nötig; HTMX-ready bei Bedarf |
| Deployment | **Docker Compose** | Einfaches Single-Server-Setup, reproduzierbar |
| WSGI Server | **Gunicorn** | Standard-Produktions-WSGI-Server für Django |

## Datenmodell

```
players (1)──(n) session_players (n)──(1) sessions
                                           │
courses (1)──(n) holes                     │
   │                │                      │
   └──(1)──(n) sessions (1)──(n) scores ◀──┘
                                    │
                          players ◀─┘
                          holes   ◀─┘

audit_log ← tracks score changes
```

### Modelle

- **Player**: Spieler (unabhängig von Django-User/Auth)
- **Course**: Minigolf-Anlage mit Bahnanzahl
- **Hole**: Einzelne Bahn einer Anlage (auto-created bei Course-Erstellung)
- **Session**: Spieltag (live / completed), verknüpft Spieler mit Anlage
- **SessionPlayer**: M2M-Zwischentabelle
- **Score**: Schlagzahl pro Spieler/Bahn/Session (unique_together)
- **AuditLog**: JSON-basierte Änderungshistorie

### Wichtige Constraints

- `Score.unique_together = (session, player, hole)` → maximal ein Eintrag pro Kombination
- `Hole.unique_together = (course, hole_number)` → keine doppelten Bahnnummern
- `SessionPlayer.unique_together = (session, player)` → Spieler nur einmal pro Session
- `Score.strokes`: 1–10 (Validator)
- `Course.holes_count`: 1–36 (Validator)
- `Course → Session`: PROTECT (keine Anlage löschen, solange Spieltage existieren)
- `Player → Score/SessionPlayer`: PROTECT (kein Spieler löschen mit bestehenden Daten)

## Request-Flow

1. Alle Routen (außer `/health/`) erfordern Login (`@login_required`)
2. Django CSRF-Protection auf allen POST-Formularen und AJAX-Calls
3. Scoring-AJAX: `POST /sessions/<id>/score/` mit JSON-Body, CSRF-Token im Header
4. Gunicorn (2 Workers) → ausreichend für ~20 gleichzeitige User

## Security

- `SECRET_KEY` aus Environment, nicht im Code
- Produktionsmodus: `Secure`-Cookies, `X-Frame-Options: DENY`, `HSTS`-ready
- SQL-Injection: ausgeschlossen durch Django ORM
- XSS: Django Template Auto-Escaping
- CSRF: Django Middleware + Token in AJAX-Calls

## Backup-Strategie

```
┌────────────┐   dump    ┌────────────┐   rsync   ┌────────────┐
│  MariaDB   │ ────────▶ │  Backup    │ ────────▶ │ Raspberry  │
│  Container │           │  Volume    │           │    Pi      │
└────────────┘           └────────────┘           └────────────┘
     db                    backup_data              Remote
```

- **Trigger**: Cronjob auf dem Host (täglich 03:00)
- **Format**: `mariadb-dump` → gzip
- **Rotation**: `BACKUP_RETAIN_DAYS` (default: 30 Tage)
- **Remote**: Push via `rsync` zum Raspberry Pi (SSH-Keys erforderlich)
