"""A voz embutida do macOS, via `say`.

Não é voz de audiobook — é voz de leitor de tela, e ouvir um romance
inteiro nela cansa. Mas ela tem duas qualidades que nenhum modelo tem:
está instalada agora, e sintetiza um capítulo em menos de um segundo.

Isso a torna o motor certo para *revisar o texto*. Antes de gastar duas
horas de Kokoro num livro de trezentas páginas, vale ouvir um capítulo
aqui e descobrir que o extrator engoliu os diálogos ou que os números
saíram errados. A revisão é do texto, e para isso qualquer voz serve.

Vale dizer ao usuário: as vozes "Aprimorada" e "Premium" da Luciana, que
se baixam em Ajustes do Sistema > Acessibilidade > Conteúdo Falado, são
muito melhores que a padrão e o `say` as usa automaticamente.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from functools import cache
from pathlib import Path

import numpy as np

from audiolivro.voz.base import MotorIndisponivel, Voz

VOZ_PADRAO = "Luciana"
# O `say` mede velocidade em palavras por minuto. 180 é o padrão dele e
# fica perto do ritmo de uma leitura em voz alta.
PPM_BASE = 180

_RE_VOZ = re.compile(r"^(?P<nome>.+?)\s+(?P<idioma>[a-z]{2}_[A-Z]{2})\s+#")


class MacOS:
    nome = "macos"
    taxa = 22_050

    def __init__(self, voz_padrao: str = VOZ_PADRAO) -> None:
        self.voz_padrao = voz_padrao

    def vozes(self) -> list[Voz]:
        return [v for v in _catalogo() if v.idioma.startswith("pt")]

    def sintetizar(
        self, texto: str, *, voz: str = VOZ_PADRAO, velocidade: float = 1.0
    ) -> np.ndarray:
        import soundfile as sf

        binario = shutil.which("say")
        if not binario:
            raise MotorIndisponivel("'say' não encontrado — isto é macOS?")

        with tempfile.TemporaryDirectory() as tmp:
            saida = Path(tmp) / "fala.wav"
            # `--data-format` fixa a taxa; sem ele o `say` escolhe uma
            # taxa por voz, e a trilha sairia com emendas de reamostragem.
            #
            # O container precisa ser WAVE, e não o AIFF padrão: AIFF é
            # big-endian e recusa o LEF32 little-endian com um "Opening
            # output file failed: fmt?" que não diz o que está errado.
            comando = [
                binario,
                "-v", voz or self.voz_padrao,
                "-r", str(int(PPM_BASE * velocidade)),
                "--file-format=WAVE",
                f"--data-format=LEF32@{self.taxa}",
                "-o", str(saida),
                texto,
            ]
            resultado = subprocess.run(comando, capture_output=True, text=True)
            if resultado.returncode != 0 or not saida.exists():
                raise MotorIndisponivel(
                    f"'say' falhou com a voz '{voz}': {resultado.stderr.strip()}"
                )
            amostras, _taxa = sf.read(saida, dtype="float32")

        if amostras.ndim > 1:
            amostras = amostras.mean(axis=1)
        return amostras.astype(np.float32)


@cache
def _catalogo() -> tuple[Voz, ...]:
    binario = shutil.which("say")
    if not binario:
        return ()

    saida = subprocess.run(
        [binario, "-v", "?"], capture_output=True, text=True
    ).stdout

    vozes = []
    for linha in saida.splitlines():
        m = _RE_VOZ.match(linha)
        if not m:
            continue
        nome = m.group("nome").strip()
        # Vozes novas do macOS vêm como "Flo (Português (Brasil))"; o
        # `say -v` só aceita o nome antes do parêntese.
        curto = nome.split(" (")[0]
        vozes.append(
            Voz(curto, nome, m.group("idioma").replace("_", "-"), "macos")
        )
    return tuple(vozes)


def instalado() -> bool:
    return bool(shutil.which("say")) and bool(_catalogo())
