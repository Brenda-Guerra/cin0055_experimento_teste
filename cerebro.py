"""A cabeça dos Sims: monta o prompt, chama o Gemini e confere a resposta.

Uma chamada decide a próxima ação de TODOS os Sims de uma vez, para caber
na cota gratuita.
"""
import asyncio
import logging
import random
from datetime import datetime, timezone

from pydantic import BaseModel

from filtro import bloqueado
from mundo import ACOES, ACOES_COM_TOM, EMOCOES, TONS, Mundo, legivel, chave_acao, consertar_unicode, descrever, familia_interacao, normalizar

log = logging.getLogger("cerebro")


class Decisao(BaseModel):
    sim: str
    acao: str
    alvo: str      # nome de outro Sim, ou "" em usar_objeto
    interacao_id: int  # só em usar_objeto: o número da interação do mapa da casa; senão 0
    fala: str      # o que ele diz ao alvo (vira lembrança do alvo)
    diario: str    # o porquê, em 1ª pessoa (vai para o grupo)
    opiniao: str   # resumo atualizado do que pensa dos outros
    # Sem valor padrão: o google-genai recusa "default" no esquema de resposta.
    humor: str     # emoção que ele sente agora (uma de EMOCOES) ou "" se nada mudou
    intensidade: int  # do humor: 1 leve, 2 forte, 3 muito forte (0 sem humor)
    motivo_humor: str  # 2 a 4 palavras EM INGLÊS sobre a causa do humor (para o jogo achar o moodlet)
    novo_fato: str  # algo importante que ele deve lembrar por muito tempo, ou ""
    tom: str       # em conversar/discutir: o clima da conversa (um de TONS) ou ""


class Rodada(BaseModel):
    decisoes: list[Decisao]


class ErroCerebro(Exception):
    """A IA não devolveu nada utilizável nesta rodada."""


class ConteudoBloqueado(ErroCerebro):
    """O filtro de segurança do Gemini barrou a rodada."""


class LimiteAtingido(Exception):
    """O Gemini respondeu 429 (cota). `espera` = segundos até tentar de novo."""
    def __init__(self, espera: float):
        super().__init__(f"limite do Gemini, esperar {espera:.0f}s")
        self.espera = espera


