"""Alta administrativa explícita; no guarda contraseñas en configuración."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys

from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings
from app.modules.audit.infrastructure.sql_repository import SqlAlchemyAuditRepository
from app.modules.audit.infrastructure.subscriber import register_audit_subscriber
from app.modules.identity_access.application.dto import RegisterUserCommand
from app.modules.identity_access.application.use_cases.create_user import CreateUser
from app.modules.identity_access.domain.value_objects import Role
from app.modules.identity_access.infrastructure.security import Argon2PasswordHasher
from app.modules.identity_access.infrastructure.sql_repository import SqlAlchemyUserRepository
from app.shared.domain.exceptions import AppError, ValidationError
from app.shared.infrastructure.db.session import create_database
from app.shared.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWorkFactory
from app.shared.infrastructure.events.in_memory_event_bus import InMemoryEventBus


async def provision_admin(settings: Settings, *, email: str, name: str, password: str) -> int:
    if not settings.database_url:
        raise ValidationError("DATABASE_URL es obligatoria: el administrador debe persistir en BD.")
    engine, factory = create_database(settings)
    assert engine is not None and factory is not None
    try:
        events = InMemoryEventBus()
        register_audit_subscriber(
            events, SqlAlchemyAuditRepository(factory), SqlAlchemyUserRepository(factory)
        )
        async with SqlAlchemyUnitOfWorkFactory(factory)():
            user = await CreateUser(
                SqlAlchemyUserRepository(factory), Argon2PasswordHasher(), events
            ).execute(
                RegisterUserCommand(
                    email=email,
                    full_name=name,
                    password=password,
                    roles={Role.ADMIN_SISTEMA},
                    area_id=None,
                )
            )
        return user.id
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--correo", required=True)
    parser.add_argument("--nombre", required=True)
    args = parser.parse_args()
    if not sys.stdin.isatty():
        parser.error("Ejecuta en una terminal interactiva para introducir la contraseña oculta.")
    try:
        password = getpass.getpass("Contraseña del administrador: ")
        confirmation = getpass.getpass("Repite la contraseña: ")
        if password != confirmation:
            raise ValidationError("Las contraseñas no coinciden.")
        user_id = asyncio.run(
            provision_admin(
                Settings(database_echo=False),
                email=args.correo,
                name=args.nombre,
                password=password,
            )
        )
    except AppError as exc:
        print(exc.message, file=sys.stderr)
        return 1
    except SQLAlchemyError:
        print(
            "No se pudo completar el alta en PostgreSQL. Comprueba la conexión y las migraciones.",
            file=sys.stderr,
        )
        return 1
    except (KeyboardInterrupt, EOFError):
        print("Alta cancelada.", file=sys.stderr)
        return 1
    print(f"Administrador creado en la base de datos (id={user_id}). Ya puede iniciar sesión.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
