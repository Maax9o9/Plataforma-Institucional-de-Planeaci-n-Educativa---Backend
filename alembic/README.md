# Alembic

Alembic versiona la ejecucion de los archivos SQL de `../bd/migrations/`.
Los modelos SQLAlchemy no generan el esquema automaticamente.

Desde `backend`:

```powershell
alembic upgrade head
alembic current
```
