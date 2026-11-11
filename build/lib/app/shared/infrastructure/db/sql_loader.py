"""Carga sentencias SQL multiples de forma compatible con asyncpg."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

_DOLLAR_TAG = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$")


def split_sql(sql: str) -> Iterator[str]:
    """Separa por punto y coma sin romper strings ni bloques dollar-quoted."""
    start = 0
    index = 0
    quote: str | None = None
    dollar_tag: str | None = None
    line_comment = False
    block_comment = False

    while index < len(sql):
        char = sql[index]
        next_char = sql[index + 1] if index + 1 < len(sql) else ""

        if line_comment:
            if char == "\n":
                line_comment = False
            index += 1
            continue

        if block_comment:
            if char == "*" and next_char == "/":
                block_comment = False
                index += 2
            else:
                index += 1
            continue

        if quote:
            if char == quote:
                if next_char == quote:
                    index += 2
                    continue
                quote = None
            elif char == "\\" and quote == "'":
                index += 2
                continue
            index += 1
            continue

        if dollar_tag:
            if sql.startswith(dollar_tag, index):
                index += len(dollar_tag)
                dollar_tag = None
            else:
                index += 1
            continue

        if char == "-" and next_char == "-":
            line_comment = True
            index += 2
            continue
        if char == "/" and next_char == "*":
            block_comment = True
            index += 2
            continue
        if char in {"'", '"'}:
            quote = char
            index += 1
            continue
        if char == "$":
            match = _DOLLAR_TAG.match(sql, index)
            if match:
                dollar_tag = match.group(0)
                index = match.end()
                continue
        if char == ";":
            statement = sql[start:index].strip()
            if statement:
                yield statement
            start = index + 1
        index += 1

    statement = sql[start:].strip()
    if statement:
        yield statement


def execute_sql_file(operation, path: Path) -> None:
    for statement in split_sql(path.read_text(encoding="utf-8")):
        operation.execute(statement)
