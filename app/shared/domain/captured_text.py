from __future__ import annotations

INVISIBLES_QUE_SOBREVIVEN_AL_RECORTE = ("\u200b", "\ufeff", "\u00ad")


def recortado_sin_invisibles(capturado: str) -> str:
    sin_invisibles = capturado
    for invisible in INVISIBLES_QUE_SOBREVIVEN_AL_RECORTE:
        sin_invisibles = sin_invisibles.replace(invisible, "")
    return sin_invisibles.strip()
