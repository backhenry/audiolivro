"""EPUB -> blocos. O caso fácil, com duas armadilhas.

Um EPUB é HTML, então a estrutura que o PDF nos obriga a adivinhar já
vem escrita: `<h2>` é título, `<p>` é parágrafo, `<blockquote>` é
citação. Quase todo o trabalho é traduzir tags.

As duas armadilhas:

**A ordem não é a ordem dos arquivos.** É a do *spine*, que o EPUB
declara à parte. Ler os arquivos na ordem em que aparecem no zip embaralha
os capítulos em boa parte dos livros comerciais.

**O que não se lê.** Sumário navegável, número de nota sobrescrito,
crédito de imagem, cabeçalho de tabela. Na tela isso é mobília; no áudio
é texto lido em voz alta no meio do capítulo.
"""

from __future__ import annotations

import re
from pathlib import Path

from audiolivro.texto.estrutura import BlocoBruto
from audiolivro.texto.normalizar import juntar_letras_espacadas

# Tags cujo conteúdo inteiro é descartado antes de qualquer leitura.
# `figure` não está aqui de propósito: a imagem some, mas a legenda dela
# costuma ser texto que vale ouvir ("A bancada, em 1998").
DESCARTAR = (
    "script", "style", "nav", "sup", "sub", "table",
    "svg", "img", "head", "aside",
)

# Só tags de bloco. Um `<q>` ou um `<em>` no meio de uma frase é inline:
# tratá-lo como bloco partiria o parágrafo em três e perderia o texto que
# está em volta.
MAPA = {
    "h1": "titulo", "h2": "titulo", "h3": "subtitulo",
    "h4": "subtitulo", "h5": "subtitulo", "h6": "subtitulo",
    "p": "paragrafo", "div": "paragrafo",
    "blockquote": "citacao",
    "li": "lista", "dd": "lista", "dt": "lista",
    "figcaption": "legenda", "caption": "legenda",
    "pre": "paragrafo",
}

# Um <p> dentro de <blockquote> é citação, não parágrafo: o tipo do
# ancestral vence o da própria tag.
HERDA = {"blockquote", "li", "figcaption", "caption"}

_RE_CLASSE_NOTA = re.compile(r"\b(footnote|endnote|nota|note|calibre_note)\b", re.I)


def ler(caminho: Path, *, ler_notas: bool = False) -> tuple[dict, list[BlocoBruto]]:
    import warnings

    import ebooklib
    from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
    from ebooklib import epub

    # O conteúdo é XHTML e o parser é o de HTML, de propósito: EPUB
    # comercial vem com tag mal fechada com frequência, e o parser de XML
    # aborta o capítulo inteiro onde o de HTML segue em frente. O aviso
    # descreve corretamente a situação e não há nada a corrigir nela.
    warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

    livro = epub.read_epub(str(caminho), options={"ignore_ncx": False})
    meta = _metadados(livro, caminho)

    blocos: list[BlocoBruto] = []
    for item in _na_ordem_do_spine(livro, ebooklib):
        sopa = BeautifulSoup(item.get_content(), "lxml")
        for tag in sopa.find_all(DESCARTAR):
            tag.decompose()
        blocos.extend(_extrair(sopa, ler_notas=ler_notas))

    return meta, blocos


def _na_ordem_do_spine(livro, ebooklib) -> list:
    """Os documentos na ordem de leitura declarada pelo EPUB."""
    documentos = {
        item.get_id(): item
        for item in livro.get_items_of_type(ebooklib.ITEM_DOCUMENT)
    }
    ordenados = [
        documentos[idref]
        for idref, _linear in livro.spine
        if idref in documentos
    ]
    # Um spine quebrado (ou ausente) não pode custar o livro inteiro:
    # caímos na ordem do zip, que é errada mas é melhor que vazio.
    return ordenados or list(documentos.values())


def _extrair(sopa, *, ler_notas: bool) -> list[BlocoBruto]:
    blocos: list[BlocoBruto] = []
    corpo = sopa.body or sopa

    for tag in corpo.find_all(list(MAPA)):
        # Uma tag de bloco que contém outra é só um contêiner — o
        # `<blockquote>` em volta do `<p>`, o `<div>` em volta de tudo. O
        # texto dela será lido pelos filhos, com o tipo herdado via
        # `HERDA`; pegá-la também faria cada citação ser lida duas vezes.
        if tag.find(list(MAPA)):
            continue

        # A junção de letras espaçadas precisa vir antes do colapso dos
        # brancos: é o espaço duplo que diz onde a palavra terminou, em
        # "C A P Í T U L O  I". Depois de colapsar, some a pista.
        texto = " ".join(juntar_letras_espacadas(tag.get_text(" ", strip=True)).split())
        if not texto:
            continue

        classes = " ".join(tag.get("class") or []) + " " + (tag.get("epub:type") or "")
        e_nota = bool(_RE_CLASSE_NOTA.search(classes))
        if e_nota and not ler_notas:
            continue

        blocos.append(BlocoBruto(tipo="nota" if e_nota else _tipo(tag), texto=texto))

    return blocos


def _tipo(tag) -> str:
    for ancestral in tag.parents:
        if ancestral.name in HERDA:
            return MAPA[ancestral.name]
    return MAPA.get(tag.name, "paragrafo")


def _metadados(livro, caminho: Path) -> dict:
    def primeiro(campo: str) -> str:
        valores = livro.get_metadata("DC", campo)
        return valores[0][0].strip() if valores else ""

    return {
        "titulo": primeiro("title") or caminho.stem.replace("_", " "),
        "autor": primeiro("creator"),
        "idioma": primeiro("language") or "pt-BR",
    }