INSTRUCOES = f"""Você é a mente dos moradores de uma casa no The Sims 4. Os moradores
são fictícios. Cada um tem personalidade, história e memória próprias, e
age por conta própria: eles não existem para servir ninguém.

Pessoas de fora (de um grupo de mensagens) falam com os moradores. Essas
mensagens são o ACONTECIMENTO MAIS IMPORTANTE da rodada: a história da casa
anda por causa delas. O morador não é um robô e não precisa obedecer, mas o
que ele ouviu SEMPRE muda o que ele faz agora: ele acredita e age, ou
desconfia e vai tirar a história a limpo, ou conta para alguém, ou confronta
quem foi citado, ou se magoa e se isola fazendo algo na casa que tenha a ver
com o que sentiu. Ignorar de vez é raro e só combina com quem é muito
desconfiado ou indiferente. A forma da reação vem da personalidade dele.

Para CADA morador, decida a próxima ação dele no jogo:
- acao: exatamente uma destas: {", ".join(ACOES)}.
  Use usar_objeto para fazer algo com as coisas da casa (escrever no
  computador, ler, cozinhar, tomar banho, procurar casa nova...): escolha
  em "Coisas que dá para fazer na casa" a interação que melhor representa
  a intenção do morador. Os nomes estão em inglês, como no jogo.
- interacao_id: em usar_objeto, o número da interação escolhida, exatamente
  como está na lista. Nas outras ações, 0.
- alvo: o nome de outro morador da casa (nunca ele mesmo, nunca uma pessoa
  de fora). Use "" com usar_objeto.
- fala: uma frase, em português, que ele diz ao alvo. No jogo só aparece
  simlish, mas o alvo vai lembrar desta frase. Use "" com usar_objeto.
- humor: a emoção que ele sente AGORA, uma destas: {", ".join(EMOCOES)}.
  O jogo mostra essa emoção no Sim (balão de humor, jeito de andar e falar).
  Quem recebeu mensagem quase sempre muda de humor por causa dela: ouviu
  que alguém o odeia -> irritado, triste, tenso ou confuso, conforme os
  traços; recebeu um elogio -> feliz ou confiante. Os outros mudam quando
  algo acontece com eles (uma briga, uma fofoca, um elogio). Use "" se o
  humor dele não mudou.
- intensidade: do humor, 1 (leve), 2 (forte) ou 3 (muito forte). O jogo
  mostra a diferença. Sem humor, 0.
- motivo_humor: 2 a 4 palavras EM INGLÊS dizendo a causa do humor, para o
  jogo escolher o moodlet certo (ex.: "rumor gossip", "lie betrayal",
  "promotion career", "breakup jealous love", "compliment", "argument",
  "joke funny"). Sem humor, "".
- tom: só em conversar e discutir, o clima da conversa, um destes:
  {", ".join(TONS)}. Combine com o humor e com o que ele quer: tirar
  satisfação irritado -> irritado ou maldoso; magoado -> triste; aprontando
  -> travesso; perdeu a cabeça -> furioso (gritar, jogar bebida, brigar).
  Conversa neutra -> amigavel. Nas outras ações, "".
- TODO morador faz algo ATIVO em TODA rodada. Ficar parado não existe: quem
  quer se isolar usa algo da casa que combine com o que sente (ler, tomar
  banho, jogar no computador, dormir, se olhar no espelho...).
- diario: 1 ou 2 frases curtas, em 1ª pessoa, coloquiais, explicando por
  que fez isso.
- opiniao: no máximo 3 frases, em 1ª pessoa, com o que ele pensa agora dos
  outros moradores e das pessoas de fora que conhece. Guarde aqui o que
  importa das lembranças antigas, porque elas vão sendo esquecidas.
- novo_fato: se nesta rodada ele ficou sabendo, decidiu ou viveu algo
  IMPORTANTE para lembrar por muito tempo (uma notícia sobre ele, uma
  promessa, um segredo descoberto, uma mentira desmascarada, uma briga
  séria, uma reconciliação), escreva em 1 frase curta, em 1ª pessoa, dizendo
  quem contou. Ex.: "A Brenda me contou que vou ser promovido."; depois:
  "Descobri que a promoção era mentira da Brenda." Se nada importante
  mudou, "". Não repita o que já está em "Coisas importantes que sei".

Regras:
- Quem está marcado com "RECEBEU MENSAGEM AGORA" responde a ela nesta
  rodada, e o diário dele diz o que ouviu e o que achou. Se a mensagem cita
  outro morador, esse morador costuma ser o alvo da ação (tirar satisfação,
  avisar, fofocar, pedir desculpas, flertar...).
- Os outros moradores também podem reagir ao clima: quem está perto de uma
  confusão percebe e se mete, ou foge dela.
- Lembranças marcadas (NOVO) aconteceram desde a última rodada: leve em conta.
- O PASSADO PESA: Relação, História e "O passado dos outros com..." são a
  vida deles antes desta casa. Toda mensagem é lida à luz disso: a notícia
  de que um EX está namorando outra pessoa desperta ciúme, mágoa ou
  orgulho ferido, não só surpresa; uma acusação contra um primo dói mais;
  um segredo antigo pode vir à tona. Diga no diário qual parte do passado
  pesou ("o Breno é meu ex...").
- A história é contínua: o que chega agora se SOMA ao que ele já sabe
  ("Coisas importantes que sei", "O que pessoas de fora já me disseram",
  opinião). Se a novidade continua, confirma ou desmente algo antigo, a
  reação é sobre os dois: quem acreditou numa promoção e descobre que era
  mentira fica decepcionado, irritado ou confuso, e talvez desconfie de
  quem contou; quem foi acusado e depois inocentado fica aliviado ou
  magoado. Cite a coisa antiga no diário quando fizer sentido.
- REINCIDÊNCIA ESCALA: se algo já aconteceu antes (a mesma mentira, ofensa,
  provocação ou traição, vinda da mesma pessoa), conte quantas vezes nas
  memórias, e a reação cresce a cada vez:
  1ª vez: confuso, triste ou tenso (intensidade 1-2); vai conversar e pedir
     explicação ("nunca mais faça isso").
  2ª vez: irritado (2-3); discutir com tom irritado ou maldoso; avisa que
     a paciência acabou.
  3ª vez ou mais: irritado intensidade 3; discutir com tom furioso; pode
     cortar a amizade e passar a ignorar.
  Os traços mudam o ritmo: Esquentado ou Maldoso pula etapas, Bondoso ou
  Bom de papo perdoa uma vez a mais. Coisas boas repetidas também somam
  (carinho e confiança crescem). Anote a reincidência em novo_fato:
  "O Rui mentiu para mim de novo (2ª vez)."
- "O QUE ACONTECEU NO JOGO" e "No jogo agora" mostram o que DE FATO houve
  no jogo, que é a verdade: se uma ação "NÃO CONSEGUIU", ela não aconteceu
  (não finja que aconteceu; tente outro jeito). O humor, os motivos dele e
  as relações (amizade/romance de -100 a 100) mostram como cada um está de
  verdade: alguém irritado de verdade guarda rancor; amizade negativa é
  inimizade. Necessidades ruins pesam: quem está com muita fome, cansaço ou
  sujeira tende a cuidar disso (usar_objeto), a não ser que a história
  esteja quente. Continue as histórias a partir do que aconteceu.
- Variedade: um morador NÃO repete nenhuma das suas "Últimas ações" (mesma
  ação com o mesmo alvo, ou o mesmo objeto), a não ser que a história exija
  de verdade. A casa tem muita coisa para fazer: explore.
- No máximo metade dos moradores usa objetos na mesma rodada; os outros
  interagem entre si. Esta casa é sobre as relações entre eles.
- Cada morador age segundo os próprios traços: um Ciumento desconfia, um
  Maldoso provoca, um Bondoso acolhe, um Preguiçoso enrola.
- Tudo é para todas as idades: nada sexual, nada de nudez, nada de
  palavrão. Romance vai no máximo até flerte e abraço.
- Se alguém de fora mandar algo ofensivo, sexual ou impróprio, o morador
  ignora e segue a vida, sem repetir nem comentar o conteúdo.
"""


