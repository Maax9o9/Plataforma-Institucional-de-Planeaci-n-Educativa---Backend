"""Seed idempotente del ambiente compartido de integracion."""

from __future__ import annotations

import asyncio
import os
from datetime import date
from hashlib import sha256
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from app.core.config import get_settings
from app.core.security import hash_password

TEST_ACCOUNTS = (
    ("admin.sistema@upchiapas.edu.mx", "Administracion del sistema", "admin_sistema", None),
    ("planeacion@upchiapas.edu.mx", "Equipo de Planeacion", "planeacion", "PLN"),
    (
        "responsable.area@upchiapas.edu.mx",
        "Responsable de Ingenieria Biomedica",
        "responsable_area",
        "IBIO",
    ),
    ("rectoria@upchiapas.edu.mx", "Rectoria", "rectoria", "REC"),
    ("consulta@upchiapas.edu.mx", "Usuario de consulta", "consulta", "PLN"),
)


async def _scalar(connection: AsyncConnection, sql: str, **params) -> int:
    value = await connection.scalar(text(sql), params)
    if value is None:
        raise RuntimeError("El seed no pudo recuperar el identificador insertado.")
    return int(value)


async def _area(
    connection: AsyncConnection,
    code: str,
    name: str,
    area_type: str,
    color: str,
) -> int:
    return await _scalar(
        connection,
        """
        INSERT INTO areas (codigo, nombre, tipo, color, activo)
        VALUES (:code, :name, :area_type, :color, TRUE)
        ON CONFLICT (nombre) DO UPDATE SET
            codigo = EXCLUDED.codigo,
            tipo = EXCLUDED.tipo,
            color = EXCLUDED.color,
            activo = TRUE
        RETURNING id
        """,
        code=code,
        name=name,
        area_type=area_type,
        color=color,
    )


async def _user(
    connection: AsyncConnection,
    email: str,
    name: str,
    role: str,
    area_id: int | None,
    password_hash: str,
) -> int:
    user_id = await _scalar(
        connection,
        """
        INSERT INTO usuarios (
            nombre, correo, hash_password, area_id, activo,
            notificar_correo, requiere_configurar_contrasena
        ) VALUES (:name, :email, :password_hash, :area_id, TRUE, TRUE, FALSE)
        ON CONFLICT (correo) DO UPDATE SET
            nombre = EXCLUDED.nombre,
            hash_password = EXCLUDED.hash_password,
            area_id = EXCLUDED.area_id,
            activo = TRUE,
            requiere_configurar_contrasena = FALSE
        RETURNING id
        """,
        name=name,
        email=email,
        password_hash=password_hash,
        area_id=area_id,
    )
    await connection.execute(
        text("DELETE FROM usuario_roles WHERE usuario_id = :user_id"),
        {"user_id": user_id},
    )
    await connection.execute(
        text(
            "INSERT INTO usuario_roles (usuario_id, rol) "
            "VALUES (:user_id, CAST(:role AS rol))"
        ),
        {"user_id": user_id, "role": role},
    )
    return user_id


async def _reference(connection: AsyncConnection, table: str, key: str, name: str) -> int:
    if table == "criterios_seaes":
        sql = """
            INSERT INTO criterios_seaes (clave, nombre, activo)
            VALUES (:key, :name, TRUE)
            ON CONFLICT (clave) DO UPDATE SET nombre = EXCLUDED.nombre, activo = TRUE
            RETURNING id
        """
    elif table == "tipos_indicador":
        sql = """
            INSERT INTO tipos_indicador (nombre, activo)
            VALUES (:name, TRUE)
            ON CONFLICT (nombre) DO UPDATE SET activo = TRUE
            RETURNING id
        """
    else:
        raise ValueError("Catalogo no permitido por el seed.")
    return await _scalar(connection, sql, key=key, name=name)


