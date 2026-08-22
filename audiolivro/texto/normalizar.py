"""De texto impresso para texto falado.

Esta é a diferença entre um audiobook e um leitor de tela. O olho pula o
que não interessa e reconstrói o resto: vê "Sr. Silva (1890–1942), pág.
37" e entende. O ouvido recebe o que mandarmos, na ordem que mandarmos,
e não pode voltar. Se mandarmos os caracteres crus, ele ouve "esse erre
ponto Silva parêntese mil oitocentos e noventa travessão..." e desiste.

A ordem das transformações não é negociável, e é a fonte da maioria dos
bugs num normalizador. `R$ 1.250,50` precisa ser reconhecido como moeda
*antes* que a regra de milhar toque no `1.250`; `12/03/1998` precisa ser
data antes que a barra vire "barra"; `1º` precisa ser ordinal antes que
o `1` vire cardinal. Cada função aqui assume que as anteriores já
rodaram, e `normalizar()` é quem garante isso.

Duas decisões que valem explicar:

**Não lemos pontuação, lemos ritmo.** Um travessão de diálogo não vira
"travessão" nem some: ele vira uma pausa, porque é isso que ele faz na
página. O mesmo para reticências e parênteses.

**Na dúvida, não converta.** Transformar "DIVA" em "504" porque parece
romano, ou "MIX" em "mil e nove", estraga mais do que deixar a sigla
passar. Toda conversão ambígua aqui exige contexto explícito.
"""

from __future__ import annotations

import re
import unicodedata

from audiolivro.texto.numeros import ordinal, por_extenso, romano_para_int

# -- 1. limpeza de caracteres -------------------------------------------

# Caracteres que existem só para a tipografia e que confundem tudo
# depois: o hífen-suave é invisível na tela mas parte a palavra no meio
# para o fonemizador; o espaço fino não casa com \s em algumas versões.
_INVISIVEIS = dict.fromkeys(map(ord, "­​‌‍⁠﻿"), None)
_TRADUCOES = {
    " ": " ", " ": " ", " ": " ", " ": " ", " ": "\n",
    "‘": "'", "’": "'", "‚": ",", "“": '"', "”": '"',
    "„": '"', "′": "'", "″": '"', "‹": "'", "›": "'",
    "‐": "-", "‑": "-", "‒": "-", "ﬁ": "fi", "ﬂ": "fl",
    "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl", "Œ": "OE",
    "œ": "oe", "⁄": "/",
}
_TRADUCAO_TABELA = str.maketrans(_TRADUCOES)

# Expoentes de nota de rodapé. Na tela são um "3" pequenininho que o olho
# ignora; no áudio viram "três" no meio da frase. É o defeito mais
# irritante de audiobook gerado a partir de livro técnico.
_SOBRESCRITOS = "¹²³⁰⁴⁵⁶⁷⁸⁹⁺⁻"


# Letra solta, em qualquer alfabeto, sem dígito nem sublinhado.
_LETRA = r"[^\W\d_]"
def _regra(minimo: int) -> re.Pattern[str]:
    """Sequência de `minimo` letras isoladas separadas por um espaço."""
    return re.compile(rf"(?<!{_LETRA})((?:{_LETRA} ){{{minimo - 1},}}{_LETRA})(?!{_LETRA})")


_RE_LETRAS_ESPACADAS = _regra(3)
_RE_LETRAS_ESPACADAS_PAR = _regra(2)


def parece_espacado(texto: str) -> bool:
    """O texto tem uma sequência de letras isoladas — "C A P Í T U L O"?"""
    return bool(_RE_LETRAS_ESPACADAS.search(texto))


