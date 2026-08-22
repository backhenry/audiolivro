"""Linha de comando do audiolivro.

Os comandos seguem os três estágios: `extrair` produz o `Livro`, `gerar`
produz o áudio, `player` abre a interface. `ouvir` faz os três de uma vez,
que é o que se quer na maioria das vezes.

`previa` merece nota à parte: ele sintetiza um punhado de frases em
segundos. Antes de mandar duas horas de síntese num livro de trezentas
páginas, é como se descobre que a voz escolhida não agrada ou que o
extrator comeu os diálogos — e são dois erros caros de descobrir depois.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
)
from rich.table import Table

from audiolivro import ingest, sintetizar as _sintetizar
from audiolivro.modelo import Livro, Trilha
from audiolivro.voz import MotorIndisponivel, catalogo, disponiveis

app = typer.Typer(
    name="audiolivro",
    help="Transforma livros em audiobooks que dá para ouvir. Tudo local.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()


# -- opções compartilhadas ----------------------------------------------

OpMotor = Annotated[
    str | None,
    typer.Option("--motor", "-m", help="kokoro, piper ou macos. Padrão: o melhor disponível."),
]
OpVoz = Annotated[
    str | None, typer.Option("--voz", "-v", help="Nome da voz. Veja com 'audiolivro vozes'.")
]
OpVelocidade = Annotated[
    float, typer.Option("--velocidade", help="1.0 é o natural; 1.15 já soa apressado.")
]
OpOcr = Annotated[
    str, typer.Option("--ocr", help="auto, sempre ou nunca. Só afeta PDF.")
]
OpNotas = Annotated[
    bool, typer.Option("--notas/--sem-notas", help="Ler as notas de rodapé.")
]


@app.command()
def extrair(
    arquivo: Annotated[Path, typer.Argument(help="EPUB, PDF, TXT ou Markdown.")],
    saida: Annotated[Path | None, typer.Option("-o", "--saida", help="Onde gravar o livro.json.")] = None,
    ocr: OpOcr = "auto",
    notas: OpNotas = False,
    mostrar: Annotated[int, typer.Option("--mostrar", help="Quantas falas exibir de amostra.")] = 6,
) -> None:
    """Lê o arquivo e grava o `Livro` — o JSON com o texto já preparado.

    Vale abrir o resultado e olhar antes de sintetizar. É um arquivo de
    texto comum: dá para corrigir um nome próprio que a voz vai errar, ou
    apagar a página de créditos que virou capítulo.
    """
    livro = _extrair(arquivo, ocr=ocr, notas=notas)
    destino = saida or arquivo.with_suffix(".livro.json")
    livro.salvar(destino)

    _resumo(livro)
    if mostrar:
        console.print("\n[bold]Amostra do que será lido:[/bold]")
        for fala in livro.falas()[:mostrar]:
            console.print(f"  [dim]·[/dim] {fala.texto}")
    console.print(f"\n[green]✓[/green] {destino}")


@app.command()
def vozes() -> None:
    """Lista as vozes prontas para usar nesta máquina."""
    prontos = disponiveis()
    if not prontos:
        console.print("[red]Nenhum motor disponível.[/red]")
        console.print("  pip install kokoro-onnx espeakng-loader")
        raise typer.Exit(1)

    tabela = Table(title="Vozes em português")
    tabela.add_column("Motor")
    tabela.add_column("Voz")
    tabela.add_column("Nome")
    tabela.add_column("Timbre")
    for voz in catalogo():
        if not voz.idioma.startswith("pt"):
            continue
        tabela.add_row(voz.motor, voz.id, voz.nome, voz.genero or "—")
    console.print(tabela)
    console.print(f"\nMotores prontos: [bold]{', '.join(prontos)}[/bold]")

    # As dicas seguem a ordem de preferência: sem o Piper, o usuário está
    # preso nas vozes do sistema e nem sabe disso — a lista acima parece
    # completa. Mencionar o Kokoro antes disso seria apontar para a
    # segunda escolha.
    if "piper" not in prontos:
        console.print(
            "\n[yellow]As vozes com pronúncia brasileira ainda não foram "
            "baixadas.[/yellow]\nRode: [bold]audiolivro baixar[/bold]  "
            "[dim](~190 MB, uma vez só)[/dim]"
        )
    elif "kokoro" not in prontos:
        console.print(
            "\n[dim]O Kokoro tem prosódia melhor, com sotaque levemente "
            "americano. Para experimentar:\n"
            "  audiolivro baixar kokoro   (350 MB)[/dim]"
        )


@app.command()
def baixar(
    motor: Annotated[str, typer.Argument(help="piper, kokoro ou todos.")] = "piper",
) -> None:
    """Baixa os pesos das vozes. Uma vez só.

    O padrão é o Piper: são as vozes com pronúncia brasileira e o motor
    escolhido automaticamente. O Kokoro tem prosódia melhor, pesa 350 MB
    e traz um sotaque levemente americano — vale se você preferir
    entonação a pronúncia.
    """
    if motor not in ("piper", "kokoro", "todos"):
        console.print(f"[red]Motor '{motor}' não existe. Use piper, kokoro ou todos.[/red]")
        raise typer.Exit(1)

    with Progress(
        SpinnerColumn(), TextColumn("{task.description}"), BarColumn(),
        TaskProgressColumn(), TimeRemainingColumn(), console=console,
    ) as barra:
        if motor in ("piper", "todos"):
            from audiolivro.voz import piper

            for voz in piper.VOZES:
                # O `urlretrieve` do Piper não reporta progresso por
                # pedaço; a barra aqui marca voz concluída, não byte.
                tarefa = barra.add_task(f"{voz.nome} ({voz.id})", total=1)
                piper.garantir_modelo(voz.id)
                barra.update(tarefa, completed=1)
            console.print(f"[green]✓[/green] Vozes Piper em {piper.PASTA}")

        if motor in ("kokoro", "todos"):
            from audiolivro.voz import kokoro

            tarefas: dict[str, int] = {}

            def progresso(nome: str, baixado: int, total: int) -> None:
                if nome not in tarefas:
                    tarefas[nome] = barra.add_task(nome, total=total or None)
                barra.update(tarefas[nome], completed=baixado)

            kokoro.garantir_modelo(ao_baixar=progresso)
            console.print(f"[green]✓[/green] Kokoro em {kokoro.PASTA}")


@app.command()
def previa(
    arquivo: Annotated[Path, typer.Argument(help="Livro (qualquer formato) ou .livro.json.")],
    motor: OpMotor = None,
    voz: OpVoz = None,
    velocidade: OpVelocidade = 1.0,
    falas: Annotated[int, typer.Option("--falas", "-n", help="Quantas falas sintetizar.")] = 8,
    pular: Annotated[int, typer.Option("--pular", help="Quantas falas ignorar no começo.")] = 0,
    ocr: OpOcr = "auto",
) -> None:
    """Sintetiza um punhado de frases e toca — para conferir voz e texto.

    Leva segundos. Rode isto antes de todo `gerar`.
    """
    livro = _abrir(arquivo, ocr=ocr, notas=False)
    recorte = _recortar(livro, pular, falas)
    destino = Path(arquivo).with_suffix(".previa.m4a")

    trilha = _rodar_sintese(recorte, destino, motor, voz, velocidade, formato="m4a")
    console.print(f"[green]✓[/green] {destino} ({trilha.duracao:.0f}s)")

    _tocar(destino)


@app.command()
def gerar(
    arquivo: Annotated[Path, typer.Argument(help="Livro (qualquer formato) ou .livro.json.")],
    saida: Annotated[Path | None, typer.Option("-o", "--saida")] = None,
    motor: OpMotor = None,
    voz: OpVoz = None,
    velocidade: OpVelocidade = 1.0,
    formato: Annotated[str, typer.Option("--formato", help="m4b, m4a, mp3 ou wav.")] = "m4b",
    pausas: Annotated[float, typer.Option("--pausas", help="Multiplica todos os silêncios.")] = 1.0,
    threads: Annotated[int | None, typer.Option("--threads")] = None,
    por_capitulo: Annotated[bool, typer.Option("--por-capitulo", help="Também gerar um arquivo por capítulo.")] = False,
    ocr: OpOcr = "auto",
    notas: OpNotas = False,
) -> None:
    """Sintetiza o livro inteiro num M4B com capítulos."""
    livro = _abrir(arquivo, ocr=ocr, notas=notas)
    destino = saida or Path(arquivo).with_suffix(f".{formato}")

    _resumo(livro)
    previsao = _sintetizar.prever(livro, motor or (disponiveis() or ["kokoro"])[0])
    console.print(
        f"Estimativa: [bold]{_hms(previsao['duracao_audio'])}[/bold] de áudio, "
        f"~{_hms(previsao['tempo_de_sintese'])} de síntese, "
        f"~{previsao['tamanho_m4b'] / 1e6:.0f} MB\n"
    )

    trilha = _rodar_sintese(
        livro, destino, motor, voz, velocidade,
        formato=formato, pausas=pausas, threads=threads,
    )
    caminho_trilha = destino.with_suffix(".trilha.json")
    trilha.salvar(caminho_trilha)
    livro.salvar(destino.with_suffix(".livro.json"))

    if por_capitulo:
        from audiolivro import montar

        fatias = [
            montar.Capitulo(t, i, prox)
            for (t, i), prox in zip(
                trilha.capitulos,
                [c[1] for c in trilha.capitulos[1:]] + [trilha.duracao],
            )
        ]
        pasta = destino.with_suffix("")
        arquivos = montar.dividir_por_capitulo(destino, fatias, pasta)
        console.print(f"[green]✓[/green] {len(arquivos)} capítulos em {pasta}/")

    console.print(f"\n[green]✓[/green] {destino}  ({_hms(trilha.duracao)})")
    console.print(f"[dim]  trilha: {caminho_trilha}[/dim]")


@app.command()
def capitulos(
    arquivo: Annotated[Path, typer.Argument(help="Livro ou .livro.json.")],
    ocr: OpOcr = "auto",
) -> None:
    """Mostra a estrutura que o extrator encontrou."""
    livro = _abrir(arquivo, ocr=ocr, notas=False)
    tabela = Table(title=livro.titulo)
    tabela.add_column("#", justify="right")
    tabela.add_column("Capítulo")
    tabela.add_column("Blocos", justify="right")
    tabela.add_column("Falas", justify="right")
    tabela.add_column("Duração", justify="right")
    for i, capitulo in enumerate(livro.capitulos, 1):
        segundos = capitulo.caracteres / 14.0
        tabela.add_row(
            str(i), capitulo.titulo[:60], str(len(capitulo.blocos)),
            str(len(capitulo.falas())), _hms(segundos),
        )
    console.print(tabela)


@app.command()
def ui(
    porta: Annotated[int, typer.Option("--porta", "-p")] = 8730,
    abrir_navegador: Annotated[bool, typer.Option("--abrir/--nao-abrir")] = True,
) -> None:
    """Abre a interface: subir o livro, conferir, sintetizar e ouvir.

    É o caminho completo sem passar pela linha de comando. O pulo do gato
    é o meio: entre abrir o arquivo e gerar duas horas de áudio, a tela
    mostra o que o extrator entendeu — e é ali que se percebe que faltou
    um capítulo, antes de gastar o tempo.
    """
    from audiolivro.ui.server import servir

    servir(None, porta=porta, abrir=abrir_navegador)


@app.command()
def player(
    arquivo: Annotated[Path, typer.Argument(help="O .m4b gerado, ou o .livro.json ao lado dele.")],
    porta: Annotated[int, typer.Option("--porta", "-p")] = 8730,
    abrir_navegador: Annotated[bool, typer.Option("--abrir/--nao-abrir")] = True,
) -> None:
    """Abre a interface já num audiobook pronto."""
    from audiolivro.ui.server import servir

    servir(Path(arquivo), porta=porta, abrir=abrir_navegador)


@app.command()
def ouvir(
    arquivo: Annotated[Path, typer.Argument(help="EPUB, PDF, TXT ou Markdown.")],
    motor: OpMotor = None,
    voz: OpVoz = None,
    velocidade: OpVelocidade = 1.0,
    ocr: OpOcr = "auto",
    notas: OpNotas = False,
    porta: Annotated[int, typer.Option("--porta", "-p")] = 8730,
) -> None:
    """Extrai, sintetiza e abre o player. O caminho completo, num comando."""
    destino = Path(arquivo).with_suffix(".m4b")
    if not destino.exists():
        gerar(arquivo, saida=destino, motor=motor, voz=voz,
              velocidade=velocidade, ocr=ocr, notas=notas)
    player(destino, porta=porta, abrir_navegador=True)


# -- apoio ---------------------------------------------------------------


def _extrair(arquivo: Path, *, ocr: str, notas: bool) -> Livro:
    with console.status(f"Lendo {arquivo.name}…"):
        try:
            return ingest.ler(arquivo, ocr=ocr, ler_notas=notas)
        except (ingest.FormatoDesconhecido, FileNotFoundError) as erro:
            console.print(f"[red]{erro}[/red]")
            raise typer.Exit(1) from erro


def _abrir(arquivo: Path, *, ocr: str, notas: bool) -> Livro:
    """Aceita tanto o arquivo original quanto um `.livro.json` já revisado."""
    arquivo = Path(arquivo)
    if arquivo.suffixes[-2:] == [".livro", ".json"]:
        return Livro.carregar(arquivo)
    if arquivo.suffix in (".m4b", ".m4a", ".mp3", ".wav"):
        vizinho = arquivo.with_suffix(".livro.json")
        if vizinho.exists():
            return Livro.carregar(vizinho)
    return _extrair(arquivo, ocr=ocr, notas=notas)


def _recortar(livro: Livro, pular: int, quantas: int) -> Livro:
    """Um `Livro` menor, com só um trecho — usado pela prévia."""
    from copy import deepcopy

    recorte = deepcopy(livro)
    restam = quantas
    saltar = pular
    for capitulo in recorte.capitulos:
        for bloco in capitulo.blocos:
            mantidas = []
            for fala in bloco.falas:
                if saltar > 0:
                    saltar -= 1
                elif restam > 0:
                    mantidas.append(fala)
                    restam -= 1
            bloco.falas = mantidas
        capitulo.blocos = [b for b in capitulo.blocos if b.falas]
    recorte.capitulos = [c for c in recorte.capitulos if c.blocos]
    return recorte


def _rodar_sintese(
    livro: Livro,
    destino: Path,
    motor: str | None,
    voz: str | None,
    velocidade: float,
    *,
    formato: str = "m4b",
    pausas: float = 1.0,
    threads: int | None = None,
) -> Trilha:
    with Progress(
        SpinnerColumn(), TextColumn("[bold]{task.description}"), BarColumn(),
        TaskProgressColumn(), TimeRemainingColumn(), console=console,
    ) as barra:
        tarefa = barra.add_task("sintetizando", total=len(livro.falas()))

        def progresso(estado: _sintetizar.Progresso) -> None:
            barra.update(tarefa, completed=estado.prontas, description=estado.fase)

        try:
            trilha = _sintetizar.sintetizar(
                livro, destino, motor=motor, voz=voz, velocidade=velocidade,
                formato=formato, escala_de_pausa=pausas, threads=threads,
                ao_progredir=progresso,
            )
        except MotorIndisponivel as erro:
            console.print(f"[red]{erro}[/red]")
            raise typer.Exit(1) from erro

    return trilha


def _resumo(livro: Livro) -> None:
    console.print(
        f"[bold]{livro.titulo}[/bold]"
        + (f" — {livro.autor}" if livro.autor else "")
    )
    console.print(
        f"{len(livro.capitulos)} capítulos · {len(livro.falas())} falas · "
        f"{livro.caracteres:,} caracteres".replace(",", ".")
    )


def _tocar(arquivo: Path) -> None:
    """Toca o arquivo no player padrão do sistema.

    A prévia existe para ser ouvida na hora; obrigar o usuário a achar o
    arquivo no disco anularia o propósito dela. Cada sistema tem seu
    comando, e nenhum deles é essencial: falhar aqui não pode derrubar o
    programa, então o caminho do arquivo é impresso de todo jeito.
    """
    comandos = {
        "darwin": ["afplay", str(arquivo)],
        "win32": ["cmd", "/c", "start", "", str(arquivo)],
    }
    comando = comandos.get(sys.platform, ["xdg-open", str(arquivo)])
    if not shutil.which(comando[0]):
        return
    try:
        subprocess.run(comando, check=False)
    except OSError:
        pass


def _hms(segundos: float) -> str:
    segundos = int(segundos)
    h, resto = divmod(segundos, 3600)
    m, s = divmod(resto, 60)
    return f"{h}h{m:02d}min" if h else (f"{m}min{s:02d}s" if m else f"{s}s")


if __name__ == "__main__":
    app()
