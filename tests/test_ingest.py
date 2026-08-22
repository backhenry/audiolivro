"""A camada de entrada — TXT, Markdown, EPUB e PDF virando `Livro`.

É o único ponto do pacote que não tinha teste nenhum, e é também o que
todo usuário atravessa primeiro: sem um extrator que não engula frases,
nem a revisão nem a síntese recebem o texto certo. Estes testes cobrem
os quatro formatos e o despacho por extensão de arquivo em `ingest.ler`.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from audiolivro import ingest
from audiolivro.ingest import epub as _epub
from audiolivro.ingest import pdf as _pdf
from audiolivro.ingest import texto as _texto
from audiolivro.texto.estrutura import titulo_falado


# -- despacho ------------------------------------------------------------


def test_arquivo_desconhecido_e_recusado(tmp_path: Path) -> None:
    arquivo = tmp_path / "livro.xyz"
    arquivo.write_text("não importa", encoding="utf-8")
    with pytest.raises(ingest.FormatoDesconhecido):
        ingest.ler(arquivo)


def test_arquivo_inexistente_levanta(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        ingest.ler(tmp_path / "soma.pdf")


@pytest.mark.parametrize("sufixo", [".md", ".markdown", ".mdown", ".text", ".txt"])
def test_extensoes_de_texto_sao_aceitas(tmp_path: Path, sufixo: str) -> None:
    arquivo = tmp_path / f"livro{sufixo}"
    arquivo.write_text("Um parágrafo só.", encoding="utf-8")
    livro = ingest.ler(arquivo)
    assert livro.capitulos, "um capítulo Início deveria ter sido criado"


# -- TXT puro ------------------------------------------------------------


def test_txt_sem_marcacao_agrupa_em_capitulo_unico(tmp_path: Path) -> None:
    arquivo = tmp_path / "livro.txt"
    arquivo.write_text(
        "Primeiro parágrafo. Com duas frases.\n\nSegundo parágrafo solto.",
        encoding="utf-8",
    )
    livro = ingest.ler(arquivo)
    assert len(livro.capitulos) == 1
    assert qualquer_fala(livro, "Primeiro parágrafo")
    assert qualquer_fala(livro, "Segundo parágrafo")


def test_txt_nome_do_arquivo_vira_titulo(tmp_path: Path) -> None:
    arquivo = tmp_path / "A Casa.txt"
    arquivo.write_text("Texto qualquer.", encoding="utf-8")
    assert ingest.ler(arquivo).titulo == "A Casa"


def test_txt_primeiro_titulo_vira_nome_do_livro(tmp_path: Path) -> None:
    arquivo = tmp_path / "livro.txt"
    arquivo.write_text(
        "O Nome da Rosa\n\nEra uma vez um livro.",
        encoding="utf-8",
    )
    livro = ingest.ler(arquivo)
    assert livro.titulo == "O Nome da Rosa"


def test_txt_linhas_quebradas_em_coluna_fixa_sao_recompostas(tmp_path: Path) -> None:
    """Arquivo estilo Gutenberg: linhas quebradas em ~70 colunas."""
    arquivo = tmp_path / "gutenberg.txt"
    linhas = [
        "Era uma vez um homem que morava numa casa muito grande no campo",
        "sossegado de Vila Real, perto de um rio fundo e de uma ponte.",
        "Ele gostava de passear todas as manhas bem cedo, antes do sol.",
        "Depois voltava para tomar o cafe e ler o jornal na varanda.",
    ]
    arquivo.write_text("\n".join(linhas), encoding="utf-8")
    livro = ingest.ler(arquivo)
    # As quatro linhas formam um único parágrafo contínuo.
    assert qualquer_fala(livro, "campo sossegado de Vila Real")


def test_txt_desifeniza_quebra_de_fim_de_linha(tmp_path: Path) -> None:
    arquivo = tmp_path / "livro.txt"
    arquivo.write_text("A palavra impres-\nsionante parte no fim da linha.", encoding="utf-8")
    livro = ingest.ler(arquivo)
    assert qualquer_fala(livro, "impressionante")


# -- Markdown ------------------------------------------------------------


def test_markdown_cabecalhos_criam_capitulos(tmp_path: Path) -> None:
    arquivo = tmp_path / "livro.md"
    arquivo.write_text("# Introdução\n\nPrimeiro capítulo.\n\n# Fim\n\nÚltimo.", encoding="utf-8")
    livro = ingest.ler(arquivo)
    assert [c.titulo for c in livro.capitulos] == ["Introdução", "Fim"]


def test_markdown_h1_e_h2_sao_titulos_h3_subtitulo(tmp_path: Path) -> None:
    arquivo = tmp_path / "livro.md"
    arquivo.write_text("# H1\n\n## H2\n\n### H3\n\nCorpo.", encoding="utf-8")
    blocos = _texto.ler(arquivo)[1]
    tipos = [b.tipo for b in blocos]
    assert tipos[:3] == ["titulo", "titulo", "subtitulo"]


def test_markdown_citacao_agrupa_linhas_vizinhas(tmp_path: Path) -> None:
    arquivo = tmp_path / "livro.md"
    arquivo.write_text("> Citação longa\n> continua no parágrafo seguinte.", encoding="utf-8")
    blocos = _texto.ler(arquivo)[1]
    assert blocos[0].tipo == "citacao"
    assert "Citação longa" in blocos[0].texto
    assert "continua" in blocos[0].texto


def test_markdown_lista_gera_um_bloco_por_item(tmp_path: Path) -> None:
    arquivo = tmp_path / "livro.md"
    arquivo.write_text("- primeiro\n- segundo\n\nCorpo depois.", encoding="utf-8")
    blocos = _texto.ler(arquivo)[1]
    assert [b.tipo for b in blocos[:2]] == ["lista", "lista"]
    assert [b.texto for b in blocos[:2]] == ["primeiro", "segundo"]


def test_markdown_fence_de_codigo_e_ignorado(tmp_path: Path) -> None:
    arquivo = tmp_path / "livro.md"
    arquivo.write_text(
        'Antes.\n\n```python\nprint("não se lê")\nx = 1\n```\n\nDepois.',
        encoding="utf-8",
    )
    blocos = _texto.ler(arquivo)[1]
    textos = [b.texto for b in blocos]
    assert not any("não se lê" in t for t in textos)
    assert any(t == "Antes." for t in textos)
    assert any(t == "Depois." for t in textos)


def test_markdown_enfase_link_e_imagem_sao_reduzidos(tmp_path: Path) -> None:
    arquivo = tmp_path / "livro.md"
    arquivo.write_text(
        "Negrito **forte** e *itálico* e `código` e [link](http://x) e ![img](img.png).",
        encoding="utf-8",
    )
    blocos = _texto.ler(arquivo)[1]
    texto = blocos[0].texto
    assert "forte" in texto and "*" not in texto
    assert "link" in texto and "http" not in texto
    assert "img" not in texto


def test_markdown_regra_horizontal_separa_blocos(tmp_path: Path) -> None:
    arquivo = tmp_path / "livro.md"
    arquivo.write_text("Parágrafo um.\n\n---\n\nParágrafo dois.", encoding="utf-8")
    blocos = _texto.ler(arquivo)[1]
    assert len(blocos) == 2


# -- EPUB ----------------------------------------------------------------


def _epub_minimo(caminho: Path, *, notas: bool = True) -> Path:
    """Monta um EPUB pequeno em memória, com dois documentos no spine."""
    cap1 = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>C1</title></head><body>
<h1>O Nome da Rosa</h1>
<p>Primeiro parágrafo da história. Continua aqui<script>alert('x')</script>.</p>
<p>Parágrafo com nota<sup>1</sup> de rodapé.</p>
<blockquote><p>Uma citação em bloco.</p></blockquote>
</body></html>"""
    cap2 = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>C2</title></head><body>
