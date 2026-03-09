# #TeamMinigolf

Schlanke, dockerisierte WebApp zur Verwaltung von Minigolf-Spielern, Anlagen und Spieltagen – inkl. Live-Scoring, nachträglicher Ergebniserfassung und aussagekräftiger Statistiken.

**Stack:** Django 5 · MariaDB 11 · Bootstrap 5 · Docker Compose

---

## Schnellstart

```bash
# 1. Repository klonen
git clone <repo-url> && cd TeamMinigolf

# 2. Umgebungsvariablen konfigurieren
cp .env.example .env
# → .env bearbeiten: DJANGO_SECRET_KEY, MYSQL_PASSWORD etc. anpassen

# 3. Starten
docker compose up -d --build

# 4. Admin-User anlegen
docker compose exec web python manage.py createsuperuser

# 5. (Optional) Beispieldaten laden
docker compose exec web python /app/../scripts/seed_data.py
# Oder direkt:
docker compose exec web python manage.py shell -c "
from django.contrib.auth.models import User
User.objects.create_superuser('admin', 'admin@example.com', 'admin')
"
```

Die App ist unter **http://localhost:8000** erreichbar.

### Dev-Tools (Adminer)

```bash
docker compose --profile dev up -d
# Adminer: http://localhost:8080
```

---

## Konfiguration (.env)

| Variable | Beschreibung | Default |
|---|---|---|
| `DJANGO_SECRET_KEY` | Django Secret Key (≥50 Zeichen) | *muss gesetzt werden* |
| `DJANGO_DEBUG` | Debug-Modus (`1`/`0`) | `0` |
| `DJANGO_ALLOWED_HOSTS` | Komma-getrennte Hosts | `localhost,127.0.0.1` |
| `MYSQL_ROOT_PASSWORD` | MariaDB Root-Passwort | *muss gesetzt werden* |
| `MYSQL_DATABASE` | Datenbankname | `minigolf` |
| `MYSQL_USER` | DB-User | `minigolf` |
| `MYSQL_PASSWORD` | DB-Passwort | *muss gesetzt werden* |
| `BACKUP_REMOTE_HOST` | SSH-Host für Backup-Push | *(optional)* |
| `BACKUP_REMOTE_USER` | SSH-User | *(optional)* |
| `BACKUP_REMOTE_PATH` | Zielpfad auf Remote | *(optional)* |
| `BACKUP_RETAIN_DAYS` | Aufbewahrungsdauer Backups | `30` |

---

## Projektstruktur

```
TeamMinigolf/
├── app/                    # Django-Anwendung
│   ├── config/             # Django Settings, URLs, WSGI
│   ├── core/               # Hauptapp (Models, Views, Templates)
│   │   ├── models.py       # Player, Course, Hole, Session, Score, AuditLog
│   │   ├── views.py        # Dashboard, CRUD, Scoring, Stats
│   │   ├── forms.py        # Formulare
│   │   ├── urls.py         # URL-Routing
│   │   ├── admin.py        # Django Admin-Konfiguration
│   │   ├── templates/      # Server-rendered HTML (Bootstrap 5)
│   │   └── tests/          # pytest / Django TestCase
│   ├── static/css/         # Custom CSS
│   ├── manage.py
│   └── requirements.txt
├── docker/
│   └── web/
│       ├── Dockerfile      # Python 3.12 + Gunicorn
│       └── entrypoint.sh   # DB-Wait, Migrate, Collectstatic
├── scripts/
│   ├── backup.sh           # MariaDB Dump + Rotation + Push
│   ├── restore.sh          # Restore aus Backup
│   ├── seed_data.py        # Beispieldaten
│   └── crontab.example     # Cron für tägliches Backup
├── docs/
│   └── ARCHITECTURE.md
├── docker-compose.yml
├── .env.example
├── .gitignore
├── pyproject.toml          # Ruff + pytest Config
└── README.md
```

---

## Datenbank & Migrationen

Django verwaltet das Schema über Migrationen. Bei jedem Start führt der Entrypoint `python manage.py migrate` aus.

```bash
# Migration erstellen (nach Model-Änderungen)
docker compose exec web python manage.py makemigrations

# Migration anwenden
docker compose exec web python manage.py migrate

# SQL einer Migration anzeigen
docker compose exec web python manage.py sqlmigrate core 0001
```

