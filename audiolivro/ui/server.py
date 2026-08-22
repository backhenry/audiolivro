"""Servidor local da interface.

Um aplicativo de mesa que por acaso fala HTTP: um projeto aberto por
vez, sem sessão e sem autenticação, ouvindo só em 127.0.0.1. Sessão,
login e isolamento por usuário só acrescentariam complexidade sem
resolver problema nenhum aqui.

A interface cobre o caminho inteiro — subir o arquivo, ver o que o
extrator entendeu, escolher a voz, sintetizar e ouvir. O meio desse
caminho é o que justifica ela existir: entre "abri o EPUB" e "gerei duas
horas de áudio" há uma decisão que só quem olha o texto pode tomar, e a
linha de comando obriga a tomá-la às cegas.

Duas regras de estado que valem explicar, porque as duas foram erradas na
primeira versão:

**A tela inicial é sempre a lista de projetos.** Antes, o servidor
guardava "o livro aberto" e a interface entrava direto nele — abrir a
interface de manhã caía no último livro testado ontem, sem lista e sem
saída óbvia. Agora entrar num projeto é sempre um clique explícito.

**A exceção é a síntese em andamento.** Aí sim a interface volta para a
tela de progresso: é a única situação em que o usuário quer ser levado
de volta a algo, porque há trabalho acontecendo que ele não pode perder
de vista.
"""

from __future__ import annotations

import mimetypes
import shutil
import subprocess
import sys
import threading
from pathlib import Path

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from audiolivro import ingest, projeto as _projeto, sintetizar as _sintetizar
from audiolivro.projeto import Projeto, ProjetoInvalido
from audiolivro.voz import catalogo, disponiveis
from audiolivro.tarefas import Controle, Executor, Tarefa

ESTATICO = Path(__file__).parent / "estatico"

TIPOS = {".m4b": "audio/mp4", ".m4a": "audio/mp4", ".mp3": "audio/mpeg", ".wav": "audio/wav"}

# Limite de upload. Um PDF escaneado de 800 páginas passa dos 300 MB;
# acima de meio giga é quase certo que o arquivo não é um livro.
LIMITE_UPLOAD = 512 * 1024 * 1024


class Estado:
    """O que o servidor guarda entre requisições."""

    def __init__(self) -> None:
        self.atual: Projeto | None = None
        # Uma thread só: a síntese já ocupa todos os núcleos, e dois
        # livros ao mesmo tempo deixariam os dois mais lentos enquanto o
        # progresso mentiria sobre quanto falta em cada um.
        self.executor = Executor(trabalhadores=1)
        self.tarefa: Tarefa | None = None
        self.projeto_do_job: str = ""
        self.trava = threading.Lock()

    def exigir(self) -> Projeto:
        if self.atual is None:
            raise HTTPException(400, "Nenhum projeto aberto.")
        return self.atual

    def com_audio(self) -> Projeto:
        projeto = self.exigir()
        if projeto.audio() is None:
            raise HTTPException(400, "Este projeto ainda não foi sintetizado.")
        return projeto

    def adotar(self, projeto: Projeto) -> Projeto:
        with self.trava:
            self.atual = projeto
        return projeto

    @property
    def sintetizando(self) -> bool:
        return self.tarefa is not None and self.tarefa.situacao in ("na_fila", "rodando")


