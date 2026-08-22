"""Livro -> audiobook. O estágio caro, e por isso o que mais tem cache.

Sintetizar um romance leva de uma a três horas. Isso muda o que conta
como um bom projeto: qualquer coisa que force a repetir o trabalho
inteiro é um defeito grave, e o cache deixa de ser otimização para virar
requisito.

O cache é endereçado por conteúdo — a chave é o hash de
`(motor, voz, velocidade, texto)`. A consequência prática é a que
importa: você corrige o nome do protagonista no capítulo 7, roda de
novo, e só aquelas duas frases são sintetizadas. As outras nove mil vêm
do disco em segundos. E como a chave inclui o motor, dá para comparar
Kokoro e Piper no mesmo livro sem que um invalide o outro.

Duas fases, deliberadamente separadas:

1. **Sintetizar** o que falta, em paralelo, fora de ordem.
2. **Montar** em ordem, transmitindo para o ffmpeg.

Juntá-las pareceria mais simples e seria pior: a montagem precisa ser
sequencial, e amarrar a síntese a ela desperdiçaria os outros núcleos.
"""

from __future__ import annotations

import hashlib
import os
import threading
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from audiolivro import montar as _montar
from audiolivro.modelo import Fala, Livro, Marca, Trilha
from audiolivro.voz import abrir, aparar, normalizar_volume
from audiolivro.voz.base import Motor


class Cancelado(RuntimeError):
    """O chamador pediu para parar."""


@dataclass
class Progresso:
    total: int
    prontas: int = 0
    do_cache: int = 0
    fase: str = "sintetizando"

    @property
    def fracao(self) -> float:
        return self.prontas / self.total if self.total else 1.0


def sintetizar(
    livro: Livro,
    destino: Path,
    *,
    motor: str | None = None,
    voz: str | None = None,
    velocidade: float = 1.0,
    formato: str = "m4b",
    bitrate: str = _montar.BITRATE_PADRAO,
    escala_de_pausa: float = 1.0,
    threads: int | None = None,
    cache: Path | None = None,
    ao_progredir: Callable[[Progresso], None] | None = None,
    deve_parar: Callable[[], bool] | None = None,
) -> Trilha:
    """Sintetiza `livro` em `destino` e devolve a `Trilha` com os tempos."""
    instancia, escolhida = abrir(motor, voz)
    falas = livro.audiveis()
    if not falas:
        raise ValueError(
            "Não há nada para sintetizar: o livro está vazio ou todas as "
            "falas foram marcadas para não ler."
        )

    destino = Path(destino)
    pasta = Path(cache) if cache else destino.parent / f".{destino.stem}.falas"
    pasta.mkdir(parents=True, exist_ok=True)

    estado = Progresso(total=len(falas))
    _avisar = ao_progredir or (lambda _p: None)
    _parar = deve_parar or (lambda: False)

    caminhos = {
        f.id: pasta / f"{_chave(f, instancia.nome, escolhida, velocidade)}.flac"
        for f in falas
    }

    _fase_sintese(
        falas, caminhos, instancia, escolhida, velocidade,
        threads=threads, estado=estado, avisar=_avisar, parar=_parar,
    )

    estado.fase = "montando"
    _avisar(estado)
    return _fase_montagem(
        livro, caminhos, instancia, escolhida, velocidade,
        destino=destino, formato=formato, bitrate=bitrate,
        escala_de_pausa=escala_de_pausa, parar=_parar,
    )


# -- fase 1 --------------------------------------------------------------


def _chave(fala: Fala, motor: str, voz: str, velocidade: float) -> str:
    """Identidade do áudio desta fala.

    Repare no que *não* entra: o id da fala. Duas frases idênticas em
    capítulos diferentes — "Ele não respondeu." aparece dezenas de vezes
    num romance — compartilham o mesmo arquivo. E inserir um parágrafo no
    começo do livro, que renumera todos os ids seguintes, não invalida
    absolutamente nada.
    """
    assinatura = f"{motor}|{voz}|{velocidade:.3f}|{fala.texto}"
    return hashlib.sha256(assinatura.encode("utf-8")).hexdigest()[:24]


def _fase_sintese(
    falas: list[Fala],
    caminhos: dict[str, Path],
    motor: Motor,
    voz: str,
    velocidade: float,
    *,
    threads: int | None,
    estado: Progresso,
    avisar: Callable[[Progresso], None],
    parar: Callable[[], bool],
) -> None:
    # Falas repetidas apontam para o mesmo arquivo; sintetizar uma vez
    # basta, e num diálogo isso corta um pedaço real do trabalho.
    pendentes: dict[Path, Fala] = {}
    quantas: Counter[Path] = Counter()
    for fala in falas:
        alvo = caminhos[fala.id]
        if alvo.exists():
            estado.do_cache += 1
            estado.prontas += 1
        else:
            pendentes.setdefault(alvo, fala)
            quantas[alvo] += 1

    avisar(estado)
    if not pendentes:
        return

    trava = threading.Lock()

    def _uma(item: tuple[Path, Fala]) -> None:
        alvo, fala = item
        if parar():
            raise Cancelado("Síntese cancelada.")
        _sintetizar_fala(fala, alvo, motor, voz, velocidade)
        # O progresso conta falas, não arquivos: uma frase que se repete
        # cinco vezes no livro avança cinco passos de uma vez, e a barra
        # continua batendo com o total anunciado no começo.
        with trava:
            estado.prontas += quantas[alvo]
            avisar(estado)

    with ThreadPoolExecutor(max_workers=threads or _threads_padrao()) as piscina:
        for _ in piscina.map(_uma, pendentes.items()):
            pass


