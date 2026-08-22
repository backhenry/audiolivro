"""Um livro em produção: uma pasta com tudo dentro.

A primeira versão espalhava os arquivos de todos os livros numa pasta só,
distinguidos pelo nome-tronco (`O Nome da Rosa.livro.json`, `O Nome da
Rosa.trilha.json`, …). Funcionava e era ruim por três motivos que só
aparecem depois do segundo livro: não dá para ver o que pertence a quê,
não dá para apagar um livro sem caçar seis arquivos, e o cache de falas
de um livro fica indistinguível do de outro.

Agora cada livro é uma pasta. Apagar um projeto é apagar um diretório;
saber quanto ele ocupa é somar o que há dentro; levar para outra máquina
é copiar a pasta. E o cache mora junto do que ele serve.

    ~/Audiolivros/
      O Nome da Rosa/
        livro.json        o texto já preparado — editável à mão
        trilha.json       os tempos, para o player sincronizar
        audio.m4b         o audiobook
        posicao.json      onde a escuta parou
        original.epub     o arquivo de onde tudo veio
        .falas/           cache de síntese, endereçado por conteúdo
"""

from __future__ import annotations

import json
import re
import shutil
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from audiolivro.modelo import Livro, Trilha

BIBLIOTECA = Path.home() / "Audiolivros"

NOME_LIVRO = "livro.json"
NOME_TRILHA = "trilha.json"
NOME_POSICAO = "posicao.json"
PASTA_CACHE = ".falas"
PASTA_EXPORT = "exportado"
AUDIOS = ("audio.m4b", "audio.m4a", "audio.mp3", "audio.wav")


class ProjetoInvalido(ValueError):
    """O nome recebido não corresponde a um projeto da biblioteca."""