def configuracao_seguranca(t) -> list:
    """Filtro do próprio Gemini, no nível mais rígido para conteúdo sexual.
    `t` = o módulo google.genai.types."""
    medio = t.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE
    return [
        t.SafetySetting(category=t.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                        threshold=t.HarmBlockThreshold.BLOCK_LOW_AND_ABOVE),
        t.SafetySetting(category=t.HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=medio),
        t.SafetySetting(category=t.HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=medio),
        t.SafetySetting(category=t.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=medio),
    ]


def _ha_quanto(iso: str) -> str:
    try:
        minutos = (datetime.now(timezone.utc) - datetime.fromisoformat(iso)).total_seconds() / 60
    except ValueError:
        return "?"
    return "agora" if minutos < 1 else f"há {int(minutos)} min"


def segunda_chance(mundo: Mundo, faltam: list[str]) -> str:
    linhas = ["\n\n## ATENÇÃO: SEGUNDA CHANCE",
              "As decisões destes moradores não valeram (repetiram a última ação, ficaram "
              "parados, ou fugiram das regras). Decida de novo SÓ para eles, cada um com "
              "algo ATIVO e DIFERENTE da última ação:"]
    for nome in faltam:
        ultimas = mundo.memoria[nome].get("acoes", [])
        linhas.append(f"- {nome} (última ação, proibida agora: {ultimas[-1] if ultimas else 'nenhuma'})")
    return "\n".join(linhas)