def criar_app(estado: Estado | None = None) -> FastAPI:
    estado = estado or Estado()
    app = FastAPI(title="audiolivro", docs_url=None, redoc_url=None)

    # -- páginas ---------------------------------------------------------

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(ESTATICO / "index.html")

    @app.get("/app.js")
    def script() -> FileResponse:
        return FileResponse(ESTATICO / "app.js", media_type="text/javascript")

    @app.get("/estilo.css")
    def estilo() -> FileResponse:
        return FileResponse(ESTATICO / "estilo.css", media_type="text/css")

    # -- estado e projetos -----------------------------------------------

    @app.get("/api/estado")
    def ler_estado() -> JSONResponse:
        """O que a interface precisa saber ao abrir.

        `retomar` é o único caminho para entrar num projeto sem clique: só
        existe enquanto há síntese em andamento.
        """
        return JSONResponse({
            "projetos": [p.resumo() for p in _projeto.listar()],
            "retomar": estado.projeto_do_job if estado.sintetizando else None,
            "job": estado.tarefa.instantaneo() if estado.sintetizando else None,
            "motores": disponiveis(),
            "vozes": [
                {
                    "id": v.id, "nome": v.nome, "motor": v.motor,
                    "genero": v.genero,
                    # pt-PT entra na lista, mas com o idioma à vista:
                    # "Joana" no meio das brasileiras parece uma delas, e a
                    # diferença de sotaque só apareceria depois de
                    # sintetizar o livro inteiro.
                    "idioma": "" if v.idioma == "pt-BR" else v.idioma,
                }
                for v in catalogo()
                if v.idioma.startswith("pt")
            ],
            "biblioteca": str(_projeto.BIBLIOTECA),
            "formatos": sorted(ingest.FORMATOS),
            # Botões que só existem em alguns sistemas. Melhor a interface
            # não os mostrar do que mostrá-los sem fazer nada ao clicar.
            "seletor_nativo": bool(shutil.which("osascript")),
            "revelar": sys.platform in ("darwin", "win32") or bool(shutil.which("xdg-open")),
            "ocr": _ocr_disponivel(),
        })

    @app.post("/api/projetos/abrir")
    def abrir_projeto(dados: dict = Body(...)) -> JSONResponse:
        projeto = estado.adotar(_carregar(dados.get("nome", "")))
        return JSONResponse(_detalhe(projeto))

    @app.post("/api/projetos/apagar")
    def apagar_projeto(dados: dict = Body(...)) -> JSONResponse:
        nome = dados.get("nome", "")
        if estado.sintetizando and estado.projeto_do_job == nome:
            raise HTTPException(409, "Este projeto está sendo sintetizado agora.")
        try:
            _projeto.apagar(nome)
        except ProjetoInvalido as erro:
            raise HTTPException(404, str(erro)) from erro
        with estado.trava:
            if estado.atual is not None and estado.atual.nome == nome:
                estado.atual = None
        return JSONResponse({"apagado": nome})

    @app.post("/api/projetos/apagar-audio")
    def apagar_audio(dados: dict = Body(...)) -> JSONResponse:
        """Joga fora o áudio e o cache, mantém o texto revisado."""
        nome = dados.get("nome", "")
        if estado.sintetizando and estado.projeto_do_job == nome:
            raise HTTPException(409, "Este projeto está sendo sintetizado agora.")
        projeto = _carregar(nome)
        projeto.apagar_audio()
        if estado.atual is not None and estado.atual.nome == nome:
            estado.adotar(projeto)
        return JSONResponse(_detalhe(projeto))

    @app.post("/api/projetos/reextrair")
    def reextrair(dados: dict = Body(...)) -> JSONResponse:
        """Relê o arquivo original e substitui o texto do projeto.

        Reenviar o mesmo livro cai no projeto existente de propósito, para
        não perder as correções feitas nele. O efeito colateral é que uma
        melhoria no extrator nunca alcança um projeto antigo. Esta é a
        saída — e ela avisa, porque joga fora as correções manuais.
        """
        nome = dados.get("nome", "")
        if estado.sintetizando and estado.projeto_do_job == nome:
            raise HTTPException(409, "Este projeto está sendo sintetizado agora.")

        projeto = _carregar(nome)
        origem = projeto.original()
        if origem is None:
            raise HTTPException(
                400,
                "Este projeto não guardou o arquivo original, então não há "
                "de onde reextrair. Suba o livro de novo como projeto novo.",
            )

        try:
            livro = ingest.ler(
                origem,
                ocr=dados.get("ocr", "auto"),
                ler_notas=bool(dados.get("notas", False)),
            )
        except Exception as erro:
            raise HTTPException(400, f"Não consegui reler o original: {erro}") from erro
        if not livro.falas():
            raise HTTPException(400, "A releitura não achou texto nenhum.")

        # O título vem do arquivo e pode ter mudado com o extrator novo,
        # mas a pasta não é renomeada: o nome dela é a identidade do
        # projeto, e trocá-la quebraria o marcador e as exportações.
        projeto.livro = livro
        projeto.gravar_livro()
        estado.adotar(projeto)
        return JSONResponse(_detalhe(projeto))

    @app.post("/api/fechar")
    def fechar() -> JSONResponse:
        with estado.trava:
            estado.atual = None
        return JSONResponse({"ok": True})

    # -- criar projeto ---------------------------------------------------

    @app.post("/api/procurar")
    def procurar() -> JSONResponse:
        """Diálogo nativo do macOS, para quem prefere navegar até a pasta."""
        caminho = _escolher_arquivo()
        if caminho is None:
            return JSONResponse({"cancelado": True})
        return JSONResponse({"caminho": caminho})

    @app.post("/api/enviar")
    async def enviar(
        arquivo: UploadFile = File(...),
        ocr: str = Form("auto"),
        notas: bool = Form(False),
    ) -> JSONResponse:
        """Recebe o arquivo arrastado para a janela e cria o projeto."""
        nome = Path(arquivo.filename or "livro").name
        if Path(nome).suffix.lower() not in ingest.FORMATOS:
            aceitos = ", ".join(sorted(ingest.FORMATOS))
            raise HTTPException(400, f"Não sei ler '{nome}'. Aceito: {aceitos}")

        # O upload vai para uma área temporária: só depois de extrair com
        # sucesso é que sabemos o título, e é o título que dá nome à pasta
        # do projeto. Falhando a extração, nada fica para trás.
        temporaria = _projeto.BIBLIOTECA / ".entrada"
        temporaria.mkdir(parents=True, exist_ok=True)
        bruto = temporaria / nome
        try:
            await _gravar(arquivo, bruto)
            resposta = _novo_projeto(estado, bruto, ocr=ocr, notas=notas)
        finally:
            await arquivo.close()
            bruto.unlink(missing_ok=True)
        return JSONResponse(resposta)

    @app.post("/api/abrir")
    def abrir(dados: dict = Body(...)) -> JSONResponse:
        """Cria um projeto a partir de um arquivo que já está no disco."""
        bruto = (dados.get("caminho") or "").strip()
        if not bruto:
            raise HTTPException(400, "Informe o caminho do livro.")
        caminho = Path(bruto).expanduser()
        if not caminho.exists():
            raise HTTPException(404, f"Arquivo não encontrado: {caminho}")

        return JSONResponse(_novo_projeto(
            estado, caminho,
            ocr=dados.get("ocr", "auto"),
            notas=bool(dados.get("notas", False)),
        ))

    # -- sintetizar ------------------------------------------------------

    @app.post("/api/sintetizar")
    def sintetizar(dados: dict = Body(...)) -> JSONResponse:
        if estado.sintetizando:
            raise HTTPException(409, "Já há uma síntese em andamento.")

        projeto = estado.exigir()
        formato = dados.get("formato", "m4b")
        destino = projeto.pasta / f"audio.{formato}"

        def trabalho(controle: Controle) -> dict:
            def progresso(p: _sintetizar.Progresso) -> None:
                # `controle.progresso` também é o ponto de desistência: ele
                # levanta se o usuário cancelou, então cada fala pronta
                # vira automaticamente uma chance de parar.
                controle.progresso(
                    p.fracao,
                    f"{p.fase} · {p.prontas} de {p.total} falas"
                    + (f" ({p.do_cache} do cache)" if p.do_cache else ""),
                )

            # Trocar de formato deixaria o áudio antigo para trás, e o
            # projeto ficaria com dois arquivos e uma trilha apontando
            # para um deles.
            for antigo in _projeto.AUDIOS:
                if antigo != destino.name:
                    (projeto.pasta / antigo).unlink(missing_ok=True)

            trilha = _sintetizar.sintetizar(
                projeto.livro, destino,
                motor=dados.get("motor") or None,
                voz=dados.get("voz") or None,
                velocidade=float(dados.get("velocidade", 1.0)),
                formato=formato,
                escala_de_pausa=float(dados.get("pausas", 1.0)),
                cache=projeto.cache,
                ao_progredir=progresso,
                deve_parar=lambda: controle.tarefa.cancelada,
            )
            projeto.gravar_trilha(trilha)
            projeto.gravar_livro()
            return {"duracao": trilha.duracao}

        tarefa = estado.executor.enviar("sintetizar", trabalho)
        estado.tarefa = tarefa
        estado.projeto_do_job = projeto.nome
        return JSONResponse(tarefa.instantaneo())

    @app.get("/api/tarefa/{tarefa_id}")
    def ver_tarefa(tarefa_id: str) -> JSONResponse:
        tarefa = estado.executor.buscar(tarefa_id)
        if tarefa is None:
            raise HTTPException(404, "Tarefa desconhecida.")
        instantaneo = tarefa.instantaneo()
        if tarefa.situacao == "concluido":
            instantaneo["resultado"] = tarefa.resultado
        return JSONResponse(instantaneo)

    @app.post("/api/tarefa/{tarefa_id}/cancelar")
    def cancelar(tarefa_id: str) -> JSONResponse:
        return JSONResponse({"cancelado": estado.executor.cancelar(tarefa_id)})

    # -- editar ----------------------------------------------------------

    @app.post("/api/fala")
    def corrigir_fala(dados: dict = Body(...)) -> JSONResponse:
        """Reescreve o texto de uma fala, ou tira ela do áudio.

        É a razão de o player mostrar o texto. Ouvir um nome próprio
        pronunciado errado e consertar ali mesmo; ou ouvir a ficha
        catalográfica sendo lida e mandar pular. Como o cache é por
        conteúdo, a próxima geração refaz só o que mudou.
        """
        projeto = estado.exigir()
        alvo = str(dados.get("id", ""))

        for fala in projeto.livro.falas():
            if fala.id != alvo:
                continue
            if "texto" in dados:
                texto = str(dados["texto"]).strip()
                if not texto:
                    raise HTTPException(400, "O texto não pode ficar vazio.")
                fala.texto = texto
            if "ler" in dados:
                fala.ler = bool(dados["ler"])
            projeto.gravar_livro()
            return JSONResponse({"id": alvo, "texto": fala.texto, "ler": fala.ler})
        raise HTTPException(404, f"Fala {alvo} não existe.")

    @app.post("/api/trecho")
    def marcar_trecho(dados: dict = Body(...)) -> JSONResponse:
        """Liga ou desliga a leitura de um bloco ou de um capítulo inteiro.

        Existe porque o que se quer tirar quase nunca é uma frase: é a
        página de créditos, o índice remissivo, a bibliografia. Marcar
        frase por frase um índice de trinta páginas não é uma opção.
        """
        projeto = estado.exigir()
        alvo = str(dados.get("id", ""))
        ler = bool(dados.get("ler", True))

        atingidas = 0
        for capitulo in projeto.livro.capitulos:
            for bloco in capitulo.blocos:
                if alvo in (capitulo.id, bloco.id):
                    for fala in bloco.falas:
                        fala.ler = ler
                        atingidas += 1
        if not atingidas:
            raise HTTPException(404, f"Não achei o trecho {alvo}.")

        projeto.gravar_livro()
        return JSONResponse({"id": alvo, "ler": ler, "falas": atingidas})

    @app.post("/api/exportar")
    def exportar(dados: dict = Body(...)) -> JSONResponse:
        """Prepara o arquivo para download e devolve o nome dele.

        Vai para uma tarefa porque recodificar dez horas de áudio leva
        dezenas de segundos, e a interface precisa continuar respondendo —
        e mostrando progresso — enquanto isso.
        """
        if estado.sintetizando:
            raise HTTPException(409, "Espere a síntese em andamento terminar.")
        projeto = estado.com_audio()
        formato = dados.get("formato", "mp3")
        if formato not in ("mp3", "m4b", "m4a", "wav"):
            raise HTTPException(400, f"Formato '{formato}' não é aceito.")
        por_capitulo = bool(dados.get("por_capitulo", False))

        def trabalho(controle: Controle) -> dict:
            controle.progresso(
                0.1,
                "separando os capítulos…" if por_capitulo else f"convertendo para {formato}…",
            )
            arquivo = projeto.exportar(formato, por_capitulo=por_capitulo)
            controle.progresso(1.0, "pronto")
            return {"arquivo": arquivo.name, "bytes": arquivo.stat().st_size}

        tarefa = estado.executor.enviar("exportar", trabalho)
        estado.tarefa = tarefa
        estado.projeto_do_job = projeto.nome
        return JSONResponse(tarefa.instantaneo())

    @app.get("/api/baixar")
    def baixar(arquivo: str) -> FileResponse:
        """Entrega o arquivo exportado, com nome de verdade.

        O `filename` é o que faz o navegador salvar como "O Nome da
        Rosa.mp3" em vez de "baixar". Sem ele, quem recebe o arquivo não
        sabe o que é.
        """
        projeto = estado.exigir()
        # O nome vem da resposta da exportação, mas chega pela URL: só
        # aceitamos um arquivo que esteja de fato na pasta de exportação.
        caminho = (projeto.pasta / _projeto.PASTA_EXPORT / Path(arquivo).name).resolve()
        esperada = (projeto.pasta / _projeto.PASTA_EXPORT).resolve()
        if caminho.parent != esperada or not caminho.is_file():
            raise HTTPException(404, "Arquivo exportado não encontrado.")
        return FileResponse(
            caminho, filename=caminho.name, media_type="application/octet-stream"
        )

    @app.post("/api/revelar")
    def revelar(dados: dict = Body(default={})) -> JSONResponse:
        nome = (dados or {}).get("nome")
        projeto = _carregar(nome) if nome else estado.exigir()
        alvo = projeto.audio() or projeto.pasta
        return JSONResponse({"ok": _revelar_no_sistema(alvo)})

    # -- ouvir -----------------------------------------------------------

    @app.get("/api/posicao")
    def ler_posicao() -> JSONResponse:
        return JSONResponse(estado.exigir().posicao())

    @app.post("/api/posicao")
    def gravar_posicao(dados: dict = Body(...)) -> JSONResponse:
        return JSONResponse(estado.com_audio().guardar_posicao(
            float(dados.get("segundo", 0.0)),
            float(dados.get("velocidade", 1.0)),
        ))

    @app.get("/audio")
    def audio() -> FileResponse:
        caminho = estado.com_audio().audio()
        # O FileResponse do Starlette responde a Range sozinho, e é disso
        # que depende arrastar a barra de um arquivo de 300 MB sem baixar
        # o livro inteiro antes.
        tipo = TIPOS.get(caminho.suffix) or mimetypes.guess_type(caminho.name)[0]
        return FileResponse(caminho, media_type=tipo or "application/octet-stream")

    @app.get("/api/texto")
    def texto() -> JSONResponse:
        """O livro achatado na ordem da trilha, pronto para desenhar.

        O navegador poderia montar isto a partir do `livro.json`, mas seria
        refazer em JavaScript o percurso capítulo→bloco→fala que o servidor
        já sabe fazer — e teria que repetir exatamente a mesma ordem, que é
        justamente onde um erro passaria despercebido.
        """
        projeto = estado.com_audio()
        por_fala = {m.fala: m for m in projeto.trilha.marcas}
        capitulos = []
        for capitulo in projeto.livro.capitulos:
            blocos = []
            for bloco in capitulo.blocos:
                falas = [
                    {
                        "id": f.id,
                        "texto": f.exibicao,
                        "falado": f.texto,
                        "ler": f.ler,
                        "inicio": por_fala[f.id].inicio if f.id in por_fala else None,
                        "fim": (por_fala[f.id].inicio + por_fala[f.id].duracao)
                               if f.id in por_fala else None,
                    }
                    for f in bloco.falas
                    # A fala excluída continua aparecendo, riscada: sumir
                    # com ela esconderia justamente o que se quer revisar.
                    if f.id in por_fala or not f.ler
                ]
                if falas:
                    blocos.append({"id": bloco.id, "tipo": bloco.tipo, "falas": falas})
            if blocos:
                # A primeira fala do capítulo pode estar excluída, e aí não
                # tem tempo nenhum. O início do capítulo é o da primeira
                # fala que sobrou; sem nenhuma, o capítulo é só texto na
                # tela e o sumário não pula para ele.
                inicios = [
                    f["inicio"] for b in blocos for f in b["falas"]
                    if f["inicio"] is not None
                ]
                capitulos.append({
                    "id": capitulo.id,
                    "titulo": capitulo.titulo,
                    "inicio": inicios[0] if inicios else None,
                    "blocos": blocos,
                })

        return JSONResponse({
            "titulo": projeto.livro.titulo,
            "autor": projeto.livro.autor,
            "duracao": projeto.trilha.duracao,
            "voz": f"{projeto.trilha.motor}:{projeto.trilha.voz}",
            "capitulos": capitulos,
        })

    return app