def juntar_letras_espacadas(texto: str) -> str:
    """Reverte o espaçamento de letra da diagramação: "C A P Í T U L O".

    Diagramador espaça letra para dar ar a um título. Na página o olho lê
    "CAPÍTULO" sem esforço; na extração viram oito letras soltas, e o
    motor as soletra uma a uma — "cê, á, pê, i…" — no lugar de ler a
    palavra. É o defeito mais audível que um título pode ter, porque
    acontece logo na abertura de cada capítulo.

    O que separa uma palavra da seguinte é o tamanho do espaço, e essa
    pista sobrevive à extração de formas diferentes: às vezes como espaço
    duplo, às vezes como quebra de linha. Por isso a regra só aceita **um**
    espaço entre as letras de uma mesma palavra — qualquer coisa maior
    encerra a sequência. É o que faz "C A P Í T U L O  I I I" virar
    "CAPÍTULO III" em vez de "CAPÍTULOIII".

    Exige três letras seguidas e case uniforme. Duas bastariam para
    disparar em "a b" de uma enumeração; e a mistura de caixa denuncia
    que aquilo não é uma palavra espaçada, e sim letras que se
    encontraram por acaso.
    """

    def _juntar(m: re.Match[str]) -> str:
        letras = m.group(1).split()
        if not (all(c.isupper() for c in letras) or all(c.islower() for c in letras)):
            return m.group(0)
        return "".join(letras)

    juntado = _RE_LETRAS_ESPACADAS.sub(_juntar, texto)

    # Segunda passada, só se a primeira encontrou algo. Uma palavra de
    # duas letras no meio de um título espaçado — o "DA" de "O NOME DA
    # ROSA" — não tem letras suficientes para provar sozinha que está
    # espaçada, e exigir duas por padrão dispararia em toda enumeração
    # "a) b)". Mas se o mesmo trecho já teve uma junção, o espaçamento
    # está provado, e aí o par deixa de ser ambíguo.
    if juntado != texto:
        juntado = _RE_LETRAS_ESPACADAS_PAR.sub(_juntar, juntado)
    return juntado


def limpar(texto: str) -> str:
    """Normaliza caracteres antes de qualquer análise. Não muda palavras."""
    texto = unicodedata.normalize("NFC", texto)
    texto = texto.translate(_INVISIVEIS).translate(_TRADUCAO_TABELA)
    texto = re.sub(f"[{_SOBRESCRITOS}]+", "", texto)
    # Antes de colapsar os brancos: depois disso, tabulação e espaço duplo
    # somem, e com eles a última pista de onde uma palavra terminava.
    texto = juntar_letras_espacadas(texto)
    # Qualquer branco vira um espaço só, quebra de linha inclusive: um
    # bloco é um parágrafo por definição, e a quebra que sobrou do HTML
    # ou do PDF é da diagramação, não do texto.
    texto = re.sub(r"\s+", " ", texto)
    # Espaço antes de pontuação é resto de algo removido — o expoente da
    # nota, uma tag inline. Some do texto falado pelo `ritmo`, mas o texto
    # exibido no player nunca passa por lá, e "estreita , entre" na tela
    # denuncia a limpeza mal feita.
    texto = re.sub(r"\s+([,.;:!?…])", r"\1", texto)
    return texto.strip()


# -- 2. abreviações ------------------------------------------------------
#
# Chave sem o ponto final; a regex acrescenta. A lista é usada duas
# vezes: aqui, para expandir, e em `sentencas.py`, para *não* quebrar a
# frase no ponto de "Sr.". As duas coisas precisam da mesma lista, e é
# por isso que ela mora aqui e é importada de lá.

ABREVIACOES: dict[str, str] = {
    "sr": "senhor", "sra": "senhora", "srta": "senhorita", "srs": "senhores",
    "sras": "senhoras", "dr": "doutor", "dra": "doutora", "drs": "doutores",
    "prof": "professor", "profa": "professora", "profs": "professores",
    "exmo": "excelentíssimo", "exma": "excelentíssima",
    "sto": "santo", "sta": "santa", "eng": "engenheiro",
    "pe": "padre", "ver": "vereador", "dep": "deputado", "sen": "senador",
    "pág": "página", "pag": "página", "págs": "páginas", "pags": "páginas",
    "pp": "páginas", "cap": "capítulo", "caps": "capítulos",
    "vol": "volume", "vols": "volumes", "ed": "edição", "org": "organizador",
    "trad": "tradução", "rev": "revisão", "col": "coleção",
    "séc": "século", "sécs": "séculos", "art": "artigo", "arts": "artigos",
    "inc": "inciso", "par": "parágrafo", "ref": "referência",
    "obs": "observação", "cf": "confira", "op": "obra", "apud": "apud",
    "av": "avenida", "trav": "travessa", "ltda": "limitada",
    "etc": "et cetera", "aprox": "aproximadamente", "máx": "máximo",
    "mín": "mínimo", "núm": "número", "tel": "telefone",
    "séries": "séries", "fig": "figura", "tab": "tabela",
}

