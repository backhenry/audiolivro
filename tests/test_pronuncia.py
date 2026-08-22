"""O dicionário de pronúncia do livro.

A correção por frase não escala: num livro sobre a Cinérea, o nome
aparece dezenas de vezes. Aqui uma entrada vale para o livro inteiro — e
a parte delicada é casar o termo certo, sem alcançar palavras vizinhas.
"""

from __future__ import annotations

import pytest

from audiolivro.texto.pronuncia import aplicar, carregar, ocorrencias, salvar


def test_troca_a_palavra_pela_forma_falada() -> None:
    assert aplicar("A Cinérea abriu.", {"Cinérea": "Cinêrea"}) == "A Cinêrea abriu."


def test_ignora_maiusculas_ao_procurar() -> None:
    """Um título em caixa alta é a mesma palavra do corpo do texto."""
    d = {"Cinérea": "Cinêrea"}
    assert aplicar("CINÉREA", d) == "Cinêrea"
    assert aplicar("cinérea", d) == "Cinêrea"


def test_o_termo_mais_longo_ganha() -> None:
    """As entradas se contêm, e a ordem decide qual casa primeiro.

    Com "Ouro Preto" e "Preto" no mesmo dicionário, a ordem alfabética
    faria "Preto" casar antes e "Ouro Preto" nunca ser alcançado.
    """
    d = {"Preto": "Prêto", "Ouro Preto": "Ôro Prêto"}
    assert aplicar("mora em Ouro Preto hoje", d) == "mora em Ôro Prêto hoje"
    assert aplicar("o gato Preto", d) == "o gato Prêto"


@pytest.mark.parametrize(
    "texto",
    [
        "cinéreas no plural",     # outra palavra: quem quiser, cadastra
        "Cinéreamente",           # o termo está dentro de outra
        "subCinérea",
    ],
)
def test_nao_alcanca_palavra_vizinha(texto: str) -> None:
    """A borda usa a faixa latina porque `\\b` não serve aqui.

    Para o `\\b` do Python, "Cinérea" termina no "n": o acento não conta
    como caractere de palavra em todo contexto, e a entrada casaria no
    meio de palavras maiores.
    """
    assert aplicar(texto, {"Cinérea": "Cinêrea"}) == texto


def test_dicionario_vazio_nao_toca_no_texto() -> None:
    assert aplicar("Nada muda aqui.", {}) == "Nada muda aqui."


def test_conta_em_quantas_falas_o_termo_aparece() -> None:
    """A contagem é o que denuncia a entrada que não casa com nada."""
    falas = ["A Cinérea abriu", "sem relação", "CINÉREA de novo", "cinéreas"]
    assert ocorrencias(falas, "Cinérea") == 2
    assert ocorrencias(falas, "Inexistente") == 0


def test_ida_e_volta_pelo_arquivo(tmp_path) -> None:
    salvar(tmp_path, {"Cinérea": "Cinêrea", "  ": "vazio", "ok": "  "})
    # Entradas em branco não sobrevivem: elas casariam com tudo ou nada.
    assert carregar(tmp_path) == {"Cinérea": "Cinêrea"}


def test_arquivo_corrompido_nao_impede_de_gerar(tmp_path) -> None:
    (tmp_path / "pronuncia.json").write_text("{quebrado", encoding="utf-8")
    assert carregar(tmp_path) == {}


def test_o_dicionario_entra_na_chave_do_cache() -> None:
    """É o que faz mudar uma entrada re-sintetizar só as falas afetadas."""
    from audiolivro.sintetizar import _chave

    sem = _chave("A Cinérea abriu.", "piper", "jeff", 1.0)
    com = _chave(aplicar("A Cinérea abriu.", {"Cinérea": "Cinêrea"}), "piper", "jeff", 1.0)
    assert sem != com