def _threads_padrao() -> int:
    """O onnxruntime já usa vários núcleos por inferência.

    Empilhar uma thread por núcleo em cima disso faz os workers
    disputarem os mesmos núcleos e o resultado fica *mais lento* que com
    quatro. Metade dos núcleos, teto de quatro, foi o melhor ponto nos
    testes num M-series.
    """
    nucleos = os.cpu_count() or 4
    return max(1, min(4, nucleos // 2))


def _sintetizar_fala(
    fala: Fala, destino: Path, motor: Motor, voz: str, velocidade: float
) -> None:
    import soundfile as sf

    amostras = motor.sintetizar(fala.texto, voz=voz, velocidade=velocidade)
    amostras = normalizar_volume(aparar(amostras, motor.taxa))

    # Grava em parcial e renomeia: um Ctrl-C no meio da escrita deixaria
    # um FLAC truncado no cache, e a execução seguinte o daria como
    # pronto — um capítulo com um buraco que nenhuma nova tentativa
    # conserta, porque o cache "já tem" aquela fala.
    parcial = destino.with_suffix(".part")
    sf.write(parcial, amostras, motor.taxa, format="FLAC")
    parcial.replace(destino)


# -- fase 2 --------------------------------------------------------------


def _fase_montagem(
    livro: Livro,
    caminhos: dict[str, Path],
    motor: Motor,
    voz: str,
    velocidade: float,
    *,
    destino: Path,
    formato: str,
    bitrate: str,
    escala_de_pausa: float,
    parar: Callable[[], bool],
) -> Trilha:
    import soundfile as sf

    precisa_de_capitulos = formato in ("m4b", "m4a")
    bruto = destino.with_suffix(".bruto." + formato) if precisa_de_capitulos else destino

    marcas: list[Marca] = []
    capitulos: list[_montar.Capitulo] = []

    # A taxa vem do áudio em cache, não de `motor.taxa`. Motores com taxa
    # por voz só a descobrem ao carregar o modelo — e numa execução em que
    # tudo já está em cache, modelo nenhum é carregado. O atributo estaria
    # no valor de fábrica, o ffmpeg receberia PCM de 22 kHz rotulado como
    # 24 kHz, e o livro inteiro sairia acelerado e com a voz mais aguda.
    taxa = sf.info(caminhos[livro.audiveis()[0].id]).samplerate

    with _montar.Escritor(
        bruto, taxa, formato=formato, bitrate=bitrate,
        titulo=livro.titulo, autor=livro.autor,
    ) as escritor:
        for capitulo in livro.capitulos:
            inicio = escritor.posicao
            for bloco in capitulo.blocos:
                for fala in bloco.falas:
                    if not fala.ler:
                        continue
                    if parar():
                        raise Cancelado("Montagem cancelada.")
                    amostras, _taxa = sf.read(caminhos[fala.id], dtype="float32")
                    comeco = escritor.posicao
                    escritor.escrever(amostras)
                    marcas.append(
                        Marca(fala.id, comeco, escritor.posicao - comeco)
                    )
                    escritor.silencio(fala.pausa * escala_de_pausa)
            # Um capítulo cujas falas foram todas excluídas não ocupa
            # tempo nenhum. Registrá-lo mesmo assim criaria no M4B um
            # capítulo de duração zero, que os players mostram na lista e
            # para o qual dá para pular, sem nada para ouvir.
            if escritor.posicao > inicio:
                capitulos.append(
                    _montar.Capitulo(capitulo.titulo, inicio, escritor.posicao)
                )
        duracao = escritor.posicao

    if precisa_de_capitulos:
        metadados = _montar.escrever_metadados(
            capitulos, destino.with_suffix(".metadados.txt"),
            titulo=livro.titulo, autor=livro.autor,
        )
        _montar.aplicar_capitulos(bruto, metadados, destino)
        bruto.unlink(missing_ok=True)
        metadados.unlink(missing_ok=True)

    return Trilha(
        audio=destino.name,
        duracao=duracao,
        motor=motor.nome,
        voz=voz,
        velocidade=velocidade,
        marcas=marcas,
        capitulos=[(c.titulo, c.inicio) for c in capitulos],
    )


def prever(livro: Livro, motor: str | None = None) -> dict:
    """Estimativa antes de começar — quanto tempo, quanto arquivo.

    Existe porque a primeira pergunta de quem manda sintetizar um livro é
    "quanto tempo isso vai levar?", e a resposta honesta muda a decisão
    de rodar agora ou de madrugada.
    """
    segundos = livro.duracao_estimada()
    rtf = {"kokoro": 0.24, "piper": 0.08, "macos": 0.02}.get(motor or "piper", 0.1)
    return {
        "falas": len(livro.audiveis()),
        "caracteres": livro.caracteres,
        "duracao_audio": segundos,
        "tempo_de_sintese": segundos * rtf / _threads_padrao(),
        "tamanho_m4b": segundos * 8_000,  # 64 kbit/s
    }