async def _instrument(connection: AsyncConnection, code: str, name: str) -> int:
    return await _scalar(
        connection,
        """
        INSERT INTO instrumentos (codigo, nombre, descripcion, activo)
        VALUES (:code, :name, :description, TRUE)
        ON CONFLICT (nombre) DO UPDATE SET codigo = EXCLUDED.codigo, activo = TRUE
        RETURNING id
        """,
        code=code,
        name=name,
        description=name,
    )


async def _period(
    connection: AsyncConnection,
    *,
    periodicity: str,
    label: str,
    starts_on: str,
    ends_on: str,
    status: str,
    reopened_by: int | None = None,
    reason: str | None = None,
) -> int:
    return await _scalar(
        connection,
        """
        INSERT INTO periodos (
            tipo, periodicidad, anio, etiqueta, fecha_inicio, fecha_limite,
            estado, motivo_reapertura, reabierto_por, reabierto_en
        ) VALUES (
            'indicadores', CAST(:periodicity AS periodicidad), 2026, :label,
            CAST(:starts_on AS date), CAST(:ends_on AS date),
            CAST(:status AS estado_periodo), CAST(:reason AS text),
            CAST(:reopened_by AS integer),
            CASE WHEN CAST(:reason AS text) IS NULL THEN NULL ELSE now() END
        )
        ON CONFLICT (tipo, anio, etiqueta) DO UPDATE SET
            periodicidad = EXCLUDED.periodicidad,
            fecha_inicio = EXCLUDED.fecha_inicio,
            fecha_limite = EXCLUDED.fecha_limite,
            estado = EXCLUDED.estado,
            motivo_reapertura = EXCLUDED.motivo_reapertura,
            reabierto_por = EXCLUDED.reabierto_por,
            reabierto_en = EXCLUDED.reabierto_en
        RETURNING id
        """,
        periodicity=periodicity,
        label=label,
        starts_on=date.fromisoformat(starts_on),
        ends_on=date.fromisoformat(ends_on),
        status=status,
        reason=reason,
        reopened_by=reopened_by,
    )


async def _indicator(
    connection: AsyncConnection,
    *,
    key: str,
    name: str,
    area_id: int,
    responsible_id: int,
    periodicity: str,
    indicator_type_id: int,
    instrument_id: int,
    criterion_id: int | None,
) -> int:
    indicator_id = await _scalar(
        connection,
        """
        INSERT INTO indicadores (
            clave, nombre, definicion, metodo_calculo, unidad_medida,
            tipo_indicador_id, area_id, responsable_id, periodicidad,
            umbral_verde_min, umbral_amarillo_min, activo
        ) VALUES (
            :key, :name, :definition, 'Resultado / meta * 100', 'Porcentaje',
            :indicator_type_id, :area_id, :responsible_id,
            CAST(:periodicity AS periodicidad), 90, 60, TRUE
        )
        ON CONFLICT (clave) DO UPDATE SET
            nombre = EXCLUDED.nombre,
            tipo_indicador_id = EXCLUDED.tipo_indicador_id,
            area_id = EXCLUDED.area_id,
            responsable_id = EXCLUDED.responsable_id,
            periodicidad = EXCLUDED.periodicidad,
            activo = TRUE,
            actualizado_en = now()
        RETURNING id
        """,
        key=key,
        name=name,
        definition=name,
        indicator_type_id=indicator_type_id,
        area_id=area_id,
        responsible_id=responsible_id,
        periodicity=periodicity,
    )
    await connection.execute(
        text(
            """
            INSERT INTO indicador_instrumentos (indicador_id, instrumento_id)
            VALUES (:indicator_id, :instrument_id)
            ON CONFLICT DO NOTHING
            """
        ),
        {"indicator_id": indicator_id, "instrument_id": instrument_id},
    )
    if criterion_id is not None:
        await connection.execute(
            text(
                """
                INSERT INTO indicador_criterios_seaes (indicador_id, criterio_seaes_id)
                VALUES (:indicator_id, :criterion_id)
                ON CONFLICT DO NOTHING
                """
            ),
            {"indicator_id": indicator_id, "criterion_id": criterion_id},
        )
    await connection.execute(
        text(
            """
            INSERT INTO lineas_base (indicador_id, anio, periodo, valor)
            VALUES (:indicator_id, 2025, 'Cierre 2025', 50)
            ON CONFLICT (indicador_id) DO UPDATE SET valor = EXCLUDED.valor
            """
        ),
        {"indicator_id": indicator_id},
    )
    return indicator_id


