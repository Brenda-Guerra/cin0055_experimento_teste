"""Bot do Telegram: lê o grupo, entrega as mensagens aos Sims e posta os diários.

Para falar com um Sim, a pessoa escreve no grupo:  Ana: o Pedro anda falando de você
"""
import html
import importlib.util
import logging
import os
import re
import time
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from cerebro import Cerebro, ErroCerebro, LimiteAtingido
from filtro import bloqueado
from gerador import Gerador
from motor import Motor
from mundo import EMOCOES, INTENSIDADES, Mundo, descrever

load_dotenv()

TOKEN = os.environ["TELEGRAM_TOKEN"]
GRUPO_ID = int(os.getenv("GRUPO_ID") or 0)           # 0 = aceita qualquer grupo
ADMIN_ID = int(os.getenv("ADMIN_ID") or 0)           # só essa pessoa pode usar /gerar
RODADA_S = float(os.getenv("RODADA_SEGUNDOS", 30))     # de quanto em quanto tempo checa
OCIOSO_S = float(os.getenv("OCIOSO_SEGUNDOS", 120))    # Sims agem sozinhos se ninguém falar
INTERVALO_PESSOA_S = float(os.getenv("INTERVALO_POR_PESSOA", 30))
MAX_CARACTERES = int(os.getenv("MAX_CARACTERES", 280))

