"""audiolivro — transforma um livro em algo que dá para ouvir.

O fluxo tem três estágios que não se conhecem:

    extrair       ->        decidir        ->      sintetizar
    (ingest/)              (Livro)                (voz/ + montar)
    lê o arquivo,       JSON com o texto        transforma decisão
    produz blocos       já normalizado e         em áudio e M4B
    brutos              fatiado em falas

O `Livro` no meio é o artefato de verdade. Ele é um JSON legível, então
dá para extrair uma vez e sintetizar várias, abrir o arquivo e corrigir
um nome próprio que a voz erra, ou trocar de motor sem reprocessar o PDF.

A parte difícil não é a voz — é chegar num texto que faça sentido lido em
voz alta. Um PDF entrega "Capítulo 3 42" no meio de uma frase porque o
rodapé virou linha; entrega "impres-\nsionante" quebrado na hifenização;
entrega "1.250" que o fonemizador lê como "um duzentos e cinquenta". Nada
disso aparece na tela, e todo isso aparece no ouvido. É por isso que
`texto/` é o maior subpacote daqui.
"""

__version__ = "0.1.0"
