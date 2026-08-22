"""Números por extenso: a regra do "e" e a concordância de gênero.

São as duas coisas que todo conversor de português erra, e as duas
falham de um jeito que só aparece ouvindo — o JSON continua com aspecto
perfeito.
"""

from __future__ import annotations

import pytest

from audiolivro.texto.numeros import (
    int_para_romano,
    ordinal,
    por_extenso,
    romano_para_int,
)


@pytest.mark.parametrize(
    "numero, esperado",
    [
        (0, "zero"),
        (15, "quinze"),
        (21, "vinte e um"),
        (100, "cem"),          # sozinho é "cem"
        (101, "cento e um"),   # acompanhado vira "cento"
        (199, "cento e noventa e nove"),
        (1_000, "mil"),        # nunca "um mil"
        (2_000, "dois mil"),
        (10_000, "dez mil"),
        (1_000_000, "um milhão"),
    ],
)
def test_cardinais_basicos(numero: int, esperado: str) -> None:
    assert por_extenso(numero) == esperado


@pytest.mark.parametrize(
    "numero, esperado",
    [
        # Entra "e" quando o resto é menor que cem...
        (1_005, "mil e cinco"),
        (2_300, "dois mil e trezentos"),
        # ...ou quando é centena redonda.
        (1_100, "mil e cem"),
        (1_000_100, "um milhão e cem"),
        # E não entra quando o resto é uma centena quebrada.
        (1_250, "mil duzentos e cinquenta"),
        (1_250_000, "um milhão duzentos e cinquenta mil"),
        (2_300_450, "dois milhões trezentos mil quatrocentos e cinquenta"),
    ],
)
def test_a_regra_do_e(numero: int, esperado: str) -> None:
    assert por_extenso(numero) == esperado


@pytest.mark.parametrize(
    "numero, esperado",
    [
        (1, "uma"),
        (2, "duas"),
        (31, "trinta e uma"),
        (200, "duzentas"),
        (1_200, "mil e duzentas"),
        # "mil" é invariável e o multiplicador concorda com o substantivo:
        # duas mil páginas.
        (2_000, "duas mil"),
    ],
)
def test_feminino_concorda_no_grupo_certo(numero: int, esperado: str) -> None:
    assert por_extenso(numero, feminino=True) == esperado


def test_milhao_e_substantivo_masculino_e_nao_flexiona() -> None:
    # São *dois* milhões mesmo quando se contam páginas: quem rege a
    # concordância é "milhões", não o substantivo lá na frente.
    assert por_extenso(2_000_000, feminino=True) == "dois milhões"


def test_numero_absurdo_vira_sequencia_de_digitos() -> None:
    # Um número desse tamanho num livro é código, não quantidade.
    assert por_extenso(10**18) == "um zero zero zero zero zero zero zero zero zero zero zero zero zero zero zero zero zero zero"


@pytest.mark.parametrize(
    "numero, masculino, feminino",
    [
        (1, "primeiro", "primeira"),
        (9, "nono", "nona"),
        (11, "décimo primeiro", "décima primeira"),
        (21, "vigésimo primeiro", "vigésima primeira"),
        (113, "centésimo décimo terceiro", "centésima décima terceira"),
    ],
)
def test_ordinais_flexionam_todos_os_termos(numero, masculino, feminino) -> None:
    assert ordinal(numero) == masculino
    assert ordinal(numero, feminino=True) == feminino


def test_ordinal_grande_vira_cardinal() -> None:
    # Ninguém diz "milésimo quingentésimo vigésimo terceiro".
    assert ordinal(1523) == por_extenso(1523)


@pytest.mark.parametrize("texto, valor", [("XIV", 14), ("III", 3), ("MCMXCIV", 1994)])
def test_romanos_validos(texto: str, valor: int) -> None:
    assert romano_para_int(texto) == valor


@pytest.mark.parametrize("texto", ["DIVA", "CIA", "IIII", "IC", "LP", "", "ABC"])
def test_romanos_invalidos_sao_recusados(texto: str) -> None:
    # Transformar a editora "DIVA" em 504 no meio do livro é pior que
    # não converter romano nenhum.
    assert romano_para_int(texto) is None


def test_romano_faz_ida_e_volta() -> None:
    for n in range(1, 4000):
        assert romano_para_int(int_para_romano(n)) == n
