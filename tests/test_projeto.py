"""A biblioteca de projetos.

O teste que mais importa aqui é o da travessia de caminho. `apagar()`
recebe um nome vindo do navegador e chama `shutil.rmtree` — se a
validação falhar, o alvo é qualquer diretório da máquina.
"""

from __future__ import annotations

import pytest

from audiolivro import projeto as _projeto
from audiolivro.modelo import Livro, Marca, Trilha
from audiolivro.projeto import Projeto, ProjetoInvalido
from audiolivro.texto.estrutura import BlocoBruto, montar


@pytest.fixture(autouse=True)
def biblioteca_temporaria(tmp_path, monkeypatch):
    """Nunca toca em ~/Audiolivros de verdade — estes testes apagam pastas."""
    pasta = tmp_path / "Audiolivros"
    monkeypatch.setattr(_projeto, "BIBLIOTECA", pasta)
    return pasta


def _livro(titulo: str = "O Relojoeiro") -> Livro:
    return montar(
        titulo=titulo,
        autor="Machado de Sousa",
        blocos=[BlocoBruto("titulo", "Capítulo I"), BlocoBruto("paragrafo", "Texto.")],
    )


def _trilha() -> Trilha:
    return Trilha(
        audio="audio.m4b", duracao=42.0, motor="kokoro", voz="pf_dora",
        marcas=[Marca("c001-b0000-f0", 0.0, 1.0)], capitulos=[("Capítulo I", 0.0)],
    )


# -- criar e carregar ----------------------------------------------------


def test_criar_faz_uma_pasta_com_o_livro_dentro(biblioteca_temporaria) -> None:
    p = _projeto.criar(_livro())
    assert p.pasta.parent == biblioteca_temporaria
    assert (p.pasta / "livro.json").exists()
    assert p.nome == "O Relojoeiro"


def test_original_e_guardado_junto(tmp_path) -> None:
    origem = tmp_path / "baixado.epub"
    origem.write_bytes(b"conteudo")
    p = _projeto.criar(_livro(), origem=origem)
    # Guardar o original é o que permite reextrair com OCR ou com notas
    # depois, sem pedir o arquivo de novo.
    assert p.original().name == "original.epub"
    assert p.original().read_bytes() == b"conteudo"


def test_carregar_devolve_o_que_foi_gravado() -> None:
    criado = _projeto.criar(_livro())
    lido = _projeto.carregar(criado.nome)
    assert lido.livro.titulo == "O Relojoeiro"
    assert lido.trilha is None  # ainda não sintetizado


def test_trilha_sem_audio_nao_conta_como_pronto() -> None:
    p = _projeto.criar(_livro())
    p.gravar_trilha(_trilha())  # grava a trilha, mas nenhum .m4b existe
    assert _projeto.carregar(p.nome).trilha is None
    assert p.audio() is None


def test_projeto_pronto_quando_o_audio_existe() -> None:
    p = _projeto.criar(_livro())
    p.gravar_trilha(_trilha())
    (p.pasta / "audio.m4b").write_bytes(b"\0" * 100)
    recarregado = _projeto.carregar(p.nome)
    assert recarregado.trilha is not None
    assert recarregado.audio().name == "audio.m4b"


# -- nomes ---------------------------------------------------------------


@pytest.mark.parametrize(
    "titulo, esperado",
    [
        ("O Nome da Rosa", "O Nome da Rosa"),
        ("Ficção: uma história", "Ficção uma história"),   # ':' quebra caminho
        ("A/B testing", "A B testing"),
        ("   ", "Livro sem título"),
        (".oculto", "oculto"),                              # ponto inicial esconde
    ],
)
def test_titulo_vira_nome_de_pasta(titulo: str, esperado: str) -> None:
    assert _projeto._nome_de_pasta(titulo) == esperado


def test_titulos_iguais_nao_se_sobrescrevem() -> None:
    a = _projeto.criar(_livro("Mesmo Título"))
    b = _projeto.criar(_livro("Mesmo Título"))
    assert a.pasta != b.pasta
    assert b.nome == "Mesmo Título (2)"


def test_reabrir_o_mesmo_livro_reencontra_o_projeto() -> None:
    """Senão cada reabertura criaria uma cópia e jogaria fora as correções."""
    criado = _projeto.criar(_livro("O Relojoeiro"))
    assert _projeto.por_titulo("o relojoeiro").nome == criado.nome
    assert _projeto.por_titulo("Outro Livro") is None