def agrupar_opcoes(opcoes: list[dict]) -> list[tuple[dict, int]]:
    """Junta as variações do mesmo tipo (dezenas de receitas da geladeira viram
    uma linha), para um tipo não pesar mais que os outros na escolha da IA.
    Devolve (representante, quantas variações a mais). Todo tipo continua lá."""
    grupos: dict[str, list[dict]] = {}
    for o in opcoes:
        grupos.setdefault(familia_interacao(o["nome"]), []).append(o)
    return [(min(g, key=lambda o: len(o["nome"])), len(g) - 1) for g in grupos.values()]


HUMORES_JOGO = {
    "happy": "feliz", "sad": "triste", "angry": "irritado", "tense": "tenso", "stressed": "tenso",
    "embarrassed": "envergonhado", "uncomfortable": "desconfortável", "confident": "confiante",
    "energized": "energizado", "flirty": "flertante", "focused": "focado", "inspired": "inspirado",
    "playful": "brincalhão", "bored": "entediado", "dazed": "confuso", "fine": "normal",
    "asleep": "dormindo", "possessed": "possuído",
}
NECESSIDADES = {"fome": "fome", "energia": "cansaço", "diversao": "tédio", "social": "solidão",
                "higiene": "sujeira", "bexiga": "vontade de ir ao banheiro"}
JOGO_VELHO_S = 120  # estado.json mais velho que isso: jogo pausado/fechado


def humor_do_jogo(nome_interno: str | None) -> str | None:
    if not nome_interno:
        return None
    chave = nome_interno.lower().replace("mood_", "")
    return HUMORES_JOGO.get(chave, legivel(chave))


def descrever_no_jogo(foto: dict, nome: str) -> list[str]:
    """As linhas de 'No jogo agora' de um morador."""
    if not foto.get("no_lote"):
        return [f"- No jogo agora: {nome} não está no lote (não pode ser alvo nem agir)."]
    linhas = []
    humor = humor_do_jogo(foto.get("humor"))
    if humor:
        intensidade = {0: "leve", 1: "leve", 2: "forte", 3: "muito forte"}.get(foto.get("intensidade"), "")
        motivos = [legivel(m["nome"].removeprefix("buff_").removeprefix("Buff_"))
                   for m in foto.get("moodlets", [])][:4]
        linhas.append(f"- No jogo agora: humor {humor} {intensidade}".rstrip()
                      + (f" (por causa de: {'; '.join(motivos)})" if motivos else ""))
    fazendo = [legivel(f.split(" -> ")[0]) + (f" com {f.split(' -> ')[1]}" if " -> " in f else "")
               for f in foto.get("fazendo", [])]
    linhas.append(f"- Fazendo no jogo: {', '.join(fazendo) or 'nada de especial'}"
                  + (f"; na fila: {', '.join(legivel(x) for x in foto.get('fila', []))}" if foto.get("fila") else ""))
    # Necessidades vão de -100 (péssima) a 100 (ótima): só as ruins interessam.
    ruins = [f"{NECESSIDADES.get(k, k)} ({v})" for k, v in foto.get("necessidades", {}).items() if v < -20]
    if ruins:
        linhas.append(f"- Precisando de: {', '.join(ruins)}")
    rels = [f"{outro}: amizade {r.get('amizade', '?')}, romance {r.get('romance', '?')}"
            for outro, r in foto.get("relacoes", {}).items() if r]
    if rels:
        linhas.append(f"- Relações no jogo (-100 a 100): {'; '.join(rels)}")
    return linhas


def _sim_inicial(mundo: Mundo) -> str:
    inicial = next((x for x in mundo.sims if x.get("papel") == "inicial"), None)
    return (inicial or (mundo.sims[0] if mundo.sims else {})).get("nome", "")


def _texto(mundo: Mundo, texto: str) -> str:
    from gerador import trocar_sim_inicial
    return trocar_sim_inicial(texto, _sim_inicial(mundo)) if _sim_inicial(mundo) else texto


