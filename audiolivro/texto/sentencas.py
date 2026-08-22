"""Onde termina uma frase — e onde dá para respirar dentro dela.

Duas tarefas diferentes que costumam ser confundidas:

**Segmentar** é achar o fim da frase. O ponto final é ambíguo em
português: ele termina frase, mas também fecha abreviação ("Sr."),
separa milhar ("1.250"), marca inicial ("J. R. R. Tolkien") e aparece em
reticências. Quebrar em todo ponto produz falas truncadas que o motor lê
com entonação de fim, e o resultado é picotado.

**Respirar** é achar onde partir uma frase que é longa demais para o
motor. Isso não é opcional: o Kokoro trabalha com uma janela de cerca de
510 fonemas e trunca o que passa disso — sem erro, sem aviso útil, a
frase simplesmente some pela metade no meio do capítulo. Como o corte vai
acontecer de todo jeito, é melhor que seja num ponto onde um leitor
humano também pararia para tomar ar: um ponto e vírgula, dois pontos, uma
conjunção. Cortar em cima de uma preposição é o que denuncia a máquina.
"""

from __future__ import annotations

import re

from audiolivro.texto.normalizar import ABREVIACOES

# Cerca de 510 fonemas viram, em português, algo perto de 400 caracteres.
# Ficamos bem abaixo: falas curtas também sintetizam mais rápido e falham
# de forma mais barata (re-sintetizar 300 caracteres, não 3.000).
LIMITE_FALA = 280

_ABREV = sorted(ABREVIACOES, key=len, reverse=True)

# O ponto NÃO termina a frase quando o que vem *antes* dele é:
#   - uma abreviação conhecida   (Sr., pág., cap.)
#   - uma letra sozinha          (J. R. R. Tolkien, A. C. Silva)
#
# Milhar e decimal ("1.250") não precisam entrar aqui: o candidato a fim
# de frase exige espaço depois do ponto, e ali não há. Incluí-los seria
# pior que inútil — "Ele nasceu em 1990. Depois mudou" também termina em
# dígito, e a frase deixaria de ser cortada.
_NAO_TERMINA = re.compile(
    r"(?:\b(?:" + "|".join(_ABREV) + r")|\b[A-Za-zÀ-ÿ])$",
    re.IGNORECASE,
)

# Candidato a fim de frase: pontuação final, aspas/parênteses opcionais
# de fechamento, espaço, e algo que pareça começo de frase.
_CANDIDATO = re.compile(
    r"""
    (?P<fim>[.!?…]+)         # a pontuação
    (?P<fecha>["'»)\]]*)     # fechamento que vem depois dela
    \s+
    (?=["'«(\[—–]?[A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9])   # começo plausível
    """,
    re.VERBOSE,
)

# Pontos naturais de respiro, do mais forte para o mais fraco. A ordem é
# a ordem de preferência na hora de partir uma frase longa.
_RESPIROS = (
    re.compile(r"(?<=[;:])\s+"),
    re.compile(r"(?<=,)\s+(?=(?:mas|porém|contudo|todavia|entretanto|embora|"
               r"ainda que|apesar|enquanto|quando|porque|pois|para que|"
               r"de modo que|e|ou)\b)", re.IGNORECASE),
    re.compile(r"(?<=,)\s+(?=(?:que|onde|cujo|cuja|o qual|a qual)\b)", re.IGNORECASE),
    re.compile(r"(?<=,)\s+"),
    re.compile(r"\s+(?=(?:e|ou|mas)\s)", re.IGNORECASE),
)


def segmentar(texto: str) -> list[str]:
    """Parágrafo -> lista de frases."""
    texto = texto.strip()
    if not texto:
        return []

    frases: list[str] = []
    inicio = 0
    for m in _CANDIDATO.finditer(texto):
        if m.group("fim") == "." and _NAO_TERMINA.search(texto[: m.start("fim")]):
            continue  # era abreviação ou inicial; a frase continua
        frases.append(texto[inicio : m.end("fecha")].strip())
        inicio = m.end()

    resto = texto[inicio:].strip()
    if resto:
        frases.append(resto)
    return frases


def respirar(frase: str, limite: int = LIMITE_FALA) -> list[str]:
    """Parte uma frase longa em pedaços que ainda soam inteiros.

    Tenta cada nível de respiro em ordem: só desce para um corte mais
    fraco quando o mais forte não resolveu. Se nenhum resolver — uma
    enumeração enorme sem vírgula, por exemplo — corta por palavra, que é
    feio mas é melhor que perder o texto.
    """
    if len(frase) <= limite:
        return [frase]

    for padrao in _RESPIROS:
        pedacos = _quebrar_equilibrado(frase, padrao, limite)
        if pedacos is not None:
            return [p for pedaco in pedacos for p in respirar(pedaco, limite)]

    return _quebrar_por_palavra(frase, limite)


def _quebrar_equilibrado(frase: str, padrao: re.Pattern[str], limite: int):
    """Junta os pedaços do `padrao` em grupos que caibam no limite.

    Devolve None se o padrão não corta a frase em lugar nenhum — aí o
    chamador tenta o próximo nível. Um único pedaço acima do limite não é
    motivo para desistir: a recursão volta nele com os outros padrões.
    """
    partes = padrao.split(frase)
    if len(partes) < 2:
        return None

    grupos: list[str] = []
    atual = ""
    for parte in partes:
        candidato = f"{atual} {parte}".strip() if atual else parte
        if atual and len(candidato) > limite:
            grupos.append(atual)
            atual = parte
        else:
            atual = candidato
    if atual:
        grupos.append(atual)
    return grupos


def _quebrar_por_palavra(frase: str, limite: int) -> list[str]:
    pedacos: list[str] = []
    atual = ""
    for palavra in frase.split():
        candidato = f"{atual} {palavra}".strip()
        if atual and len(candidato) > limite:
            pedacos.append(atual)
            atual = palavra
        else:
            atual = candidato
    if atual:
        pedacos.append(atual)
    return pedacos


def falar(paragrafo: str, limite: int = LIMITE_FALA) -> list[str]:
    """Atalho: parágrafo -> pedaços prontos para virar `Fala`."""
    return [
        pedaco
        for frase in segmentar(paragrafo)
        for pedaco in respirar(frase, limite)
    ]
