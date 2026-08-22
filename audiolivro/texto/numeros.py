"""Números por extenso em português do Brasil.

Existe `num2words` no PyPI, e ele funciona. Escrevemos o nosso por dois
motivos que aparecem justamente num livro:

1. **Concordância de gênero.** "1.200 páginas" é *duzentas* páginas, e
   "1.200 reais" é *duzentos* reais. Quem chama precisa poder dizer qual.
2. **O "e" do português.** É a regra que todo conversor erra. 1.250 é
   "mil duzentos e cinquenta" — sem "e" depois de "mil". Mas 1.100 é
   "mil e cem", e 1.005 é "mil e cinco". A diferença não é arbitrária:
   entra "e" quando o resto é menor que cem ou é uma centena redonda.

Ouvir "mil, duzentos e cinquenta" onde deveria ser "mil duzentos e
cinquenta" não trava a compreensão, mas ouvir "um duzentos e cinquenta"
— que é o que o fonemizador entrega sozinho — trava.
"""

from __future__ import annotations

UNIDADES = (
    "zero", "um", "dois", "três", "quatro", "cinco", "seis", "sete",
    "oito", "nove", "dez", "onze", "doze", "treze", "catorze", "quinze",
    "dezesseis", "dezessete", "dezoito", "dezenove",
)
DEZENAS = (
    "", "", "vinte", "trinta", "quarenta", "cinquenta", "sessenta",
    "setenta", "oitenta", "noventa",
)
CENTENAS = (
    "", "cento", "duzentos", "trezentos", "quatrocentos", "quinhentos",
    "seiscentos", "setecentos", "oitocentos", "novecentos",
)

# O feminino só muda em "um/uma", "dois/duas" e nas centenas a partir de
# 200. "trezentas mulheres", mas "trinta mulheres".
FEMININO = {
    "um": "uma",
    "dois": "duas",
    "duzentos": "duzentas",
    "trezentos": "trezentas",
    "quatrocentos": "quatrocentas",
    "quinhentos": "quinhentas",
    "seiscentos": "seiscentas",
    "setecentos": "setecentas",
    "oitocentos": "oitocentas",
    "novecentos": "novecentas",
}

# (singular, plural, valor). Ordem decrescente: o algoritmo consome do
# maior para o menor.
ESCALAS = (
    ("quatrilhão", "quatrilhões", 10**15),
    ("trilhão", "trilhões", 10**12),
    ("bilhão", "bilhões", 10**9),
    ("milhão", "milhões", 10**6),
    ("mil", "mil", 10**3),
)

LIMITE = 10**18


def por_extenso(n: int, *, feminino: bool = False) -> str:
    """Escreve `n` por extenso. Aceita negativos e zero.

    `feminino` concorda com o substantivo contado: `por_extenso(1200,
    feminino=True)` dá "mil e duzentas", para "mil e duzentas páginas".
    """
    if n < 0:
        return "menos " + por_extenso(-n, feminino=feminino)
    if n == 0:
        return "zero"
    if n >= LIMITE:
        # Acima disso não há nome consagrado e, num livro, um número desses
        # é quase sempre um código (ISBN, telefone) — soletrar é o certo.
        return " ".join(UNIDADES[int(d)] for d in str(n))
    return _grupos(n, feminino)


def _generoso(texto: str, feminino: bool) -> str:
    if not feminino:
        return texto
    return " ".join(FEMININO.get(p, p) for p in texto.split(" "))


def _grupos(n: int, feminino: bool) -> str:
    """Percorre as escalas de cima para baixo, montando os pedaços.

    O gênero não desce igual por todas as escalas. "mil" é invariável e o
    multiplicador concorda com o que se conta — *duas* mil páginas. Já
    "milhão" é um substantivo masculino, então o multiplicador concorda
    com ele, não com o resto da frase: *dois* milhões de páginas, mesmo
    sendo páginas. Só o último grupo, abaixo de mil, e o multiplicador de
    "mil" pegam o feminino de quem chamou.
    """
    partes: list[str] = []
    resto = n

    for singular, plural, valor in ESCALAS:
        if resto < valor:
            continue
        quantos, resto = divmod(resto, valor)
        if valor == 10**3:
            if quantos == 1:
                partes.append("mil")  # nunca "um mil"
            else:
                partes.append(f"{_grupos(quantos, feminino)} mil")
        else:
            nome = singular if quantos == 1 else plural
            partes.append(f"{_grupos(quantos, feminino=False)} {nome}")

    if resto:
        partes.append(_generoso(_ate_999(resto), feminino))

    return _juntar(partes, n)


