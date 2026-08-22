"""Piper: vozes leves, e mais opções de timbre em pt-BR.

O Kokoro tem três vozes brasileiras e ponto. Se nenhuma agradar — e
timbre é gosto, não qualidade —, o Piper tem outras quatro, cada uma com
uns 60 MB em vez de 325. Ele sintetiza mais rápido e soa um degrau
abaixo: prosódia mais plana, menos variação de entonação dentro da frase.

Existe aqui sobretudo para provar que a camada de motores é real. Trocar
de motor é `--motor piper`, e nada acima disso muda.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np

from audiolivro.voz.base import MotorIndisponivel, Voz

PASTA = Path(
    os.environ.get("AUDIOLIVRO_CACHE", Path.home() / ".cache" / "audiolivro")
) / "piper"

BASE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR"

# Na ordem em que soaram melhor num teste de escuta com prosa narrativa
# de verdade — não na ordem alfabética nem na do repositório. Quem abre a
# lista quase sempre fica com a primeira.
#
# O Jeff ficou na frente numa segunda escuta, e o número concorda com o
# ouvido: no mesmo texto ele leva 42,9 s contra 36,9 s do Faber. Fala uns
# 15% mais devagar, o que num trecho curto passa por lentidão e num livro
# de dez horas é o que separa um narrador calmo de um apressado.
VOZES = (
    Voz("pt_BR-jeff-medium", "Jeff", "pt-BR", "piper", "masculina"),
    Voz("pt_BR-faber-medium", "Faber", "pt-BR", "piper", "masculina"),
    Voz("pt_BR-cadu-medium", "Cadu", "pt-BR", "piper", "masculina"),
)
VOZ_PADRAO = "pt_BR-jeff-medium"

# A quarta voz pt-BR do Piper, `pt_BR-edresson-low`, ficou de fora: o
# mapa de fonemas dela não tem o til combinante (U+0303), então toda
# vogal nasal perde a nasalidade na conversão. "Não" vira "nau", "mão"
# vira "mau", "então" vira "entau" — em português isso não é um defeito
# de sotaque, é outra língua. O Piper apenas avisa "Missing phoneme from
# id map" numa linha de log e sintetiza assim mesmo.
VOZES_INCOMPLETAS = {"pt_BR-edresson-low": "sem vogais nasais"}


class Piper:
    nome = "piper"
    taxa = 22_050

    def __init__(self, voz_padrao: str = VOZ_PADRAO) -> None:
        self.voz_padrao = voz_padrao
        self._carregadas: dict[str, object] = {}

    def vozes(self) -> list[Voz]:
        return list(VOZES)

    def sintetizar(
        self, texto: str, *, voz: str = VOZ_PADRAO, velocidade: float = 1.0
    ) -> np.ndarray:
        modelo = self._voz(voz or self.voz_padrao)

        # O Piper mede "comprimento", não velocidade: falar mais rápido é
        # encurtar cada fonema, então o fator é o inverso.
        escala = 1.0 / max(velocidade, 0.1)
        pedacos = _sintetizar(modelo, texto, escala)
        if not pedacos:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(pedacos).astype(np.float32)

    def _voz(self, nome: str):
        if nome not in self._carregadas:
            try:
                from piper import PiperVoice
            except ImportError as erro:
                raise MotorIndisponivel(
                    "Piper não instalado. Instale com:\n  pip install piper-tts"
                ) from erro
            modelo = PiperVoice.load(str(garantir_modelo(nome)))
            # A taxa é por voz (a edresson era 16 kHz, as outras 22 kHz) e
            # precisa valer já no carregamento. Descobri-la só ao
            # sintetizar deixaria `motor.taxa` mentindo justamente quando
            # todas as falas vêm do cache e nenhuma síntese acontece.
            self.taxa = modelo.config.sample_rate
            self._carregadas[nome] = modelo
        return self._carregadas[nome]


def _sintetizar(modelo, texto: str, escala: float) -> list[np.ndarray]:
    """Absorve a diferença entre as duas gerações de API do Piper.

    A 1.x devolve objetos com `audio_float_array`; a 0.x devolve bytes
    int16 crus. Como as duas convivem no PyPI dependendo da versão do
    Python, testamos a nova e caímos na antiga.
    """
    from piper import SynthesisConfig

    if hasattr(modelo, "synthesize"):
        config = SynthesisConfig(length_scale=escala)
        return [
            np.asarray(pedaco.audio_float_array, dtype=np.float32)
            for pedaco in modelo.synthesize(texto, syn_config=config)
        ]

    bruto = b"".join(modelo.synthesize_stream_raw(texto, length_scale=escala))
    return [np.frombuffer(bruto, dtype=np.int16).astype(np.float32) / 32768.0]


def instalado() -> bool:
    """Pronto para usar *agora*, sem baixar nada.

    A checagem inclui o modelo da voz padrão, e não só o pacote Python.
    Sem isso a autodetecção elegeria o Piper numa máquina que ainda não
    tem os pesos, e a primeira frase do livro dispararia um download de
    63 MB que ninguém pediu.
    """
    try:
        import piper  # noqa: F401
    except ImportError:
        return False
    return (PASTA / f"{VOZ_PADRAO}.onnx").exists()


def garantir_modelo(nome: str) -> Path:
    """Baixa o .onnx e o .json da voz, se ainda não estiverem em cache."""
    PASTA.mkdir(parents=True, exist_ok=True)
    onnx = PASTA / f"{nome}.onnx"
    config = PASTA / f"{nome}.onnx.json"

    if onnx.exists() and config.exists():
        return onnx

    apelido = nome.removeprefix("pt_BR-").rsplit("-", 1)
    if len(apelido) != 2:
        raise MotorIndisponivel(f"Nome de voz Piper inesperado: {nome}")
    locutor, qualidade = apelido

    for destino, sufixo in ((onnx, ""), (config, ".json")):
        url = f"{BASE_URL}/{locutor}/{qualidade}/{nome}.onnx{sufixo}"
        try:
            parcial = destino.with_suffix(destino.suffix + ".part")
            urllib.request.urlretrieve(url, parcial)
            parcial.replace(destino)
        except urllib.error.URLError as erro:
            raise MotorIndisponivel(
                f"Não consegui baixar a voz {nome} ({erro}).\nURL: {url}"
            ) from erro

    # Falha cedo: um JSON corrompido só apareceria na primeira frase.
    json.loads(config.read_text(encoding="utf-8"))
    return onnx
