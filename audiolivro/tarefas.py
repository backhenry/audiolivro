"""Trabalhos em segundo plano com progresso observável.

Sintetizar um livro leva de minutos a horas e não pode bloquear o
servidor: se bloqueasse, a interface congelaria justamente enquanto o
usuário mais quer ver o que está acontecendo.

O progresso é lido por **sondagem do estado**, não por fila de eventos.
Com fila, um cliente que recarrega a página perde tudo que passou;
lendo o estado, ele reconecta e vê a situação atual — que é o que
importa quando se volta para uma síntese que começou há uma hora.
"""

from __future__ import annotations

import threading
import traceback
import uuid
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Literal

from audiolivro.ffmpeg import FFmpegCancelado

Situacao = Literal["na_fila", "rodando", "concluido", "erro", "cancelado"]


@dataclass
class Tarefa:
    id: str
    tipo: str
    situacao: Situacao = "na_fila"
    progresso: float = 0.0
    mensagem: str = ""
    resultado: Any = None
    erro: str = ""
    _desistir: threading.Event = field(default_factory=threading.Event, repr=False)

    @property
    def cancelada(self) -> bool:
        return self._desistir.is_set()

    def instantaneo(self) -> dict:
        return {
            "id": self.id,
            "tipo": self.tipo,
            "situacao": self.situacao,
            "progresso": round(self.progresso, 4),
            "mensagem": self.mensagem,
            "erro": self.erro,
        }


class TarefaCancelada(RuntimeError):
    """Levantada de dentro do trabalho quando o usuário desiste."""


@dataclass
class Controle:
    """O que a função em execução usa para reportar e checar desistência."""

    tarefa: Tarefa

    def progresso(self, fracao: float, mensagem: str | None = None) -> None:
        # Toda atualização checa a desistência: assim qualquer etapa que
        # reporte progresso vira automaticamente um ponto de parada, sem
        # precisar espalhar verificações pelo código da síntese.
        if self.tarefa.cancelada:
            raise TarefaCancelada
        self.tarefa.progresso = max(0.0, min(1.0, fracao))
        if mensagem is not None:
            self.tarefa.mensagem = mensagem

    def passo(self, mensagem: str) -> None:
        self.progresso(self.tarefa.progresso, mensagem)


class Executor:
    """Executor com poucas threads e histórico dos trabalhos."""

    def __init__(self, trabalhadores: int = 1) -> None:
        # Uma thread por padrão: a síntese já usa todos os núcleos, e dois
        # livros ao mesmo tempo deixariam os dois mais lentos enquanto o
        # progresso mentiria sobre quanto falta em cada um.
        self._piscina = ThreadPoolExecutor(max_workers=trabalhadores)
        self._tarefas: dict[str, Tarefa] = {}
        self._futuros: dict[str, Future] = {}
        self._trava = threading.Lock()

    def enviar(self, tipo: str, trabalho: Callable[[Controle], Any]) -> Tarefa:
        tarefa = Tarefa(id=uuid.uuid4().hex[:12], tipo=tipo, mensagem="na fila")
        with self._trava:
            self._tarefas[tarefa.id] = tarefa
            self._futuros[tarefa.id] = self._piscina.submit(
                self._rodar, tarefa, trabalho
            )
        return tarefa

    def _rodar(self, tarefa: Tarefa, trabalho: Callable[[Controle], Any]) -> None:
        tarefa.situacao = "rodando"
        tarefa.mensagem = "iniciando"
        try:
            tarefa.resultado = trabalho(Controle(tarefa))
            tarefa.situacao = "concluido"
            tarefa.progresso = 1.0
            tarefa.mensagem = "concluído"
        except (TarefaCancelada, FFmpegCancelado):
            # O ffmpeg encerrado a pedido também é desistência, não falha:
            # mostrar "erro" depois de clicar em Cancelar seria mentira.
            tarefa.situacao = "cancelado"
            tarefa.mensagem = "cancelado"
        except Exception as erro:
            tarefa.situacao = "erro"
            tarefa.erro = str(erro) or erro.__class__.__name__
            tarefa.mensagem = "falhou"
            traceback.print_exc()

    def buscar(self, tarefa_id: str) -> Tarefa | None:
        with self._trava:
            return self._tarefas.get(tarefa_id)

    def cancelar(self, tarefa_id: str) -> bool:
        tarefa = self.buscar(tarefa_id)
        if tarefa is None or tarefa.situacao in ("concluido", "erro", "cancelado"):
            return False
        tarefa._desistir.set()
        return True

    def encerrar(self) -> None:
        for tarefa in list(self._tarefas.values()):
            tarefa._desistir.set()
        self._piscina.shutdown(wait=False, cancel_futures=True)
