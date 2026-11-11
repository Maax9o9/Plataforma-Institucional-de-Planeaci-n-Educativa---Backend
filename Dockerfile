FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN groupadd --system app && useradd --system --gid app --create-home app

COPY pyproject.toml README.md ./
COPY app ./app
COPY alembic.ini ./alembic.ini
COPY alembic ./alembic
COPY bd ./bd

RUN pip install .

RUN mkdir -p /app/var/uploads && chown -R app:app /app
USER app

EXPOSE 8000

# Cuántos procesos atienden las peticiones. Uno solo tiene por techo un núcleo
# —Python no reparte un proceso entre varios— y el ingreso al sistema lo
# bloquea durante los 100 ms que cuesta verificar la contraseña. Dos procesos
# por vCPU es el punto donde deja de haber cola sin desperdiciar memoria.
# El programador de recordatorios no se duplica: lo toma un solo proceso con
# un candado de PostgreSQL (app/shared/infrastructure/db/turno_exclusivo.py).
ENV WEB_CONCURRENCY=2

CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY} --proxy-headers --forwarded-allow-ips '*'"]