# -- apoio ---------------------------------------------------------------


def _ocr_disponivel() -> bool:
    from audiolivro.ingest.ocr import disponivel

    return disponivel()


def _carregar(nome: str) -> Projeto:
    try:
        return _projeto.carregar(nome)
    except ProjetoInvalido as erro:
        raise HTTPException(404, str(erro)) from erro


def _detalhe(projeto: Projeto) -> dict:
    """O projeto aberto, com a previsão de síntese junto."""
    motor = (disponiveis() or ["kokoro"])[0]
    return {
        **projeto.resumo(),
        "previsao": _sintetizar.prever(projeto.livro, motor),
        "estrutura": [
            {
                "id": c.id,
                "titulo": c.titulo,
                "falas": len(c.audiveis()),
                "total": len(c.falas()),
                "ler": bool(c.audiveis()),
                "duracao": c.caracteres / 14.0,
                "amostra": [f.texto for f in c.audiveis()[:3]] or [f.texto for f in c.falas()[:3]],
            }
            for c in projeto.livro.capitulos
        ],
    }


async def _gravar(arquivo: UploadFile, destino: Path) -> None:
    """Grava o upload em pedaços, com teto de tamanho.

    Ler `await arquivo.read()` de uma vez seria mais curto e poria um PDF
    de 300 MB inteiro na memória. E o teto é checado enquanto escreve, não
    pelo cabeçalho: `Content-Length` é informado pelo cliente e nada
    obriga a ser verdade.
    """
    total = 0
    parcial = destino.with_suffix(destino.suffix + ".part")
    try:
        with parcial.open("wb") as saida:
            while pedaco := await arquivo.read(1 << 20):
                total += len(pedaco)
                if total > LIMITE_UPLOAD:
                    raise HTTPException(
                        413, f"Arquivo maior que {LIMITE_UPLOAD // 1024 // 1024} MB."
                    )
                saida.write(pedaco)
        parcial.replace(destino)
    finally:
        parcial.unlink(missing_ok=True)


