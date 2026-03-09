#!/bin/bash
set -e

echo "Waiting for database..."
python << 'EOF'
import time, os, MySQLdb
for i in range(30):
    try:
        MySQLdb.connect(
            host=os.environ.get("DATABASE_HOST", "db"),
            port=int(os.environ.get("DATABASE_PORT", 3306)),
            user=os.environ["MYSQL_USER"],
            password=os.environ["MYSQL_PASSWORD"],
            database=os.environ["MYSQL_DATABASE"],
        )
        print("Database ready!")
        break
    except Exception:
        print(f"DB not ready yet ({i+1}/30)...")
        time.sleep(2)
else:
    print("Database not available after 60s, exiting.")
    exit(1)
EOF

echo "Running migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Starting server..."
exec "$@"