# Abreviações com ponto no meio: precisam vir antes das simples, senão
# "a.C." é tratado como "a" + fim de frase + "C".
_COMPOSTAS = [
    (r"\ba\.\s?C\.", "antes de Cristo"),
    (r"\bd\.\s?C\.", "depois de Cristo"),
    (r"\ba\.\s?E\.\s?C\.", "antes da era comum"),
    (r"\bp\.\s?ex\.", "por exemplo"),
    (r"\bp\.\s?f\.", "por favor"),
    (r"\bi\.\s?e\.", "isto é"),
    (r"\be\.\s?g\.", "por exemplo"),
    (r"\bS\.\s?A\.", "sociedade anônima"),
    (r"\bE\.\s?U\.\s?A\.", "Estados Unidos"),
    # "n.º 37" e "nº 37". A forma sem ponto exige um número na sequência
    # para não confundir com a preposição "no".
    (r"\bn\.[ºo°]\.?", "número"),
    (r"\bn[º°]\s*(?=\d)", "número "),
    (r"\bN\.\s?T\.", "nota do tradutor"),
    (r"\bN\.\s?A\.", "nota do autor"),
    # "D." é dom ou dona, e não há como saber pelo texto. A exceção é o
    # monarca — "D. Pedro II", "D. João VI" —, onde o numeral romano logo
    # depois torna a leitura inequívoca. Fora desse caso a abreviação
    # fica como está: um palpite errado ("Dom Maria") é pior no ouvido
    # que a inicial soletrada.
    (r"\bD\.\s+(?=[A-ZÁÉÍÓÚÂÊÔ][a-zà-ÿ]+\s+[IVXLCDM]{1,7}\b)", "Dom "),
]

_RE_ABREV = re.compile(
    r"\b(" + "|".join(sorted(ABREVIACOES, key=len, reverse=True)) + r")\.",
    re.IGNORECASE,
)


def expandir_abreviacoes(texto: str) -> str:
    for padrao, troca in _COMPOSTAS:
        texto = re.sub(padrao, troca, texto)

    def _troca(m: re.Match[str]) -> str:
        return ABREVIACOES[m.group(1).lower()]

    return _RE_ABREV.sub(_troca, texto)


# -- 3. unidades e símbolos ---------------------------------------------

# Só expandimos a unidade quando ela vem colada num número; "km" solto
# num texto pode ser outra coisa, e "5 m" é metros mas "m" sozinho não é.
UNIDADES = {
    "km": ("quilômetro", "quilômetros"), "m": ("metro", "metros"),
    "cm": ("centímetro", "centímetros"), "mm": ("milímetro", "milímetros"),
    "kg": ("quilo", "quilos"), "g": ("grama", "gramas"),
    "mg": ("miligrama", "miligramas"), "t": ("tonelada", "toneladas"),
    "l": ("litro", "litros"), "ml": ("mililitro", "mililitros"),
    "h": ("hora", "horas"), "min": ("minuto", "minutos"),
    "s": ("segundo", "segundos"), "seg": ("segundo", "segundos"),
    "ha": ("hectare", "hectares"), "km²": ("quilômetro quadrado", "quilômetros quadrados"),
    "m²": ("metro quadrado", "metros quadrados"),
    "m³": ("metro cúbico", "metros cúbicos"),
    "kb": ("quilobyte", "quilobytes"), "mb": ("megabyte", "megabytes"),
    "gb": ("gigabyte", "gigabytes"), "tb": ("terabyte", "terabytes"),
}

SIMBOLOS = {
    "&": " e ", "§": " parágrafo ", "©": " copyright ", "®": " marca registrada ",
    "™": " marca registrada ", "×": " vezes ", "÷": " dividido por ",
    "±": " mais ou menos ", "≈": " aproximadamente ", "≠": " diferente de ",
    "≤": " menor ou igual a ", "≥": " maior ou igual a ", "†": "", "‡": "",
    "•": "", "→": " leva a ", "←": " vem de ", "°C": " graus Celsius ",
    "°F": " graus Fahrenheit ", "%": " por cento ", "‰": " por mil ",
    "№": " número ", "@": " arroba ",
}

