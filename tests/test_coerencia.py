"""A de-hifenização e a limpeza de marginais.

O hífen de fim de linha é o caso onde nenhuma lista de palavras resolve
sozinha: "clas-se" e "chamava-se" têm exatamente a mesma forma. Cada
teste aqui é um par que já quebrou uma versão anterior da regra.
"""

from __future__ import annotations

import pytest

from audiolivro.texto.coerencia import (
    assinatura,
    descartavel,
    desifenizar,
    juntar_linhas,
    marginais_repetidas,
    remover_marcas_de_nota,
    vocabulario,
)


def _juntar(entrada: str, corpus: str = "") -> str:
    texto = f"{corpus} {entrada}".strip()
    return desifenizar(entrada, vocabulario(texto))


@pytest.mark.parametrize(
    "entrada, esperado",
    [
        # Hifenização silábica: junta.
        ("impres-\nsionante", "impressionante"),
        ("clas-\nse", "classe"),        # "se" parece ênclise, mas "clas" não é verbo
        ("ofici-\nna", "oficina"),      # "na" parece pronome, mesma história
        ("pas-\nso", "passo"),
        ("pe-\nlo", "pelo"),            # "lo" sem vogal acentuada antes
        ("cor-\nredor", "corredor"),
        # Hífen gramatical: preserva.
        ("dar-\nlhe", "dar-lhe"),       # pronome sem colisão
        ("tornou-\nse", "tornou-se"),   # "-ou" é desinência verbal
        ("levá-\nlo", "levá-lo"),       # vogal acentuada antes de "-lo"
        ("bem-\nestar", "bem-estar"),   # prefixo do acordo de 1990
        ("recém-\nchegado", "recém-chegado"),
        ("Vila-\nReal", "Vila-Real"),   # maiúscula: nome composto
    ],
)
def test_hifen_de_fim_de_linha(entrada: str, esperado: str) -> None:
    assert _juntar(entrada) == esperado


def test_o_proprio_livro_desempata() -> None:
    # "chamava" aparece solto no corpus, então "Chamava-\nse" é ênclise.
    assert _juntar("Chamava-\nse", "ele chamava o cão") == "Chamava-se"
    # E quando a palavra inteira aparece no corpus, junta sem hesitar.
    assert _juntar("ofici-\nna", "a oficina abriu") == "oficina"


def test_hifen_tipografico_tambem_conta() -> None:
    # O OCR devolve U+2010 em vez do hífen-menus em algumas fontes.
    assert _juntar("impres-\nsionante".replace("-", "‐")) == "impressionante"


def test_travessao_nao_e_hifen() -> None:
    # Juntar as palavras em volta de um travessão colaria duas frases.
    assert "—" in _juntar("disse —\nsem piscar")


# -- cabeçalhos e rodapés ------------------------------------------------


def test_assinatura_ignora_o_numero_que_muda() -> None:
    assert assinatura("O Nome da Rosa · 137") == assinatura("O Nome da Rosa · 254")


def test_repetida_no_topo_de_varias_paginas_e_marginal() -> None:
    paginas = [[f"UMBERTO ECO {n}", "corpo do texto aqui"] for n in range(6)]
    assert assinatura("UMBERTO ECO 1") in marginais_repetidas(paginas)


def test_linha_longa_nunca_e_cabecalho() -> None:
    """Um livro repete frases; um cabeçalho de corrida não tem 90 caracteres.

    Sem este teto, um refrão que calhasse de cair no topo de duas páginas
    seria apagado do livro inteiro, sem aviso.
    """
    longa = "Era uma vez um relojoeiro que consertava o tempo na cidade de Ouro Preto, todo dia."
    paginas = [[longa, "UMBERTO ECO 3"] for _ in range(6)]
    marginais = marginais_repetidas(paginas)
    assert assinatura(longa) not in marginais
    assert assinatura("UMBERTO ECO 3") in marginais  # o cabeçalho curto, sim


def test_poucas_paginas_nao_dao_amostra() -> None:
    paginas = [["TÍTULO 1", "texto"], ["TÍTULO 2", "texto"]]
    assert marginais_repetidas(paginas) == set()


@pytest.mark.parametrize("linha", ["137", "  42  ", "[15]", "— 7 —", "xiv", ""])
def test_numero_de_pagina_solto_e_descartavel(linha: str) -> None:
    assert descartavel(linha, set())


def test_texto_de_verdade_nao_e_descartavel() -> None:
    assert not descartavel("Ele abriu a porta.", set())


# -- notas e parágrafos --------------------------------------------------


def test_chamada_de_nota_colada_na_palavra_some() -> None:
    assert remover_marcas_de_nota("conforme Auerbach12 demonstrou") == (
        "conforme Auerbach demonstrou"
    )


@pytest.mark.parametrize(
    "texto",
    [
        "no dia 2 de abril",       # número separado por espaço é conteúdo
        "chegou às 7h30 da manhã",  # a letra antes tem só um caractere
        "em 1937 ele voltou",
    ],
)
def test_numeros_legitimos_sobrevivem(texto: str) -> None:
    assert remover_marcas_de_nota(texto) == texto


def test_linhas_viram_paragrafos_pela_linha_curta() -> None:
    linhas = [
        "Ele caminhou pela rua estreita e mal iluminada até o fim,",
        "pensando na conversa que tivera com o irmão na véspera.",
        "Depois voltou.",
        "O sol já se punha atrás do morro e a cidade inteira ficou",
        "vermelha por alguns minutos, como acontecia todo dia.",
    ]
    paragrafos = juntar_linhas(linhas)
    assert len(paragrafos) == 2
    assert paragrafos[0].endswith("Depois voltou.")
