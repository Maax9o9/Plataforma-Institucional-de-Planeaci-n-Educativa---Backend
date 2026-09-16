# Plantillas institucionales

- `base.html`: diseño compartido, basado en la referencia proporcionada por el usuario.
- `messages/*.json`: asunto, título, cuerpo y botón predeterminados por tipo.
- `assets/`: imágenes originales proporcionadas; el logo horizontal y dragón se adjuntan vía CID.

El único marcador que puede escribir un administrador es `{{nombre}}` en los textos.
Los `$subject`, `$title`, `$label`, `$name`, `$body`, `$detail` y `$button` del HTML son
puntos de inserción internos del renderizador: no son un lenguaje de edición pública.
El renderizador escapa los datos y conserva por separado los detalles/enlaces operativos.

Para cambiar textos desde el frontend sin desplegar, usar `/api/v1/correos/plantillas`.
Para instrucciones completas ver `docs/INTEGRACION_PLANTILLAS_CORREO.md` en la raíz del proyecto.
