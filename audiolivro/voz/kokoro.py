"""Kokoro: a melhor voz que roda offline em pt-BR hoje.

82 milhões de parâmetros, ONNX, cerca de quatro vezes mais rápido que o
tempo real num M-series — um livro de dez horas leva umas duas horas e
meia para sintetizar, uma vez só.

Duas coisas precisam estar no lugar antes da primeira frase:

**Os pesos.** ~325 MB de modelo mais 27 MB de vozes, que não vêm no
pacote do PyPI. `garantir_modelo()` baixa na primeira execução e guarda
em `~/.cache/audiolivro`, uma vez só.

**O espeak-ng.** O Kokoro consome fonemas, não letras, e quem converte
letra em fonema para o português é o espeak. Ele vem embutido no
`espeakng-loader` (não precisa de brew), mas a biblioteca precisa ser
apontada antes do primeiro uso — e o erro que aparece quando não é feito
não menciona espeak em lugar nenhum, o que torna esse `_preparar_espeak`
o trecho mais chato de descobrir do pacote inteiro.
"""

from __future__ import annotations

import os
import threading
import urllib.error
import urllib.request
from functools import cache
from pathlib import Path

import numpy as np

from audiolivro.voz.base import MotorIndisponivel, Voz

PASTA = Path(
    os.environ.get("AUDIOLIVRO_CACHE", Path.home() / ".cache" / "audiolivro")
) / "kokoro"

BASE_URL = (
    "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
)
ARQUIVOS = {
    "kokoro-v1.0.onnx": 325_532_387,
    "voices-v1.0.bin": 28_214_398,
}

# O Kokoro nomeia a voz com prefixo de idioma e sexo: "pf_" é português
# feminino, "pm_" é português masculino. Só estas três falam pt-BR; as
# outras cinquenta são de outros idiomas e soariam com sotaque grosseiro.
VOZES = (
    Voz("pf_dora", "Dora", "pt-BR", "kokoro", "feminina"),
    Voz("pm_alex", "Alex", "pt-BR", "kokoro", "masculina"),
    Voz("pm_santa", "Santa", "pt-BR", "kokoro", "masculina"),
)
VOZ_PADRAO = "pf_dora"


class Kokoro:
    nome = "kokoro"
    taxa = 24_000

    def __init__(self, voz_padrao: str = VOZ_PADRAO) -> None:
        self.voz_padrao = voz_padrao
        self._motor = None
        # O espeak-ng é uma biblioteca C com estado global: duas threads
        # fonemizando ao mesmo tempo devolvem lixo, e o defeito aparece
        # como uma frase aleatória lida errado no meio do livro — quase
        # impossível de rastrear depois. A inferência ONNX, ao contrário,
        # é reentrante. Então travamos só o espeak, e a parte cara fica
        # livre para rodar em paralelo.
        self._trava_espeak = threading.Lock()
        self._trava_carga = threading.Lock()

    def vozes(self) -> list[Voz]:
        return list(VOZES)

    def sintetizar(
        self, texto: str, *, voz: str = VOZ_PADRAO, velocidade: float = 1.0
    ) -> np.ndarray:
        motor = self._carregar()
        # O Kokoro rejeita fora dessa faixa com um assert; preferimos
        # entregar áudio no limite a derrubar a síntese do livro inteiro.
        velocidade = min(max(velocidade, 0.5), 2.0)

        with self._trava_espeak:
            fonemas = motor.tokenizer.phonemize(texto, "pt-br")

        amostras, _taxa = motor.create(
            fonemas,
            voice=voz or self.voz_padrao,
            speed=velocidade,
            is_phonemes=True,
        )
        return np.asarray(amostras, dtype=np.float32)

    def _carregar(self):
        if self._motor is not None:
            return self._motor
        with self._trava_carga:
            if self._motor is None:
                _preparar_espeak()
                modelo, vozes = garantir_modelo()
                try:
                    from kokoro_onnx import Kokoro as _Kokoro
                except ImportError as erro:
                    raise MotorIndisponivel(
                        "Kokoro não instalado. Instale com:\n"
                        "  pip install kokoro-onnx espeakng-loader"
                    ) from erro
                self._motor = _Kokoro(str(modelo), str(vozes))
        return self._motor


@cache
def _preparar_espeak() -> None:
    """Aponta o phonemizer para o espeak-ng que veio no wheel.

    Sem isto o phonemizer procura um `libespeak-ng` do sistema, não acha,
    e falha com "espeak not installed on your system" — mesmo estando
    instalado dentro do próprio ambiente virtual.
    """
    try:
        import espeakng_loader
        from phonemizer.backend.espeak.wrapper import EspeakWrapper
    except ImportError as erro:
        raise MotorIndisponivel(
            "Falta o fonemizador do Kokoro. Instale com:\n"
            "  pip install espeakng-loader phonemizer-fork"
        ) from erro

    EspeakWrapper.set_library(espeakng_loader.get_library_path())
    EspeakWrapper.set_data_path(espeakng_loader.get_data_path())


def instalado() -> bool:
    try:
        import kokoro_onnx  # noqa: F401
    except ImportError:
        return False
    return all((PASTA / nome).exists() for nome in ARQUIVOS)


def garantir_modelo(
    *, ao_baixar=None
) -> tuple[Path, Path]:
    """Devolve (modelo, vozes), baixando o que faltar.

    `ao_baixar(nome, baixado, total)` recebe o progresso, para a barra da
    linha de comando. O download vai para um `.part` e só é renomeado no
    fim: uma conexão que cai no meio deixaria um ONNX truncado que falha
    de um jeito completamente ilegível na hora de carregar.
    """
    PASTA.mkdir(parents=True, exist_ok=True)
    caminhos = []

    for nome, tamanho in ARQUIVOS.items():
        destino = PASTA / nome
        if destino.exists() and destino.stat().st_size > tamanho * 0.95:
            caminhos.append(destino)
            continue
        _baixar(f"{BASE_URL}/{nome}", destino, nome, ao_baixar)
        caminhos.append(destino)

    return caminhos[0], caminhos[1]


def _baixar(url: str, destino: Path, nome: str, ao_baixar) -> None:
    parcial = destino.with_suffix(destino.suffix + ".part")
    try:
        with urllib.request.urlopen(url) as resposta, parcial.open("wb") as saida:
            total = int(resposta.headers.get("Content-Length", 0))
            baixado = 0
            while pedaco := resposta.read(1 << 20):
                saida.write(pedaco)
                baixado += len(pedaco)
                if ao_baixar:
                    ao_baixar(nome, baixado, total)
    except urllib.error.URLError as erro:
        parcial.unlink(missing_ok=True)
        raise MotorIndisponivel(
            f"Não consegui baixar {nome} ({erro}).\n"
            f"Baixe à mão de {BASE_URL}/{nome} e ponha em {PASTA}"
        ) from erro

    parcial.replace(destino)