def _novo_projeto(estado: Estado, caminho: Path, *, ocr: str, notas: bool) -> dict:
    """Extrai o livro e abre (ou reencontra) o projeto dele.

    Síncrono de propósito. Extrair um EPUB leva um piscar de olhos; só o
    OCR demora, e mesmo ele fica na casa de um segundo por página. A
    interface mostra "lendo…" e espera, o que é mais simples e mais
    honesto que uma barra de progresso para uma etapa que quase sempre
    termina antes de aparecer.
    """
    try:
        livro = ingest.ler(caminho, ocr=ocr, ler_notas=notas)
    except (ingest.FormatoDesconhecido, FileNotFoundError) as erro:
        raise HTTPException(400, str(erro)) from erro
    except Exception as erro:
        raise HTTPException(400, f"Não consegui ler o livro: {erro}") from erro

    if not livro.falas():
        raise HTTPException(
            400,
            "O extrator não achou texto nenhum. Se for um PDF escaneado, "
            "marque a opção de OCR.",
        )

    # Reabrir o mesmo livro deve cair no projeto que já existe, com as
    # correções de texto que já foram feitas nele — e não criar uma cópia
    # que joga fora aquele trabalho.
    existente = _projeto.por_titulo(livro.titulo)
    if existente is not None:
        estado.adotar(existente)
        return {**_detalhe(existente), "reaproveitado": True}

    novo = _projeto.criar(livro, origem=caminho)
    estado.adotar(novo)
    return {**_detalhe(novo), "reaproveitado": False}


