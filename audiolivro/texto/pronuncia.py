"""Como o livro deve pronunciar certas palavras.

Toda voz sintética erra nome próprio, marca, topônimo e estrangeirismo. A
correção por frase já existe, e não basta: num livro sobre a **Cinérea**,
o nome aparece dezenas de vezes. Corrigir frase a frase é reescrever a
mesma palavra cinquenta vezes, e perder tudo na próxima reextração.

Aqui a correção é do livro: uma entrada, todas as ocorrências.

    {"Cinérea": "Cinêrea", "Kierkegaard": "Quiérquegôr"}

**O dicionário se aplica na síntese, não na extração.** Parece detalhe e
é a decisão que faz a coisa funcionar:

* mudar o dicionário não exige reextrair, e portanto não joga fora as
  correções que já foram feitas frase a frase;
* o `livro.json` continua guardando o texto do livro, e não uma versão
  já deformada para a voz — o que importa quando se quer reler, exportar
  ou conferir o que o extrator entendeu;
* como a chave do cache é o texto que vai ao motor, mudar uma entrada
  re-sintetiza exatamente as falas que a contêm, e mais nenhuma.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

NOME_ARQUIVO = "pronuncia.json"


def carregar(pasta: Path) -> dict[str, str]:
    arquivo = pasta / NOME_ARQUIVO
    if not arquivo.exists():
        return {}
    try:
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}  # dicionário ilegível não pode impedir de gerar o livro
    return {
        str(k): str(v)
        for k, v in dados.items()
        if str(k).strip() and str(v).strip()
    }


def salvar(pasta: Path, dicionario: dict[str, str]) -> Path:
    arquivo = pasta / NOME_ARQUIVO
    limpo = {
        k.strip(): v.strip()
        for k, v in dicionario.items()
        if k.strip() and v.strip()
    }
    arquivo.write_text(
        json.dumps(limpo, ensure_ascii=False, indent=1, sort_keys=True),
        encoding="utf-8",
    )
    return arquivo


def compilar(dicionario: dict[str, str]) -> re.Pattern[str] | None:
    """Uma regex só para o dicionário inteiro, do termo mais longo ao menor.

    Do mais longo para o menor porque as entradas se contêm: com
    "Ouro Preto" e "Preto" no mesmo dicionário, a ordem alfabética faria
    "Preto" casar primeiro e "Ouro Preto" nunca ser alcançado.

    Uma regex só, e não uma por termo, porque ela é aplicada a cada fala
    de um livro que pode ter dez mil — vinte passadas por fala seria
    trabalho multiplicado à toa.
    """
    if not dicionario:
        return None
    termos = sorted(dicionario, key=len, reverse=True)
    return re.compile(
        r"(?<![\wÀ-ɏ])("
        + "|".join(re.escape(t) for t in termos)
        + r")(?![\wÀ-ɏ])",
        re.IGNORECASE,
    )


def aplicar(texto: str, dicionario: dict[str, str], regex: re.Pattern | None = None) -> str:
    """Troca as palavras do dicionário pela forma como devem soar.

    A comparação ignora maiúsculas, para que "CINÉREA" num título seja
    corrigida junto com "Cinérea" no corpo. A troca, porém, é literal: a
    forma escrita no dicionário é exatamente o que vai para o motor, e
    quem a escreveu sabe o que quis.

    As bordas usam a faixa latina estendida em vez de `\\b`: para o `\\b`
    do Python, "Cinérea" termina no "n" — o acento não é caractere de
    palavra em todos os contextos, e a entrada casaria no meio de
    palavras maiores.
    """
    if not dicionario:
        return texto
    padrao = regex or compilar(dicionario)
    if padrao is None:
        return texto

    baixa = {k.casefold(): v for k, v in dicionario.items()}
    return padrao.sub(lambda m: baixa.get(m.group(1).casefold(), m.group(1)), texto)


def ocorrencias(textos: list[str], termo: str) -> int:
    """Quantas falas contêm o termo. Serve para mostrar o alcance da regra."""
    padrao = compilar({termo: termo})
    if padrao is None:
        return 0
    return sum(1 for t in textos if padrao.search(t))
