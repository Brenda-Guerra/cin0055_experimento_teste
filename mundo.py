"""O estado do mundo: quem são os Sims, o que cada um lembra, e os arquivos
trocados com o mod do The Sims 4.

Nada aqui fala com o Telegram nem com o Gemini.
"""
import json
import os
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Ações que a IA pode escolher. Valor = precisa de um alvo (outro Sim)?
# O mod traduz cada nome destes para uma interação real do jogo.
ACOES = {
    "conversar": True,
    "elogiar": True,
    "discutir": True,
    "fofocar": True,
    "flertar": True,
    "abracar": True,
    "pedir_desculpas": True,
    "contar_piada": True,
    "ignorar": True,
    "usar_objeto": False,  # interação com um objeto do lote, escolhida do mapa (opcoes.json)
}
# Emoções que o mod consegue pôr no Sim (moodlet do jogo).
# chave -> (emoji, como aparece no diário)
EMOCOES = {
    "feliz": ("😄", "felicidade"),
    "triste": ("😢", "tristeza"),
    "irritado": ("😠", "raiva"),
    "tenso": ("😰", "tensão"),
    "envergonhado": ("😳", "vergonha"),
    "desconfortavel": ("😣", "desconforto"),
    "confiante": ("😎", "confiança"),
    "energizado": ("⚡", "energia"),
    "flertante": ("😏", "clima de flerte"),
    "focado": ("🎯", "foco"),
    "inspirado": ("💡", "inspiração"),
    "brincalhao": ("😜", "vontade de brincar"),
    "entediado": ("😑", "tédio"),
    "confuso": ("😵", "confusão"),
}

# Tons de conversa: o mod escolhe uma interação social do jogo desse tipo.
TONS = {
    "amigavel": "amigável",
    "maldoso": "maldoso",
    "travesso": "travesso",
    "engracado": "engraçado",
    "romantico": "romântico",
    "triste": "triste",
    "irritado": "irritado",
    "tenso": "tenso",
    "furioso": "furioso",  # o mais explosivo: gritar, jogar bebida, brigar, declarar inimizade
}
INTENSIDADES = {1: "", 2: "forte", 3: "muito forte"}
ACOES_COM_TOM = ("conversar", "discutir")

# "ficar_sozinho" saiu em 22/10: Sims ficavam parados várias rodadas seguidas.

# Como cada ação aparece no diário postado no grupo.
DESCRICOES = {
    "conversar": "foi conversar com {alvo}",
    "elogiar": "elogiou {alvo}",
    "discutir": "discutiu com {alvo}",
    "fofocar": "fofocou com {alvo}",
    "flertar": "flertou com {alvo}",
    "abracar": "abraçou {alvo}",
    "pedir_desculpas": "pediu desculpas a {alvo}",
    "contar_piada": "contou uma piada para {alvo}",
    "ignorar": "ignorou {alvo}",
    "ficar_sozinho": "ficou na sua",
    "usar_objeto": "foi fazer algo na casa ({alvo})",
}