logging.basicConfig(format="%(asctime)s %(name)s %(levelname)s %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)  # não loga a URL com o token
log = logging.getLogger("bot")

# ---------- o mod do jogo (pasta mod-npcgen/ ao lado deste arquivo) ----------

def preparar_mod() -> tuple[str, str | None]:
    """Empacota e instala o mod se o npcgen.py mudou. Devolve (situação para o
    aviso de início, pasta de troca achada ou None). Uma falha aqui não
    impede o bot de subir."""
    if os.getenv("EMPACOTAR_MOD", "1") == "0":
        return "empacotamento automático desligado (EMPACOTAR_MOD=0)", None
    caminho = Path(__file__).resolve().parent / "mod-npcgen" / "empacotar.py"
    try:
        spec = importlib.util.spec_from_file_location("empacotar", caminho)
        emp = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(emp)
        r = emp.empacotar(os.getenv("SIMS_MODS") or None, os.getenv("PYTHON37") or None)
    except Exception as e:  # inclui ErroEmpacotar e arquivo ausente
        log.warning("Mod NÃO foi empacotado: %s", e)
        return f"⚠️ não consegui atualizar o mod: {e}", None
    if not r.mudou:
        log.info("Mod já estava atualizado (%s).", r.ts4script)
        return "mod já estava atualizado", str(r.troca)
    if not r.compilado_com:
        log.warning("Mod instalado SEM compilar: falta o Python 3.7 (o jogo não vai carregá-lo).")
        return "⚠️ mod instalado SEM compilar: falta o Python 3.7 (ponha o caminho em PYTHON37)", str(r.troca)
    log.info("Mod atualizado em %s (compilado com %s).", r.ts4script, r.compilado_com)
    return "mod ATUALIZADO agora: reinicie o jogo para ele valer", str(r.troca)


SITUACAO_MOD, _troca_do_mod = preparar_mod()

mundo = Mundo(
    os.getenv("ARQUIVO_SIMS", "sims.json"),
    # PASTA_TROCA no .env tem prioridade; senão, a pasta ao lado do mod instalado.
    os.getenv("PASTA_TROCA") or _troca_do_mod or "troca",
    os.getenv("PASTA_DADOS", "dados"),
)
log.info("Pasta de troca com o jogo: %s", mundo.troca)
# GEMINI_RESERVAS (opcional): modelos para quando o principal estiver
# sobrecarregado, separados por vírgula. Vazio = o bot descobre sozinho.
_reservas = [m.strip() for m in os.getenv("GEMINI_RESERVAS", "").split(",") if m.strip()] or None
cerebro = Cerebro(os.environ["GEMINI_API_KEY"], os.getenv("GEMINI_MODELO", "gemini-3.5-flash-lite"),
                  reservas=_reservas)
gerador = Gerador(cerebro, int(os.getenv("MORADORES_MIN", 2)), int(os.getenv("MORADORES_MAX", 4)),
                  arquivo_recentes=mundo.dados / "nomes_recentes.json", ler_jogo=mundo.jogo_info)
motor = Motor(
    mundo,
    cerebro,
    ocioso_s=OCIOSO_S,
    limite_diario=int(os.getenv("LIMITE_DIARIO", 400)),
)

# "Ana: oi", "Ana, oi", "Ana - oi", "@ana oi" (com @ não precisa de separador)
ENDERECO = re.compile(r"^\s*(?:@([^\s:,\-—]+)\s*[:,\-—]?|([^\s:,\-—]+)\s*[:,\-—])\s*(.+)$", re.S)
ultimo_envio: dict[int, float] = {}
chat_do_jogo = GRUPO_ID or None


def desligar_quickedit() -> None:
    """No Windows, clicar na janela do terminal entra em modo de seleção e
    PAUSA o programa até apertar Esc/Enter: o bot para de reagir e os Sims
    param de agir. Isto desliga esse modo só para esta janela."""
    if os.name != "nt":
        return
    try:
        import ctypes
        k = ctypes.windll.kernel32
        h = k.GetStdHandle(-10)  # entrada do console
        modo = ctypes.c_uint32()
        if k.GetConsoleMode(h, ctypes.byref(modo)):
            k.SetConsoleMode(h, (modo.value & ~0x0040) | 0x0080)  # sem QuickEdit
    except Exception as e:
        log.warning("Não consegui desligar o modo de seleção do terminal: %s", e)


def grupo_permitido(update: Update) -> bool:
    return not GRUPO_ID or update.effective_chat.id == GRUPO_ID


# ---------- comandos ----------

async def ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    nomes = ", ".join(s["nome"] for s in mundo.sims) or "ninguém ainda (a casa vai ser gerada)"
    await update.effective_message.reply_text(
        "🏠 Tem uma casa no The Sims rodando no telão.\n\n"
        f"Moradores: {nomes}.\n\n"
        "Para falar com um deles, comece a mensagem pelo nome:\n"
        "   Ana: o Pedro anda falando de você\n\n"
        "Eles lembram do que ouvem, decidem sozinhos o que fazer e "
        "contam aqui no diário. Uma mensagem a cada "
        f"{int(INTERVALO_PESSOA_S)}s por pessoa.\n\n"
        "🙈 = mensagem ignorada (conteúdo +18 ou palavrão).\n\n"
        "⚠️ As mensagens vão para uma IA do Google (plano gratuito), que pode "
        "usá-las para treino. Não mande dados pessoais."
    )


def formatar_casa(sims: list[dict]) -> str:
    # A história fica de fora: os segredos são dos Sims, a turma descobre conversando.
    blocos = [
        f"• <b>{html.escape(s['nome'])}</b> ({html.escape(s.get('genero', '?'))}, {html.escape(s.get('idade', '?'))})"
        f"{' 🎮 <i>o Sim que já estava na casa</i>' if s.get('existente') else ''}\n"
        f"  Traços: {html.escape(', '.join(s.get('tracos', [])))}\n"
        f"  Aspiração: {html.escape(s.get('aspiracao', '?'))}\n"
        f"  Emprego: {html.escape(s.get('emprego', '?'))}\n"
        f"  <i>{html.escape(s.get('relacao', ''))}</i>"
        for s in sims
    ]
    # Os laços entre eles (viram as barras de relacionamento no jogo), cada par uma vez.
    vistos, lacos = set(), []
    for s in sims:
        for l in s.get("lacos", []):
            par = frozenset((s["nome"], l["com"]))
            if par in vistos:
                continue
            vistos.add(par)
            coracao = "💞" if l.get("romance", 0) >= 20 else ("💢" if l.get("amizade", 0) < 0 else "🤝")
            lacos.append(f"{coracao} {html.escape(s['nome'])} e {html.escape(l['com'])}: {html.escape(l['tipo'])}")
    if lacos:
        blocos.append("<b>Laços:</b>\n" + "\n".join(lacos))
    return "\n\n".join(blocos)


async def listar_sims(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not mundo.sims:
        await update.effective_message.reply_text("Ninguém mora aqui ainda. Use /gerar.")
        return
    await update.effective_message.reply_text(formatar_casa(mundo.sims), parse_mode=ParseMode.HTML)


async def gerar_casa(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not ADMIN_ID or update.effective_user.id != ADMIN_ID:
        await msg.reply_text("Só quem conduz o experimento pode gerar a casa.")
        return
    descricao = " ".join(context.args).strip()[:MAX_CARACTERES]
    if descricao and bloqueado(descricao):
        await msg.reply_text("🙈 Essa descrição foi barrada pelo filtro.")
        return

    if motor.gerando:
        await msg.reply_text("⏳ Já tem uma casa sendo gerada. Espere ela chegar.")
        return
    await msg.reply_text("🎲 Gerando a casa... (a memória dos Sims antigos será apagada)")
    try:
        sims = await motor.nova_casa(gerador, descricao)
    except LimiteAtingido:
        await msg.reply_text("O Gemini pediu uma pausa (limite). Tente de novo em 1 minuto.")
        return
    except ErroCerebro as e:
        await msg.reply_text(f"😕 Não consegui gerar a casa agora ({e}). Tente de novo em alguns minutos.")
        return

    log.info("Casa nova: %s", sims)
    texto = "🏠 <b>Uma família nova se mudou!</b>\n\n" + formatar_casa(sims)
    if not any(s.get("existente") for s in sims):
        await msg.reply_text("⚠️ O jogo não informou o seu Sim nem o lote (mod desligado?). "
                             "A casa foi inventada sem eles. Ligue npcgen.auto e gere de novo.")
    destinos = {update.effective_chat.id} | ({GRUPO_ID} if GRUPO_ID else set())
    for chat in destinos:
        await context.bot.send_message(chat, texto, parse_mode=ParseMode.HTML)


async def mostrar_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        f"ID deste chat: {update.effective_chat.id}\nSeu ID: {update.effective_user.id}"
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Para conferir se o bot está vivo e o que ele está fazendo."""
    ocupado = "gerando casa" if motor.gerando else ("pensando uma rodada" if motor._lock.locked() else "esperando")
    await update.effective_message.reply_text(
        f"✅ Bot no ar ({ocupado}).\n"
        f"Moradores: {', '.join(s['nome'] for s in mundo.sims) or 'ninguém'}\n"
        f"Rodada: {mundo.rodada} · mensagens na fila: {len(motor.pendentes)}\n"
        f"Chamadas restantes hoje: {motor.chamadas_restantes()}\n"
        f"Modelo da última resposta: {cerebro.ultimo_modelo or '—'}"
    )


async def cota(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(f"Chamadas à IA restantes hoje: {motor.chamadas_restantes()}")


# ---------- mensagens do grupo ----------

async def ao_receber(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global chat_do_jogo
    msg = update.effective_message
    if not grupo_permitido(update) or not msg.text:
        return
    m = ENDERECO.match(msg.text)
    if not m:
        return  # conversa normal do grupo: o bot não se mete
    nome = m.group(1) or m.group(2)
    sim = mundo.achar_sim(nome)
    antigo = mundo.achar_antigo(nome)
    if (sim or antigo) and motor.gerando:
        # A casa está sendo trocada: a mensagem se perderia na mudança.
        await msg.reply_text("🏗️ Uma família nova está se mudando agora. "
                             "Espere ela aparecer aqui e mande de novo.")
        return
    if not sim:
        if antigo:
            nomes = ", ".join(s["nome"] for s in mundo.sims)
            await msg.reply_text(f"📦 {antigo} não mora mais aqui. Moradores agora: {nomes}.")
        else:
            log.info("Ignorada: %r não é morador (moradores: %s)", nome,
                     ", ".join(s["nome"] for s in mundo.sims))
        return  # nome que não é de morador: conversa normal do grupo

    pessoa = update.effective_user
    texto = m.group(3).strip()[:MAX_CARACTERES]
    if bloqueado(texto):
        # Ignorada: não chega aos Sims nem à IA. O texto não é guardado.
        mundo.registrar("bloqueada", de=pessoa.first_name, sim=sim["nome"])
        try:
            await msg.set_reaction("🙈")
        except TelegramError as e:
            log.warning("Não consegui reagir 🙈: %s", e)
        return

    agora = time.monotonic()
    espera = INTERVALO_PESSOA_S - (agora - ultimo_envio.get(pessoa.id, -1e9))
    if espera > 0:
        await msg.reply_text(f"⏳ {pessoa.first_name}, espera {int(espera) + 1}s para falar de novo.")
        return
    ultimo_envio[pessoa.id] = agora
    chat_do_jogo = update.effective_chat.id

    motor.receber(pessoa.first_name, sim["nome"], texto)
    log.info("Mensagem de %s para %s recebida.", pessoa.first_name, sim["nome"])
    try:
        await msg.set_reaction("👀")  # "o Sim ouviu"
    except TelegramError as e:
        # Sem a reação a mensagem chega mesmo assim; avisa no grupo para ninguém mandar de novo.
        log.warning("Não consegui reagir 👀: %s", e)
        await msg.reply_text(f"👀 {sim['nome']} ouviu.")


# ---------- a rodada ----------

def formatar(d) -> str:
    humor = ""
    if d.humor in EMOCOES:
        emoji, nome = EMOCOES[d.humor]
        forca = INTENSIDADES.get(d.intensidade, "")
        humor = f"  {emoji * max(d.intensidade, 1)} {nome}" + (f" ({forca})" if forca else "")
    return (f"📔 <b>{html.escape(d.sim)}</b> {html.escape(descrever(d))}{humor}\n"
            f"<i>{html.escape(d.diario)}</i>")


async def rodada(context: ContextTypes.DEFAULT_TYPE) -> None:
    decisoes = await motor.talvez_rodar()
    if not decisoes or not chat_do_jogo:
        return
    texto = "\n\n".join(formatar(d) for d in decisoes)
    try:
        await context.bot.send_message(chat_do_jogo, texto, parse_mode=ParseMode.HTML)
    except TelegramError as e:
        log.warning("Não consegui postar o diário: %s", e)


async def avisar_inicio(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Roda logo depois que o bot começou a receber mensagens."""
    nomes = ", ".join(s["nome"] for s in mundo.sims)
    texto = ("🤖 <b>Bot inicializado</b> e pronto para receber mensagens.\n"
             + (f"Moradores: {html.escape(nomes)}.\nPara falar com um deles: <i>Nome: mensagem</i>"
                if nomes else "Ainda não tem ninguém na casa (/gerar)."))
    detalhes = (f"\n\n🔧 Mod: {html.escape(SITUACAO_MOD)}\n"
                f"Pasta de troca: <code>{html.escape(str(mundo.troca))}</code>\n"
                f"Chamadas restantes hoje: {motor.chamadas_restantes()}")
    # O grupo recebe o aviso; os detalhes técnicos vão só para quem conduz.
    envios = []
    if GRUPO_ID:
        envios.append((GRUPO_ID, texto + (detalhes if not ADMIN_ID else "")))
    if ADMIN_ID:
        envios.append((ADMIN_ID, texto + detalhes))
    if not envios:
        log.warning("Sem GRUPO_ID nem ADMIN_ID no .env: não tenho para onde mandar o aviso de início.")
    for chat, msg in envios:
        try:
            await context.bot.send_message(chat, msg, parse_mode=ParseMode.HTML)
        except TelegramError as e:
            # Comum no ADMIN_ID: o bot só fala no privado com quem já mandou /start a ele.
            log.warning("Não consegui mandar o aviso de início para %s: %s", chat, e)


def main() -> None:
    desligar_quickedit()
    # concurrent_updates: sem isso o bot atende uma mensagem por vez, e as
    # mensagens do grupo ficavam presas atrás de um /gerar esperando o Gemini.
    app = Application.builder().token(TOKEN).concurrent_updates(True).build()
    app.add_handler(CommandHandler(["start", "ajuda"], ajuda))
    app.add_handler(CommandHandler("sims", listar_sims))
    app.add_handler(CommandHandler("gerar", gerar_casa))
    app.add_handler(CommandHandler("id", mostrar_id))
    app.add_handler(CommandHandler("cota", cota))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUPS, ao_receber))
    app.job_queue.run_repeating(rodada, interval=RODADA_S, first=RODADA_S)
    # A fila de tarefas só começa depois que o bot já está recebendo mensagens.
    app.job_queue.run_once(avisar_inicio, when=1)
    log.info("Bot no ar. Moradores: %s", ", ".join(s["nome"] for s in mundo.sims) or "nenhum (use /gerar)")
    if not ADMIN_ID:
        log.warning("ADMIN_ID vazio: ninguém consegue usar /gerar. Mande /id ao bot e preencha o .env.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
