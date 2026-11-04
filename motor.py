"""O relógio do mundo: junta as mensagens da turma e, de tempos em tempos,
roda uma rodada (uma chamada ao Gemini para todos os Sims).

Não conhece o Telegram: bot.py chama `receber()` e `talvez_rodar()`.
"""
import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from cerebro import ConteudoBloqueado, ErroCerebro, LimiteAtingido
from gerador import ErroGerador
from mundo import Mundo, escrever_json, ler_json

log = logging.getLogger("motor")

# A cota diária do Gemini zera à meia-noite do horário do Pacífico.
FUSO_COTA = ZoneInfo("America/Los_Angeles")


@dataclass
class Mensagem:
    de: str     # primeiro nome de quem mandou
    sim: str    # nome do Sim destinatário
    texto: str


class Motor:
    def __init__(self, mundo: Mundo, cerebro, *, ocioso_s: float, limite_diario: int):
        self.mundo = mundo
        self.cerebro = cerebro
        self.ocioso_s = ocioso_s
        self.limite_diario = limite_diario
        self.pendentes: list[Mensagem] = []
        self._lock = asyncio.Lock()
        self._ultima = time.monotonic()  # não roda "ocioso" logo ao ligar
        self._pausa_ate = 0.0
        self._arq_cota = mundo.dados / "cota.json"
        self._avisou_cota = False
        self.gerando = False  # True enquanto uma casa nova está sendo gerada
        # A segunda chance do cérebro também gasta uma chamada da cota.
        cerebro.ao_chamar_de_novo = self._gastar_chamada

    # ---------- entrada ----------

    def receber(self, de: str, sim: str, texto: str) -> None:
        self.pendentes.append(Mensagem(de, sim, texto))
        self.mundo.registrar("mensagem", de=de, sim=sim, texto=texto)

    # ---------- cota diária (guardada em disco, sobrevive a reinícios) ----------

    def _cota(self) -> dict:
        hoje = datetime.now(FUSO_COTA).date().isoformat()
        cota = ler_json(self._arq_cota, {})
        if cota.get("dia") != hoje:
            cota = {"dia": hoje, "chamadas": 0}
        return cota

    def chamadas_restantes(self) -> int:
        return max(0, self.limite_diario - self._cota()["chamadas"])

    def _gastar_chamada(self) -> None:
        cota = self._cota()
        cota["chamadas"] += 1
        escrever_json(self._arq_cota, cota)

    # ---------- casa nova ----------

    async def nova_casa(self, gerador, descricao: str) -> list[dict]:
        """Pede à IA uma casa nova (até 2 tentativas) e muda todo mundo para ela."""
        # Checado antes de qualquer await: dois /gerar seguidos não rodam juntos.
        if self.gerando:
            raise ErroCerebro("já tem uma casa sendo gerada, espere ela chegar")
        self.gerando = True
        try:
            return await self._nova_casa(gerador, descricao)
        finally:
            self.gerando = False

    async def _nova_casa(self, gerador, descricao: str) -> list[dict]:
        async with self._lock:
            erro = None
            for _ in range(2):
                if self.chamadas_restantes() <= 0:
                    raise ErroCerebro("limite diário de chamadas atingido")
                self._gastar_chamada()
                try:
                    fichas = await gerador.gerar(descricao)
                    break
                except ErroGerador as e:
                    log.warning("Casa descartada: %s", e)
                    erro = e
            else:
                raise erro
            self.pendentes.clear()
            self.mundo.trocar_casa(fichas)
            self._ultima = time.monotonic()
            return fichas

    # ---------- a rodada ----------

    async def talvez_rodar(self):
        """Roda uma rodada se houver mensagem nova, ou se os Sims estão
        parados há `ocioso_s` segundos. Devolve as decisões, ou None."""
        async with self._lock:
            agora = time.monotonic()
            if not self.mundo.sims:
                self.pendentes.clear()
                return None
            if agora < self._pausa_ate:
                return None
            ocioso = self.ocioso_s > 0 and agora - self._ultima >= self.ocioso_s
            if not self.pendentes and not ocioso:
                return None
            if self.chamadas_restantes() <= 0:
                if not self._avisou_cota:
                    log.warning("Limite diário de %d chamadas atingido.", self.limite_diario)
                    self._avisou_cota = True
                return None
            self._avisou_cota = False

            # As mensagens viram lembranças antes da chamada: se a IA falhar,
            # o Sim continua lembrando e reage na próxima rodada.
            lote, self.pendentes = self.pendentes, []
            for m in lote:
                self.mundo.lembrar(m.sim, f'{m.de} (pessoa de fora) me disse: "{m.texto}"', fonte="turma")

            self._gastar_chamada()
            try:
                decisoes = await self.cerebro.decidir(self.mundo)
            except LimiteAtingido as e:
                log.warning("%s", e)
                self._pausa_ate = agora + e.espera
                self.mundo.salvar()
                return None
            except ConteudoBloqueado as e:
                log.warning("%s: mensagens desta rodada descartadas.", e)
                self.mundo.esquecer_turma_da_rodada()
                self.mundo.registrar("bloqueada_pela_ia", mensagens=len(lote))
                self._ultima = agora
                self.mundo.salvar()
                return None
            except ErroCerebro as e:
                log.warning("Rodada perdida: %s", e)
                self.mundo.registrar("erro", erro=str(e))
                self._ultima = agora
                self.mundo.salvar()
                return None

            self._ultima = time.monotonic()
            self.mundo.aplicar(decisoes)
            log.info("Rodada %d: %d decisões, %d chamadas restantes hoje.",
                     self.mundo.rodada, len(decisoes), self.chamadas_restantes())
            return decisoes
