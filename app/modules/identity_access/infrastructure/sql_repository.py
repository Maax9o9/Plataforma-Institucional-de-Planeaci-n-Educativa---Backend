"""Adaptadores PostgreSQL de identity_access."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.shared.domain.exceptions import ConflictError
from app.shared.domain.value_objects import Email

from ..domain.entities import User
from ..domain.ports.refresh_token_repository import RefreshTokenRecord
from ..domain.value_objects import Role
from .models import RefreshTokenModel, UserModel, UserRoleModel


class SqlAlchemyUserRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def _to_domain(self, session: AsyncSession, model: UserModel) -> User:
        roles = await session.scalars(
            select(UserRoleModel.rol).where(UserRoleModel.usuario_id == model.id)
        )
        return User(
            id=model.id,
            email=Email(model.correo),
            full_name=model.nombre,
            password_hash=model.hash_password,
            roles=frozenset(Role.from_value(role) for role in roles),
            area_id=model.area_id,
            is_active=model.activo,
            notify_email=model.notificar_correo,
            password_setup_required=model.requiere_configurar_contrasena,
            created_at=model.creado_en,
            updated_at=model.actualizado_en,
        )

    async def get_by_id(self, user_id: int) -> User | None:
        async with self.session_factory() as session:
            model = await session.get(UserModel, user_id)
            return await self._to_domain(session, model) if model else None

    async def get_by_email(self, email: str) -> User | None:
        async with self.session_factory() as session:
            result = await session.execute(
                select(UserModel).where(func.lower(UserModel.correo) == email.strip().lower())
            )
            model = result.scalar_one_or_none()
            return await self._to_domain(session, model) if model else None

    async def list(self, *, active_only: bool = False) -> list[User]:
        async with self.session_factory() as session:
            statement = select(UserModel).order_by(UserModel.id)
            if active_only:
                statement = statement.where(UserModel.activo.is_(True))
            models = (await session.scalars(statement)).all()
            return [await self._to_domain(session, model) for model in models]

    async def add(self, user: User) -> None:
        now = datetime.now(UTC)
        model = UserModel(
            nombre=user.full_name,
            correo=user.email.value,
            hash_password=user.password_hash,
            area_id=user.area_id,
            activo=user.is_active,
            notificar_correo=user.notify_email,
            requiere_configurar_contrasena=user.password_setup_required,
            creado_en=now,
            actualizado_en=now,
        )
        async with self.session_factory() as session:
            try:
                session.add(model)
                await session.flush()
                session.add_all(
                    UserRoleModel(usuario_id=model.id, rol=role.value) for role in user.roles
                )
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise ConflictError("Ya existe un usuario con ese correo electronico.") from exc
        user.id = model.id
        user.created_at = now
        user.updated_at = now

    async def update(self, user: User) -> None:
        async with self.session_factory() as session:
            try:
                model = await session.get(UserModel, user.id)
                if model is None:
                    return
                model.correo = user.email.value
                model.nombre = user.full_name
                model.area_id = user.area_id
                model.activo = user.is_active
                model.notificar_correo = user.notify_email
                model.requiere_configurar_contrasena = user.password_setup_required
                model.actualizado_en = user.updated_at
                await session.execute(
                    delete(UserRoleModel).where(UserRoleModel.usuario_id == user.id)
                )
                session.add_all(
                    UserRoleModel(usuario_id=user.id, rol=role.value) for role in user.roles
                )
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise ConflictError("Ya existe un usuario con ese correo electronico.") from exc


class SqlAlchemyRefreshTokenStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory
        self._lock = asyncio.Lock()

    @staticmethod
    def _hash(token: str) -> str:
        return sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _record(model: RefreshTokenModel, *, active: bool) -> RefreshTokenRecord:
        return RefreshTokenRecord(
            token_id=model.jti,
            user_id=model.usuario_id,
            session_id=model.session_id or model.jti,
            expires_at=model.expira_en,
            active=active,
        )

    async def save(
        self,
        *,
        token: str,
        token_id: UUID,
        user_id: int,
        session_id: UUID,
        expires_at: datetime,
    ) -> None:
        async with self.session_factory() as session:
            session.add(
                RefreshTokenModel(
                    id=uuid4(),
                    usuario_id=user_id,
                    jti=token_id,
                    hash_token=self._hash(token),
                    session_id=session_id,
                    emitido_en=datetime.now(UTC),
                    expira_en=expires_at,
                )
            )
            await session.commit()

    async def consume(self, *, token: str, token_id: UUID) -> RefreshTokenRecord | None:
        async with self._lock:
            async with self.session_factory() as session:
                result = await session.execute(
                    select(RefreshTokenModel)
                    .where(RefreshTokenModel.jti == token_id)
                    .with_for_update()
                )
                model = result.scalar_one_or_none()
                if model is None or model.hash_token != self._hash(token):
                    return None

                now = datetime.now(UTC)
                active = model.revocado_en is None and model.expira_en > now
                record = self._record(model, active=active)
                if active:
                    model.revocado_en = now
                    await session.commit()
                return record

    async def revoke(self, token_id: UUID) -> None:
        async with self.session_factory() as session:
            model = (
                await session.execute(
                    select(RefreshTokenModel).where(RefreshTokenModel.jti == token_id)
                )
            ).scalar_one_or_none()
            if model and model.revocado_en is None:
                model.revocado_en = datetime.now(UTC)
                await session.commit()

    async def revoke_session(self, session_id: UUID) -> None:
        async with self.session_factory() as session:
            models = await session.scalars(
                select(RefreshTokenModel).where(
                    RefreshTokenModel.session_id == session_id,
                    RefreshTokenModel.revocado_en.is_(None),
                )
            )
            now = datetime.now(UTC)
            for model in models:
                model.revocado_en = now
            await session.commit()

    async def revoke_user(self, user_id: int) -> None:
        async with self.session_factory() as session:
            models = await session.scalars(
                select(RefreshTokenModel).where(
                    RefreshTokenModel.usuario_id == user_id,
                    RefreshTokenModel.revocado_en.is_(None),
                )
            )
            now = datetime.now(UTC)
            for model in models:
                model.revocado_en = now
            await session.commit()
