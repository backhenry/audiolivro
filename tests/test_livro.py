"""O `Livro`, o ritmo e a `Trilha`.

O ritmo é a decisão mais barata do pacote e a que mais muda o resultado.
Ele não aparece em nenhum lugar do texto — só no silêncio entre as falas
— então é exatamente o tipo de coisa que regride sem ninguém notar.
"""

from __future__ import annotations

import json

import pytest

from audiolivro.modelo import PAUSA, Fala, Livro, Marca, Trilha
from audiolivro.texto.estrutura import BlocoBruto, montar, parece_titulo, titulo_falado


@pytest.fixture
def livro() -> Livro:
    return montar(
        titulo="Teste",
        autor="Ninguém",
        blocos=[
            BlocoBruto("titulo", "Capítulo I"),
            BlocoBruto("paragrafo", "Primeira frase. Segunda frase."),
            BlocoBruto("citacao", "Uma citação curta."),
            BlocoBruto("titulo", "Capítulo II"),
            BlocoBruto("paragrafo", "Última frase do livro."),
        ],
    )


def test_estrutura_basica(livro: Livro) -> None:
    assert [c.titulo for c in livro.capitulos] == ["Capítulo I", "Capítulo II"]
    assert len(livro.capitulos[0].blocos) == 3


def test_ids_sao_estaveis_e_posicionais(livro: Livro) -> None:
    assert livro.capitulos[0].blocos[1].falas[0].id == "c001-b0001-f0"
    assert livro.capitulos[1].blocos[1].falas[0].id == "c002-b0001-f0"


def test_pausa_entre_frases_e_menor_que_entre_paragrafos(livro: Livro) -> None:
    paragrafo = livro.capitulos[0].blocos[1]
    assert paragrafo.falas[0].pausa == PAUSA["sentenca"]
    assert paragrafo.falas[1].pausa == PAUSA["citacao"] or paragrafo.falas[1].pausa > (
        PAUSA["sentenca"]
    )


def test_capitulo_fecha_com_silencio_maior(livro: Livro) -> None:
    fim_do_primeiro = livro.capitulos[0].falas()[-1]
    assert fim_do_primeiro.pausa == PAUSA["fim_capitulo"]


def test_livro_nao_termina_com_silencio(livro: Livro) -> None:
    # A pausa de fim de capítulo, no último, seria só um rabo de silêncio.
    assert livro.falas()[-1].pausa == 0.0


def test_nota_de_rodape_nao_entra_no_corpo() -> None:
    blocos = [BlocoBruto("paragrafo", "Texto."), BlocoBruto("nota", "1. Ver Auerbach.")]
    assert len(montar(titulo="X", blocos=blocos).falas()) == 1
    assert len(montar(titulo="X", blocos=blocos, ler_notas=True).falas()) == 2


@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("Capítulo XIV", True),
        ("XIV", True),
        ("7", True),
        ("O sino tocou", True),        # curto, sem ponto final
        ("Ele abriu a porta.", False),  # tem ponto final
        ("", False),
    ],
)
def test_deteccao_de_titulo(texto: str, esperado: bool) -> None:
    assert parece_titulo(texto) is esperado


def test_titulo_que_e_so_numeral_ganha_a_palavra_que_falta() -> None:
    # "XIV" sozinho não diz nada no ouvido: o olho lia o número dentro
    # da página, e o ouvido não tem página.
    assert titulo_falado("XIV") == "Capítulo catorze."
    assert titulo_falado("7") == "Capítulo sete."
    assert titulo_falado("A porta") == "A porta."


# -- serialização --------------------------------------------------------


def test_ida_e_volta_pelo_json(livro: Livro, tmp_path) -> None:
    caminho = livro.salvar(tmp_path / "l.livro.json")
    de_volta = Livro.carregar(caminho)
    assert de_volta.to_dict() == livro.to_dict()


def test_exibicao_igual_ao_texto_nao_e_gravada(tmp_path) -> None:
    # Repetir os dois campos em toda fala dobraria um JSON já grande.
    livro = Livro(titulo="X")
    dados = montar(titulo="X", blocos=[BlocoBruto("paragrafo", "Texto simples.")]).to_dict()
    fala = dados["capitulos"][0]["blocos"][0]["falas"][0]
    assert "exibicao" not in fala


def test_formato_do_futuro_e_recusado() -> None:
    with pytest.raises(ValueError, match="v99"):
        Livro.from_dict({"versao": 99, "titulo": "X"})


def test_pausa_negativa_e_recusada() -> None:
    with pytest.raises(ValueError, match="pausa negativa"):
        Fala(id="f", texto="a", exibicao="a", pausa=-1.0)


# -- trilha --------------------------------------------------------------


def test_busca_da_marca_que_esta_soando() -> None:
    trilha = Trilha(
        audio="x.m4b", duracao=30.0, motor="kokoro", voz="pf_dora",
        marcas=[Marca("a", 0.0, 5.0), Marca("b", 5.5, 4.0), Marca("c", 10.0, 6.0)],
    )
    assert trilha.marcas[trilha.indice_em(0.0)].fala == "a"
    assert trilha.marcas[trilha.indice_em(5.4)].fala == "a"   # dentro da pausa
    assert trilha.marcas[trilha.indice_em(5.5)].fala == "b"
    assert trilha.marcas[trilha.indice_em(99.0)].fala == "c"  # depois do fim


def test_trilha_faz_ida_e_volta(tmp_path) -> None:
    trilha = Trilha(
        audio="x.m4b", duracao=30.0, motor="kokoro", voz="pf_dora",
        marcas=[Marca("a", 0.0, 5.0)], capitulos=[("Um", 0.0)],
    )
    caminho = trilha.salvar(tmp_path / "t.trilha.json")
    assert Trilha.carregar(caminho).to_dict() == trilha.to_dict()
    assert json.loads(caminho.read_text(encoding="utf-8"))["marcas"] == [["a", 0.0, 5.0]]