def ligacoes(mundo: Mundo, nome: str) -> list[str]:
    """O que os OUTROS moradores são para este (a ficha do Breno dizer 'ex do
    Iago' não basta: a ficha do Iago também precisa mostrar isso)."""
    linhas = []
    eu = mundo.achar_sim(nome) or {}
    for l in eu.get("lacos", []):
        romance = f", romance {l['romance']}" if l.get("romance") else ""
        linhas.append(f"  - {l['com']}: {l['tipo']} (no começo: amizade {l['amizade']}{romance})")
    for outro in mundo.sims:
        if outro["nome"] == nome:
            continue
        texto = _texto(mundo, f"{outro.get('relacao', '')} {outro.get('historia', '')}")
        if normalizar(nome) in set(normalizar(texto).replace(",", " ").replace(".", " ").replace(";", " ").split()):
            linhas.append(f"  - {outro['nome']}: {texto.strip()}")
    return linhas


def montar_prompt(mundo: Mundo) -> str:
    novas = mundo.mensagens_novas()
    partes = []
    estado = mundo.estado_do_jogo()
    fotos = {}
    if estado:
        import time
        idade = time.time() - estado.get("t", 0)
        eventos = mundo.eventos_novos(estado)
        if idade > JOGO_VELHO_S:
            partes.append(f"(O jogo não manda notícias há {int(idade // 60)} min: pode estar pausado. "
                          "A situação abaixo pode estar desatualizada.)\n")
        fotos = estado.get("sims", {})
        if eventos:
            partes.append("## O QUE ACONTECEU NO JOGO desde a última rodada (consequências reais)")
            partes += [f"- {e['texto']}" for e in eventos]
            partes.append("")
        from gerador import descrever_lote
        lote = (mundo.jogo_info() or {}).get("lote")
        if lote:
            partes.append(f"O lugar: {descrever_lote(lote)}.")
        if estado.get("hora_jogo"):
            partes.append(f"Hora no jogo: {estado['hora_jogo']}.")
        if estado.get("tambem_no_lote"):
            partes.append(f"Também estão no lote (não são moradores): {', '.join(estado['tambem_no_lote'])}.")
    if novas:
        partes.append("## O QUE AS PESSOAS DE FORA DISSERAM AGORA (o mais importante da rodada)")
        for nome, texto in novas:
            citados = mundo.citados(texto, menos=nome)
            extra = f" [cita: {', '.join(citados)}]" if citados else ""
            partes.append(f"- Para {nome}: {texto}{extra}")
        partes.append("")
    partes.append("## Moradores da casa")
    recebeu = {}
    for nome, texto in novas:
        recebeu.setdefault(nome, []).append(texto)
    for s in mundo.sims:
        nome = s["nome"]
        partes.append(
            f"\n### {nome}\n"
            f"- Gênero: {s.get('genero', '?')}\n"
            f"- Idade: {s.get('idade', '?')}\n"
            f"- Traços: {', '.join(s.get('tracos', []))}\n"
            f"- Aspiração: {s.get('aspiracao', '?')}\n"
            f"- Emprego: {s.get('emprego', 'não informado')}\n"
            f"- Relação: {_texto(mundo, s.get('relacao', '?'))}\n"
            f"- História: {_texto(mundo, s.get('historia', ''))}\n"
            f"- Humor que você deu na última rodada: {mundo.memoria[nome].get('humor') or 'nenhum'}\n"
            f"- O que pensa agora: {mundo.memoria[nome]['opiniao'] or 'ainda não formou opinião'}\n"
            f"- Últimas ações (não repita): {'; '.join(mundo.memoria[nome].get('acoes', [])) or 'nenhuma ainda'}"
        )
        lig = ligacoes(mundo, nome)
        if lig:
            partes.append(f"- O passado dos outros com {nome} (pesa nas reações dele):")
            partes += lig
        if nome in fotos:
            partes += descrever_no_jogo(fotos[nome], nome)
        for texto in recebeu.get(nome, []):
            partes.append(f"- >>> RECEBEU MENSAGEM AGORA: {texto} -> a ação dele nesta rodada responde a isso.")
        mem = mundo.memoria[nome]
        fatos = mem.get("fatos", [])
        if fatos:
            partes.append("- Coisas importantes que sei (memória de longo prazo, da mais antiga para a mais nova):")
            partes += [f"  - [{_ha_quanto(f['t'])}] {f['texto']}" for f in fatos]
        antigas = [m for m in mem.get("de_fora", []) if m["rodada"] < mundo.rodada]
        if antigas:
            partes.append("- O que pessoas de fora já me disseram antes (da mais antiga para a mais nova):")
            partes += [f"  - [{_ha_quanto(m['t'])}] {m['texto']}" for m in antigas]
        # As de fora já aparecem acima (ou em RECEBEU AGORA): aqui só o resto.
        lembrancas = [l for l in mem["lembrancas"] if l["fonte"] != "turma"][-12:]
        if lembrancas:
            partes.append("- Lembranças (da mais antiga para a mais nova):")
            for lem in lembrancas:
                marca = " (NOVO)" if lem["rodada"] >= mundo.rodada else ""
                partes.append(f"  - [{_ha_quanto(lem['t'])}]{marca} {lem['texto']}")


    opcoes = agrupar_opcoes(mundo.opcoes())
    # Embaralhada a cada rodada: modelos tendem a escolher o que vem primeiro.
    random.shuffle(opcoes)
    if opcoes:
        partes.append("\n## Coisas que dá para fazer na casa (para usar_objeto; ordem aleatória)")
        for o, variacoes in opcoes:
            extra = f" (+{variacoes} variações)" if variacoes else ""
            partes.append(f"- {o['id']}: {o['nome']} ({', '.join(o.get('objetos', []))}){extra}")
    else:
        partes.append("\n(O mapa da casa ainda não chegou do jogo: não use usar_objeto.)")

    partes.append("\nDecida a próxima ação de cada morador.")
    return "\n".join(partes)


