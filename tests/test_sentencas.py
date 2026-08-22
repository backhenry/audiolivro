"""Onde termina a frase, e onde dá para respirar dentro dela.

O ponto final é ambíguo em português. Cortar onde ele não termina frase
produz falas truncadas que o motor lê com entonação de fim — o texto sai
picotado, e a causa não é óbvia ouvindo.
"""

from __future__ import annotations

import pytest

from audiolivro.texto.sentencas import LIMITE_FALA, falar, respirar, segmentar


def test_frases_simples() -> None:
    assert segmentar("Ele saiu. Ela ficou. Ninguém falou.") == [
        "Ele saiu.", "Ela ficou.", "Ninguém falou.",
    ]


@pytest.mark.parametrize(
    "texto",
    [
        "O Sr. Silva chegou tarde.",
        "Veja a pág. 37 do volume.",
        "Leia J. R. R. Tolkien amanhã.",
        "Custou 1.250 reais no total.",
        "Ele nasceu em 44 a.C. na Grécia.",
    ],
)
def test_ponto_que_nao_termina_frase(texto: str) -> None:
    assert segmentar(texto) == [texto]


def test_ponto_depois_de_digito_ainda_termina_frase() -> None:
    # "1990." é fim de frase de verdade; só o milhar "1.250" não é, e o
    # que os separa é o espaço depois do ponto.
    assert segmentar("Ele nasceu em 1990. Depois mudou.") == [
        "Ele nasceu em 1990.", "Depois mudou.",
    ]


def test_pontuacao_de_fechamento_fica_com_a_frase() -> None:
    assert segmentar('Ele gritou: "não!" Depois calou.') == [
        'Ele gritou: "não!"', "Depois calou.",
    ]


def test_reticencias_nao_partem_a_frase_em_tres() -> None:
    assert len(segmentar("Ele hesitou... e então falou.")) == 1


def test_frase_curta_nao_e_partida() -> None:
    assert respirar("Ele saiu.") == ["Ele saiu."]


def test_frase_longa_respira_na_conjuncao() -> None:
    longa = (
        "Ele caminhou pela rua estreita e mal iluminada, pensando na conversa "
        "que tivera com o irmão na véspera, quando ainda acreditava que tudo "
        "poderia ser resolvido com uma carta bem escrita e entregue em mãos, "
        "mas agora, depois de tudo o que ouvira naquela tarde interminável, "
        "já não tinha certeza de nada, nem mesmo do próprio nome."
    )
    assert len(longa) > LIMITE_FALA
    pedacos = respirar(longa)
    assert len(pedacos) > 1
    assert all(len(p) <= LIMITE_FALA for p in pedacos)
    # O corte escolhido é onde um leitor humano também tomaria ar.
    assert any(p.startswith("mas agora") for p in pedacos)
    assert " ".join(pedacos) == longa


def test_enumeracao_sem_pontuacao_ainda_cabe() -> None:
    """Sem nenhum ponto de respiro, corta por palavra.

    Feio, mas o texto chega inteiro — truncar seria perder o trecho, e é
    o que o motor faz sozinho quando a fala passa da janela dele.
    """
    longa = "palavra " * 120
    pedacos = respirar(longa.strip())
    assert all(len(p) <= LIMITE_FALA for p in pedacos)
    assert " ".join(pedacos) == longa.strip()


def test_falar_junta_os_dois_passos() -> None:
    paragrafo = "Primeira frase. " + "Segunda frase bem comprida, " * 12
    pedacos = falar(paragrafo)
    assert pedacos[0] == "Primeira frase."
    assert all(len(p) <= LIMITE_FALA for p in pedacos)