async def _capture(
    connection: AsyncConnection,
    indicator_id: int,
    period_id: int,
    capturer_id: int,
    status: str,
    result: int,
    progress: int | None,
    semaphore: str | None,
) -> int:
    return await _scalar(
        connection,
        """
        INSERT INTO capturas (
            indicador_id, periodo_id, capturista_id, resultado,
            datos_fuente, actividad_realizada, observaciones, estado,
            pct_avance, semaforo
        ) VALUES (
            :indicator_id, :period_id, :capturer_id, :result,
            'Seed de integracion', 'Validacion del flujo', 'Registro reproducible',
            CAST(:status AS estado_captura), :progress, CAST(:semaphore AS semaforo)
        )
        ON CONFLICT (indicador_id, periodo_id) DO UPDATE SET
            capturista_id = EXCLUDED.capturista_id,
            resultado = EXCLUDED.resultado,
            estado = EXCLUDED.estado,
            pct_avance = EXCLUDED.pct_avance,
            semaforo = EXCLUDED.semaforo,
            actualizado_en = now()
        RETURNING id
        """,
        indicator_id=indicator_id,
        period_id=period_id,
        capturer_id=capturer_id,
        status=status,
        result=result,
        progress=progress,
        semaphore=semaphore,
    )


async def _evidence(
    connection: AsyncConnection,
    *,
    capture_id: int,
    user_id: int,
    name: str,
    evidence_type: str,
    versions: list[tuple[str, str | None, int | None, str | None]],
) -> None:
    evidence_id = await connection.scalar(
        text("SELECT id FROM evidencias WHERE nombre = :name ORDER BY id LIMIT 1"),
        {"name": name},
    )
    if evidence_id is None:
        evidence_id = await _scalar(
            connection,
            """
            INSERT INTO evidencias (nombre, descripcion, fecha, tipo, subida_por)
            VALUES (
                :name, 'Evidencia reproducible del seed', CURRENT_DATE,
                CAST(:evidence_type AS tipo_evidencia), :user_id
            ) RETURNING id
            """,
            name=name,
            evidence_type=evidence_type,
            user_id=user_id,
        )
    await connection.execute(
        text(
            """
            INSERT INTO evidencia_vinculos (evidencia_id, entidad, entidad_id, vinculado_por)
            VALUES (:evidence_id, 'captura', :capture_id, :user_id)
            ON CONFLICT DO NOTHING
            """
        ),
        {"evidence_id": evidence_id, "capture_id": capture_id, "user_id": user_id},
    )
    for path, mime_type, size, checksum in versions:
        await connection.execute(
            text(
                """
                INSERT INTO evidencia_versiones (
                    evidencia_id, ruta_o_url, mime_type, tamanio_bytes,
                    checksum_sha256, usuario_id
                )
                SELECT
                    CAST(:evidence_id AS integer),
                    CAST(:path AS text),
                    CAST(:mime_type AS text),
                    CAST(:size AS bigint),
                    CAST(:checksum AS text),
                    CAST(:user_id AS integer)
                WHERE NOT EXISTS (
                    SELECT 1 FROM evidencia_versiones
                    WHERE evidencia_id = CAST(:evidence_id AS integer)
                      AND ruta_o_url = CAST(:path AS text)
                )
                """
            ),
            {
                "evidence_id": evidence_id,
                "path": path,
                "mime_type": mime_type,
                "size": size,
                "checksum": checksum,
                "user_id": user_id,
            },
        )