def _revelar_no_sistema(alvo: Path) -> bool:
    """Abre o gerenciador de arquivos com o alvo selecionado."""
    comandos = {
        "darwin": ["open", "-R", str(alvo)],
        "win32": ["explorer", f"/select,{alvo}"],
    }
    # No Linux não há como selecionar o arquivo de forma portátil, então
    # abrimos a pasta, que resolve o mesmo problema com um clique a mais.
    comando = comandos.get(sys.platform, ["xdg-open", str(alvo.parent)])
    if not shutil.which(comando[0]):
        return False
    try:
        subprocess.run(comando, check=False)
    except OSError:
        return False
    return True


def _escolher_arquivo() -> str | None:
    """Diálogo nativo de escolha de arquivo."""
    if not shutil.which("osascript"):
        return None
    tipos = ", ".join(f'"{ext.lstrip(".")}"' for ext in sorted(ingest.FORMATOS))
    script = (
        'tell application "System Events" to activate\n'
        f'set f to choose file with prompt "Escolha o livro" of type {{{tipos}}}\n'
        "POSIX path of f"
    )
    resultado = subprocess.run(
        ["osascript", "-e", script], capture_output=True, text=True
    )
    if resultado.returncode != 0:
        return None  # o usuário cancelou
    return resultado.stdout.strip() or None


