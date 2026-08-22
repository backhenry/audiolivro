"""Achar e executar o ffmpeg, com erros que dizem o que aconteceu.

`subprocess.run(["ffmpeg", ...])` espalhado pelo código vira dívida
rápido. Aqui centralizamos as duas coisas chatas que o audiolivro precisa:

1. Achar o binário e falhar cedo, com a instrução de instalação junto.
2. Guardar as últimas linhas de stderr, porque o erro real do ffmpeg
   quase sempre está lá — e não no código de saída.

O ffmpeg é usado num lugar só, em `montar.py`, e sempre da mesma forma:
recebendo PCM pela entrada padrão e escrevendo o audiobook. Por isso este
módulo é bem menor que um utilitário de ffmpeg completo — não há
progresso a acompanhar nem filtros a montar.
"""

from __future__ import annotations

import shutil
from collections.abc import Sequence
from functools import cache

# O ffmpeg escreve o banner e a configuração antes do erro de verdade,
# então guardamos linhas suficientes para a mensagem útil caber.
LINHAS_DE_ERRO = 40


class FFmpegError(RuntimeError):
    """Falha ao executar o ffmpeg, já com o stderr relevante anexado."""

    def __init__(self, args: Sequence[str], codigo: int, stderr: str) -> None:
        self.args_usados = list(args)
        self.codigo = codigo
        self.stderr = stderr
        comando = " ".join(args[:6]) + (" …" if len(args) > 6 else "")
        super().__init__(f"ffmpeg falhou (código {codigo}): {comando}\n{stderr}")


class FFmpegCancelado(RuntimeError):
    """O chamador pediu para parar e o processo foi encerrado."""


@cache
def caminho_do_ffmpeg() -> str:
    achado = shutil.which("ffmpeg")
    if not achado:
        raise FFmpegError(
            ["ffmpeg"],
            127,
            "'ffmpeg' não encontrado no PATH. Instale com: brew install ffmpeg",
        )
    return achado