def consertar_unicode(texto: str) -> str:
    """O Gemini às vezes devolve letras acentuadas como código: 'G#u00eamea' ou
    'G\\u00eamea' em vez de 'Gêmea'. Converte de volta (visto em 21/10)."""
    import re
    return re.sub(r"[#\\]u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), texto or "")


MAX_ACOES_LEMBRADAS = 5  # ações recentes de cada Sim mostradas à IA (para ela variar)


def legivel(nome_interno: str) -> str:
    """'computer_PlayGames' -> 'computer play games'"""
    import re
    partes = re.sub(r"([a-z])([A-Z])", r"\1 \2", nome_interno).replace("_", " ").split()
    return " ".join(partes).lower()


ULTIMAS_ACOES = 3  # por Sim, mostradas à IA para ela não repetir


def chave_acao(d) -> str:
    """Identifica a ação para detectar repetição: 'usar_objeto:13192', 'discutir:Ana'."""
    return f"{d.acao}:{d.interacao_id if d.acao == 'usar_objeto' else d.alvo}"


def familia_interacao(nome_interno: str) -> str:
    """O tipo da interação: 'fridge_Cook_PieMenu_Lunch_8Servings' -> 'fridge cook'.
    Variações (receitas, porções...) do mesmo tipo contam como a mesma coisa."""
    return " ".join(legivel(nome_interno).split()[:2])


def chave_acao(d) -> str:
    """O que conta como 'a mesma ação' para a regra de não repetir."""
    if d.acao == "usar_objeto":
        return "objeto:" + familia_interacao(d.alvo or str(d.interacao_id))
    return f"{d.acao}:{d.alvo}"


def descrever(d) -> str:
    """Cabeçalho do diário: 'discutiu com Ana', 'foi fazer algo na casa (computer play games)'."""
    if d.acao == "usar_objeto":
        return DESCRICOES["usar_objeto"].format(alvo=legivel(d.alvo or str(d.interacao_id)))
    texto = DESCRICOES[d.acao].format(alvo=d.alvo)
    tom = getattr(d, "tom", "")
    return f"{texto}, em tom {TONS[tom]}" if tom in TONS else texto

MAX_LEMBRANCAS = 60  # por Sim; as mais antigas saem (a "opinião" guarda o resumo)
# Memória de longo prazo, que não sai com o tempo como as lembranças comuns:
MAX_DE_FORA = 20     # tudo o que as pessoas de fora disseram a cada Sim
MAX_FATOS = 15       # o que a IA marcou como importante para ele lembrar (novo_fato)
MAX_COMANDOS = 200   # comandos guardados no arquivo do mod


def agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalizar(texto: str) -> str:
    """'Ána ' -> 'ana'. Serve para casar nomes digitados de qualquer jeito."""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sem_acento.lower().strip()


def ler_json(caminho: Path, padrao):
    try:
        return json.loads(Path(caminho).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return padrao


def escrever_json(caminho: Path, dados) -> None:
    """Escreve num arquivo temporário e troca de uma vez, para o mod nunca ler
    um arquivo pela metade."""
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_suffix(caminho.suffix + ".tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, caminho)


class Mundo:
    def __init__(self, arquivo_sims: str, pasta_troca: str, pasta_dados: str):
        # Sem sims.json, a casa começa vazia até alguém usar /gerar.
        self.arquivo_sims = Path(arquivo_sims)
        self._definir_sims(ler_json(self.arquivo_sims, {}).get("sims", []))
        self.antigos: dict[str, str] = {}  # moradores da casa anterior (nome normalizado -> nome)

        self.troca = Path(pasta_troca)
        self.dados = Path(pasta_dados)
        self.dados.mkdir(parents=True, exist_ok=True)
        self.troca.mkdir(parents=True, exist_ok=True)

        salvo = ler_json(self.dados / "memoria.json", {})
        self.rodada: int = salvo.get("rodada", 0)
        # Último evento do jogo que a IA já viu (os eventos vêm do mod, em estado.json).
        self.ultimo_evento: int = salvo.get("ultimo_evento", 0)
        self._evento_mostrado = self.ultimo_evento
        mem = salvo.get("sims", {})
        self.memoria = {
            s["nome"]: mem.get(s["nome"], {"lembrancas": [], "opiniao": "", "acoes": []})
            for s in self.sims
        }

        cmds = ler_json(self.troca / "comandos.json", {"comandos": []})
        self.comandos: list[dict] = cmds.get("comandos", [])
        self._prox_id = max((c["id"] for c in self.comandos), default=0) + 1

    # ---------- Sims e memória ----------

    def _definir_sims(self, sims: list[dict]) -> None:
        self.sims: list[dict] = sims
        self._por_nome = {normalizar(s["nome"]): s for s in sims}

    def trocar_casa(self, fichas: list[dict]) -> None:
        """Muda-se uma casa nova: moradores novos, memória zerada."""
        novos = {normalizar(f["nome"]) for f in fichas}
        # Quem se mudou: o bot avisa se alguém ainda mandar mensagem para eles.
        self.antigos = {k: s["nome"] for k, s in self._por_nome.items() if k not in novos}
        self._definir_sims(fichas)
        self.memoria = {s["nome"]: {"lembrancas": [], "opiniao": "", "acoes": []} for s in fichas}
        # O que aconteceu no jogo com a casa anterior não interessa à nova.
        eventos = (self.estado_do_jogo() or {}).get("eventos", [])
        if eventos:
            self.ultimo_evento = self._evento_mostrado = eventos[-1].get("n", 0)
        escrever_json(self.arquivo_sims, {"sims": fichas})
        # Para o mod criar os Sims. O id muda a cada /gerar: é assim que o mod
        # percebe que chegou uma casa nova.
        escrever_json(self.troca / "casa.json", {"id": uuid.uuid4().hex, "sims": fichas})
        self.registrar("casa_gerada", sims=fichas)
        self.salvar()

    def achar_sim(self, nome: str) -> dict | None:
        return self._por_nome.get(normalizar(nome or ""))

    def achar_antigo(self, nome: str) -> str | None:
        """Nome de quem morava na casa anterior, se for o caso."""
        return self.antigos.get(normalizar(nome or ""))

    def lembrar(self, sim: str, texto: str, fonte: str, rodada: int | None = None) -> None:
        """Guarda uma lembrança. `rodada` = em que rodada ela é novidade."""
        lista = self.memoria[sim]["lembrancas"]
        lista.append({
            "t": agora_iso(),
            "rodada": self.rodada if rodada is None else rodada,
            "fonte": fonte,
            "texto": texto,
        })
        del lista[:-MAX_LEMBRANCAS]
        if fonte == "turma":
            # Recado de fora fica também na memória longa: "a promoção era
            # mentira" só faz sentido se ele ainda lembra da promoção.
            longa = self.memoria[sim].setdefault("de_fora", [])
            longa.append(dict(lista[-1]))
            del longa[:-MAX_DE_FORA]

    def esquecer_turma_da_rodada(self) -> None:
        """Apaga as mensagens da turma ainda não processadas (usado quando o
        filtro do Gemini barra a rodada, para ela não travar as próximas)."""
        for mem in self.memoria.values():
            for chave in ("lembrancas", "de_fora"):
                mem[chave] = [
                    lem for lem in mem.get(chave, [])
                    if not (lem["fonte"] == "turma" and lem["rodada"] >= self.rodada)
                ]

    def mensagens_novas(self) -> list[tuple[str, str]]:
        """(Sim, texto) de cada mensagem da turma ainda não processada."""
        return [
            (nome, lem["texto"])
            for nome, mem in self.memoria.items()
            for lem in mem["lembrancas"]
            if lem["fonte"] == "turma" and lem["rodada"] >= self.rodada
        ]

    def citados(self, texto: str, menos: str = "") -> list[str]:
        """Moradores cujo nome aparece no texto ('aurora disse...' -> ['Aurora'])."""
        import re
        palavras = set(re.findall(r"[a-z0-9]+", normalizar(texto)))
        return [s["nome"] for s in self.sims
                if normalizar(s["nome"]) in palavras and s["nome"] != menos]

    def recentes(self, sim: str, n: int = 12) -> list[dict]:
        return self.memoria[sim]["lembrancas"][-n:]

    def opcoes(self) -> list[dict]:
        """Todas as interações que os objetos do lote oferecem, mapeadas pelo mod.
        Vazia enquanto o jogo não estiver aberto com o automático ligado."""
        return ler_json(self.troca / "opcoes.json", {}).get("interacoes", [])

    def opcao(self, interacao_id: int) -> dict | None:
        return next((o for o in self.opcoes() if o.get("id") == interacao_id), None)

    def jogo_info(self):
        """O seu Sim e o lote, como o mod descreveu (jogo.json). None sem o mod."""
        return ler_json(self.troca / "jogo.json", None)

    def estado_do_jogo(self):
        """O que o mod escreveu sobre o jogo (humor, o que cada Sim está fazendo,
        necessidades, relações, eventos). None se o mod ainda não escreveu."""
        return ler_json(self.troca / "estado.json", None)

    def eventos_novos(self, estado, maximo: int = 30) -> list[dict]:
        """Eventos do jogo que a IA ainda não viu. Marca até onde foi mostrado;
        só conta como visto quando a rodada dá certo (em aplicar)."""
        eventos = (estado or {}).get("eventos", [])
        novos = [e for e in eventos if e.get("n", 0) > self.ultimo_evento][-maximo:]
        if eventos:
            self._evento_mostrado = max(self.ultimo_evento, eventos[-1].get("n", 0))
        return novos

    # ---------- Aplicar o que a IA decidiu ----------

    def aplicar(self, decisoes) -> None:
        proxima = self.rodada + 1
        for d in decisoes:
            if d.acao == "usar_objeto":
                cmd = self._enfileirar_comando(d.sim, d.acao, None, d.interacao_id, d.alvo)
            else:
                cmd = self._enfileirar_comando(d.sim, d.acao, d.alvo)
            # O mod põe a emoção no Sim antes da ação, e usa o tom na conversa.
            humor, tom = getattr(d, "humor", ""), getattr(d, "tom", "")
            if humor:
                intensidade = getattr(d, "intensidade", 1) or 1
                cmd["humor"], cmd["intensidade"] = humor, intensidade
                if getattr(d, "motivo_humor", ""):
                    cmd["motivo"] = d.motivo_humor  # o mod escolhe o moodlet que combina
                self.memoria[d.sim]["humor"] = f"{humor} {INTENSIDADES[intensidade]}".strip()
            if tom:
                cmd["tom"] = tom
            # O Sim lembra do que ele mesmo fez (não conta como novidade).
            self.lembrar(d.sim, f"(eu) {d.diario}", fonte="eu")
            # O alvo lembra do que ouviu -> é assim que fofoca se espalha.
            if d.alvo and d.fala:
                self.lembrar(d.alvo, f'{d.sim} me disse: "{d.fala}"', fonte=d.sim, rodada=proxima)
            self.memoria[d.sim]["opiniao"] = d.opiniao
            fato = getattr(d, "novo_fato", "")
            if fato:
                fatos = self.memoria[d.sim].setdefault("fatos", [])
                fatos.append({"t": agora_iso(), "rodada": self.rodada, "texto": fato})
                del fatos[:-MAX_FATOS]
            acoes = self.memoria[d.sim].setdefault("acoes", [])
            acoes.append(descrever(d))
            del acoes[:-MAX_ACOES_LEMBRADAS]
            self.memoria[d.sim]["ultima_chave"] = chave_acao(d)
            self.registrar("decisao", comando=cmd["id"], **d.model_dump())
        self.rodada = proxima
        self.ultimo_evento = self._evento_mostrado
        self.salvar()

    def _enfileirar_comando(self, sim: str, acao: str, alvo: str | None,
                            interacao_id: int = 0, interacao_nome: str = "") -> dict:
        cmd = {"id": self._prox_id, "t": agora_iso(), "sim": sim, "acao": acao, "alvo": alvo or None}
        if acao == "usar_objeto":
            cmd.update(interacao_id=interacao_id, interacao_nome=interacao_nome)
        self._prox_id += 1
        self.comandos.append(cmd)
        self.comandos = self.comandos[-MAX_COMANDOS:]
        return cmd

    # ---------- Arquivos ----------

    def salvar(self) -> None:
        escrever_json(self.dados / "memoria.json", {"rodada": self.rodada, "sims": self.memoria,
                                                    "ultimo_evento": self.ultimo_evento})
        escrever_json(self.troca / "comandos.json", {"comandos": self.comandos})

    def registrar(self, tipo: str, **dados) -> None:
        """Log de tudo, para o REGISTRO.md depois do teste."""
        linha = {"t": agora_iso(), "tipo": tipo, **dados}
        with open(self.dados / "log.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(linha, ensure_ascii=False) + "\n")