# -- segurança -----------------------------------------------------------


@pytest.mark.parametrize(
    "nome", ["..", "../..", "/etc", "a/b", "a\\b", "", ".", "não-existe"]
)
def test_nome_perigoso_e_recusado(nome: str) -> None:
    # `apagar` chama rmtree no que isto devolver.
    with pytest.raises(ProjetoInvalido):
        _projeto.pasta_de(nome)


def test_link_para_fora_da_biblioteca_e_recusado(biblioteca_temporaria, tmp_path) -> None:
    """Um link dentro da biblioteca apontando para fora não pode passar.

    É por isso que a checagem acontece *depois* de resolver o caminho: em
    `BIBLIOTECA / nome` o link ainda parece um filho bem-comportado.
    """
    biblioteca_temporaria.mkdir(parents=True, exist_ok=True)
    alvo = tmp_path / "importante"
    alvo.mkdir()
    (biblioteca_temporaria / "atalho").symlink_to(alvo, target_is_directory=True)

    with pytest.raises(ProjetoInvalido):
        _projeto.pasta_de("atalho")
    assert alvo.exists()


# -- apagar --------------------------------------------------------------


def test_apagar_leva_a_pasta_inteira(biblioteca_temporaria) -> None:
    p = _projeto.criar(_livro())
    _projeto.apagar(p.nome)
    assert not p.pasta.exists()
    assert biblioteca_temporaria.exists()  # a biblioteca em si fica


def test_apagar_audio_preserva_o_texto_revisado() -> None:
    """A revisão do texto é o trabalho caro; o áudio se refaz do cache."""
    p = _projeto.criar(_livro())
    p.gravar_trilha(_trilha())
    (p.pasta / "audio.m4b").write_bytes(b"\0" * 100)
    p.cache.mkdir()
    (p.cache / "abc.flac").write_bytes(b"\0")

    p.livro.capitulos[0].blocos[1].falas[0].texto = "Texto corrigido."
    p.gravar_livro()
    p.apagar_audio()

    assert not (p.pasta / "audio.m4b").exists()
    assert not p.cache.exists()
    assert p.trilha is None
    assert _projeto.carregar(p.nome).livro.capitulos[0].blocos[1].falas[0].texto == (
        "Texto corrigido."
    )


# -- listagem ------------------------------------------------------------


def test_listar_ignora_pasta_que_nao_e_projeto(biblioteca_temporaria) -> None:
    _projeto.criar(_livro("Um"))
    (biblioteca_temporaria / "lixo").mkdir()
    (biblioteca_temporaria / ".entrada").mkdir()  # área temporária do upload
    assert [p.livro.titulo for p in _projeto.listar()] == ["Um"]


def test_listar_ignora_projeto_corrompido(biblioteca_temporaria) -> None:
    _projeto.criar(_livro("Bom"))
    quebrado = biblioteca_temporaria / "Quebrado"
    quebrado.mkdir()
    (quebrado / "livro.json").write_text("{isto não é json", encoding="utf-8")
    # Um projeto ilegível não pode derrubar a lista inteira.
    assert [p.livro.titulo for p in _projeto.listar()] == ["Bom"]


def test_resumo_traz_o_que_o_cartao_mostra() -> None:
    p = _projeto.criar(_livro())
    resumo = p.resumo()
    assert resumo["titulo"] == "O Relojoeiro"
    assert resumo["autor"] == "Machado de Sousa"
    assert resumo["pronto"] is False
    assert resumo["tamanho"] > 0


def test_posicao_sobrevive_a_um_arquivo_corrompido() -> None:
    p = _projeto.criar(_livro())
    (p.pasta / "posicao.json").write_text("{quebrado", encoding="utf-8")
    # Marcador ilegível não pode impedir de abrir o livro.
    assert p.posicao() == {"segundo": 0.0, "velocidade": 1.0}


def test_posicao_nao_passa_do_fim() -> None:
    p = _projeto.criar(_livro())
    p.gravar_trilha(_trilha())  # 42 segundos
    assert p.guardar_posicao(9999.0, 1.5)["segundo"] == 42.0
    assert p.guardar_posicao(-5.0, 1.0)["segundo"] == 0.0
