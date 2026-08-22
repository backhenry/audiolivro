"""PDF -> blocos. O leitor mais difícil dos quatro.

Um PDF não tem parágrafos, capítulos nem noção de "corpo do texto". Tem
caracteres com coordenadas. Tudo o que este módulo faz é reconstruir, a
partir de geometria e tamanho de fonte, a estrutura que o diagramador
destruiu ao imprimir.

A ordem das perguntas é o projeto do módulo:

1. Qual é o tamanho de fonte do corpo? Tudo depois disso é relativo a
   ele — título é o que é maior, nota de rodapé é o que é menor. Medir
   isso primeiro é o que faz o extrator funcionar em livro de bolso e em
   manual técnico sem configuração.
2. A página tem uma ou duas colunas? Errar aqui embaralha as frases das
   duas colunas, e o texto vira ruído — é o pior defeito possível, e o
   único que não dá para perceber sem ler o resultado.
3. Que linhas não são texto? Cabeçalho, rodapé, número de página.
4. Onde termina cada parágrafo? Espaçamento vertical, recuo e linha
   curta — nessa ordem de confiança.

Só depois disso o texto vira `BlocoBruto`.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from statistics import median

from audiolivro.ingest.ocr import OCRIndisponivel, disponivel as ocr_disponivel, reconhecer
from audiolivro.texto import coerencia
from audiolivro.texto.estrutura import BlocoBruto, parece_titulo
from audiolivro.texto.normalizar import juntar_letras_espacadas

# Abaixo disso a página é imagem: o extrator devolveu quase nada porque
# não há texto embutido, só o retrato de uma página impressa.
LIMIAR_OCR = 40
DPI_OCR = 300


@dataclass
class Linha:
    texto: str
    x0: float
    y0: float
    x1: float
    y1: float
    tamanho: float
    negrito: bool = False

    @property
    def largura(self) -> float:
        return self.x1 - self.x0


@dataclass
class Pagina:
    numero: int
    largura: float
    altura: float
    linhas: list[Linha]
    veio_de_ocr: bool = False


def ler(
    caminho: Path,
    *,
    paginas: range | None = None,
    ocr: str = "auto",
    ler_notas: bool = False,
) -> tuple[dict, list[BlocoBruto]]:
    """Extrai metadados e blocos de um PDF.

    `ocr` aceita "auto" (só nas páginas sem texto embutido), "sempre" e
    "nunca". "auto" é o certo para quase tudo, inclusive para o caso
    comum de um livro digital com um caderno de fotos escaneado no meio.
    """
    import pymupdf

    doc = pymupdf.open(caminho)
    try:
        indices = paginas if paginas is not None else range(doc.page_count)
        lidas = [
            _ler_pagina(doc, i, modo_ocr=ocr)
            for i in indices
            if 0 <= i < doc.page_count
        ]
        meta = _metadados(doc, caminho)
    finally:
        doc.close()

    lidas = [p for p in lidas if p.linhas]
    if not lidas:
        return meta, []

    corpo = _tamanho_do_corpo(lidas)
    marginais = coerencia.marginais_repetidas(
        [[l.texto for l in p.linhas] for p in lidas]
    )
    # O vocabulário é do livro inteiro, não da página: a palavra que
    # resolve um hífen partido no capítulo 2 costuma estar no capítulo 9.
    vocab = coerencia.vocabulario(
        "\n".join(l.texto for p in lidas for l in p.linhas)
    )

    blocos: list[BlocoBruto] = []
    notas: list[BlocoBruto] = []
    for pagina in lidas:
        uteis, rodape = _separar(pagina, corpo, marginais)
        for coluna in _colunas(pagina, uteis):
            blocos.extend(_paragrafos(coluna, corpo, pagina, vocab=vocab))
        if ler_notas and rodape:
            notas.extend(
                _paragrafos(rodape, corpo, pagina, vocab=vocab, forcar="nota")
            )

    blocos = _costurar_paginas(blocos, vocab)
    return meta, blocos + notas


# -- leitura de uma página ----------------------------------------------


def _ler_pagina(doc, indice: int, *, modo_ocr: str) -> Pagina:
    pagina = doc[indice]
    caixa = pagina.rect
    linhas = [] if modo_ocr == "sempre" else _linhas_embutidas(pagina)

    caracteres = sum(len(l.texto) for l in linhas)
    precisa = modo_ocr == "sempre" or (modo_ocr == "auto" and caracteres < LIMIAR_OCR)
    if precisa and ocr_disponivel():
        try:
            linhas = _linhas_ocr(pagina, caixa.width, caixa.height)
            return Pagina(indice, caixa.width, caixa.height, linhas, veio_de_ocr=True)
        except OCRIndisponivel:
            pass  # segue com o que houver de texto embutido

    return Pagina(indice, caixa.width, caixa.height, linhas)


def _linhas_embutidas(pagina) -> list[Linha]:
    dados = pagina.get_text("dict")
    linhas: list[Linha] = []
    for bloco in dados.get("blocks", []):
        if bloco.get("type") != 0:  # 0 = texto; 1 = imagem
            continue
        for linha in bloco.get("lines", []):
            spans = linha.get("spans", [])
            texto = "".join(s.get("text", "") for s in spans).strip()
            if not texto:
                continue
            # O tamanho da linha é o do span mais longo, não a média: uma
            # capitular ou um expoente puxariam a média e a linha inteira
            # seria classificada errado.
            principal = max(spans, key=lambda s: len(s.get("text", "")))
            x0, y0, x1, y1 = linha["bbox"]
            linhas.append(
                Linha(
                    texto=texto,
                    x0=x0, y0=y0, x1=x1, y1=y1,
                    tamanho=round(float(principal.get("size", 10.0)), 1),
                    negrito=bool(principal.get("flags", 0) & 2**4),
                )
            )
    linhas.sort(key=lambda l: (round(l.y0, 1), l.x0))
    return linhas


def _linhas_ocr(pagina, largura: float, altura: float) -> list[Linha]:
    import pymupdf

    escala = DPI_OCR / 72.0
    pix = pagina.get_pixmap(matrix=pymupdf.Matrix(escala, escala))
    achadas = reconhecer(pix.tobytes("png"), largura, altura)
    return [
        Linha(
            texto=l.texto,
            x0=l.x0, y0=l.y0, x1=l.x1, y1=l.y1,
            # Sem informação de fonte, a altura da caixa é a melhor
            # aproximação — e como todas as comparações aqui são
            # relativas ao corpo, a escala arbitrária não atrapalha.
            tamanho=round(l.altura, 1),
        )
        for l in achadas
        if l.confianca > 0.30
    ]


def _metadados(doc, caminho: Path) -> dict:
    meta = doc.metadata or {}
    titulo = (meta.get("title") or "").strip()
    return {
        "titulo": titulo or caminho.stem.replace("_", " "),
        "autor": (meta.get("author") or "").strip(),
        "paginas": doc.page_count,
    }


# -- medidas globais -----------------------------------------------------


def _tamanho_do_corpo(paginas: list[Pagina]) -> float:
    """O tamanho de fonte do corpo do texto, pesado por quantidade de texto.

    Pesar por caracteres e não por número de linhas é o que impede que um
    livro com muitos títulos curtos eleja o tamanho do título como corpo.

    A estatística muda conforme a origem. Num PDF com texto embutido o
    tamanho é exato e a moda acerta em cheio. No OCR ele é a altura da
    caixa, que varia com acento e descendente na mesma fonte — e a moda
    de um valor ruidoso escolhe um pico acidental. Aí a mediana é a
    medida certa, porque atravessa o ruído em vez de se prender a ele.
    """
    amostras: list[tuple[float, int]] = [
        (linha.tamanho, len(linha.texto))
        for pagina in paginas
        for linha in pagina.linhas
    ]
    if not amostras:
        return 10.0

    if any(p.veio_de_ocr for p in paginas):
        expandidas = sorted(t for t, peso in amostras for _ in range(max(peso // 4, 1)))
        return expandidas[len(expandidas) // 2]

    peso: Counter[float] = Counter()
    for tamanho, caracteres in amostras:
        peso[tamanho] += caracteres
    return peso.most_common(1)[0][0]


def _separar(
    pagina: Pagina, corpo: float, marginais: set[str]
) -> tuple[list[Linha], list[Linha]]:
    """Divide as linhas em (corpo do texto, notas de rodapé)."""
    topo = pagina.altura * 0.075
    pe = pagina.altura * 0.925
    zona_de_nota = pagina.altura * 0.68

    uteis: list[Linha] = []
    rodape: list[Linha] = []
    for linha in pagina.linhas:
        if coerencia.descartavel(linha.texto, marginais):
            continue
        # Uma linha na margem só é descartada se for curta. Num livro sem
        # margens generosas, a primeira linha do parágrafo pode encostar
        # no topo, e jogá-la fora comeria o começo do capítulo.
        if (linha.y1 < topo or linha.y0 > pe) and len(linha.texto) < 60:
            continue
        if linha.tamanho < corpo * 0.90 and linha.y0 > zona_de_nota:
            rodape.append(linha)
            continue
        uteis.append(linha)
    return uteis, rodape


def _colunas(pagina: Pagina, linhas: list[Linha]) -> list[list[Linha]]:
    """Uma ou duas colunas? Devolve as linhas já na ordem de leitura.

    O teste é a calha: se quase nenhuma linha atravessa a faixa central
    da página, e há texto suficiente dos dois lados, então o que parece
    uma página é na verdade duas. Ler duas colunas como uma intercala as
    frases e destrói o texto de um jeito que só se percebe ouvindo.
    """
    if len(linhas) < 6:
        return [linhas]

    centro = pagina.largura / 2
    faixa = pagina.largura * 0.04
    atravessam = sum(1 for l in linhas if l.x0 < centro - faixa < centro + faixa < l.x1)
    if atravessam > len(linhas) * 0.12:
        return [linhas]

    esquerda = [l for l in linhas if (l.x0 + l.x1) / 2 < centro]
    direita = [l for l in linhas if (l.x0 + l.x1) / 2 >= centro]
    if min(len(esquerda), len(direita)) < len(linhas) * 0.25:
        return [linhas]
    return [esquerda, direita]


# -- parágrafos ----------------------------------------------------------


def _paragrafos(
    linhas: list[Linha],
    corpo: float,
    pagina: Pagina,
    *,
    vocab: tuple[set[str], set[str]] | None = None,
    forcar: str | None = None,
) -> list[BlocoBruto]:
    if not linhas:
        return []

    espacamento = _espacamento_tipico(linhas)
    margem_esq = min(l.x0 for l in linhas)
    margem_dir = max(l.x1 for l in linhas)
    largura = max(margem_dir - margem_esq, 1.0)

    grupos: list[list[Linha]] = [[linhas[0]]]
    for anterior, atual in zip(linhas, linhas[1:]):
        if _quebra(
            anterior, atual, espacamento, margem_esq, largura, corpo,
            exato=not pagina.veio_de_ocr,
        ):
            grupos.append([atual])
        else:
            grupos[-1].append(atual)

    blocos: list[BlocoBruto] = []
    for grupo in grupos:
        texto = coerencia.desifenizar("\n".join(l.texto for l in grupo), vocab)
        # Antes de colapsar os brancos: num título espaçado, o limite
        # entre palavras chega como quebra de linha ("C A P Í T U L O" numa
        # linha, "I I I" na outra), e colapsar primeiro apagaria a pista.
        texto = juntar_letras_espacadas(texto)
        texto = " ".join(texto.split())
        if not texto:
            continue
        texto = coerencia.remover_marcas_de_nota(texto)
        tipo = forcar or _classificar(
            grupo, texto, corpo, margem_esq, largura, exato=not pagina.veio_de_ocr
        )
        blocos.append(BlocoBruto(tipo=tipo, texto=texto))
    return blocos


def _espacamento_tipico(linhas: list[Linha]) -> float:
    saltos = [
        b.y0 - a.y0
        for a, b in zip(linhas, linhas[1:])
        if 0 < b.y0 - a.y0 < 100
    ]
    return median(saltos) if saltos else 12.0


def _quebra(
    anterior: Linha,
    atual: Linha,
    espacamento: float,
    margem_esq: float,
    largura: float,
    corpo: float,
    *,
    exato: bool = True,
) -> bool:
    """Estas duas linhas pertencem a parágrafos diferentes?

    Os sinais estão em ordem de confiança. O salto vertical é quase
    infalível; o recuo é forte em livro impresso e ausente em PDF de
    processador de texto; a linha curta é o mais fraco dos três e por
    isso exige, além do encurtamento, uma pontuação que feche a frase.
    """
    # Mudança de tamanho de fonte: título encostado no parágrafo. No OCR
    # o "tamanho" é a altura da caixa, que muda de linha para linha só
    # porque uma tem "ç" e a outra não — com o limiar apertado, todo
    # parágrafo era picado linha a linha, e a palavra hifenizada na
    # emenda ficava partida porque a de-hifenização é feita dentro do
    # grupo, e as duas metades caíam em grupos diferentes.
    margem = max(0.8, corpo * 0.08) if exato else corpo * 0.30
    if abs(atual.tamanho - anterior.tamanho) > margem:
        return True

    salto = atual.y0 - anterior.y0
    if salto > espacamento * 1.45:
        return True
    if salto < espacamento * 0.4:
        return False  # mesma linha, partida em dois blocos pelo extrator

    # Recuo de primeira linha — medido contra a linha anterior, não
    # contra a margem da página. Contra a margem, toda linha de uma
    # citação recuada dispararia a regra, e a citação sairia partida em
    # tantos parágrafos quantas linhas tem. O que marca um parágrafo novo
    # é o degrau, e um degrau só existe em relação ao que veio antes.
    if atual.x0 > anterior.x0 + largura * 0.02:
        return True

    fim_curto = anterior.x1 < margem_esq + largura * 0.88
    fechou = anterior.texto.rstrip()[-1:] in ".!?…\"»"
    return fim_curto and fechou


def _classificar(
    grupo: list[Linha],
    texto: str,
    corpo: float,
    margem_esq: float,
    largura: float,
    *,
    exato: bool = True,
) -> str:
    tamanho = max(l.tamanho for l in grupo)
    recuo = min(l.x0 for l in grupo) - margem_esq
    direita = max(l.x1 for l in grupo)

    # `exato` é falso quando o "tamanho" veio da altura da caixa do OCR.
    # Aí a margem precisa ser bem maior, senão uma linha de corpo cheia de
    # acentos ultrapassa o limiar e vira título no meio do parágrafo — o
    # que quebra o capítulo em dezenas de pedaços.
    limiar_titulo = 1.35 if exato else 1.60
    if tamanho > corpo * limiar_titulo:
        return "titulo"
    if exato and tamanho > corpo * 1.12:
        return "titulo" if len(texto) < 90 else "paragrafo"
    if exato and all(l.negrito for l in grupo) and len(texto) < 90 and parece_titulo(texto):
        return "subtitulo"
    # Citação em bloco: recuada dos dois lados, ou recuada e em corpo
    # menor. Só o recuo à esquerda não basta — isso é a primeira linha de
    # um parágrafo comum.
    recuada = recuo > largura * 0.06
    if recuada and (direita < margem_esq + largura * 0.96 or tamanho < corpo * 0.98):
        return "citacao"
    if len(grupo) == 1 and parece_titulo(texto) and tamanho >= corpo * (1.0 if exato else 1.12):
        return "titulo"
    return "paragrafo"


def _costurar_paginas(
    blocos: list[BlocoBruto], vocab: tuple[set[str], set[str]] | None = None
) -> list[BlocoBruto]:
    """Junta o parágrafo que a virada de página partiu em dois.

    Nada na página diz que ela continua na seguinte — mas se a última
    linha não fechou a frase e a próxima começa em minúscula, é o mesmo
    parágrafo. Sem isso, toda virada de página vira uma pausa longa no
    meio de uma frase, e o livro inteiro soa entrecortado.
    """
    costurados: list[BlocoBruto] = []
    for bloco in blocos:
        anterior = costurados[-1] if costurados else None
        se_junta = (
            anterior is not None
            and anterior.tipo == bloco.tipo
            and anterior.tipo in ("paragrafo", "citacao")
            and anterior.texto
            and anterior.texto.rstrip()[-1] not in ".!?…:;\"»"
            # Minúscula *ou dígito*: uma frase cortada em "entrara às" /
            # "7h30 carregando" é tão continuação quanto qualquer outra,
            # e exigir letra minúscula deixava justamente as passagens
            # com número partidas ao meio.
            and (bloco.texto[:1].islower() or bloco.texto[:1].isdigit())
        )
        if se_junta:
            # A emenda pode cair no meio de uma palavra hifenizada. Juntar
            # com "\n" e passar pela de-hifenização resolve os dois casos
            # com o mesmo código — sem hífen, ela não faz nada.
            anterior.texto = " ".join(
                coerencia.desifenizar(
                    f"{anterior.texto}\n{bloco.texto}", vocab
                ).split()
            )
        else:
            costurados.append(bloco)
    return costurados