MESES = {
    1: "janeiro", 2: "fevereiro", 3: "março", 4: "abril", 5: "maio",
    6: "junho", 7: "julho", 8: "agosto", 9: "setembro", 10: "outubro",
    11: "novembro", 12: "dezembro",
}

MOEDAS = {
    "R$": ("real", "reais", "centavo", "centavos"),
    "US$": ("dólar", "dólares", "cent", "cents"),
    "$": ("dólar", "dólares", "cent", "cents"),
    "€": ("euro", "euros", "cêntimo", "cêntimos"),
    "£": ("libra", "libras", "pêni", "pence"),
}


# -- 4. números em contexto ---------------------------------------------


def _inteiro(s: str) -> int:
    """Lê "1.250" e "1 250" como 1250. O separador de milhar some."""
    return int(re.sub(r"[.\s ]", "", s))


def _moeda(m: re.Match[str]) -> str:
    simbolo = m.group("moeda")
    sing, plur, csing, cplur = MOEDAS[simbolo]
    inteiro = _inteiro(m.group("int"))
    centavos = int((m.group("cent") or "0").ljust(2, "0")[:2])

    partes = []
    if inteiro or not centavos:
        partes.append(f"{por_extenso(inteiro)} {sing if inteiro == 1 else plur}")
    if centavos:
        partes.append(f"{por_extenso(centavos)} {csing if centavos == 1 else cplur}")
    return " e ".join(partes)


_RE_MOEDA = re.compile(
    r"(?P<moeda>R\$|US\$|\$|€|£)\s?(?P<int>\d{1,3}(?:[.\s]\d{3})*|\d+)"
    r"(?:,(?P<cent>\d{1,2}))?"
)

# "1,5 milhão" / "3,2 bilhões": a escala fica, o decimal vira fração.
_RE_ESCALA = re.compile(
    r"\b(?P<num>\d{1,3}(?:[.\s]\d{3})*|\d+)(?:,(?P<dec>\d+))?\s+"
    r"(?P<escala>milhões|milhão|bilhões|bilhão|trilhões|trilhão|mil)\b",
    re.IGNORECASE,
)

# O marcador de ordinal no dia é comum no Brasil: "1º/05/2020". Sem
# aceitá-lo aqui, a data escapa desta regra, o "1º" vira "primeiro"
# sozinho e sobra "primeiro barra zero cinco barra dois mil e vinte".
_RE_DATA = re.compile(r"\b(\d{1,2})[º°]?/(\d{1,2})/(\d{2,4})\b")
_RE_HORA = re.compile(r"\b(\d{1,2})[h:](\d{2})(?:min)?\b")
_RE_HORA_CHEIA = re.compile(r"\b(\d{1,2})\s?h\b")
_RE_ORDINAL = re.compile(r"\b(\d{1,4})\s?([ºª°]|\.[ºª])")
_RE_PERCENT = re.compile(r"\b(\d{1,3}(?:[.\s]\d{3})*|\d+)(?:,(\d+))?\s?%")
_RE_INTERVALO = re.compile(r"\b(\d{1,4})\s?[-–—]\s?(\d{1,4})\b")
_RE_DECIMAL = re.compile(r"\b(\d{1,3}(?:[.\s]\d{3})*|\d+),(\d+)\b")
_RE_UNIDADE = re.compile(
    r"\b(\d{1,3}(?:[.\s]\d{3})*|\d+)\s?("
    + "|".join(sorted(UNIDADES, key=len, reverse=True))
    + r")\b"
)
_RE_MILHAR = re.compile(r"\b\d{1,3}(?:[.\s]\d{3})+\b")
_RE_SIMPLES = re.compile(r"\b\d+\b")

