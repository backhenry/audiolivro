"""Desfazer o que a diagramação fez com o texto.

Um PDF não guarda parágrafos. Ele guarda linhas — pedaços de texto com
uma posição na página — e a noção de "parágrafo" só existe no olho de
quem lê. Extrair um PDF e mandar para a voz sem reconstruir isso produz
três defeitos, todos audíveis:

1. **Palavra partida.** "impres-" numa linha, "sionante" na outra. Lido
   direto, vira "impres... sionante", com pausa no meio.
2. **Frase interrompida pelo rodapé.** O cabeçalho "O Nome da Rosa 137"
   está fisicamente entre duas linhas do mesmo parágrafo, e a extração o
   entrega no meio da frase.
3. **Parágrafo picado.** Cada linha vira uma unidade, então a voz baixa a
   entonação a cada dez palavras, como se tudo fossem frases curtas.

Este módulo é só texto: recebe listas de linhas, devolve parágrafos. A
parte que sabe de coordenadas e tamanho de fonte mora em `ingest/pdf.py`,
porque é lá que existe uma página.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Sequence

# -- hifenização --------------------------------------------------------
#
# Nem todo hífen no fim da linha é quebra de sílaba: parte é hífen de
# verdade, que precisa sobreviver. Juntar "dar-" + "lhe" em "darlhe"
# produz uma palavra que não existe e que o fonemizador lê tateando.

# Pronomes que praticamente não colidem com sílaba final de palavra
# comum: onde eles aparecem depois de um hífen, o hífen é de verdade.
ENCLITICOS_SEGUROS = ("me", "te", "lhe", "lhes", "vos", "nos")

# Estes são pronomes enclíticos legítimos *e* sílabas finais de palavras
# comuns. "clas-se" e "chamava-se" têm exatamente a mesma forma, e nenhuma
# lista de palavras resolve os dois: manter o hífen quebra "classe" ao
# meio, tirá-lo cola "chamavase". A saída não é escolher um dos erros — é
# perguntar outra coisa. Ênclise só acontece depois de verbo. Então, para
# estes, o hífen só fica se a raiz for uma palavra que o próprio livro usa
# solta ("chamava") ou terminar em desinência verbal ("-va", "-ou").
# "clas" e "ofici" não são nem uma coisa nem outra.
ENCLITICOS_AMBIGUOS = (
    "se", "o", "a", "os", "as", "no", "na", "nas", "lo", "la", "los", "las",
)
DESINENCIAS_VERBAIS = (
    "ar", "er", "ir", "or", "ou", "eu", "iu", "ez", "va", "ia", "am", "em",
    "ra", "ria", "sse", "ndo", "õe", "ão", "ará", "erá", "irá",
)
# "levá-lo", "fazê-lo", "pô-los": aqui o verbo perdeu o -r/-s final e
# ganhou acento. Sem o acento é hifenização comum — "pe-lo", "so-la".
ENCLITICOS_APOS_ACENTO = ("lo", "la", "los", "las")
_ACENTUADAS = "áàâãéêíóôõúü"

# Mesóclise: "dar-lhe-ia", "far-se-á". A segunda metade é a desinência.
MESOCLITICOS = ("ia", "iam", "á", "ão", "ei", "emos", "eis", "íamos")

# Prefixos que mantêm o hífen no acordo ortográfico de 1990.
PREFIXOS_COM_HIFEN = (
    "bem", "além", "aquém", "recém", "sem", "ex", "pré", "pós", "pró",
    "vice", "grão", "grã", "mal", "sub", "sota", "soto", "vizo",
    "primeiro", "segundo", "terceiro", "quarto", "não", "quase",
)

# Todos os hífens que existem na prática, e só eles: hífen-menos,
# hífen-suave, hífen tipográfico e hífen inquebrável. Travessão (—) e
# meia-risca (–) ficam de fora de propósito — são pontuação, e juntar as
# palavras em volta deles colaria duas frases.
_RE_QUEBRA = re.compile(r"(\S*?)([-­‐‑])\s*\n\s*(\S+)")
_RE_PALAVRA = re.compile(r"[\wÀ-ÿ]+(?:-[\wÀ-ÿ]+)*")


def vocabulario(texto: str) -> tuple[set[str], set[str]]:
    """Palavras do documento, separadas em inteiras e hifenizadas.

    É o sinal mais forte que existe para decidir um hífen de fim de
    linha, e ele é de graça: o próprio livro quase sempre traz a mesma
    palavra escrita por extenso em outro lugar. Se "oficina" aparece
    inteira na página 40, o "ofici-\\nna" da página 12 se resolve sozinho,
    sem heurística nenhuma. Só as palavras que *não* estão partidas
    contam — senão a dúvida se confirmaria a si mesma.
    """
    limpo = _RE_QUEBRA.sub(" ", texto)
    inteiras: set[str] = set()
    hifenizadas: set[str] = set()
    for palavra in _RE_PALAVRA.findall(limpo):
        (hifenizadas if "-" in palavra else inteiras).add(palavra.lower())
    return inteiras, hifenizadas


def _parece_verbo(raiz: str, inteiras: set[str]) -> bool:
    """A raiz antes do hífen pode reger uma ênclise?

    Duas evidências, nesta ordem. Se o livro usa a raiz como palavra
    solta em outro lugar — "chamava" aparece dezenas de vezes num romance
    —, ela é uma palavra, e o hífen separa duas coisas. Senão, resta a
    morfologia: terminar em desinência verbal. "clas" e "ofici" falham
    nas duas, e é assim que se separam de "chamava" e "tornou".
    """
    if len(raiz) < 3:
        return False
    return raiz in inteiras or raiz.endswith(DESINENCIAS_VERBAIS)


def desifenizar(texto: str, vocab: tuple[set[str], set[str]] | None = None) -> str:
    """Junta palavras partidas pela quebra de linha, preservando hífens reais.

    Passe `vocab` (de `vocabulario()` sobre o documento inteiro) sempre
    que possível: a evidência do próprio texto decide melhor que qualquer
    lista. As heurísticas abaixo só entram quando o documento não tem o
    que dizer sobre aquela palavra.
    """
    inteiras, hifenizadas = vocab if vocab else (set(), set())

    def _decidir(m: re.Match[str]) -> str:
        antes, _hifen, depois = m.group(1), m.group(2), m.group(3)
        nu = re.sub(r"[^\wÀ-ÿ]", "", depois).lower()
        raiz = antes.lower()

        # 1. O documento já respondeu.
        if f"{raiz}-{nu}" in hifenizadas:
            return f"{antes}-{depois}"
        if f"{raiz}{nu}" in inteiras:
            return f"{antes}{depois}"

        # 2. Maiúscula depois do hífen: nome composto, "Vila-Real".
        if depois[:1].isupper():
            return f"{antes}-{depois}"

        # 3. Gramática.
        if nu in ENCLITICOS_SEGUROS or nu in MESOCLITICOS:
            return f"{antes}-{depois}"
        if raiz in PREFIXOS_COM_HIFEN:
            return f"{antes}-{depois}"
        if nu in ENCLITICOS_APOS_ACENTO and raiz[-1:] in _ACENTUADAS:
            return f"{antes}-{depois}"
        if nu in ENCLITICOS_AMBIGUOS and _parece_verbo(raiz, inteiras):
            return f"{antes}-{depois}"

        return f"{antes}{depois}"

    return _RE_QUEBRA.sub(_decidir, texto)


# -- cabeçalhos e rodapés ------------------------------------------------

_RE_SO_NUMERO = re.compile(r"^[\s\[\(|—–-]*\d{1,4}[\s\]\)|—–-]*$")
_RE_ROMANO_SOLTO = re.compile(r"^[\s|]*[ivxlcdm]{1,7}[\s|.]*$", re.IGNORECASE)


def assinatura(linha: str) -> str:
    """Reduz a linha ao que ela tem de estável entre páginas.

    O rodapé "O Nome da Rosa · 137" muda de página para página só no
    número. Trocando todo dígito por '#', as duas ocorrências viram a
    mesma assinatura e a contagem funciona.
    """
    s = re.sub(r"\d+", "#", linha.strip().lower())
    return re.sub(r"\s+", " ", s)


# Um cabeçalho de corrida é curto por natureza: título do livro, nome do
# autor, número da página. Acima disso é linha de texto — e como um livro
# repete frases (diálogos, refrões, fórmulas), sem este teto uma frase
# recorrente que calhasse de cair no topo de duas páginas seria apagada
# do livro inteiro, silenciosamente.
LIMITE_MARGINAL = 80


def marginais_repetidas(
    paginas: Sequence[Sequence[str]], *, faixa: int = 2, limiar: float = 0.25
) -> set[str]:
    """Assinaturas das linhas que se repetem no topo/pé de muitas páginas.

    `faixa` é quantas linhas de cada ponta entram na análise; `limiar`, a
    fração de páginas em que a linha precisa aparecer para ser condenada.
    Um quarto das páginas é baixo de propósito: livros costumam alternar
    cabeçalho par/ímpar (título de um lado, autor do outro), então cada
    variante só aparece em metade das páginas — e capítulos que começam
    sem cabeçalho derrubam ainda mais essa fração.
    """
    if len(paginas) < 4:
        return set()  # amostra pequena demais para distinguir de conteúdo

    contagem: Counter[str] = Counter()
    for pagina in paginas:
        vistas = {
            assinatura(l)
            for l in [*pagina[:faixa], *pagina[-faixa:]]
            if l.strip() and len(l.strip()) <= LIMITE_MARGINAL
        }
        contagem.update(vistas)

    minimo = max(2, int(len(paginas) * limiar))
    return {sig for sig, n in contagem.items() if n >= minimo and sig}


def descartavel(linha: str, repetidas: set[str]) -> bool:
    """Cabeçalho, rodapé ou número de página solto."""
    s = linha.strip()
    if not s:
        return True
    if _RE_SO_NUMERO.match(s) or _RE_ROMANO_SOLTO.match(s):
        return True
    return assinatura(s) in repetidas


# -- reconstrução de parágrafos -----------------------------------------

_FIM_DE_FRASE = re.compile(r'[.!?…:][")\']*$')
_INICIO_DE_PARAGRAFO = re.compile(r'^\s*(?:[—–-]\s|["“«]|[A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9])')
# A chamada de nota é um número *colado* no fim de uma palavra de
# verdade: "Auerbach12". Exigimos as três letras à esquerda e proibimos
# qualquer espaço no meio. Sem esse rigor a regra alcança qualquer número
# precedido de palavra — "dia 2 de abril" viraria "dia de abril", e
# "7h30" viraria "7h", que é um estrago muito maior do que a nota que ela
# pretendia limpar.
_RE_MARCA_NOTA = re.compile(r"\b([A-Za-zÀ-ÿ]{3,})\[?\d{1,3}\]?\b(?=\s|$|[,.;:!?])")


def juntar_linhas(
    linhas: Iterable[str], *, largura_tipica: float | None = None
) -> list[str]:
    """Linhas soltas -> parágrafos.

    Sem as coordenadas da página, o único sinal disponível é o formato do
    texto. Uma linha que termina bem antes da largura típica da mancha
    encerrou o parágrafo: o resto do espaço ficou vazio porque não havia
    mais o que pôr ali. É o mesmo raciocínio que o olho faz sem perceber.

    Quando `largura_tipica` não é informada, ela é medida do próprio
    texto — a mediana serve melhor que a média porque títulos e a última
    linha de cada parágrafo puxariam a média para baixo.
    """
    linhas = [l.rstrip() for l in linhas]
    if largura_tipica is None:
        cheias = sorted(len(l) for l in linhas if l.strip())
        largura_tipica = cheias[len(cheias) // 2] if cheias else 0.0

    corte = largura_tipica * 0.80
    paragrafos: list[str] = []
    atual: list[str] = []

    for linha in linhas:
        if not linha.strip():
            if atual:
                paragrafos.append(" ".join(atual))
                atual = []
            continue

        atual.append(linha.strip())

        curta = len(linha) < corte
        fechou = bool(_FIM_DE_FRASE.search(linha.strip()))
        # Linha curta *e* terminada em pontuação: fim de parágrafo. Uma
        # das duas coisas sozinha não basta — linha curta no meio de um
        # parágrafo acontece antes de uma palavra comprida, e ponto final
        # no meio da linha é só o fim de uma frase.
        if curta and fechou:
            paragrafos.append(" ".join(atual))
            atual = []

    if atual:
        paragrafos.append(" ".join(atual))
    return [p for p in paragrafos if p.strip()]


def remover_marcas_de_nota(texto: str) -> str:
    """Tira o número de chamada de nota que sobrou colado na palavra.

    Só age quando o número está grudado no fim de uma palavra —
    "conforme Auerbach12 demonstrou". Número separado por espaço é
    conteúdo ("em 1937 ele voltou") e fica.
    """
    return _RE_MARCA_NOTA.sub(r"\1", texto)
