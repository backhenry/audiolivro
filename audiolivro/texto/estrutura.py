"""De blocos brutos para um `Livro`: capítulos, falas e ritmo.

Todos os quatro formatos de entrada convergem aqui. O EPUB chega com a
estrutura pronta e quase não usa a detecção de capítulo; o PDF e o TXT
chegam com uma lista plana de parágrafos e dependem inteiramente dela.
Manter o estágio comum evita que "capítulo" signifique uma coisa quando
o livro vem de EPUB e outra quando vem de PDF.

É aqui também que se decide o ritmo — quanto silêncio vai depois de cada
fala. É a decisão mais barata de tomar e a que mais muda o resultado: a
mesma voz, com as mesmas palavras, soa competente ou apressada só em
função disso.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from audiolivro.modelo import PAUSA, Bloco, Capitulo, Fala, Livro, TipoBloco
from audiolivro.texto.normalizar import limpar, normalizar
from audiolivro.texto.numeros import por_extenso, romano_para_int
from audiolivro.texto.sentencas import falar


@dataclass
class BlocoBruto:
    """O que os leitores de formato produzem. Texto e tipo, nada mais."""

    tipo: TipoBloco
    texto: str


_RE_CAPITULO = re.compile(
    r"^\s*(cap[íi]tulo|cap\.|parte|livro|se[çc][ãa]o|ato|canto|t[íi]tulo|"
    r"ep[íi]logo|pr[óo]logo|pref[áa]cio|introdu[çc][ãa]o|conclus[ãa]o|"
    r"posf[áa]cio|ap[êe]ndice|anexo|nota do autor|agradecimentos)\b",
    re.IGNORECASE,
)
_RE_SO_NUMERAL = re.compile(r"^\s*(\d{1,3}|[IVXLCDM]{1,15})\s*[.\-—–]?\s*$")
_RE_PONTUACAO_FINAL = re.compile(r"[.!?,;:]$")
# O número que abre a nota é a chamada dela, não conteúdo. Lido em voz
# alta, "um. Ver Auerbach" começa a nota com um número solto que o
# ouvinte não tem como relacionar a nada.
_RE_MARCADOR_DE_NOTA = re.compile(r"^\s*[\[\(]?\d{1,3}[\]\)]?\s*[.)\-—]?\s+")


def parece_titulo(texto: str) -> bool:
    """Uma linha solta é título de capítulo?

    Três sinais, em ordem de confiança. A palavra "Capítulo" é quase
    conclusiva. Um numeral sozinho numa linha também: nenhum parágrafo de
    prosa consiste em "XIV". O terceiro sinal — linha curta, sem
    pontuação final — é o mais fraco e o mais útil, porque é assim que a
    maioria dos títulos de romance aparece.
    """
    s = texto.strip()
    if not s or len(s) > 90:
        return False
    if _RE_CAPITULO.match(s):
        return True
    if _RE_SO_NUMERAL.match(s):
        return True
    if _RE_PONTUACAO_FINAL.search(s):
        return False
    # Linha curta sem ponto final, começando em maiúscula. Exigimos no
    # máximo dez palavras: acima disso é mais provável ser uma frase que
    # perdeu o ponto na extração do que um título.
    return len(s.split()) <= 10 and s[:1].isupper()


def titulo_falado(texto: str) -> str:
    """Como o título deve soar.

    Um capítulo chamado "XIV" está escrito para o olho, que lê o número
    dentro da página. Sozinho, no ouvido, "catorze" não diz nada — falta
    a palavra que o olho supriu. Então repomos "Capítulo".
    """
    s = limpar(texto).strip()
    m = _RE_SO_NUMERAL.match(s)
    if m:
        bruto = m.group(1)
        valor = int(bruto) if bruto.isdigit() else romano_para_int(bruto)
        if valor is not None:
            return f"Capítulo {por_extenso(valor)}."
    return normalizar(s)


def montar(
    *,
    titulo: str,
    autor: str = "",
    blocos: list[BlocoBruto],
    origem: str = "",
    idioma: str = "pt-BR",
    ler_notas: bool = False,
) -> Livro:
    """Blocos brutos -> `Livro` com ids estáveis, falas e pausas."""
    livro = Livro(titulo=titulo, autor=autor, idioma=idioma, origem=origem)
    capitulo: Capitulo | None = None
    n_bloco = 0

    for bruto in blocos:
        texto = limpar(bruto.texto)
        if not texto:
            continue
        if bruto.tipo == "nota":
            if not ler_notas:
                continue
            texto = _RE_MARCADOR_DE_NOTA.sub("", texto)

        # Um título abre capítulo. O primeiro bloco de um livro sem
        # título nenhum também precisa de um capítulo onde morar, e é por
        # isso que existe o ramo do "Início".
        if bruto.tipo in ("titulo", "subtitulo") or capitulo is None:
            if bruto.tipo in ("titulo", "subtitulo"):
                nome = texto
            else:
                nome = livro.titulo or "Início"
            capitulo = Capitulo(id=f"c{len(livro.capitulos) + 1:03d}", titulo=nome)
            livro.capitulos.append(capitulo)
            n_bloco = 0
            if bruto.tipo in ("titulo", "subtitulo"):
                capitulo.blocos.append(
                    _bloco(capitulo.id, n_bloco, bruto.tipo, texto,
                           [titulo_falado(texto)], PAUSA["depois_titulo"])
                )
                n_bloco += 1
                continue

        pedacos = falar(texto)
        normalizados = [(p, normalizar(p)) for p in pedacos]
        audiveis = [(p, n) for p, n in normalizados if n]
        if not audiveis:
            continue

        capitulo.blocos.append(
            _bloco(
                capitulo.id,
                n_bloco,
                bruto.tipo,
                texto,
                [n for _, n in audiveis],
                _pausa_do_tipo(bruto.tipo),
                exibicoes=[p for p, _ in audiveis],
            )
        )
        n_bloco += 1

    _fechar_capitulos(livro)
    return livro


def _bloco(
    capitulo_id: str,
    indice: int,
    tipo: TipoBloco,
    exibicao: str,
    textos: list[str],
    pausa_final: float,
    exibicoes: list[str] | None = None,
) -> Bloco:
    bloco_id = f"{capitulo_id}-b{indice:04d}"
    exibicoes = exibicoes or textos
    falas = [
        Fala(
            id=f"{bloco_id}-f{i}",
            texto=texto,
            exibicao=exibicoes[i],
            pausa=pausa_final if i == len(textos) - 1 else PAUSA["sentenca"],
        )
        for i, texto in enumerate(textos)
    ]
    return Bloco(id=bloco_id, tipo=tipo, exibicao=exibicao, falas=falas)


def _pausa_do_tipo(tipo: TipoBloco) -> float:
    return {
        "citacao": PAUSA["citacao"],
        "verso": PAUSA["verso"],
        "lista": PAUSA["lista"],
        "legenda": PAUSA["paragrafo"],
        "nota": PAUSA["paragrafo"],
    }.get(tipo, PAUSA["paragrafo"])


def _fechar_capitulos(livro: Livro) -> None:
    """Silêncio maior no fim de cada capítulo — e nenhum no fim do livro.

    A pausa final de capítulo é o que dá ao ouvinte a chance de perceber
    que uma parte terminou. No último capítulo ela vira só um rabo de
    silêncio no arquivo, então é cortada.
    """
    for capitulo in livro.capitulos:
        falas = capitulo.falas()
        if falas:
            falas[-1].pausa = PAUSA["fim_capitulo"]

    todas = livro.falas()
    if todas:
        todas[-1].pausa = 0.0


def remover_capitulos_vazios(livro: Livro) -> Livro:
    """Tira capítulos que só têm o título — folha de rosto, página em branco."""
    livro.capitulos = [
        c for c in livro.capitulos
        if any(b.tipo not in ("titulo", "subtitulo") for b in c.blocos)
    ]
    return livro