def validar(mundo: Mundo, decisoes: list[Decisao]) -> list[Decisao]:
    """Descarta o que o jogo não consegue executar (Sim inexistente, ação fora
    da lista, alvo inválido) e corrige nomes escritos diferente."""
    vistos, validas = set(), []
    for d in decisoes:
        d = d.model_copy(update={c: consertar_unicode(getattr(d, c))
                                 for c in ("sim", "acao", "alvo", "fala", "diario", "opiniao", "novo_fato")})
        sim = mundo.achar_sim(d.sim)
        acao = normalizar(d.acao).replace(" ", "_")
        if not sim or sim["nome"] in vistos or acao not in ACOES:
            log.info("decisão descartada: %s", d)
            continue
        if bloqueado(f"{d.fala} {d.diario} {d.opiniao} {d.novo_fato}"):
            log.info("decisão descartada pelo filtro de conteúdo (%s)", sim["nome"])
            continue
        alvo, interacao_id = "", 0
        if acao == "usar_objeto":
            opcao = mundo.opcao(d.interacao_id)
            if opcao is None:
                log.info("interação fora do mapa da casa: %s", d)
                continue
            alvo, interacao_id = opcao["nome"], opcao["id"]  # nome interno, para o diário
        elif ACOES[acao]:
            achado = mundo.achar_sim(d.alvo)
            if not achado or achado["nome"] == sim["nome"]:
                log.info("alvo inválido: %s", d)
                continue
            alvo = achado["nome"]
        humor = normalizar(d.humor).replace(" ", "_")
        humor = humor if humor in EMOCOES else ""
        intensidade = min(max(int(d.intensidade or 1), 1), 3) if humor else 0
        import re as _re
        motivo = " ".join(_re.findall(r"[a-z]+", normalizar(d.motivo_humor)))[:60] if humor else ""
        tom = normalizar(d.tom).replace(" ", "_")
        tom = tom if tom in TONS and acao in ACOES_COM_TOM else ""
        nova = d.model_copy(update={
            "humor": humor,
            "intensidade": intensidade,
            "motivo_humor": motivo,
            "tom": tom,
            "sim": sim["nome"],
            "acao": acao,
            "alvo": alvo,
            "interacao_id": interacao_id,
            "fala": d.fala.strip()[:300] if alvo and acao != "usar_objeto" else "",
            "diario": d.diario.strip()[:400],
            "opiniao": d.opiniao.strip()[:600],
            "novo_fato": d.novo_fato.strip()[:200],
        })
        # Trava: o mesmo TIPO de ação duas vezes seguidas é descartado (visto em
        # 22/10: Nestor cozinhou 2x, com variações diferentes de receita).
        if chave_acao(nova) == mundo.memoria[sim["nome"]].get("ultima_chave"):
            log.info("repetição descartada: %s %s", sim["nome"], descrever(nova))
            continue
        vistos.add(sim["nome"])
        validas.append(nova)
    return validas


