"""Despacho por formato: um arquivo entra, um `Livro` sai.

Este é o único ponto do pacote que sabe que existem quatro formatos. Do
`estrutura.montar` para a frente, um livro que veio de PDF escaneado é
indistinguível de um que veio de EPUB — e é isso que permite que a
síntese, o cache e o player não tenham um `if` sequer sobre formato.
"""

from __future__ import annotations

from pathlib import Path

from audiolivro.ingest import epub as _epub
from audiolivro.ingest import pdf as _pdf
from audiolivro.ingest import texto as _texto
from audiolivro.modelo import Livro
from audiolivro.texto.estrutura import montar, remover_capitulos_vazios

FORMATOS = {
    ".epub": "epub",
    ".pdf": "pdf",
    ".txt": "texto",
    ".text": "texto",
    ".md": "texto",
    ".markdown": "texto",
    ".mdown": "texto",
}


class FormatoDesconhecido(ValueError):
    pass


def ler(
    caminho: Path,
    *,
    ocr: str = "auto",
    ler_notas: bool = False,
    paginas: range | None = None,
    limpar_vazios: bool = True,
) -> Livro:
    """Lê `caminho` e devolve o `Livro` pronto para sintetizar."""
    caminho = Path(caminho)
    if not caminho.exists():
        raise FileNotFoundError(f"Não encontrei {caminho}")

    formato = FORMATOS.get(caminho.suffix.lower())
    if formato is None:
        conhecidos = ", ".join(sorted(FORMATOS))
        raise FormatoDesconhecido(
            f"Não sei ler '{caminho.suffix}'. Formatos aceitos: {conhecidos}"
        )

    if formato == "epub":
        meta, blocos = _epub.ler(caminho, ler_notas=ler_notas)
    elif formato == "pdf":
        meta, blocos = _pdf.ler(
            caminho, ocr=ocr, ler_notas=ler_notas, paginas=paginas
        )
    else:
        meta, blocos = _texto.ler(caminho)

    livro = montar(
        titulo=meta.get("titulo", caminho.stem),
        autor=meta.get("autor", ""),
        idioma=meta.get("idioma", "pt-BR"),
        origem=str(caminho),
        blocos=blocos,
        ler_notas=ler_notas,
    )
    return remover_capitulos_vazios(livro) if limpar_vazios else livro