# Palavras que autorizam ler o romano seguinte como número. Sem elas,
# "DIVA" e "MIX" viram algarismos e o livro fica sem sentido.
_CONTEXTO_ROMANO = (
    r"cap[íi]tulo|livro|parte|se[çc][ãa]o|volume|tomo|ato|canto|s[ée]culo|"
    r"guerra|d[ée]cada|artigo|anexo|figura|tabela|classe|tipo|fase|rodada"
)
_RE_ROMANO = re.compile(
    rf"\b(?P<palavra>{_CONTEXTO_ROMANO})\s+(?P<num>[IVXLCDM]{{1,8}})\b",
    re.IGNORECASE,
)
# Reis e papas: "Luís XIV", "João Paulo II" -> ordinal até dez, cardinal
# depois, que é a convenção em português.
_RE_ROMANO_NOME = re.compile(r"\b([A-ZÁÉÍÓÚÂÊÔÃÕÇ][a-zà-ÿ]+)\s+([IVXLCDM]{1,8})\b")


def converter_numeros(texto: str) -> str:
    """Aplica as regras numéricas na ordem em que elas dependem umas das outras."""
    texto = _RE_MOEDA.sub(_moeda, texto)
    texto = _RE_DATA.sub(_data, texto)
    texto = _RE_ORDINAL.sub(_ordinal, texto)
    texto = _RE_PERCENT.sub(_percentual, texto)
    texto = _RE_HORA.sub(_hora, texto)
    texto = _RE_HORA_CHEIA.sub(_hora_cheia, texto)
    texto = _RE_ESCALA.sub(_escala, texto)
    texto = _RE_UNIDADE.sub(_unidade, texto)
    texto = _RE_INTERVALO.sub(_intervalo, texto)
    texto = _RE_ROMANO.sub(_romano_contexto, texto)
    texto = _RE_ROMANO_NOME.sub(_romano_nome, texto)
    texto = _RE_DECIMAL.sub(_decimal, texto)
    texto = _RE_MILHAR.sub(lambda m: por_extenso(_inteiro(m.group(0))), texto)
    texto = _RE_SIMPLES.sub(_numero_simples, texto)
    return texto


def _data(m: re.Match[str]) -> str:
    dia, mes, ano = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if not (1 <= mes <= 12 and 1 <= dia <= 31):
        return m.group(0)  # não era data; deixa para as regras seguintes
    if ano < 100:
        ano += 2000 if ano < 30 else 1900
    # Em português, o dia 1 é ordinal e os outros cardinais.
    d = "primeiro" if dia == 1 else por_extenso(dia)
    return f"{d} de {MESES[mes]} de {_ano(ano)}"


def _ano(n: int) -> str:
    """1998 -> "mil novecentos e noventa e oito", não "um nove nove oito"."""
    return por_extenso(n)


def _ordinal(m: re.Match[str]) -> str:
    marca = m.group(2)
    fem = "ª" in marca
    return ordinal(int(m.group(1)), feminino=fem)


def _percentual(m: re.Match[str]) -> str:
    inteiro = por_extenso(_inteiro(m.group(1)))
    if m.group(2):
        return f"{inteiro} vírgula {_digitos(m.group(2))} por cento"
    return f"{inteiro} por cento"


def _hora(m: re.Match[str]) -> str:
    h, mi = int(m.group(1)), int(m.group(2))
    if h > 23 or mi > 59:
        return m.group(0)
    hora = f"{por_extenso(h, feminino=True)} {'hora' if h == 1 else 'horas'}"
    return hora if mi == 0 else f"{hora} e {por_extenso(mi)}"


def _hora_cheia(m: re.Match[str]) -> str:
    h = int(m.group(1))
    if h > 23:
        return m.group(0)
    return f"{por_extenso(h, feminino=True)} {'hora' if h == 1 else 'horas'}"


def _escala(m: re.Match[str]) -> str:
    escala = m.group("escala").lower()
    num = _inteiro(m.group("num"))
    dec = m.group("dec")
    # "mil" já é tratado como parte do número: 3 mil -> três mil.
    if escala == "mil" and not dec:
        return por_extenso(num * 1000)
    cabeca = por_extenso(num)
    if dec:
        cabeca += f" vírgula {_digitos(dec)}"
    return f"{cabeca} {escala}"


def _unidade(m: re.Match[str]) -> str:
    n = _inteiro(m.group(1))
    sing, plur = UNIDADES[m.group(2).lower()]
    return f"{por_extenso(n)} {sing if n == 1 else plur}"


