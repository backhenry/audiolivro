"""Escolha do motor de voz.

A ordem de preferência é **Piper, Kokoro, macOS**, e ela mudou depois de
um teste de escuta. O Kokoro tem a melhor prosódia dos três — variação de
entonação, ênfase, respiração — mas o modelo é treinado quase todo em
inglês e as três vozes portuguesas entraram com pouco dado: ele acerta os
fonemas do português e erra o timbre das vogais, o que soa levemente
americano. O Piper é o contrário: cada voz foi treinada só em português
brasileiro, então a prosódia é mais plana e a pronúncia é nossa.

Num leitor de livros em português, sotaque nativo pesa mais que prosódia:
o sotaque incomoda a cada frase, durante dez horas. Por isso o Piper vem
primeiro, mesmo sendo o modelo tecnicamente menor.

A escolha automática nunca *baixa* nada. Se um motor está instalado sem
os pesos, a autodetecção passa adiante em vez de disparar centenas de
megabytes que o usuário não pediu — baixar é sempre uma decisão
explícita, de quem escreveu `audiolivro baixar` ou `--motor kokoro`. É o
que permite `audiolivro ouvir livro.epub` funcionar na hora numa máquina
recém-formatada, com voz pior, em vez de travar antes da primeira
palavra.
"""

from __future__ import annotations

from audiolivro.voz import kokoro as _kokoro
from audiolivro.voz import macos as _macos
from audiolivro.voz import piper as _piper
from audiolivro.voz.base import Motor, MotorIndisponivel, Voz, aparar, normalizar_volume

__all__ = [
    "Motor", "MotorIndisponivel", "Voz", "aparar", "normalizar_volume",
    "abrir", "catalogo", "disponiveis", "melhor_motor", "MOTORES",
]

MOTORES = {
    "kokoro": (_kokoro.Kokoro, _kokoro.instalado, _kokoro.VOZ_PADRAO),
    "piper": (_piper.Piper, _piper.instalado, _piper.VOZ_PADRAO),
    "macos": (_macos.MacOS, _macos.instalado, _macos.VOZ_PADRAO),
}
PREFERENCIA = ("piper", "kokoro", "macos")


def disponiveis() -> list[str]:
    """Motores prontos para usar agora, sem baixar nada."""
    return [nome for nome in PREFERENCIA if MOTORES[nome][1]()]


def melhor_motor() -> str:
    prontos = disponiveis()
    if not prontos:
        raise MotorIndisponivel(
            "Nenhum motor de voz disponível.\n"
            "  pip install kokoro-onnx espeakng-loader   (melhor qualidade)\n"
            "  pip install piper-tts                     (mais leve)\n"
            "No macOS, o 'say' deveria estar sempre presente."
        )
    return prontos[0]


def abrir(motor: str | None = None, voz: str | None = None) -> tuple[Motor, str]:
    """Devolve (motor, voz) prontos.

    Aceita também a forma "motor:voz" em `motor`, que é como a `Trilha`
    grava a escolha — assim dá para re-sintetizar exatamente igual a
    partir do que ficou registrado.
    """
    if motor and ":" in motor:
        motor, _, voz_embutida = motor.partition(":")
        voz = voz or voz_embutida

    nome = motor or melhor_motor()
    if nome not in MOTORES:
        conhecidos = ", ".join(MOTORES)
        raise MotorIndisponivel(f"Motor '{nome}' não existe. Conhecidos: {conhecidos}")

    classe, _instalado, voz_padrao = MOTORES[nome]
    instancia = classe()
    escolhida = voz or voz_padrao

    validas = {v.id for v in instancia.vozes()}
    if validas and escolhida not in validas:
        raise MotorIndisponivel(
            f"'{escolhida}' não é voz do motor {nome}.\n"
            f"Disponíveis: {', '.join(sorted(validas))}"
        )
    return instancia, escolhida


def catalogo() -> list[Voz]:
    """Todas as vozes pt-BR dos motores prontos para usar."""
    achadas: list[Voz] = []
    for nome in disponiveis():
        classe, _instalado, _padrao = MOTORES[nome]
        try:
            achadas.extend(classe().vozes())
        except MotorIndisponivel:
            continue
    return achadas