---

## Backup & Restore

### Tägliches Backup

```bash
# Einmalig manuell
docker compose --profile backup run --rm backup

# Cronjob installieren (auf dem Host)
crontab -e
# Zeile aus scripts/crontab.example einfügen
```

Das Backup erzeugt komprimierte SQL-Dumps im Docker-Volume `backup_data` und rotiert nach `BACKUP_RETAIN_DAYS` Tagen.

### Push zum Raspberry Pi

Das Backup-Script kann Dumps per `rsync` an ein Remote-Ziel pushen. Konfiguration über `.env`:
```
BACKUP_REMOTE_HOST=192.168.1.100
BACKUP_REMOTE_USER=pi
BACKUP_REMOTE_PATH=/home/pi/backups/minigolf
```

**Voraussetzungen auf dem Pi:**
```bash
mkdir -p /home/pi/backups/minigolf
```

**SSH-Keys** müssen eingerichtet sein (passwordless). Für Docker-Nutzung das `~/.ssh`-Verzeichnis als Volume mounten:
```yaml
# In docker-compose.yml unter backup:
volumes:
  - ~/.ssh:/root/.ssh:ro
```

### Restore

```bash
# Aus einem lokalen .sql.gz
./scripts/restore.sh ./mein_backup.sql.gz

# Aus dem Backup-Volume
docker compose --profile backup run --rm backup ls /backups/
docker compose --profile backup run --rm -v backup_data:/backups backup \
  bash -c "gunzip < /backups/minigolf_20260101_030000.sql.gz | mariadb -h db -u\$MYSQL_USER -p\$MYSQL_PASSWORD \$MYSQL_DATABASE"
```

---

## Cloudflare Tunnel

Empfohlenes Setup: `cloudflared` als eigener Container im Compose:

```yaml
# In docker-compose.yml – auskommentierte Sektion aktivieren:
services:
  cloudflared:
    image: cloudflare/cloudflared:latest
    container_name: minigolf-tunnel
    restart: unless-stopped
    command: tunnel run
    environment:
      - TUNNEL_TOKEN=${CLOUDFLARE_TUNNEL_TOKEN}
    depends_on:
      web:
        condition: service_healthy
    profiles:
      - tunnel
```

```bash
# .env ergänzen:
CLOUDFLARE_TUNNEL_TOKEN=your-tunnel-token

# Starten:
docker compose --profile tunnel up -d
```

**Wichtig:** `DJANGO_ALLOWED_HOSTS` in `.env` um die Tunnel-Domain ergänzen.

---

## Entwicklung

### Linting

```bash
# Ruff (im Container oder lokal)
pip install ruff
ruff check app/
ruff format app/
```

### Tests

```bash
# Im Container
docker compose exec web python manage.py test core

# Oder lokal (mit SQLite zum schnellen Testen)
cd app && python manage.py test core --settings=config.settings
```

---

## Features

### MVP (implementiert)
- **Auth**: Django-Login mit Sessions, Admin-Backend
- **Spielerverwaltung**: CRUD, Aktiv/Inaktiv
- **Anlagenverwaltung**: CRUD, automatische Bahnerstellung
- **Spieltage**: Erstellen, Spieler zuweisen, Live/Abgeschlossen
- **Live-Scoring**: Echtzeit-Eingabe pro Bahn mit Auto-Save
- **Nachtragen**: Ergebnisse nachträglich editierbar
- **Statistiken**: Durchschnitt pro Spieler/Bahn/Saison/Anlage
- **Leaderboard**: Rangliste mit Saisonfilter
- **Audit-Log**: Änderungen an Scores werden protokolliert
- **Backup**: Automatisierter DB-Dump mit Rotation + Remote-Push

### Nächste Schritte (Backlog)
- CSV/JSON Export & Import
- Erweitertes Rechte-System (Admin vs. User-Rolle)
- Trend-Charts (z. B. Chart.js)
- Kurs-Setup-Wizard (Par-Werte setzen)
- Spieler-Profile mit Detailstatistiken
- Progressive Web App (PWA) für Offline-Scoring
- E-Mail-Benachrichtigungen bei Spieltag-Einladungen
- API (DRF) für mobile Apps