<h2>Capítulo II</h2><p>Segundo capítulo texto.</p>
</body></html>"""
    container = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
</rootfiles></container>"""
    opf = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="uid">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:title>O Nome da Rosa</dc:title><dc:creator>Umberto Eco</dc:creator><dc:language>pt-BR</dc:language>
</metadata>
<manifest>
<item id="c1" href="cap1.xhtml" media-type="application/xhtml+xml"/>
<item id="c2" href="cap2.xhtml" media-type="application/xhtml+xml"/>
<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
</manifest>
<spine toc="ncx"><itemref idref="c1"/><itemref idref="c2"/></spine></package>"""
    ncx = "<?xml version=\"1.0\"?><ncx xmlns=\"http://www.daisy.org/z3986/2005/ncx/\"><head/><docTitle><text>t</text></docTitle><navMap/></ncx>"

    with zipfile.ZipFile(caminho, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr("META-INF/container.xml", container)
        z.writestr("OEBPS/content.opf", opf)
        z.writestr("OEBPS/toc.ncx", ncx)
        z.writestr("OEBPS/cap1.xhtml", cap1)
        z.writestr("OEBPS/cap2.xhtml", cap2)
    return caminho


def test_epub_le_metadados(tmp_path: Path) -> None:
    meta, _blocos = _epub.ler(_epub_minimo(tmp_path / "t.epub"))
    assert meta["titulo"] == "O Nome da Rosa"
    assert meta["autor"] == "Umberto Eco"
    assert meta["idioma"] == "pt-BR"


def test_epub_tradutor_faz_o_basico(tmp_path: Path) -> None:
    livro = ingest.ler(_epub_minimo(tmp_path / "t.epub"))
    assert livro.titulo == "O Nome da Rosa"
    assert len(livro.capitulos) >= 2


def test_epub_citacao_dentro_de_blockquote_mantem_o_tipo(tmp_path: Path) -> None:
    blocos = _epub.ler(_epub_minimo(tmp_path / "t.epub"))[1]
    assert any(b.tipo == "citacao" for b in blocos)


def test_epub_script_e_removido_do_corpo(tmp_path: Path) -> None:
    livros_texto = " ".join(b.texto for b in _epub.ler(_epub_minimo(tmp_path / "t.epub"))[1])
    assert "alert" not in livros_texto
    assert "continua aqui" in livros_texto.lower()


def test_epub_nota_sup_nao_e_lida_no_corpo(tmp_path: Path) -> None:
    blocos = _epub.ler(_epub_minimo(tmp_path / "t.epub"))[1]
    assert not any(b.tipo == "nota" for b in blocos)


def test_epub_livro_vazio_vira_sem_capitulos(tmp_path: Path) -> None:
    # Um EPUB sem nenhum parágrafo útil não deve explodir.
    blocos = _epub.ler(_epub_minimo(tmp_path / "t.epub"))[1]
    assert blocos


# -- PDF -----------------------------------------------------------------


def test_pdf_extrai_texto_de_paragrafos(tmp_path: Path) -> None:
    import pymupdf

    doc = pymupdf.open()
    pagina = doc.new_page()
    pagina.insert_text(
        (72, 72), "Primeiro paragrafo de teste com texto suficiente.", fontsize=11
    )
    pagina.insert_text((72, 90), "Continuacao do mesmo paragrafo aqui.", fontsize=11)
    pagina.insert_text((72, 140), "Segundo texto depois.", fontsize=11)
    arquivo = tmp_path / "pagina.pdf"
    doc.save(str(arquivo))
    doc.close()

    meta, blocos = _pdf.ler(arquivo)
    assert meta["titulo"] == "pagina"
    textos = " ".join(b.texto for b in blocos)
    assert "Primeiro paragrafo" in textos
    assert "Segundo texto" in textos


def test_pdf_titulo_em_fonte_maior_e_detectado(tmp_path: Path) -> None:
    import pymupdf

    doc = pymupdf.open()
    pagina = doc.new_page()
    pagina.insert_text((72, 72), "Capítulo", fontsize=20)
    pagina.insert_text((72, 100), "Corpo do texto normal aqui.", fontsize=11)
    arquivo = tmp_path / "cap.pdf"
    doc.save(str(arquivo))
    doc.close()

    blocos = _pdf.ler(arquivo)[1]
    assert any(b.tipo == "titulo" for b in blocos)


def test_pdf_sem_conteudo_nao_explode(tmp_path: Path) -> None:
    import pymupdf

    doc = pymupdf.open()
    doc.new_page()
    arquivo = tmp_path / "branco.pdf"
    doc.save(str(arquivo))
    doc.close()
    meta, blocos = _pdf.ler(arquivo)
    assert blocos == []


# -- titular romano -----------------------------------------------------


@pytest.mark.parametrize(
    "romano, esperado",
    [
        ("XIV", "Capítulo catorze."),
        ("MCMXCVIII", "Capítulo mil novecentos e noventa e oito."),
        ("MMMCMXCIX", "Capítulo três mil novecentos e noventa e nove."),
    ],
)
def test_titulo_romano_longo_ganha_a_palavra_que_falta(romano: str, esperado: str) -> None:
    assert titulo_falado(romano) == esperado


def qualquer_fala(livro, trecho: str) -> bool:
    trecho = trecho.casefold()
    return any(trecho in f.texto.casefold() for f in livro.falas())