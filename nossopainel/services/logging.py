from __future__ import annotations

from pathlib import Path
from typing import Union


PathLike = Union[str, Path]


def append_line(log_path: PathLike, message: str) -> None:
    """
    Acrescenta uma linha ao arquivo indicado, criando o diretório pai caso necessário.

    Parâmetros:
        log_path: Caminho absoluto ou relativo do arquivo de log.
        message: Texto que será gravado em uma única linha.
    """
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handler:
        handler.write(message + "\n")
