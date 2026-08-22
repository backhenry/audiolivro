"""OCR pelo Vision, o motor de reconhecimento do próprio macOS.

O caminho óbvio seria o Tesseract, mas ele exige `brew install`, um pacote
de idioma à parte para o português, e entrega qualidade pior em página
escaneada torta. O Vision já está instalado — é o que reconhece texto
numa foto no app Fotos — fala pt-BR, corrige com modelo de linguagem, e
não custa nada em disco.

O preço é falar Objective-C via pyobjc. As três esquisitices que importam:

* Os métodos viram `nomeComDoisPontos_virando_underline_`.
* O `boundingBox` vem normalizado (0–1) e com origem embaixo à esquerda,
  ao contrário de todo o resto do código, que usa pontos com origem em
  cima. A conversão acontece aqui e não vaza.
* `performRequests_error_` devolve `(sucesso, erro)` em vez de levantar.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from statistics import median

IDIOMAS_PADRAO = ("pt-BR", "en-US")


@dataclass
class LinhaOCR:
    texto: str
    confianca: float
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def altura(self) -> float:
        return self.y1 - self.y0


class OCRIndisponivel(RuntimeError):
    """O Vision não pôde ser carregado (pyobjc ausente ou macOS antigo)."""


@cache
def disponivel() -> bool:
    try:
        import Quartz  # noqa: F401
        import Vision  # noqa: F401
    except ImportError:
        return False
    return True


@cache
def idiomas_suportados() -> tuple[str, ...]:
    if not disponivel():
        return ()
    import Vision

    req = Vision.VNRecognizeTextRequest.alloc().init()
    langs, _erro = req.supportedRecognitionLanguagesAndReturnError_(None)
    return tuple(langs or ())


def reconhecer(
    png: bytes,
    largura: float,
    altura: float,
    *,
    idiomas: tuple[str, ...] = IDIOMAS_PADRAO,
    rapido: bool = False,
) -> list[LinhaOCR]:
    """Reconhece o texto de uma página já rasterizada.

    `largura` e `altura` são as da página em pontos, não em pixels: as
    coordenadas devolvidas ficam no mesmo sistema do resto do extrator de
    PDF, e o chamador não precisa saber em que resolução rasterizamos.
    """
    if not disponivel():
        raise OCRIndisponivel(
            "OCR precisa do Vision. Instale com:\n"
            "  pip install pyobjc-framework-Vision pyobjc-framework-Quartz"
        )

    import Quartz
    import Vision
    from Foundation import NSData

    dados = NSData.dataWithBytes_length_(png, len(png))
    fonte = Quartz.CGImageSourceCreateWithData(dados, None)
    if fonte is None:
        return []
    imagem = Quartz.CGImageSourceCreateImageAtIndex(fonte, 0, None)
    if imagem is None:
        return []

    pedido = Vision.VNRecognizeTextRequest.alloc().init()
    pedido.setRecognitionLevel_(1 if rapido else 0)  # 0 = accurate
    pedido.setUsesLanguageCorrection_(True)
    disponiveis = idiomas_suportados()
    pedido.setRecognitionLanguages_(
        [i for i in idiomas if i in disponiveis] or list(idiomas)
    )

    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(
        imagem, None
    )
    ok, erro = handler.performRequests_error_([pedido], None)
    if not ok:
        raise OCRIndisponivel(f"Vision falhou: {erro}")

    linhas: list[LinhaOCR] = []
    for obs in pedido.results() or []:
        candidatos = obs.topCandidates_(1)
        if not candidatos:
            continue
        texto = candidatos[0].string()
        if not texto or not texto.strip():
            continue
        caixa = obs.boundingBox()
        x = caixa.origin.x * largura
        # O Vision conta o y de baixo para cima; o PDF, de cima para
        # baixo. Sem esta inversão as linhas saem na ordem trocada.
        y = (1.0 - caixa.origin.y - caixa.size.height) * altura
        linhas.append(
            LinhaOCR(
                texto=texto.strip(),
                confianca=float(candidatos[0].confidence()),
                x0=x,
                y0=y,
                x1=x + caixa.size.width * largura,
                y1=y + caixa.size.height * altura,
            )
        )

    # O Vision devolve por ordem de confiança, não de leitura. Para
    # ordenar por linha é preciso agrupar os `y` próximos, e a régua desse
    # agrupamento tem que ser *uma só* para a página inteira: dividindo o
    # y pela altura de cada linha, uma linha com acentos e outra sem caem
    # em réguas diferentes e a ordem sai embaralhada — frases de
    # parágrafos distintos acabam intercaladas.
    if linhas:
        regua = max(median([l.altura for l in linhas]) * 0.6, 1.0)
        linhas.sort(key=lambda l: (round(l.y0 / regua), l.x0))
    return linhas
