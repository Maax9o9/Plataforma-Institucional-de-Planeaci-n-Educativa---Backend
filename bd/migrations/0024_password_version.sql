-- Revocación persistente de todas las sesiones al cambiar la contraseña.
ALTER TABLE usuarios ADD COLUMN password_version INTEGER NOT NULL DEFAULT 0;
ALTER TABLE usuarios ADD CONSTRAINT ck_usuarios_password_version CHECK (password_version >= 0);