def servir(
    caminho: Path | None = None, *, porta: int = 8730, abrir: bool = True
) -> None:
    """Sobe o servidor. Com `caminho`, já abre aquele projeto."""
    import webbrowser

    import uvicorn

    estado = Estado()
    if caminho is not None:
        estado.adotar(_projeto_de_caminho(Path(caminho)))
        print(f"audiolivro — {estado.exigir().livro.titulo}")
    else:
        print("audiolivro")

    endereco = f"http://127.0.0.1:{porta}"
    print(f"  {endereco}   (Ctrl-C para parar)")

    if abrir:
        threading.Timer(0.8, lambda: webbrowser.open(endereco)).start()
    try:
        uvicorn.run(criar_app(estado), host="127.0.0.1", port=porta, log_level="warning")
    finally:
        estado.executor.encerrar()


def _projeto_de_caminho(caminho: Path) -> Projeto:
    """Aceita a pasta do projeto ou qualquer arquivo dentro dela."""
    caminho = caminho.resolve()
    pasta = caminho if caminho.is_dir() else caminho.parent
    try:
        return _projeto.carregar(pasta.name)
    except ProjetoInvalido as erro:
        raise SystemExit(
            f"{caminho} não é um projeto do audiolivro.\n"
            f"Os projetos ficam em {_projeto.BIBLIOTECA}. Use 'audiolivro ui' para ver a lista."
        ) from erro