async def seed() -> None:
    settings = get_settings()
    password = os.getenv("SEED_TEST_PASSWORD")
    if settings.database_url is None:
        raise RuntimeError("DATABASE_URL es obligatoria para ejecutar el seed.")
    if not password or len(password) < 12:
        raise RuntimeError("SEED_TEST_PASSWORD debe configurarse con al menos 12 caracteres.")
    password_hash = hash_password(password)
    engine = create_async_engine(settings.database_url)
    try:
        async with engine.begin() as connection:
            areas = {
                "PLN": await _area(
                    connection, "PLN", "Direccion de Planeacion", "administrativa", "#1F4E78"
                ),
                "REC": await _area(
                    connection, "REC", "Rectoria", "administrativa", "#7030A0"
                ),
                "IBIO": await _area(
                    connection,
                    "IBIO",
                    "Ingenieria Biomedica",
                    "programa_educativo",
                    "#01ADEF",
                ),
                "ISOF": await _area(
                    connection,
                    "ISOF",
                    "Ingenieria en Software",
                    "programa_educativo",
                    "#00A651",
                ),
            }
            users = {}
            for email, name, role, area_code in TEST_ACCOUNTS:
                users[role] = await _user(
                    connection,
                    email,
                    name,
                    role,
                    areas[area_code] if area_code else None,
                    password_hash,
                )

            instruments = {
                code: await _instrument(connection, code, name)
                for code, name in (
                    ("PIDE", "PIDE"),
                    ("SEAES", "SEAES"),
                    ("COCODI", "COCODI"),
                    ("INST", "Institucional"),
                )
            }
            criteria = [
                await _reference(connection, "criterios_seaes", key, name)
                for key, name in (
                    ("C1", "Compromiso con la responsabilidad social"),
                    ("C2", "Equidad social y de genero"),
                    ("C3", "Inclusion y excelencia"),
                )
            ]
            indicator_types = [
                await _reference(connection, "tipos_indicador", "", name)
                for name in ("Gestion", "Resultado", "Impacto")
            ]
            periods = {
                "monthly": await _period(
                    connection,
                    periodicity="mensual",
                    label="Agosto 2026 - Seed",
                    starts_on="2026-08-01",
                    ends_on="2026-08-31",
                    status="abierto",
                ),
                "four_month": await _period(
                    connection,
                    periodicity="cuatrimestral",
                    label="Segundo cuatrimestre 2026 - Seed",
                    starts_on="2026-05-01",
                    ends_on="2026-08-31",
                    status="abierto",
                ),
                "closed": await _period(
                    connection,
                    periodicity="mensual",
                    label="Julio 2026 - Cerrado Seed",
                    starts_on="2026-07-01",
                    ends_on="2026-07-31",
                    status="cerrado",
                ),
                "reopened": await _period(
                    connection,
                    periodicity="mensual",
                    label="Junio 2026 - Reabierto Seed",
                    starts_on="2026-06-01",
                    ends_on="2026-06-30",
                    status="abierto",
                    reopened_by=users["planeacion"],
                    reason="Correccion autorizada para pruebas de integracion",
                ),
            }
            specs = (
                ("PIDE-01", "Matricula total", "IBIO", "mensual", "PIDE", 0, 0),
                ("PIDE-02", "Retencion escolar", "IBIO", "mensual", "PIDE", 1, 1),
                ("SEAES-01", "Cobertura SEAES", "ISOF", "cuatrimestral", "SEAES", 2, 2),
                ("COCODI-01", "Acciones de control", "IBIO", "mensual", "COCODI", 0, 0),
                ("INST-01", "Satisfaccion institucional", "ISOF", "mensual", "INST", 1, 1),
                ("PIDE-03", "Eficiencia terminal", "IBIO", "mensual", "PIDE", 2, 2),
            )
            indicators = []
            for key, name, area_code, periodicity, instrument, type_index, criterion in specs:
                indicators.append(
                    await _indicator(
                        connection,
                        key=key,
                        name=name,
                        area_id=areas[area_code],
                        responsible_id=users["responsable_area"],
                        periodicity=periodicity,
                        indicator_type_id=indicator_types[type_index],
                        instrument_id=instruments[instrument],
                        criterion_id=criteria[criterion],
                    )
                )
            for indicator_id in indicators:
                target_period = (
                    periods["four_month"]
                    if indicator_id == indicators[2]
                    else periods["monthly"]
                )
                await connection.execute(
                    text(
                        """
                        INSERT INTO metas (indicador_id, periodo_id, valor)
                        VALUES (:indicator_id, :period_id, 40)
                        ON CONFLICT (indicador_id, periodo_id) DO UPDATE SET valor = 40
                        """
                    ),
                    {"indicator_id": indicator_id, "period_id": target_period},
                )
            captures = [
                await _capture(
                    connection,
                    indicators[0],
                    periods["monthly"],
                    users["responsable_area"],
                    "borrador",
                    20,
                    None,
                    None,
                ),
                await _capture(
                    connection,
                    indicators[1],
                    periods["monthly"],
                    users["responsable_area"],
                    "enviado",
                    30,
                    None,
                    None,
                ),
                await _capture(
                    connection,
                    indicators[2],
                    periods["four_month"],
                    users["responsable_area"],
                    "validado",
                    40,
                    100,
                    "verde",
                ),
                await _capture(
                    connection,
                    indicators[3],
                    periods["monthly"],
                    users["responsable_area"],
                    "rechazado",
                    10,
                    None,
                    None,
                ),
            ]

            await _evidence(
                connection,
                capture_id=captures[1],
                user_id=users["responsable_area"],
                name="Enlace institucional Seed",
                evidence_type="enlace",
                versions=[("https://example.com/evidencias/seed", None, None, None)],
            )
            pdf = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n%%EOF\n"
            first_name = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.pdf"
            second_name = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb.pdf"
            storage = Path(settings.upload_directory).resolve()
            storage.mkdir(parents=True, exist_ok=True)
            (storage / first_name).write_bytes(pdf)
            (storage / second_name).write_bytes(pdf + b"% version 2\n")
            await _evidence(
                connection,
                capture_id=captures[2],
                user_id=users["responsable_area"],
                name="Reporte versionado Seed",
                evidence_type="archivo",
                versions=[
                    (first_name, "application/pdf", len(pdf), sha256(pdf).hexdigest()),
                    (
                        second_name,
                        "application/pdf",
                        len(pdf + b"% version 2\n"),
                        sha256(pdf + b"% version 2\n").hexdigest(),
                    ),
                ],
            )
            for capture_id, status in zip(
                captures,
                ("borrador", "enviado", "validado", "rechazado"),
                strict=True,
            ):
                await connection.execute(
                    text(
                        """
                        INSERT INTO cambios_estado (
                            entidad, entidad_id, de_estado, a_estado,
                            usuario_id, comentario
                        )
                        SELECT 'captura', :capture_id, NULL,
                               CAST(:status AS estado_captura), :user_id,
                               CASE WHEN :status = 'rechazado'
                                    THEN 'Correccion requerida por el seed' ELSE NULL END
                        WHERE NOT EXISTS (
                            SELECT 1 FROM cambios_estado
                            WHERE entidad = 'captura' AND entidad_id = :capture_id
                              AND a_estado = CAST(:status AS estado_captura)
                        )
                        """
                    ),
                    {
                        "capture_id": capture_id,
                        "status": status,
                        "user_id": users["planeacion"],
                    },
                )
            await connection.execute(
                text(
                    """
                    INSERT INTO bitacora (
                        usuario_id, evento, accion, entidad, entidad_id, valor_nuevo
                    )
                    SELECT :user_id, 'IntegrationSeedRestored', 'seed_restored',
                           'system', 1, '{"source":"seed_integration"}'::jsonb
                    WHERE NOT EXISTS (
                        SELECT 1 FROM bitacora
                        WHERE accion = 'seed_restored' AND entidad = 'system' AND entidad_id = 1
                    )
                    """
                ),
                {"user_id": users["admin_sistema"]},
            )
    finally:
        await engine.dispose()
    print("Seed de integracion restaurado. Las contrasenas no se imprimen.")


if __name__ == "__main__":
    asyncio.run(seed())