@dataclass
class Projeto:
    pasta: Path
    livro: Livro
    trilha: Trilha | None = None

    # -- caminhos --------------------------------------------------------

    @property
    def nome(self) -> str:
        """O identificador do projeto — o nome da pasta."""
        return self.pasta.name

    @property
    def cache(self) -> Path:
        return self.pasta / PASTA_CACHE

    def audio(self) -> Path | None:
        if self.trilha is None:
            return None
        caminho = self.pasta / self.trilha.audio
        return caminho if caminho.exists() else None

    def original(self) -> Path | None:
        return next((p for p in self.pasta.glob("original.*")), None)

    # -- persistência ----------------------------------------------------

    def gravar_livro(self) -> None:
        self.livro.salvar(self.pasta / NOME_LIVRO)

    def gravar_trilha(self, trilha: Trilha) -> None:
        self.trilha = trilha
        trilha.salvar(self.pasta / NOME_TRILHA)

    def pronuncia(self) -> dict[str, str]:
        from audiolivro.texto import pronuncia as _p

        return _p.carregar(self.pasta)

    def gravar_pronuncia(self, dicionario: dict[str, str]) -> None:
        from audiolivro.texto import pronuncia as _p

        _p.salvar(self.pasta, dicionario)

    def posicao(self) -> dict:
        arquivo = self.pasta / NOME_POSICAO
        if arquivo.exists():
            try:
                return json.loads(arquivo.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass  # marcador corrompido não impede de abrir o livro
        return {"segundo": 0.0, "velocidade": 1.0}

    def guardar_posicao(self, segundo: float, velocidade: float) -> dict:
        teto = self.trilha.duracao if self.trilha else 0.0
        dados = {
            "segundo": max(0.0, min(segundo, teto)),
            "velocidade": velocidade,
        }
        (self.pasta / NOME_POSICAO).write_text(json.dumps(dados), encoding="utf-8")
        return dados

    # -- limpeza ---------------------------------------------------------

    def capitulos_com_tempo(self) -> list[tuple[str, float, float]]:
        """(título, início, fim) de cada capítulo que virou áudio."""
        if self.trilha is None:
            return []
        marcos = self.trilha.capitulos
        fins = [c[1] for c in marcos[1:]] + [self.trilha.duracao]
        return [(t, i, f) for (t, i), f in zip(marcos, fins)]

    def exportar(
        self, formato: str = "mp3", *, por_capitulo: bool = False, bitrate: str = "64k"
    ) -> Path:
        """Produz um arquivo para levar embora, e devolve o caminho dele."""
        origem = self.audio()
        if origem is None:
            raise ProjetoInvalido("Este projeto ainda não tem áudio.")
        return exportar_audio(
            origem, self.capitulos_com_tempo(), self.livro,
            self.pasta / PASTA_EXPORT, formato,
            por_capitulo=por_capitulo, bitrate=bitrate,
        )

    def apagar_audio(self) -> None:
        """Joga fora o áudio e o cache, preserva o texto revisado.

        É o que se quer ao trocar de voz depois de ter corrigido cinquenta
        frases à mão: o trabalho de revisão fica, o áudio se refaz.
        """
        for nome in AUDIOS:
            (self.pasta / nome).unlink(missing_ok=True)
        (self.pasta / NOME_TRILHA).unlink(missing_ok=True)
        shutil.rmtree(self.cache, ignore_errors=True)
        shutil.rmtree(self.pasta / PASTA_EXPORT, ignore_errors=True)
        self.trilha = None

    def tamanho(self) -> int:
        return sum(p.stat().st_size for p in self.pasta.rglob("*") if p.is_file())

    def resumo(self) -> dict:
        """O cartão do projeto na lista."""
        audio = self.audio()
        return {
            "nome": self.nome,
            "titulo": self.livro.titulo,
            "autor": self.livro.autor,
            "origem": (o.name if (o := self.original()) else ""),
            "capitulos": len(self.livro.capitulos),
            # O que conta para quem vai gerar é o que vira som. O total
            # aparece ao lado só quando difere, para o usuário saber que
            # há coisa excluída e não achar que o livro veio truncado.
            "falas": len(self.livro.audiveis()),
            "falas_no_livro": len(self.livro.falas()),
            "pronto": audio is not None,
            "duracao": self.trilha.duracao if self.trilha else 0.0,
            "voz": f"{self.trilha.motor}:{self.trilha.voz}" if self.trilha else "",
            "tamanho": self.tamanho(),
            "posicao": self.posicao().get("segundo", 0.0) if self.trilha else 0.0,
            "modificado": _modificado(self.pasta),
        }


def exportar_audio(
    origem: Path,
    capitulos: list[tuple[str, float, float]],
    livro: Livro,
    pasta: Path,
    formato: str = "mp3",
    *,
    por_capitulo: bool = False,
    bitrate: str = "64k",
) -> Path:
    """Áudio já montado -> arquivo para distribuir.

    Parte do áudio pronto, não das falas: trocar de formato é uma passada
    de ffmpeg, não uma nova síntese. Num livro de dez horas, é a
    diferença entre segundos e meia hora.

    Por capítulo, o resultado é um zip. Entregar trinta arquivos soltos
    pelo navegador seriam trinta downloads, e ninguém quer isso.

    Função de módulo, e não método: ela precisa só do áudio, da trilha e
    do livro, então serve tanto ao projeto da biblioteca quanto aos
    arquivos soltos que a linha de comando deixa ao lado do original.
    """
    from audiolivro import montar as _montar

    # Não limpamos a pasta: formatos diferentes geram nomes diferentes e
    # convivem bem. Apagar tudo faria a segunda exportação sumir com a
    # primeira, o que surpreende quem gerou MP3 e M4B para comparar.
    pasta.mkdir(parents=True, exist_ok=True)
    nome = _nome_de_pasta(livro.titulo)

    if not por_capitulo:
        destino = pasta / f"{nome}.{formato}"
        # Mesmo formato e arquivo único: nada a recodificar, só um nome
        # decente no lugar de "audio.m4b".
        if origem.suffix.lstrip(".") == formato:
            shutil.copy2(origem, destino)
            return destino
        return _montar.converter(
            origem, destino, bitrate=bitrate,
            titulo=livro.titulo, autor=livro.autor,
        )

    if not capitulos:
        raise ProjetoInvalido("A trilha não tem capítulos para separar.")
    soltos = pasta / "capitulos"
    arquivos = _montar.dividir_por_capitulo(
        origem, [_montar.Capitulo(t, i, f) for t, i, f in capitulos], soltos,
        extensao=formato, bitrate=bitrate,
        titulo_do_livro=livro.titulo, autor=livro.autor,
    )
    zipado = _montar.compactar(arquivos, pasta / f"{nome} ({formato}).zip", nome)
    shutil.rmtree(soltos, ignore_errors=True)
    return zipado


# -- a biblioteca --------------------------------------------------------


def criar(livro: Livro, origem: Path | None = None) -> Projeto:
    """Abre um projeto novo para `livro`, sem colidir com os existentes."""
    BIBLIOTECA.mkdir(parents=True, exist_ok=True)
    pasta = BIBLIOTECA / _sem_colidir(_nome_de_pasta(livro.titulo))
    pasta.mkdir(parents=True, exist_ok=True)

    projeto = Projeto(pasta=pasta, livro=livro)
    projeto.gravar_livro()
    if origem is not None and origem.exists():
        # Guardar o original é o que permite reextrair depois — com OCR,
        # com notas, com outro ajuste — sem pedir o arquivo de novo.
        destino = pasta / f"original{origem.suffix.lower()}"
        if origem.resolve() != destino.resolve():
            shutil.copy2(origem, destino)
    return projeto


def carregar(nome: str) -> Projeto:
    pasta = pasta_de(nome)
    arquivo = pasta / NOME_LIVRO
    if not arquivo.exists():
        raise ProjetoInvalido(f"O projeto '{nome}' não tem {NOME_LIVRO}.")

    projeto = Projeto(pasta=pasta, livro=Livro.carregar(arquivo))
    trilha = pasta / NOME_TRILHA
    if trilha.exists():
        try:
            candidata = Trilha.carregar(trilha)
            if (pasta / candidata.audio).exists():
                projeto.trilha = candidata
        except (OSError, json.JSONDecodeError, KeyError, ValueError):
            pass  # trilha ilegível: o projeto continua abrindo como rascunho
    return projeto


def listar() -> list[Projeto]:
    """Todos os projetos, do mais recente para o mais antigo."""
    if not BIBLIOTECA.exists():
        return []
    achados = []
    for pasta in BIBLIOTECA.iterdir():
        if not pasta.is_dir() or pasta.name.startswith("."):
            continue
        try:
            achados.append(carregar(pasta.name))
        except (ProjetoInvalido, OSError, json.JSONDecodeError, ValueError):
            continue  # pasta que não é projeto, ou projeto corrompido
    achados.sort(key=lambda p: _modificado(p.pasta), reverse=True)
    return achados


def por_titulo(titulo: str) -> Projeto | None:
    """Acha um projeto existente com este título, para não duplicar.

    Reabrir o mesmo EPUB deve cair no projeto que já existe — inclusive
    com as correções de texto que já foram feitas nele — em vez de criar
    "Livro 2" e jogar fora o trabalho anterior.
    """
    alvo = titulo.strip().casefold()
    return next((p for p in listar() if p.livro.titulo.strip().casefold() == alvo), None)


def apagar(nome: str) -> None:
    shutil.rmtree(pasta_de(nome))


def pasta_de(nome: str) -> Path:
    """Resolve o nome do projeto para uma pasta, recusando o que não for.

    O nome vem do navegador, então é entrada não confiável: "../.." ou um
    caminho absoluto apagariam qualquer coisa no disco quando passassem
    por `apagar`. Só aceitamos um filho direto da biblioteca que exista de
    verdade — e conferimos depois de resolver, porque um link simbólico
    dentro da biblioteca poderia apontar para fora dela.
    """
    if not nome or "/" in nome or "\\" in nome or nome in (".", ".."):
        raise ProjetoInvalido(f"Nome de projeto inválido: {nome!r}")

    pasta = (BIBLIOTECA / nome).resolve()
    if pasta.parent != BIBLIOTECA.resolve() or not pasta.is_dir():
        raise ProjetoInvalido(f"O projeto '{nome}' não existe na biblioteca.")
    return pasta


# -- nomes ---------------------------------------------------------------

_PROIBIDOS = re.compile(r'[/\\:*?"<>|\x00-\x1f]')


def _nome_de_pasta(titulo: str, limite: int = 70) -> str:
    """Título do livro -> nome de pasta legível.

    Acentos ficam: é o nome que o usuário vai ver no Finder, e o APFS
    lida bem com eles. Só saem os caracteres que quebram caminho e os
    pontos iniciais, que esconderiam a pasta.
    """
    nome = unicodedata.normalize("NFC", titulo).strip()
    nome = _PROIBIDOS.sub(" ", nome)
    nome = " ".join(nome.split())[:limite].strip(" .")
    return nome or "Livro sem título"


def _sem_colidir(nome: str) -> str:
    if not (BIBLIOTECA / nome).exists():
        return nome
    for n in range(2, 1000):
        candidato = f"{nome} ({n})"
        if not (BIBLIOTECA / candidato).exists():
            return candidato
    raise ProjetoInvalido(f"Não consegui achar um nome livre para '{nome}'.")


def _modificado(pasta: Path) -> float:
    """O arquivo mais recente da pasta manda na data do projeto.

    A data da própria pasta não serve: gravar `posicao.json` a cada cinco
    segundos de escuta atualiza o arquivo, mas nem sempre o diretório.
    """
    try:
        return max(
            (p.stat().st_mtime for p in pasta.iterdir() if p.is_file()),
            default=pasta.stat().st_mtime,
        )
    except OSError:
        return 0.0


def formatar_data(instante: float) -> str:
    return datetime.fromtimestamp(instante).strftime("%d/%m/%Y %H:%M")
