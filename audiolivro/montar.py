"""Das falas soltas para um arquivo que o Apple Books entende.

O ponto central deste módulo é o que ele *não* faz: acumular o livro na
memória. Dez horas de áudio a 24 kHz em float32 são 3,4 GB — o programa
morreria no meio de qualquer livro sério. Em vez disso, cada fala é
escrita para o ffmpeg assim que sai do cache, e o processo inteiro nunca
segura mais que uns poucos segundos de som.

O M4B sai em duas passagens, e não por desleixo: os capítulos precisam
dos tempos de início e fim, e o fim do último capítulo só se conhece
quando o áudio acabou. Então a primeira passagem codifica, e a segunda
carimba os metadados com `-c copy` — que é remux, não recodificação, e
leva segundos mesmo num livro longo.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from audiolivro.ffmpeg import FFmpegError, caminho_do_ffmpeg

# 64 kbit/s em mono AAC é transparente para voz e deixa um livro de dez
# horas em ~290 MB. Acima disso só cresce o arquivo.
BITRATE_PADRAO = "64k"

FORMATOS = {
    "m4b": ("aac", "ipod", "m4b"),
    "m4a": ("aac", "ipod", "m4a"),
    "mp3": ("libmp3lame", "mp3", "mp3"),
    "wav": ("pcm_s16le", "wav", "wav"),
}


@dataclass
class Capitulo:
    titulo: str
    inicio: float
    fim: float


class Escritor:
    """Recebe blocos de amostras e vai empurrando para o ffmpeg.

    Usado como contexto: ao sair, fecha a entrada e espera o encoder
    terminar. Se o ffmpeg morrer no meio (codec ausente, disco cheio), o
    erro aparece aqui com o stderr junto, e não como um `BrokenPipeError`
    solto na primeira escrita — que é o que aconteceria sem o tratamento
    do `_empurrar`.
    """

    def __init__(
        self,
        destino: Path,
        taxa: int,
        *,
        formato: str = "m4b",
        bitrate: str = BITRATE_PADRAO,
        titulo: str = "",
        autor: str = "",
    ) -> None:
        if formato not in FORMATOS:
            raise ValueError(f"Formato '{formato}' desconhecido: {', '.join(FORMATOS)}")
        self.destino = destino
        self.taxa = taxa
        self.formato = formato
        self.bitrate = bitrate
        self.titulo = titulo
        self.autor = autor
        self.amostras_escritas = 0
        self._proc: subprocess.Popen | None = None

    @property
    def posicao(self) -> float:
        """Onde estamos na trilha, em segundos."""
        return self.amostras_escritas / self.taxa

    def __enter__(self) -> Escritor:
        codec, formato_saida, _ext = FORMATOS[self.formato]
        self.destino.parent.mkdir(parents=True, exist_ok=True)

        comando = [
            caminho_do_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
            "-f", "f32le", "-ar", str(self.taxa), "-ac", "1", "-i", "pipe:0",
            "-c:a", codec,
        ]
        if codec != "pcm_s16le":
            comando += ["-b:a", self.bitrate]
        if self.titulo:
            comando += ["-metadata", f"title={self.titulo}"]
        if self.autor:
            comando += ["-metadata", f"artist={self.autor}", "-metadata", f"album_artist={self.autor}"]
        if self.formato in ("m4b", "m4a"):
            # Sem isto o QuickTime e o Books tratam o arquivo como música
            # e não guardam a posição de escuta entre sessões.
            comando += ["-metadata", "media_type=2"]
        comando += ["-f", formato_saida, str(self.destino)]

        self._proc = subprocess.Popen(
            comando, stdin=subprocess.PIPE, stderr=subprocess.PIPE
        )
        return self

    def escrever(self, amostras: np.ndarray) -> None:
        if amostras.size:
            self._empurrar(np.ascontiguousarray(amostras, dtype=np.float32).tobytes())
            self.amostras_escritas += amostras.size

    def silencio(self, segundos: float) -> None:
        quadros = int(segundos * self.taxa)
        if quadros > 0:
            self._empurrar(b"\x00" * (quadros * 4))
            self.amostras_escritas += quadros

    def _empurrar(self, dados: bytes) -> None:
        assert self._proc is not None and self._proc.stdin is not None
        try:
            self._proc.stdin.write(dados)
        except BrokenPipeError as erro:
            erro_ffmpeg = (self._proc.stderr.read() or b"").decode(errors="replace")
            raise FFmpegError(["ffmpeg"], self._proc.returncode or 1, erro_ffmpeg) from erro

    def __exit__(self, *_excecao) -> None:
        if self._proc is None:
            return
        if self._proc.stdin:
            self._proc.stdin.close()
        erro = (self._proc.stderr.read() or b"").decode(errors="replace")
        codigo = self._proc.wait()
        if codigo != 0:
            raise FFmpegError(["ffmpeg"], codigo, erro)


def escrever_metadados(
    capitulos: list[Capitulo], destino: Path, *, titulo: str = "", autor: str = ""
) -> Path:
    """Gera o arquivo FFMETADATA com os capítulos."""
    linhas = [";FFMETADATA1"]
    if titulo:
        linhas.append(f"title={_escapar(titulo)}")
    if autor:
        linhas.append(f"artist={_escapar(autor)}")
        linhas.append(f"album={_escapar(titulo or autor)}")

    for capitulo in capitulos:
        linhas += [
            "",
            "[CHAPTER]",
            "TIMEBASE=1/1000",
            f"START={int(capitulo.inicio * 1000)}",
            f"END={int(capitulo.fim * 1000)}",
            f"title={_escapar(capitulo.titulo)}",
        ]

    destino.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return destino


def _escapar(valor: str) -> str:
    """O FFMETADATA usa '=' ';' '#' '\\' e a quebra de linha como sintaxe."""
    for caractere in ("\\", "=", ";", "#"):
        valor = valor.replace(caractere, "\\" + caractere)
    return valor.replace("\n", " ").strip()


def aplicar_capitulos(audio: Path, metadados: Path, destino: Path) -> Path:
    """Segunda passagem: carimba os capítulos sem recodificar.

    `-map_metadata 1` puxa do arquivo de metadados; `-map_chapters 1` é
    o que a maioria dos exemplos na internet esquece, e sem ele o M4B sai
    com o título certo e nenhum capítulo.
    """
    comando = [
        caminho_do_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(audio), "-i", str(metadados),
        "-map", "0:a", "-map_metadata", "1", "-map_chapters", "1",
        "-c", "copy", str(destino),
    ]
    resultado = subprocess.run(comando, capture_output=True, text=True)
    if resultado.returncode != 0:
        raise FFmpegError(comando, resultado.returncode, resultado.stderr)
    return destino


def _rodar(comando: list[str]) -> None:
    resultado = subprocess.run(comando, capture_output=True, text=True)
    if resultado.returncode != 0:
        raise FFmpegError(comando, resultado.returncode, resultado.stderr)


def _etiquetas(
    titulo: str, autor: str, album: str = "", faixa: int | None = None, total: int | None = None
) -> list[str]:
    """Metadados que fazem o arquivo aparecer com nome no player.

    Sem isto, um MP3 solto entra na biblioteca de quem recebeu como
    "audio", sem autor e sem ordem — e um audiobook de trinta capítulos
    fora de ordem é inutilizável.
    """
    marcas = []
    for chave, valor in (("title", titulo), ("artist", autor),
                         ("album", album or titulo), ("album_artist", autor),
                         ("genre", "Audiobook")):
        if valor:
            marcas += ["-metadata", f"{chave}={valor}"]
    if faixa is not None:
        marcas += ["-metadata", f"track={faixa}" + (f"/{total}" if total else "")]
    return marcas


def converter(
    origem: Path, destino: Path, *, bitrate: str = BITRATE_PADRAO,
    titulo: str = "", autor: str = "",
) -> Path:
    """Converte o áudio já pronto para outro formato, sem re-sintetizar.

    Trocar de formato pela geração completa funcionaria — o cache
    devolveria cada fala do disco — mas percorreria o livro inteiro fala
    a fala para montar de novo. Recodificar o arquivo pronto é uma
    passada só do ffmpeg, e leva segundos mesmo em dez horas de áudio.

    A perda de qualidade de recodificar um áudio já comprimido é real,
    mas irrelevante em voz a 64 kbit/s: o que se perde está muito acima
    da banda que a fala ocupa.
    """
    codec, formato_saida, _ext = FORMATOS[destino.suffix.lstrip(".")]
    destino.parent.mkdir(parents=True, exist_ok=True)
    comando = [
        caminho_do_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(origem), "-vn", "-c:a", codec,
    ]
    if codec != "pcm_s16le":
        comando += ["-b:a", bitrate]
    comando += _etiquetas(titulo, autor) + ["-f", formato_saida, str(destino)]
    _rodar(comando)
    return destino


def dividir_por_capitulo(
    audio: Path,
    capitulos: list[Capitulo],
    pasta: Path,
    *,
    extensao: str = "m4a",
    bitrate: str = BITRATE_PADRAO,
    titulo_do_livro: str = "",
    autor: str = "",
) -> list[Path]:
    """Um arquivo por capítulo, para distribuir ou montar lista de reprodução.

    Quando a extensão de saída é a mesma da entrada, corta com `-c copy`:
    rápido, sem perda, e alinhado ao quadro mais próximo — a diferença de
    alguns milissegundos não é audível numa fronteira que já é silêncio.
    Sendo outra, recodifica, porque copiar AAC para dentro de um MP3 não
    existe.
    """
    pasta.mkdir(parents=True, exist_ok=True)
    mesmo_formato = audio.suffix.lstrip(".") == extensao
    codec = FORMATOS[extensao][0]
    saidas: list[Path] = []

    for i, capitulo in enumerate(capitulos, start=1):
        destino = pasta / f"{_nome_de_arquivo(f'{i:03d} - {capitulo.titulo}')}.{extensao}"
        comando = [
            caminho_do_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(audio),
            "-ss", f"{capitulo.inicio:.3f}", "-to", f"{capitulo.fim:.3f}", "-vn",
        ]
        if mesmo_formato:
            comando += ["-c", "copy"]
        else:
            comando += ["-c:a", codec]
            if codec != "pcm_s16le":
                comando += ["-b:a", bitrate]
        comando += _etiquetas(
            capitulo.titulo, autor, album=titulo_do_livro, faixa=i, total=len(capitulos)
        )
        comando.append(str(destino))
        _rodar(comando)
        saidas.append(destino)
    return saidas


def compactar(arquivos: list[Path], destino: Path, pasta_interna: str = "") -> Path:
    """Junta os capítulos num zip, para caber num anexo de e-mail.

    Sem compressão: o áudio já está comprimido, e tentar de novo gastaria
    minutos de CPU para economizar quase nada.
    """
    import zipfile

    destino.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_STORED) as z:
        for arquivo in arquivos:
            interno = f"{pasta_interna}/{arquivo.name}" if pasta_interna else arquivo.name
            z.write(arquivo, interno)
    return destino


def _nome_de_arquivo(texto: str, limite: int = 70) -> str:
    limpo = "".join(c if c.isalnum() or c in " -_,." else " " for c in texto)
    return " ".join(limpo.split())[:limite].strip() or "capitulo"