def _ate_999(n: int) -> str:
    if n < 20:
        return UNIDADES[n]
    if n < 100:
        dez, uni = divmod(n, 10)
        return DEZENAS[dez] + (f" e {UNIDADES[uni]}" if uni else "")
    if n == 100:
        return "cem"  # "cem" sozinho; "cento" só acompanhado
    cem, resto = divmod(n, 100)
    return CENTENAS[cem] + (f" e {_ate_999(resto)}" if resto else "")


def _juntar(partes: list[str], total: int) -> str:
    """Aplica a regra do "e" entre a última escala e o resto.

    Dentro de cada grupo o "e" já foi posto por `_ate_999`. O que falta é
    a junção final: "mil **e** cem" contra "mil duzentos e cinquenta".
    """
    if len(partes) == 1:
        return partes[0]

    resto = total % 1000
    ultimo = partes[-1]
    cabeca = " ".join(partes[:-1])

    # Sem resto abaixo de mil, as escalas se juntam com vírgula falada —
    # que aqui é só um espaço: "dois milhões trezentos mil".
    if resto == 0:
        return f"{cabeca} {ultimo}"

    # Entra "e" quando o resto é pequeno (< 100) ou é centena redonda.
    # 1.100 -> "mil e cem"; 1.005 -> "mil e cinco"; 1.250 -> sem "e".
    if resto < 100 or resto % 100 == 0:
        return f"{cabeca} e {ultimo}"
    return f"{cabeca} {ultimo}"


# -- ordinais -----------------------------------------------------------

_ORD_UNI = (
    "", "primeiro", "segundo", "terceiro", "quarto", "quinto", "sexto",
    "sétimo", "oitavo", "nono",
)
_ORD_DEZ = (
    "", "décimo", "vigésimo", "trigésimo", "quadragésimo", "quinquagésimo",
    "sexagésimo", "septuagésimo", "octogésimo", "nonagésimo",
)
_ORD_CEM = (
    "", "centésimo", "ducentésimo", "trecentésimo", "quadringentésimo",
    "quingentésimo", "seiscentésimo", "septingentésimo", "octingentésimo",
    "noningentésimo",
)


def ordinal(n: int, *, feminino: bool = False) -> str:
    """"3º" -> "terceiro". Acima de 1000 vira cardinal, que é como se fala.

    Ninguém diz "milésimo quingentésimo vigésimo terceiro capítulo".
    Passando de mil, a leitura corrente é o cardinal — e é isso que soa
    natural num livro.
    """
    if n <= 0 or n >= 1000:
        return por_extenso(n, feminino=feminino)

    cem, resto = divmod(n, 100)
    dez, uni = divmod(resto, 10)
    partes = [p for p in (_ORD_CEM[cem], _ORD_DEZ[dez], _ORD_UNI[uni]) if p]

    # No ordinal composto, *todos* os termos flexionam: "vigésima
    # primeira", não "vigésimo primeira". Como todo ordinal masculino
    # daqui termina em -o, a troca final por -a basta em cada termo.
    if feminino:
        partes = [p.removesuffix("o") + "a" for p in partes]
    return " ".join(partes)


# -- romanos ------------------------------------------------------------

_ROMANOS = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def romano_para_int(s: str) -> int | None:
    """Converte "XIV" em 14. Devolve None se não for romano válido.

    A validação importa: "MIX", "DIVA" e "CIA" são palavras que passariam
    por romanos numa checagem ingênua de caracteres, e transformar o nome
    da editora "DIVA" em "504" no meio do livro é pior que não converter.
    """
    s = s.upper()
    if not s or any(c not in _ROMANOS for c in s):
        return None

    total = 0
    anterior = 0
    for c in reversed(s):
        valor = _ROMANOS[c]
        total += -valor if valor < anterior else valor
        anterior = max(anterior, valor)

    # Ida e volta: só aceitamos a forma canônica. "IIII" e "IC" caem aqui.
    return total if int_para_romano(total) == s else None


def int_para_romano(n: int) -> str:
    if not 0 < n < 4000:
        return ""
    tabela = (
        (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"),
        (90, "XC"), (50, "L"), (40, "XL"), (10, "X"), (9, "IX"),
        (5, "V"), (4, "IV"), (1, "I"),
    )
    saida = []
    for valor, simbolo in tabela:
        quantos, n = divmod(n, valor)
        saida.append(simbolo * quantos)
    return "".join(saida)