def _intervalo(m: re.Match[str]) -> str:
    a, b = int(m.group(1)), int(m.group(2))
    # Um intervalo crescente é "de X a Y"; ao contrário, era um traço
    # qualquer e não mexemos.
    if a >= b:
        return m.group(0)

    # A preposição pode já estar escrita: "de 1914-1918" viraria "de de
    # mil novecentos...". Quando ela está lá, entramos só com a ponte.
    antes = m.string[: m.start()].rstrip().lower()
    if antes.endswith("entre"):
        return f"{por_extenso(a)} e {por_extenso(b)}"
    if antes.endswith(" de") or antes.endswith("de"):
        return f"{por_extenso(a)} a {por_extenso(b)}"
    return f"de {por_extenso(a)} a {por_extenso(b)}"


def _decimal(m: re.Match[str]) -> str:
    return f"{por_extenso(_inteiro(m.group(1)))} vírgula {_digitos(m.group(2))}"


def _digitos(s: str) -> str:
    """Casas decimais se leem dígito a dígito: 3,14 -> "três vírgula um quatro"."""
    return " ".join(por_extenso(int(d)) for d in s)


def _numero_simples(m: re.Match[str]) -> str:
    s = m.group(0)
    n = int(s)
    # Zeros à esquerda quase sempre indicam código, não quantidade:
    # "007" é "zero zero sete", não "sete".
    if len(s) > 1 and s[0] == "0":
        return " ".join(por_extenso(int(d)) for d in s)
    # Sequências muito longas são identificadores; ler por extenso um
    # CPF de onze dígitos é incompreensível.
    if len(s) > 9:
        return " ".join(por_extenso(int(d)) for d in s)
    return por_extenso(n)


def _romano_contexto(m: re.Match[str]) -> str:
    valor = romano_para_int(m.group("num"))
    if valor is None:
        return m.group(0)
    palavra = m.group("palavra")
    return f"{palavra} {por_extenso(valor)}"


def _romano_nome(m: re.Match[str]) -> str:
    valor = romano_para_int(m.group(2))
    if valor is None or valor > 30:
        return m.group(0)
    nome = m.group(1)
    # "Luís catorze" soa errado; "Luís décimo quarto" é a forma corrente
    # até dez, e a partir daí o uso oscila — ficamos no ordinal, que
    # nunca soa estranho.
    return f"{nome} {ordinal(valor)}"


# -- 5. siglas -----------------------------------------------------------

LETRAS = {
    "A": "á", "B": "bê", "C": "cê", "D": "dê", "E": "é", "F": "éfe",
    "G": "gê", "H": "agá", "I": "i", "J": "jota", "K": "cá", "L": "éle",
    "M": "ême", "N": "êne", "O": "ó", "P": "pê", "Q": "quê", "R": "érre",
    "S": "ésse", "T": "tê", "U": "u", "V": "vê", "W": "dábliu", "X": "xis",
    "Y": "ípsilon", "Z": "zê",
}

_VOGAIS = set("AEIOUÁÉÍÓÚÂÊÔÃÕ")
# Encontros consonantais que abrem sílaba em português. Fora desta lista,
# duas consoantes seguidas no meio da sigla significam que ela não é
# pronunciável como palavra.
_ONSETS = {
    "BL", "BR", "CL", "CR", "DR", "FL", "FR", "GL", "GR", "PL", "PR",
    "TR", "VR", "CH", "LH", "NH", "QU", "GU", "PS", "PN",
}
_CODAS = set("RSLMNXZ")

_RE_SIGLA = re.compile(r"\b[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{2,6}\b")
_RE_CAIXA_ALTA = re.compile(r"\b(?:[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{2,}\W+){2,}[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{2,}\b")


def _pronunciavel(sigla: str) -> bool:
    """"ONU" e "OTAN" se leem como palavra; "IBGE" e "CNPJ", letra a letra."""
    if not any(c in _VOGAIS for c in sigla):
        return False
    for grupo in re.findall(r"[^AEIOUÁÉÍÓÚÂÊÔÃÕ]+", sigla):
        if len(grupo) == 1:
            continue
        if len(grupo) > 2:
            return False
        # Duas consoantes: ou abrem sílaba juntas ("BR"), ou a primeira
        # fecha a anterior e a segunda abre a próxima ("RT" em "OTAN").
        if grupo not in _ONSETS and grupo[0] not in _CODAS:
            return False
    return True


