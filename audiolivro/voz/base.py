"""O contrato que todo motor de voz cumpre.

Um motor recebe texto e devolve amostras. Só isso. Ele não sabe o que é
um capítulo, não cuida de pausa, não escreve arquivo e não conhece o
cache — tudo isso é responsabilidade de `sintetizar.py`, e mantê-lo fora
daqui é o que permite trocar Kokoro por uma API de nuvem alterando uma
linha de configuração.

A taxa de amostragem é do motor, não do sistema: o Kokoro entrega 24 kHz
e o `say` do macOS pode entregar outra coisa. Quem monta a trilha
reamostra se precisar, porque só ele sabe qual é a taxa de destino.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import numpy as np


@dataclass(frozen=True)
class Voz:
    id: str
    nome: str
    idioma: str
    motor: str
    genero: str = ""

    def __str__(self) -> str:
        return f"{self.motor}:{self.id}"


class MotorIndisponivel(RuntimeError):
    """O motor existe no código mas não pode rodar nesta máquina.

    Carrega sempre a instrução de instalação: descobrir que falta um
    modelo é inútil sem saber como obtê-lo.
    """


@runtime_checkable
class Motor(Protocol):
    nome: str
    taxa: int

    def vozes(self) -> list[Voz]:
        """Vozes disponíveis, já filtradas pelo que existe na máquina."""
        ...

    def sintetizar(
        self, texto: str, *, voz: str, velocidade: float = 1.0
    ) -> np.ndarray:
        """Texto -> amostras float32 mono em `self.taxa`, faixa [-1, 1]."""
        ...


def aparar(amostras: np.ndarray, taxa: int, *, limiar: float = 0.005) -> np.ndarray:
    """Corta o silêncio das pontas.

    Isto não é cosmético. Todo motor entrega um pouco de silêncio antes e
    depois da fala, e o tamanho varia com o texto. Se as pausas do livro
    forem inseridas por cima desse silêncio variável, o ritmo que
    `modelo.PAUSA` define deixa de valer: a pausa real vira "o que eu pedi
    mais o que o motor resolveu dar". Aparando primeiro, a pausa entre
    duas falas é exatamente a que está no `Livro` — e um capítulo inteiro
    passa a soar regular.

    A margem de 15 ms que sobra evita o clique de corte em zero abrupto.
    """
    if amostras.size == 0:
        return amostras

    forte = np.abs(amostras) > limiar
    if not forte.any():
        return amostras[:0]

    margem = int(taxa * 0.015)
    inicio = max(0, int(np.argmax(forte)) - margem)
    fim = min(len(amostras), len(amostras) - int(np.argmax(forte[::-1])) + margem)
    return amostras[inicio:fim]


def normalizar_volume(amostras: np.ndarray, alvo: float = 0.89) -> np.ndarray:
    """Iguala o pico. Falas curtas saem mais baixas em quase todo motor,
    e a diferença aparece como oscilação de volume ao longo do capítulo.
    """
    pico = float(np.max(np.abs(amostras))) if amostras.size else 0.0
    if pico < 1e-6:
        return amostras
    return (amostras * (alvo / pico)).astype(np.float32)
