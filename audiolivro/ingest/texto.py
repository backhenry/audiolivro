"""TXT e Markdown -> blocos.

Markdown é fácil: `#` é título, `>` é citação, `-` é lista. TXT puro é o
caso interessante, porque não há marcação nenhuma — só convenções. Duas
delas são universais o bastante para valer código: linha em branco separa
parágrafo, e uma linha curta e solta entre dois brancos é um título.

Arquivos de Projeto Gutenberg e afins costumam vir com as linhas quebradas
em 70 colunas. Isso não é parágrafo por linha — é a mesma coisa que o PDF
faz, e a reconstrução em `coerencia.juntar_linhas` resolve. Detectamos o
caso pelo formato do arquivo, não por opção do usuário, porque ninguém
sabe de cabeça se o .txt que baixou está quebrado ou não.
"""

from __future__ import annotations

import re
from pathlib import Path

from audiolivro.texto import coerencia
from audiolivro.texto.estrutura import _RE_CAPITULO, BlocoBruto, parece_titulo
from audiolivro.texto.normalizar import juntar_letras_espacadas

_RE_TITULO_MD = re.compile(r"^(#{1,6})\s+(.*)$")
_RE_CITACAO_MD = re.compile(r"^>\s?(.*)$")
_RE_LISTA_MD = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.*)$")
_RE_REGRA = re.compile(r"^\s*(?:[-*_=~]{3,}|\*\s?\*\s?\*)\s*$")
_RE_CERCA = re.compile(r"^\s*```")
_RE_ENFASE = re.compile(r"(\*{1,3}|_{1,3}|`)(.+?)\1")
_RE_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_RE_IMAGEM = re.compile(r"!\[[^\]]*\]\([^)]*\)")


def ler(caminho: Path, *, markdown: bool | None = None) -> tuple[dict, list[BlocoBruto]]:
    conteudo = caminho.read_text(encoding="utf-8", errors="replace")
    if markdown is None:
        markdown = caminho.suffix.lower() in (".md", ".markdown", ".mdown")

    meta = {"titulo": caminho.stem.replace("_", " "), "autor": ""}
    blocos = _markdown(conteudo) if markdown else _texto_puro(conteudo)

    # O primeiro título vira o nome do livro quando não há metadado
    # algum — a menos que ele seja só a marcação do primeiro capítulo,
    # caso em que o nome do arquivo diz mais.
    if blocos and blocos[0].tipo == "titulo" and not _RE_CAPITULO.match(blocos[0].texto):
        meta["titulo"] = blocos[0].texto
    return meta, blocos


def _markdown(conteudo: str) -> list[BlocoBruto]:
    blocos: list[BlocoBruto] = []
    acumulado: list[str] = []
    tipo_atual = "paragrafo"
    dentro_de_cerca = False

    def fechar() -> None:
        nonlocal acumulado, tipo_atual
        if acumulado:
            blocos.append(BlocoBruto(tipo=tipo_atual, texto=" ".join(acumulado)))
            acumulado = []
        tipo_atual = "paragrafo"

    for linha in conteudo.splitlines():
        if _RE_CERCA.match(linha):
            fechar()
            dentro_de_cerca = not dentro_de_cerca
            continue
        if dentro_de_cerca:
            continue  # bloco de código não se lê em voz alta

        linha = _RE_IMAGEM.sub("", linha)
        linha = _RE_LINK.sub(r"\1", linha)
        linha = _RE_ENFASE.sub(r"\2", linha)

        if not linha.strip() or _RE_REGRA.match(linha):
            fechar()
            continue

        if m := _RE_TITULO_MD.match(linha):
            fechar()
            nivel = len(m.group(1))
            blocos.append(
                BlocoBruto(tipo="titulo" if nivel <= 2 else "subtitulo", texto=m.group(2))
            )
            continue

        if m := _RE_CITACAO_MD.match(linha):
            if tipo_atual != "citacao":
                fechar()
                tipo_atual = "citacao"
            acumulado.append(m.group(1))
            continue

        if m := _RE_LISTA_MD.match(linha):
            fechar()
            blocos.append(BlocoBruto(tipo="lista", texto=m.group(1)))
            continue

        if tipo_atual == "citacao":
            fechar()
        acumulado.append(linha.strip())

    fechar()
    return blocos


def _texto_puro(conteudo: str) -> list[BlocoBruto]:
    conteudo = coerencia.desifenizar(conteudo, coerencia.vocabulario(conteudo))
    linhas = conteudo.splitlines()

    if _linhas_quebradas(linhas):
        paragrafos = coerencia.juntar_linhas(linhas)
    else:
        paragrafos = [
            # Mesma ordem do EPUB: juntar antes de colapsar, senão o
            # espaço duplo que separa as palavras espaçadas desaparece.
            " ".join(juntar_letras_espacadas(p).split())
            for p in re.split(r"\n\s*\n", conteudo)
            if p.strip()
        ]

    return [
        BlocoBruto(tipo="titulo" if parece_titulo(p) else "paragrafo", texto=p)
        for p in paragrafos
    ]


def _linhas_quebradas(linhas: list[str]) -> bool:
    """O arquivo tem quebra fixa de coluna (estilo Gutenberg)?

    O sinal é a regularidade: num texto quebrado em 70 colunas, a maioria
    das linhas não vazias chega perto do limite. Num texto com um
    parágrafo por linha, os comprimentos variam de dez a quinhentos
    caracteres, e essa concentração não existe.
    """
    cheias = [len(l) for l in linhas if l.strip()]
    if len(cheias) < 20:
        return False
    teto = max(cheias)
    if teto > 120:
        return False
    perto = sum(1 for c in cheias if c > teto * 0.7)
    return perto / len(cheias) > 0.6
