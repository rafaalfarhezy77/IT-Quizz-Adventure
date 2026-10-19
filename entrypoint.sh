#!/bin/sh
set -e

# Pastikan folder instance dan direktori upload file fisik tersedia
mkdir -p /app/instance/uploads/hardware

# Inisialisasi awal database SQLite jika belum ada di volume instance
if [ ! -f /app/instance/competition.db ]; then
    echo "================================================================"
    echo " Database tidak ditemukan di /app/instance/competition.db       "
    echo " Menjalankan seed awal (python seed.py)...                      "
    echo "================================================================"
    python seed.py
    echo "✓ Inisialisasi database awal berhasil diselesaikan!"
else
    echo "✓ Database /app/instance/competition.db ditemukan. Menjalankan aplikasi..."
fi

# Jalankan server WSGI production Gunicorn
echo "🚀 Memulai server Gunicorn pada port ${PORT:-5000}..."
exec gunicorn \
    --bind "0.0.0.0:${PORT:-5000}" \
    --workers "${GUNICORN_WORKERS:-4}" \
    --threads "${GUNICORN_THREADS:-2}" \
    --timeout "${GUNICORN_TIMEOUT:-120}" \
    --access-logfile - \
    --error-logfile - \
    "app:app"