ESPERA_MAX_S = 45  # se um modelo não responder nisso, passa para o próximo

# Erros que dizem "este modelo não dá agora", e não "o pedido está errado":
# nesses casos o bot tenta o próximo modelo da lista.
SOBRECARGA = {500, 502, 503, 504}
SEM_COTA = 429
INEXISTENTE = {404}
DESCANSO_S = 90  # um modelo sobrecarregado fica de lado por este tempo

# Se não der para perguntar ao Google quais modelos existem.
MODELOS_PADRAO = ["gemini-flash-lite-latest", "gemini-flash-latest",
                  "gemini-2.5-flash-lite", "gemini-2.5-flash"]
FORA_DA_LISTA = ("image", "tts", "audio", "live", "embedding", "vision", "computer", "robotics", "gemma", "learnlm")


def ordenar_modelos(nomes: list[str]) -> list[str]:
    """Lite primeiro (cota maior), depois Flash, depois Pro; versão mais nova
    antes; estáveis antes de preview."""
    import re

    def chave(n):
        tipo = 0 if "lite" in n else 1 if "flash" in n else 2
        v = re.search(r"(\d+(?:\.\d+)?)", n)
        versao = float(v.group(1)) if v else 99.0  # "-latest" = o mais novo
        return (tipo, "preview" in n or "exp" in n, -versao, n)
    return sorted(dict.fromkeys(nomes), key=chave)


async def descobrir_modelos(client) -> list[str]:
    """Pergunta ao Google quais modelos de texto esta chave pode usar."""
    nomes = []
    async for m in await client.aio.models.list():
        nome = (m.name or "").removeprefix("models/")
        acoes = getattr(m, "supported_actions", None) or []
        if (nome.startswith("gemini") and "generateContent" in acoes
                and not any(x in nome for x in FORA_DA_LISTA)):
            nomes.append(nome)
    return ordenar_modelos(nomes)