def soletrar_siglas(texto: str) -> str:
    """Trechos em CAIXA ALTA viram minúsculas; siglas viram letras faladas.

    A ordem importa: um título gritado em maiúsculas ("O FIM DA TARDE")
    não é uma sequência de siglas, e soletrá-lo palavra por palavra seria
    catastrófico. Por isso a caixa alta corrida é rebaixada primeiro, e só
    o que sobra isolado é tratado como sigla.
    """
    texto = _RE_CAIXA_ALTA.sub(lambda m: m.group(0).lower(), texto)

    def _troca(m: re.Match[str]) -> str:
        sigla = m.group(0)
        if _pronunciavel(sigla):
            return sigla.capitalize()
        return "-".join(LETRAS.get(c, c) for c in sigla)

    return _RE_SIGLA.sub(_troca, texto)


# -- 6. pontuação e ritmo ------------------------------------------------

_RE_URL = re.compile(r"\b(?:https?://|www\.)\S+", re.IGNORECASE)
_RE_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")
# Travessão, meia-risca e o hífen cercado de espaços — que é como o OCR
# costuma devolver um travessão, e como muita gente digita um. Os espaços
# dos dois lados são o que distingue a pontuação da palavra composta:
# "guarda-chuva" não tem espaço e não é tocado.
_RE_TRAVESSAO = re.compile(r"\s*[—–]\s*|\s+-\s+")
_RE_RETICENCIAS = re.compile(r"\.{3,}|…")
_RE_PARENTESE = re.compile(r"\s*[()\[\]{}]\s*")
_RE_ASPAS = re.compile(r'["“”«»]')
_RE_PONTUACAO_REPETIDA = re.compile(r"([!?])\1+")
_RE_ESPACO = re.compile(r"\s{2,}")
_RE_VIRGULA_SOLTA = re.compile(r"\s+([,.;:!?])")


def ritmo(texto: str) -> str:
    """Troca marcas visuais por marcas de prosódia.

    O motor não entende parêntese, mas entende vírgula: ele encurta a
    frase e baixa o tom. Então o parêntese vira vírgula, o travessão vira
    vírgula, e as reticências viram reticências mesmo — que o espeak já
    trata como pausa longa.
    """
    texto = _RE_URL.sub(" um endereço na internet ", texto)
    texto = _RE_EMAIL.sub(" um endereço de e-mail ", texto)
    texto = _RE_RETICENCIAS.sub("… ", texto)
    texto = _RE_TRAVESSAO.sub(", ", texto)
    texto = _RE_PARENTESE.sub(", ", texto)
    texto = _RE_ASPAS.sub("", texto)
    texto = _RE_PONTUACAO_REPETIDA.sub(r"\1", texto)

    for simbolo, troca in SIMBOLOS.items():
        if simbolo in texto:
            texto = texto.replace(simbolo, troca)

    texto = _RE_VIRGULA_SOLTA.sub(r"\1", texto)
    texto = re.sub(r"(,\s*){2,}", ", ", texto)
    texto = re.sub(r",\s*([.!?;:])", r"\1", texto)
    texto = _RE_ESPACO.sub(" ", texto)
    return texto.strip(" ,;")


# -- 7. o pipeline -------------------------------------------------------


def normalizar(texto: str) -> str:
    """Texto de uma sentença -> texto pronto para o motor de voz.

    Recebe *uma sentença*, não um parágrafo: a segmentação precisa
    acontecer antes, com a lista de abreviações em mãos, senão "Sr." vira
    fim de frase. Ver `sentencas.segmentar`.
    """
    texto = limpar(texto)
    texto = expandir_abreviacoes(texto)
    texto = converter_numeros(texto)
    texto = soletrar_siglas(texto)
    texto = ritmo(texto)

    if not texto:
        return ""
    # Sem pontuação final o motor não baixa a entonação e a frase seguinte
    # cola nesta, como se fossem uma só.
    if texto[-1] not in ".!?…:;":
        texto += "."
    return texto
