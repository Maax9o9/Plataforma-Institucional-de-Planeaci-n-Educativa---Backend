"""Mensajes seguros de validación HTTP, sin devolver valores recibidos."""


def validation_detail(error: dict) -> dict:
    kind = error["type"]
    messages = {
        "missing": "Este campo es obligatorio.",
        "extra_forbidden": "Este campo no está permitido. Revise su nombre y el endpoint.",
        "string_type": "Debe enviar un texto.",
        "string_too_short": "El texto está vacío o es más corto de lo permitido.",
        "string_too_long": "El texto supera la longitud permitida.",
        "int_parsing": "Debe enviar un número entero válido.",
        "int_type": "Debe enviar un número entero.",
        "decimal_parsing": "Debe enviar un número decimal válido.",
        "decimal_max_digits": "El número supera la cantidad de dígitos permitida.",
        "decimal_max_places": "El número tiene más decimales de los permitidos.",
        "finite_number": "El número debe ser finito.",
        "greater_than_equal": "El valor es menor que el mínimo permitido.",
        "less_than_equal": "El valor supera el máximo permitido.",
        "literal_error": "Seleccione una de las opciones permitidas.",
        "list_type": "Debe enviar una lista.",
        "too_short": "La lista contiene menos elementos de los requeridos.",
        "too_long": "La lista contiene más elementos de los permitidos.",
        "json_invalid": "El cuerpo no es JSON válido.",
        "date_from_datetime_parsing": "Use una fecha válida con formato AAAA-MM-DD.",
        "date_parsing": "Use una fecha válida con formato AAAA-MM-DD.",
    }
    message = messages.get(kind, "El valor no es válido para este campo.")
    if kind == "value_error":
        # Los validadores propios usan mensajes fijos, sin interpolar datos de la solicitud.
        message = error["msg"].removeprefix("Value error, ")
    loc = error["loc"]
    path = loc[1:] if loc and loc[0] in {"body", "query", "path", "header", "cookie"} else loc
    return {"loc": loc, "field": ".".join(map(str, path)), "msg": message, "type": kind}
