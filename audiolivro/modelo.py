"""O `Livro`: artefato central, legível e editável à mão.

Duas escalas de tempo convivem aqui, e confundi-las é a origem de quase
todo bug de sincronia num player:

| | significado | onde vive |
|---|---|---|
| **tempo de fala** | duração do áudio de uma fala isolada | `Fala.duracao` |
| **tempo de trilha** | posição no audiobook final | `Trilha.marcas` |

A ponte é a `Trilha`, produzida pela síntese. O `Livro` sozinho não sabe
nada de áudio: ele é só texto com decisões de leitura. Isso é de propósito
— dá para versionar, revisar e corrigir o livro sem invalidar nada, e a
`Trilha` é sempre regenerável a partir dele.

O `id` de cada fala é estável e derivado da posição (`c003-b0012-f1`).
Ele é a chave do cache de síntese: corrigir o nome do protagonista no
capítulo 7 re-sintetiza as falas daquele bloco, não as outras nove mil.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

VERSAO_FORMATO = 1

# `titulo` e `subtitulo` viram cabeçalho falado com pausa larga em volta.
# `nota` é o que foi arrancado do corpo (rodapé, nota de fim) e só é lido
# se o usuário pedir — no meio de um parágrafo, uma nota destrói a frase.
TipoBloco = Literal[
    "titulo",
    "subtitulo",
    "paragrafo",
    "citacao",
    "lista",
    "verso",
    "nota",
    "legenda",
]


@dataclass
class Fala:
    """Uma unidade de síntese: quase sempre uma frase.

    `texto` é o que o motor recebe — já com "1.250" virado "mil duzentos
    e cinquenta". `exibicao` é o que o leitor vê na tela. Os dois divergem
    sempre, e guardar os dois é o que permite destacar o texto original
    enquanto se ouve a versão normalizada.
    """

    id: str
    texto: str
    exibicao: str
    pausa: float = 0.35
    """Silêncio inserido depois desta fala, em segundos."""
    ler: bool = True
    """Se falso, a fala existe no livro mas não entra no áudio.

    Excluir em vez de apagar é de propósito. Todo livro traz coisa que
    não se ouve: página de créditos, ficha catalográfica, índice
    remissivo, a legenda de uma figura que não existe em áudio. Apagar
    resolveria o áudio e perderia o texto, e com ele a chance de voltar
    atrás depois de ouvir. Assim o `livro.json` continua sendo o livro
    inteiro, e o que muda é só o que se lê em voz alta.
    """

    def __post_init__(self) -> None:
        if self.pausa < 0:
            raise ValueError(f"pausa negativa em {self.id}: {self.pausa}")


@dataclass
class Bloco:
    id: str
    tipo: TipoBloco
    exibicao: str
    falas: list[Fala] = field(default_factory=list)

    @property
    def audivel(self) -> bool:
        return bool(self.falas)


@dataclass
class Capitulo:
    id: str
    titulo: str
    blocos: list[Bloco] = field(default_factory=list)

    @property
    def caracteres(self) -> int:
        return sum(len(f.texto) for f in self.audiveis())

    def falas(self) -> list[Fala]:
        return [f for b in self.blocos for f in b.falas]

    def audiveis(self) -> list[Fala]:
        return [f for f in self.falas() if f.ler]


@dataclass
class Livro:
    titulo: str
    autor: str = ""
    idioma: str = "pt-BR"
    origem: str = ""
    capitulos: list[Capitulo] = field(default_factory=list)

    @property
    def caracteres(self) -> int:
        return sum(c.caracteres for c in self.capitulos)

    def falas(self) -> list[Fala]:
        return [f for c in self.capitulos for f in c.falas()]

    def audiveis(self) -> list[Fala]:
        """Só o que vai virar som. É esta a lista que a síntese percorre."""
        return [f for f in self.falas() if f.ler]

    def duracao_estimada(self) -> float:
        """Segundos aproximados, para dar uma barra de progresso honesta.

        14 caracteres por segundo é a taxa medida do Kokoro em pt-BR na
        velocidade 1.0. Serve para estimar, não para sincronizar.
        """
        pausas = sum(f.pausa for f in self.audiveis())
        return self.caracteres / 14.0 + pausas

    # -- serialização ---------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "versao": VERSAO_FORMATO,
            "titulo": self.titulo,
            "autor": self.autor,
            "idioma": self.idioma,
            "origem": self.origem,
            "capitulos": [
                {
                    "id": c.id,
                    "titulo": c.titulo,
                    "blocos": [
                        {
                            "id": b.id,
                            "tipo": b.tipo,
                            "exibicao": b.exibicao,
                            "falas": [
                                {
                                    "id": f.id,
                                    "texto": f.texto,
                                    # Só gravamos `exibicao` quando ela
                                    # difere: na maioria das falas ela é
                                    # idêntica, e repetir tudo dobraria o
                                    # tamanho de um JSON já grande.
                                    **(
                                        {"exibicao": f.exibicao}
                                        if f.exibicao != f.texto
                                        else {}
                                    ),
                                    "pausa": round(f.pausa, 3),
                                    **({} if f.ler else {"ler": False}),
                                }
                                for f in b.falas
                            ],
                        }
                        for b in c.blocos
                    ],
                }
                for c in self.capitulos
            ],
        }

    @classmethod
    def from_dict(cls, dados: dict) -> Livro:
        versao = dados.get("versao", 1)
        if versao > VERSAO_FORMATO:
            raise ValueError(
                f"Livro gravado no formato v{versao}, mas esta versão do "
                f"audiolivro só entende até v{VERSAO_FORMATO}."
            )
        return cls(
            titulo=dados.get("titulo", ""),
            autor=dados.get("autor", ""),
            idioma=dados.get("idioma", "pt-BR"),
            origem=dados.get("origem", ""),
            capitulos=[
                Capitulo(
                    id=c["id"],
                    titulo=c.get("titulo", ""),
                    blocos=[
                        Bloco(
                            id=b["id"],
                            tipo=b.get("tipo", "paragrafo"),
                            exibicao=b.get("exibicao", ""),
                            falas=[
                                Fala(
                                    id=f["id"],
                                    texto=f["texto"],
                                    exibicao=f.get("exibicao", f["texto"]),
                                    pausa=float(f.get("pausa", 0.35)),
                                    ler=bool(f.get("ler", True)),
                                )
                                for f in b.get("falas", [])
                            ],
                        )
                        for b in c.get("blocos", [])
                    ],
                )
                for c in dados.get("capitulos", [])
            ],
        )

    def salvar(self, destino: Path) -> Path:
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
        return destino

    @classmethod
    def carregar(cls, origem: Path) -> Livro:
        return cls.from_dict(json.loads(origem.read_text(encoding="utf-8")))


@dataclass
class Marca:
    """Onde uma fala caiu na trilha final."""

    fala: str
    inicio: float
    duracao: float


@dataclass
class Trilha:
    """Resultado da síntese: o áudio e o mapa de volta para o texto.

    Sem `marcas`, o player consegue tocar mas não consegue destacar a
    frase que está soando nem retomar de onde parou em termos de texto —
    só em segundos, que é inútil quando o livro é re-sintetizado.
    """

    audio: str
    duracao: float
    motor: str
    voz: str
    velocidade: float = 1.0
    marcas: list[Marca] = field(default_factory=list)
    capitulos: list[tuple[str, float]] = field(default_factory=list)
    """(título, início em segundos) — vira capítulo de verdade no M4B."""

    def indice_em(self, segundo: float) -> int:
        """Índice da marca que está soando em `segundo` (busca binária)."""
        lo, hi = 0, len(self.marcas) - 1
        achado = 0
        while lo <= hi:
            meio = (lo + hi) // 2
            if self.marcas[meio].inicio <= segundo:
                achado = meio
                lo = meio + 1
            else:
                hi = meio - 1
        return achado

    def to_dict(self) -> dict:
        return {
            "versao": VERSAO_FORMATO,
            "audio": self.audio,
            "duracao": round(self.duracao, 3),
            "motor": self.motor,
            "voz": self.voz,
            "velocidade": self.velocidade,
            "capitulos": [[t, round(s, 3)] for t, s in self.capitulos],
            "marcas": [
                [m.fala, round(m.inicio, 3), round(m.duracao, 3)] for m in self.marcas
            ],
        }

    @classmethod
    def from_dict(cls, dados: dict) -> Trilha:
        return cls(
            audio=dados["audio"],
            duracao=float(dados.get("duracao", 0.0)),
            motor=dados.get("motor", ""),
            voz=dados.get("voz", ""),
            velocidade=float(dados.get("velocidade", 1.0)),
            capitulos=[(t, float(s)) for t, s in dados.get("capitulos", [])],
            marcas=[Marca(m[0], float(m[1]), float(m[2])) for m in dados.get("marcas", [])],
        )

    def salvar(self, destino: Path) -> Path:
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False), encoding="utf-8"
        )
        return destino

    @classmethod
    def carregar(cls, origem: Path) -> Trilha:
        return cls.from_dict(json.loads(origem.read_text(encoding="utf-8")))


# -- pausas ------------------------------------------------------------
#
# O que separa um audiobook de uma leitura de robô não é a voz, é o
# ritmo. Estes números vieram de ouvir: pausa curta demais entre
# parágrafos e o texto vira uma avalanche; longa demais e parece que o
# arquivo travou. O silêncio antes de um título é maior que o de depois,
# porque ele fecha o capítulo anterior — o de depois só apresenta o novo.

PAUSA = {
    "sentenca": 0.32,
    "virgula_forte": 0.18,  # sentença longa quebrada em respiros
    "paragrafo": 0.68,
    "antes_titulo": 1.30,
    "depois_titulo": 0.90,
    "fim_capitulo": 1.60,
    "citacao": 0.55,
    "verso": 0.42,
    "lista": 0.45,
}
