# Plantillas institucionales

- `base.html`: diseño compartido, basado en la referencia proporcionada por el usuario.
- `messages/*.json`: asunto, título, cuerpo y botón predeterminados por tipo.
- `assets/`: imágenes originales proporcionadas; el logo horizontal y dragón se adjuntan vía CID.

El único marcador que puede escribir un administrador es `{{nombre}}` en los textos.
Los `$subject`, `$title`, `$label`, `$name`, `$body`, `$detail` y `$button` del HTML son
puntos de inserción internos del renderizador: no son un lenguaje de edición pública.
El renderizador escapa los datos y conserva por separado los detalles/enlaces operativos.

El ancho máximo es 720 px; el respaldo condicional de Outlook debe coincidir.
Las clases de tema también se usan en los párrafos/botones generados por `rendering.py`.
No eliminar los contenedores `gmail-screen`/`gmail-difference`: protegen el texto blanco
en ciertos modos oscuros de Gmail. Sus estilos sólo se activan mediante el selector
`u + .email-body`, para no introducir fondos negros en otros clientes.
La placa clara del logo evita que sus trazos azules se pierdan sobre un fondo oscuro.

Para cambiar textos desde el frontend sin desplegar, usar `/api/v1/correos/plantillas`.
Para instrucciones completas ver `docs/INTEGRACION_PLANTILLAS_CORREO.md` en la raíz del proyecto.