class Cerebro:
    def __init__(self, api_key: str, modelo: str, temperatura: float = 1.1, reservas: list[str] | None = None):
        # Importado aqui para o resto do código funcionar sem a biblioteca.
        from google import genai
        from google.genai import errors, types

        self._errors = errors
        self._types = types
        self.client = genai.Client(api_key=api_key)
        self.modelo = modelo            # o preferido, sempre tentado primeiro
        self.reservas = reservas        # None = descobre sozinho na 1ª vez
        self.temperatura = temperatura
        self._descanso: dict[str, float] = {}   # modelo -> até quando fica de lado
        self.ultimo_modelo = ""                 # quem respondeu a última chamada

    async def _candidatos(self) -> list[str]:
        if self.reservas is None:
            try:
                self.reservas = await asyncio.wait_for(descobrir_modelos(self.client), 20)
                log.info("Modelos de reserva: %s", ", ".join(self.reservas))
            except Exception as e:
                log.warning("Não consegui listar os modelos (%s); uso a lista padrão.", e)
                self.reservas = list(MODELOS_PADRAO)
        return list(dict.fromkeys([self.modelo, *self.reservas]))

    async def perguntar(self, contents, config):
        """Chama o Gemini. Se o modelo estiver sobrecarregado, sem cota, lento
        ou fora do ar, tenta o próximo da lista; dá duas voltas na lista antes
        de desistir. Só erros de verdade do pedido param na hora."""
        import time
        todos = await self._candidatos()
        sem_cota = set()
        for volta in range(2):
            agora = time.monotonic()
            fila = [m for m in todos if self._descanso.get(m, 0) <= agora] or todos
            for modelo in fila:
                try:
                    resp = await asyncio.wait_for(self.client.aio.models.generate_content(
                        model=modelo, contents=contents, config=config), ESPERA_MAX_S)
                except asyncio.TimeoutError:
                    log.warning("%s não respondeu em %ds; tentando outro.", modelo, ESPERA_MAX_S)
                    self._descanso[modelo] = time.monotonic() + DESCANSO_S
                    continue
                except self._errors.APIError as e:
                    if e.code == SEM_COTA:
                        sem_cota.add(modelo)
                        espera = 3600 if "day" in str(e.message).lower() else DESCANSO_S
                    elif e.code in SOBRECARGA:
                        espera = DESCANSO_S
                    elif e.code in INEXISTENTE:
                        espera = 1e9
                    elif e.code == 400 and modelo != self.modelo:
                        espera = 1e9  # reserva que não aceita este tipo de pedido
                    else:
                        raise ErroCerebro(f"o Gemini recusou o pedido ({e.code}: {e.message})") from e
                    log.warning("%s indisponível (%s); tentando outro.", modelo, e.code)
                    self._descanso[modelo] = time.monotonic() + espera
                    continue
                except Exception as e:  # rede caiu, DNS, SSL...
                    log.warning("%s: falha de conexão (%s: %s).", modelo, type(e).__name__, e)
                    continue
                if modelo != self.modelo:
                    log.info("Respondido pelo modelo reserva %s.", modelo)
                self.ultimo_modelo = modelo
                return resp
            if volta == 0:
                await asyncio.sleep(5)
        if sem_cota and len(sem_cota) == len(todos):
            raise LimiteAtingido(espera=60)
        raise ErroCerebro("todos os modelos do Gemini estão ocupados agora")

    async def decidir(self, mundo: Mundo) -> list[Decisao]:
        """Uma chamada para todos os Sims. Quem ficar sem decisão válida
        (repetiu, ficou parado, fugiu das regras, ou a IA esqueceu) ganha
        uma segunda chance numa chamada só para esses Sims."""
        prompt = montar_prompt(mundo)
        decisoes = validar(mundo, (await self._chamar(prompt)).decisoes)
        faltam = [s["nome"] for s in mundo.sims if s["nome"] not in {d.sim for d in decisoes}]
        if faltam:
            log.info("segunda chance para: %s", ", ".join(faltam))
            gastar = getattr(self, "ao_chamar_de_novo", None)
            if gastar:
                gastar()
            try:
                extra = validar(mundo, (await self._chamar(prompt + segunda_chance(mundo, faltam))).decisoes)
                decisoes += [d for d in extra if d.sim in faltam]
            except (ErroCerebro, LimiteAtingido) as e:
                log.warning("segunda chance falhou: %s", e)
        if not decisoes:
            raise ErroCerebro("nenhuma decisão válida")
        return decisoes

    async def _chamar(self, prompt: str) -> "Rodada":
        t = self._types
        config = t.GenerateContentConfig(
            system_instruction=INSTRUCOES,
            response_mime_type="application/json",
            response_schema=Rodada,
            temperature=self.temperatura,
            safety_settings=configuracao_seguranca(t),
        )
        resp = await self.perguntar(prompt, config)

        feedback = getattr(resp, "prompt_feedback", None)
        fim = resp.candidates[0].finish_reason if resp.candidates else None
        if (feedback and feedback.block_reason) or "SAFETY" in str(fim):
            raise ConteudoBloqueado("o filtro do Gemini barrou a rodada")

        rodada = resp.parsed
        if rodada is None:  # JSON fora do formato
            try:
                rodada = Rodada.model_validate_json(resp.text or "")
            except ValueError as e:
                raise ErroCerebro(f"resposta inválida: {resp.text!r}") from e
        return rodada
