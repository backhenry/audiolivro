"""A montagem do M4B e o cache de síntese.

Dois pontos frágeis. O FFMETADATA tem sintaxe própria, e um título de
capítulo com "=" no meio corrompe o arquivo inteiro em silêncio. E a
chave do cache é o que decide se corrigir uma frase re-sintetiza duas
falas ou nove mil.
"""

from __future__ import annotations

import numpy as np
import pytest

from audiolivro.modelo import Fala
from audiolivro.montar import Capitulo, Escritor, escrever_metadados
from audiolivro.sintetizar import _chave
from audiolivro.voz.base import aparar, normalizar_volume


def test_metadados_escapam_a_sintaxe(tmp_path) -> None:
    capitulos = [Capitulo("Custo = 3; ver #4", 0.0, 12.5)]
    conteudo = escrever_metadados(
        capitulos, tmp_path / "m.txt", titulo="A; B", autor="C=D"
    ).read_text(encoding="utf-8")

    assert r"title=Custo \= 3\; ver \#4" in conteudo
    assert r"title=A\; B" in conteudo
    assert "START=0" in conteudo and "END=12500" in conteudo


def test_quebra_de_linha_no_titulo_nao_vira_diretiva(tmp_path) -> None:
    # Uma quebra dentro do valor faria o resto do título virar uma chave
    # nova do FFMETADATA — e o ffmpeg abortaria sem dizer por quê.
    conteudo = escrever_metadados(
        [Capitulo("Um\ntitle=falso", 0.0, 1.0)], tmp_path / "m.txt"
    ).read_text(encoding="utf-8")
    assert conteudo.count("title=") == 1


def test_escritor_produz_audio_com_a_duracao_pedida(tmp_path) -> None:
    destino = tmp_path / "saida.wav"
    taxa = 24_000
    with Escritor(destino, taxa, formato="wav") as escritor:
        escritor.escrever(np.zeros(taxa, dtype=np.float32))
        escritor.silencio(0.5)
        escritor.escrever(np.zeros(taxa // 2, dtype=np.float32))
        assert escritor.posicao == pytest.approx(2.0)

    import soundfile as sf

    amostras, lido = sf.read(destino)
    assert lido == taxa
    assert len(amostras) / lido == pytest.approx(2.0, abs=0.01)


def test_formato_desconhecido_falha_cedo(tmp_path) -> None:
    with pytest.raises(ValueError, match="ogg"):
        Escritor(tmp_path / "x.ogg", 24_000, formato="ogg")


# -- cache ---------------------------------------------------------------


def _fala(texto: str, id_: str = "c001-b0001-f0") -> Fala:
    return Fala(id=id_, texto=texto, exibicao=texto)


def test_frases_iguais_compartilham_o_audio() -> None:
    # "Ele não respondeu." aparece dezenas de vezes num romance.
    a = _chave(_fala("Ele não respondeu.", "c001-b0002-f0"), "kokoro", "pf_dora", 1.0)
    b = _chave(_fala("Ele não respondeu.", "c009-b0100-f3"), "kokoro", "pf_dora", 1.0)
    assert a == b


def test_inserir_paragrafo_no_comeco_nao_invalida_o_resto() -> None:
    # O id não entra na chave justamente por isso: renumerar tudo depois
    # de uma inserção jogaria fora horas de síntese.
    antes = _chave(_fala("Mesma frase.", "c001-b0001-f0"), "kokoro", "pf_dora", 1.0)
    depois = _chave(_fala("Mesma frase.", "c001-b0002-f0"), "kokoro", "pf_dora", 1.0)
    assert antes == depois


@pytest.mark.parametrize(
    "motor, voz, velocidade",
    [("piper", "pf_dora", 1.0), ("kokoro", "pm_alex", 1.0), ("kokoro", "pf_dora", 1.2)],
)
def test_trocar_motor_voz_ou_velocidade_muda_a_chave(motor, voz, velocidade) -> None:
    base = _chave(_fala("Uma frase."), "kokoro", "pf_dora", 1.0)
    assert _chave(_fala("Uma frase."), motor, voz, velocidade) != base


# -- tratamento das amostras ---------------------------------------------


def test_aparar_tira_o_silencio_das_pontas() -> None:
    """Sem isto, a pausa real é a pedida mais o que o motor resolveu dar.

    Como o silêncio que cada motor deixa varia com o texto, o ritmo
    definido em `PAUSA` deixaria de valer e o capítulo soaria irregular.
    """
    taxa = 24_000
    som = np.concatenate([
        np.zeros(taxa, dtype=np.float32),
        np.full(taxa // 2, 0.5, dtype=np.float32),
        np.zeros(taxa, dtype=np.float32),
    ])
    aparado = aparar(som, taxa)
    # Meio segundo de som, mais a margem de 15 ms de cada lado.
    assert len(aparado) / taxa == pytest.approx(0.53, abs=0.02)


def test_aparar_aguenta_silencio_total() -> None:
    assert aparar(np.zeros(1000, dtype=np.float32), 24_000).size == 0


def test_volume_e_igualado_entre_falas() -> None:
    baixa = normalizar_volume(np.full(100, 0.1, dtype=np.float32))
    alta = normalizar_volume(np.full(100, 0.9, dtype=np.float32))
    assert float(np.max(baixa)) == pytest.approx(float(np.max(alta)), abs=1e-6)
