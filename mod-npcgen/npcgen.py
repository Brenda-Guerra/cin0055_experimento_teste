# npcgen.py — mod do The Sims 4 (roda DENTRO do jogo, no Python 3.7 dele).
#
# Conversa com o bot do Telegram por arquivos na pasta troca/:
#   casa.json      <- a casa gerada pela IA (/gerar). O mod cria esses Sims.
#   comandos.json  <- as ações que a IA decidiu. O mod faz os Sims executarem.
#
# Console de cheats (Ctrl+Shift+C):
#   npcgen.auto                    -> liga/desliga o modo automático (a cada 3 s:
#                                     cria a casa nova se houver e executa as ações)
#   npcgen.criar                   -> cria agora os Sims da última casa gerada
#   npcgen.limpar                  -> remove do lote e da família todos menos o Sim que você controla
#   npcgen.executar                -> executa agora as ações novas do bot
#   npcgen.ola                     -> o mod está vivo? onde fica a pasta troca?
#   npcgen.sims                    -> quais Sims o mod enxerga no lote
#   npcgen.tracos                  -> diagnóstico: traços/aspirações achados no jogo
#   npcgen.listar <tipo> [texto]   -> nomes internos do jogo (tracos, aspiracoes, interacoes)
#   npcgen.trilhas                 -> etapas de cada trilha de aspiração (para conferir o mapa)
#   npcgen.veraspiracao            -> põe no Sim ativo uma aspiração do mapa por vez (repita para avançar)
#   npcgen.buscar <texto>          -> procura interações do jogo pelo nome (mostra o ID)
#   npcgen.acoes                   -> quais interações de cada ação existem no jogo
#   npcgen.catalogo                -> salva em catalogo.json TODAS as interações do jogo, com ID
#   npcgen.mapear                  -> salva em opcoes.json o que os objetos do lote oferecem
#                                     (o automático refaz ao trocar de lote e a cada minuto)
#   npcgen.jogo                    -> o que o /gerar vai saber do seu Sim e do lote (jogo.json)
#   npcgen.lacos                   -> apresenta os moradores e (re)aplica as barras de
#                                     amizade/romance do /gerar (o automático faz sozinho)
#   npcgen.estado                  -> o que o mod está vendo agora (humor, ações, necessidades)
#                                     e salva em estado.json (o automático faz isso a cada 3 s)
#   npcgen.humores                 -> qual moodlet o mod usa para cada emoção
#   npcgen.humor <emoção> <Sim> [1|2|3] [motivo] -> põe uma emoção no Sim
#                                     (ex.: npcgen.humor irritado Ana 3 rumor+jealous)
#   npcgen.tons [tom]              -> interações sociais achadas para cada tom de conversa
#   npcgen.testar <ação|nome|ID> <Sim> <Alvo> -> testa uma ação à mão
#                                     ex.: npcgen.testar abracar Ana Rui
#
# Erros vão para troca/npcgen_log.txt.

import json
import os
import time
import traceback

import services
import sims4.commands

# O .ts4script fica em Mods/npcgen/npcgen.ts4script; a pasta de troca fica ao lado.
PASTA_MOD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASTA_TROCA = os.path.join(PASTA_MOD, 'troca')
ARQ_COMANDOS = os.path.join(PASTA_TROCA, 'comandos.json')
ARQ_EXECUTADO = os.path.join(PASTA_TROCA, 'executado.json')
ARQ_CASA = os.path.join(PASTA_TROCA, 'casa.json')
ARQ_CRIADOS = os.path.join(PASTA_TROCA, 'criados.json')
ARQ_LOG = os.path.join(PASTA_TROCA, 'npcgen_log.txt')

LIMITE_CASA = 8  # o jogo não deixa mais de 8 Sims numa casa
ESPERA_SAIDA = 5  # voltas (~15 s) esperando a casa anterior sair antes de criar a nova

# Ação do bot -> interações do jogo, por NOME (ou ID), em ordem de preferência:
# se a primeira não existir ou o jogo recusar, tenta a próxima.
# Quase todas são "mixers" sociais: só rodam dentro de uma conversa, então o
# mod inicia a conversa (CONVERSA) e dispara o mixer logo depois.
# Lista vazia = o Sim não faz nada (fica na dele).
CONVERSA = 'sim_Chat'
INTERACOES = {
    'conversar': ['sim_Chat'],
    'elogiar': ['mixer_social_ComplimentOutfit_targeted_Friendly_alwaysOn_skills',
                'mixer_social_HeartfeltCompliment_targeted_friendly_emotionSpecific'],
    # Nomes conferidos no catálogo do jogo em 29/10 (Argue/Insult/Disagree não existem).
    'discutir': ['mixer_social_YellAT_targeted_mean',
                 'mixer_social_RileUp_targeted_mean_alwaysOn',
                 'mixer_social_ChewOut_targeted_mean_emotionSpecific',
                 'mixer_social_InsultFace_targeted_mean_emotionSpecific',
                 'mixer_social_Jeer_targeted_mean_middleScore',
                 'mixer_social_Intimidate_targeted_mean_middleScore',
                 'mixer_social_DismissGoodness_targeted_mean_alwaysOn',
                 'mixer_social_MockOutfit_targeted_Mean_middleScore'],
    'fofocar': ['mixer_social_GossipAbout_targeted_friendly_alwaysOn',
                'mixer_social_SpreadMeanGossip_targeted_friendly_alwaysOn'],
    'flertar': ['mixer_social_Flirt_targeted_romance_alwaysOn'],
    'abracar': ['mixer_social_Hug_targeted_Friendly_MiddleScore',
                'mixer_social_Hug_Friendly_Middlescore_NoMoodTest',
                'mixer_social_BroHug_targeted_Friendly_alwaysOn'],
    'pedir_desculpas': ['mixer_social_Apologize_targeted_friendly_lowScore',
                        'mixer_social_BegForgiveness_targeted_friendly_lowScore',
                        'mixer_social_DeclareTruce_targeted_friendly_lowScore'],
    'contar_piada': ['mixer_social_TryOutMaterial_targeted_funny_alwaysOn',
                     'mixer_socials_GoofAround_targeted_Funny_alwaysOn',
                     'mixer_social_DoAnImpression_targeted_funny_alwaysOn',
                     'mixer_social_KnockKnockJoke_targeted_funny_alwaysOn_skills',
                     'mixer_socials_TellJoke_group_Funny_alwaysOn'],
    'ignorar': [],
    'ficar_sozinho': [],
}
# Emoção do bot -> trecho do nome do humor no jogo (Mood_Angry, Mood_Sad...).
# O mod procura um moodlet temporário desse humor e põe no Sim.
EMOCOES_JOGO = {
    'feliz': ['happy'], 'triste': ['sad'], 'irritado': ['angry'],
    'tenso': ['tense', 'stress'], 'envergonhado': ['embarrass'],
    'desconfortavel': ['uncomfortable'], 'confiante': ['confident'],
    'energizado': ['energized', 'energised'], 'flertante': ['flirty'],
    'focado': ['focused'], 'inspirado': ['inspired'], 'brincalhao': ['playful'],
    'entediado': ['bored'], 'confuso': ['dazed'],
}
# Moodlets preferidos para cada emoção, em ordem (nomes vistos no jogo em
# 29/10). De origem social sempre que possível: "irritado por um boato",
# "pilhado", "sementes da dúvida"... Se nenhum existir, o mod procura sozinho.
HUMORES_PREFERIDOS = {
    'feliz': ['buff_Social_Media_Moodlets_Superior_Happy', 'Cowplant_Essence_Buff_Happy'],
    'triste': ['Buff_Sad_MelancholyThoughts', 'buff_Social_Media_Moodlets_Superior_Sad',
               'Cowplant_Essence_Buff_Sad'],
    'irritado': ['Buff_AngryAboutViciousRumor', 'Buff_RiledUp_Target',
                 'buff_Social_Media_Moodlets_Superior_Angry', 'Cowplant_Essence_Buff_Angry'],
    'tenso': ['Buff_SeedsOfDoubt', 'buff_Social_Media_Moodlets_Superior_Stressed',
              'Cowplant_Essence_Buff_Stressed'],
    'envergonhado': ['buff_Social_Media_Moodlets_Superior_Embarrassed', 'Cowplant_Essence_Buff_Embarrassed'],
    'desconfortavel': ['buff_Social_Media_Moodlets_Superior_Uncomfortable', 'Cowplant_Essence_Buff_Uncomfortable'],
    'confiante': ['buff_Social_Media_Moodlets_Superior_Confident', 'Cowplant_Essence_Buff_Confident'],
    'energizado': ['buff_Social_Media_Moodlets_Superior_Energized', 'Cowplant_Essence_Buff_Energized'],
    'flertante': ['buff_Social_Media_Moodlets_Superior_Flirty', 'Buff_Memory_flirty', 'Cowplant_Essence_Buff_Flirty'],
    'focado': ['buff_Social_Media_Moodlets_Superior_Focused', 'Cowplant_Essence_Buff_Focused', 'Buff_PlayChess_FocusedMed'],
    'inspirado': ['buff_Social_Media_Moodlets_Superior_Inspired', 'Cowplant_Essence_Buff_Inspired',
                  'Buff_Inspired_SawSomeStars'],
    'brincalhao': ['Buff_FunniestJoke_Playful', 'buff_Social_Media_Moodlets_Superior_Playful',
                   'Cowplant_Essence_Buff_Playful'],
    'entediado': ['buff_Social_Media_Moodlets_Superior_Bored', 'Cowplant_Essence_Buff_Bored'],
    # Confuso tem poucas fontes no jogo (log de 29/10): fumaça, susto do foguete,
    # essência de Vacaplanta, fantasia de urso (essa some sem a fantasia).
    'confuso': ['buff_Social_Media_Moodlets_Superior_Dazed', 'buff_Object_OffTheGrid_Fumes',
                'Buff_Object_Rocketship_EscapedCrash', 'Cowplant_Essence_Buff_Sloshed',
                'Cowplant_Essence_Buff_Dazed', 'Buff_Clothing_DazedBear'],
}
# Para forçar outro moodlet numa emoção (veja as opções com npcgen.humores):
# ex.: 'irritado': 'buff_Relationship_NewEnemy'
HUMORES_FIXOS = {}
# O que importa é o humor certo, não de onde vem o moodlet: TODOS os moodlets
# temporários da emoção são opções. Só ficam de fora os que têm efeito
# colateral (gravidez, morte, ocultismo, doença) ou conteúdo adulto.
BUFF_FORA = ('debug', 'cheat', 'pregnan', 'death', 'dying', 'ghost', 'vampire', 'werewolf',
             'spellcaster', 'mermaid', 'alien', 'plantsim', 'servo', 'illness', 'sick', 'curse',
             'possess', 'woohoo', 'naked', 'nude', 'drunk', 'hangover', 'npc_', 'hidden')
MAX_TENTATIVAS_TOM = 15
MAX_MOODLETS = 5  # se o jogo não mostrar a emoção pedida, empilha até este tanto  # interações do tom testadas antes de cair no padrão da ação

# Tom de conversa do bot -> PALAVRAS do nome dos mixers sociais do jogo.
# O nome é quebrado em palavras (mixer_social_ComplainAboutProblems_targeted_friendly
# -> complain, about, problems, targeted, friendly...), e a palavra precisa
# começar com o trecho: "sad" não casa mais com "ExpressAdmiration".
TONS_JOGO = {
    'amigavel': ['friendly'],
    'maldoso': ['mean'],
    'travesso': ['mischief', 'prank'],
    'engracado': ['funny', 'joke', 'goof', 'impression', 'imitate'],
    'romantico': ['romance', 'flirt'],
    'triste': ['sad', 'cry', 'vent', 'mope', 'insecurities', 'burden', 'problems', 'reassurance', 'sob'],
    'irritado': ['rant', 'yell', 'chew', 'provoke', 'throw', 'rile', 'angry', 'furious'],
    'tenso': ['fears', 'scared', 'nervous', 'worried', 'worry', 'anxious', 'tense', 'stress',
              'insecurities', 'reassurance', 'doubt'],
    # O mais explosivo: gritar, jogar bebida, brigar, declarar inimizade.
    'furioso': ['fight', 'throw', 'yell', 'chew', 'declare', 'denounce', 'intimidate', 'rile'],
}
# Nunca escolhidos por tom: além de beijo e afins (a casa é para todas as
# idades: romance vai até flerte e abraço), os que dependem de situação
# específica, mexem com dinheiro/mudança, ou terminam a conversa.
TOM_FORA = ('woohoo', 'tryforbaby', 'try_for_baby', 'makeout', 'make_out', 'sexy', 'strip',
            'naked', 'nude', 'streak', 'dirty', 'risque', 'seduc', 'kiss', 'intimate', 'cuddle',
            'massage', 'inbed', 'enticing', 'makeamove', 'leavespouse', 'whisperseduct',
            'propose', 'marry', 'promisering', 'breakup', 'break_up', 'divorce', 'sexual',
            'pregnan', 'duedate', 'bignews', 'loan', 'repay', 'movein', 'move_in', 'saygoodbye',
            'pickpocket', 'burglar', 'police', 'ghost', 'villain', 'death', 'picker', 'debug',
            'cheat', 'askto', 'ask_to', 'invite', 'askondate', 'pet_', 'child', 'toddler', 'baby')
# Fora de um tom específico (o "amigável" não pode ser pegadinha nem briga).
TOM_FORA_POR_TOM = {
    'amigavel': ('prank', 'complain', 'spreadmean', 'fight', 'rant', 'trashtalk', 'blameenemy', 'crime', 'cursed'),
    'furioso': ('truce', 'practicefighting', 'independence'),
}
# Interações que só funcionam em situação específica (emprego, evento, idade,
# habilidade...): tentadas depois das gerais, que quase sempre funcionam.
CONTEXTO_ESPECIFICO = ('skills', 'career', 'situation', 'event', 'neighbor', 'teen', 'trait',
                       'costume', 'stc', 'athlete', 'bills', 'aspiration', 'dlc', 'ev0', 'evt',
                       'r4', 'writingjournalism', 'loyal', 'relationship', 'sentiments')
ACOES_COM_TOM = ('conversar', 'discutir')

# Se tudo da ação falhar, o mod tenta qualquer interação deste clima.
RESERVA_DA_ACAO = {'discutir': 'maldoso', 'elogiar': 'amigavel', 'fofocar': 'amigavel',
                   'flertar': 'romantico', 'abracar': 'amigavel', 'pedir_desculpas': 'amigavel',
                   'contar_piada': 'engracado'}
MAX_ESPERA_CONVERSA = 10  # voltas do automático (~3 s cada) esperando a conversa começar

# Mapa do lote: interações que os objetos da casa oferecem (troca/opcoes.json).
# O bot manda essa lista para a IA, que pode escolher "usar_objeto".
ARQ_OPCOES = os.path.join(PASTA_TROCA, 'opcoes.json')
# Trechos de nome que ficam de fora: depuração, cheats, menus de escolha
# (picker abre uma janela para o jogador) e modo construção.
IGNORAR_NO_MAPA = ('debug', 'cheat', 'picker', 'buildbuy', 'build_buy', 'cas_', 'test_', 'tutorial')
MAPEAR_A_CADA = 20  # voltas do automático (~1 min)

# Etiqueta usada pela IA -> nomes prováveis do traço no jogo (sem o "trait_").
# Se um não for achado, `npcgen.tracos` mostra qual; corrija aqui.
TRACOS_JOGO = {
    'Ambicioso': ['Ambitious'], 'Alegre': ['Cheerful'], 'Criativo': ['Creative'],
    'Gênio': ['Genius'], 'Melancólico': ['Gloomy'], 'Brincalhão': ['Goofball'],
    'Esquentado': ['HotHeaded', 'Hot_Headed'], 'Romântico': ['Romantic'],
    'Autoconfiante': ['SelfAssured', 'Self_Assured'], 'Malvado': ['Evil'],
    'Bondoso': ['Good'], 'Maldoso': ['Mean'], 'Ciumento': ['Jealous'],
    'Solitário': ['Loner'], 'Extrovertido': ['Outgoing'], 'Esnobe': ['Snob'],
    'Ama a Família': ['FamilyOriented', 'Family_Oriented'],
    'Odeia Crianças': ['HatesChildren', 'Hates_Children'],
    'Excêntrico': ['Insane', 'Erratic'], 'Ativo': ['Active'], 'Infantil': ['Childish'],
    'Desastrado': ['Clumsy'], 'Guloso': ['Glutton'], 'Preguiçoso': ['Lazy'],
    'Materialista': ['Materialistic'], 'Organizado': ['Neat'],
    'Perfeccionista': ['Perfectionist'], 'Desleixado': ['Slob'],
    'Ama a Natureza': ['LovesOutdoors', 'Loves_Outdoors', 'Outdoors'],
    'Amante de Arte': ['ArtLover', 'Art_Lover'], 'Rato de Biblioteca': ['Bookworm'],
    'Gourmet': ['Foodie'], 'Nerd': ['Geek'], 'Ama Música': ['MusicLover', 'Music_Lover'],
    'Cleptomaníaco': ['Kleptomaniac'], 'Vegetariano': ['Vegetarian'],
}

# Etiqueta (nome que o jogo mostra em português) -> trilha de aspiração.
# Conferido no jogo com `npcgen.veraspiracao` em 21/10. Food_B e Love_A não
# foram vistos no painel: são a única outra aspiração da categoria no jogo-base.
ASPIRACOES_JOGO = {
    'Fisiculturista': ['Track_Athletic_A'],
    'Pintor Extraordinário': ['Track_Creativity_A'],
    'Autor Best-Seller': ['Track_Creativity_B'],
    'Gênio Musical': ['Track_Creativity_C'],
    'Inimigo Público': ['Track_Deviance_A'],
    'Rei das Travessuras': ['Track_Deviance_B'],
    'Família Grande e Feliz': ['Track_Family_B'],
    'Mestre da Mixologia': ['Track_Food_A'],
    'Mestre Cuca': ['Track_Food_B'],
    'Fabulosamente Rico': ['Track_Fortune_A'],
    'Barão das Mansões': ['Track_Fortune_B'],
    'Sim da Renascença': ['Track_Knowledge_A'],
    'Gênio da Informática': ['Track_Knowledge_B'],
    'Cérebro Nerd': ['Track_Knowledge_C'],
    'Alma Gêmea': ['Track_Love_A'],
    'Romântico em Série': ['Track_Love_B'],
    'Botânico Autônomo': ['Track_Nature_A'],
    'Estrela da Comédia': ['Track_Popularity_A'],
    'Amigo do Mundo': ['Track_Popularity_B'],
    'Grande Festeiro': ['Track_Popularity_C'],
}


# ---------- utilidades ----------

def _log(texto):
    try:
        if not os.path.isdir(PASTA_TROCA):
            os.makedirs(PASTA_TROCA)
        with open(ARQ_LOG, 'a', encoding='utf-8') as f:
            f.write(str(texto) + '\n')
    except Exception:
        pass


def _ler_json(caminho, padrao):
    try:
        with open(caminho, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return padrao


def _escrever_json(caminho, dados):
    tmp = caminho + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(dados, f, ensure_ascii=False)
    os.replace(tmp, caminho)


def _sims_no_lote():
    """{'ana': (sim_info, sim)} para cada Sim instanciado no lote atual."""
    sims = {}
    for info in services.sim_info_manager().get_all():
        sim = info.get_sim_instance()
        if sim is not None:
            sims[info.first_name.strip().lower()] = (info, sim)
    return sims


def _rodar(_connection, func, *args):
    """Qualquer erro vira mensagem no console e linha no log, sem travar o jogo."""
    output = sims4.commands.CheatOutput(_connection)
    try:
        func(output, *args)
    except Exception:
        erro = traceback.format_exc()
        _log(erro)
        output('npcgen: ERRO, detalhes em ' + ARQ_LOG)
        output(erro.strip().splitlines()[-1])


def _chave(nome):
    return nome.lower().replace('_', '').replace('-', '').replace(' ', '')


_CACHE = {}


def _resolver(tipo, rotulo, candidatos, prefixo):
    """Acha o tuning do jogo para `rotulo`: primeiro nome exato, depois o
    nome mais curto que contenha um dos candidatos. None se não achar."""
    if (tipo, rotulo) in _CACHE:
        return _CACHE[(tipo, rotulo)]
    import sims4.resources
    gerente = services.get_instance_manager(getattr(sims4.resources.Types, tipo))
    tabela = {_chave(t.__name__): t for t in gerente.types.values()}
    achado = None
    for c in candidatos:
        achado = tabela.get(_chave(prefixo + c))
        if achado is not None:
            break
    if achado is None:
        parecidos = sorted(
            (len(k), k) for k in tabela
            if k.startswith(_chave(prefixo)) and any(_chave(c) in k for c in candidatos)
        )
        achado = tabela[parecidos[0][1]] if parecidos else None
    _CACHE[(tipo, rotulo)] = achado
    return achado


def _traco(rotulo):
    return _resolver('TRAIT', rotulo, TRACOS_JOGO.get(rotulo, []), 'trait_')


def _aspiracao(rotulo):
    return _resolver('ASPIRATION_TRACK', rotulo, ASPIRACOES_JOGO.get(rotulo, []), '')


_INTERACOES_POR_NOME = {}


def _interacao(nome_ou_id):
    """Acha a interação do jogo pelo nome (sem diferenciar maiúsculas) ou pelo ID."""
    import sims4.resources
    gerente = services.get_instance_manager(sims4.resources.Types.INTERACTION)
    if isinstance(nome_ou_id, int) or str(nome_ou_id).isdigit():
        return gerente.get(int(nome_ou_id))
    if not _INTERACOES_POR_NOME:
        for t in gerente.types.values():
            _INTERACOES_POR_NOME[t.__name__.lower()] = t
    return _INTERACOES_POR_NOME.get(str(nome_ou_id).lower())


def _eh_mixer(afordancia):
    try:
        from interactions.base.mixer_interaction import MixerInteraction
        return issubclass(afordancia, MixerInteraction)
    except Exception:
        return 'mixer' in afordancia.__name__.lower()


def _contexto(sim):
    from interactions.context import InteractionContext
    from interactions.priority import Priority
    return InteractionContext(sim, InteractionContext.SOURCE_SCRIPT, Priority.High)


def _empurrar_super(sim, afordancia, alvo_sim):
    """Interação 'grande' (super interação), como sim_Chat."""
    resultado = sim.push_super_affordance(afordancia, alvo_sim, _contexto(sim))
    return bool(resultado), '{} -> {}'.format(afordancia.__name__, resultado)


def _conversa_com(sim, alvo_sim):
    """A super interação social em andamento entre sim e alvo, se houver.
    Conversa com outra pessoa não serve: aí o mod inicia uma nova com o alvo."""
    try:
        interacoes = list(sim.si_state)
    except Exception:
        _log('si_state\n' + traceback.format_exc())
        return None
    for si in interacoes:
        if not getattr(si, 'is_social', False):
            continue
        grupo = getattr(si, 'social_group', None)
        try:
            no_grupo = grupo is not None and alvo_sim in grupo
        except Exception:
            no_grupo = False
        if si.target is alvo_sim or no_grupo:
            return si
    return None


def _empurrar_mixer(sim, mixer, alvo_sim, conversa):
    """Ação social (mixer) dentro de uma conversa que já está acontecendo."""
    from interactions.aop import AffordanceObjectPair
    aop = AffordanceObjectPair(mixer, alvo_sim, conversa.affordance, conversa)
    resultado = aop.test_and_execute(_contexto(sim))
    return bool(resultado), '{} -> {}'.format(mixer.__name__, resultado)


def _objetos_do_lote():
    """Objetos (não Sims) que estão no lote ativo."""
    for obj in list(services.object_manager().get_all()):
        if getattr(obj, 'is_sim', False):
            continue
        try:
            if not obj.is_on_active_lot():
                continue
        except Exception:
            continue
        yield obj


def _interacoes_do_objeto(obj, contexto=None):
    try:
        return list(obj.super_affordances(contexto))
    except Exception:
        try:
            return list(obj.super_affordances())
        except Exception:
            return []


ARQ_CATALOGO = os.path.join(PASTA_TROCA, 'catalogo.json')


def catalogo(output):
    """Salva em catalogo.json TODAS as interações do jogo, com ID e tipo.
    Referência completa; não depende do lote."""
    import sims4.resources
    gerente = services.get_instance_manager(sims4.resources.Types.INTERACTION)
    itens = []
    for t in gerente.types.values():
        itens.append({
            'id': getattr(t, 'guid64', None),
            'nome': t.__name__,
            'tipo': 'mixer' if _eh_mixer(t) else 'super',
            'jogador_pode_escolher': bool(getattr(t, 'allow_user_directed', True)),
        })
    itens.sort(key=lambda x: x['nome'].lower())
    _escrever_json(ARQ_CATALOGO, {'interacoes': itens})
    output('npcgen: {} interações no catálogo do jogo. Salvo em catalogo.json'.format(len(itens)))


def _lote_atual():
    try:
        return services.current_zone_id()
    except Exception:
        return None


def mapear(output):
    """Salva em opcoes.json as interações que os objetos do lote oferecem."""
    client = services.client_manager().get_first_client()
    ativo = client.active_sim if client is not None else None
    try:
        contexto = _contexto(ativo) if ativo is not None else None
    except Exception:
        contexto = None
    achadas, n_objetos = {}, 0
    for obj in _objetos_do_lote():
        n_objetos += 1
        objeto = type(obj).__name__
        for aff in _interacoes_do_objeto(obj, contexto):
            nome = aff.__name__
            guid = getattr(aff, 'guid64', None)
            if guid is None or not getattr(aff, 'allow_user_directed', True):
                continue
            if any(p in nome.lower() for p in IGNORAR_NO_MAPA):
                continue
            item = achadas.setdefault(guid, {'id': guid, 'nome': nome, 'objetos': []})
            if objeto not in item['objetos'] and len(item['objetos']) < 3:
                item['objetos'].append(objeto)
    # As oferecidas por mais tipos de objeto primeiro (as mais comuns da casa).
    lista = sorted(achadas.values(), key=lambda x: (-len(x['objetos']), x['nome'].lower()))
    _escrever_json(ARQ_OPCOES, {'lote': _lote_atual(), 'interacoes': lista})
    output('npcgen: {} objetos no lote, {} interações possíveis. Salvo em opcoes.json'.format(
        n_objetos, len(lista)))


def _fazer_objeto(sim, nome_ou_id):
    """Faz o Sim usar um objeto do lote que ofereça essa interação."""
    aff = _interacao(nome_ou_id)
    if aff is None:
        return 'falhou', 'interação {} não existe'.format(nome_ou_id)
    if _eh_mixer(aff):
        return 'falhou', '{} é social; use com um alvo'.format(aff.__name__)
    erros = []
    for obj in _objetos_do_lote():
        if aff not in _interacoes_do_objeto(obj):
            continue
        ok, msg = _empurrar_super(sim, aff, obj)
        if ok:
            return 'ok', '{} em {}'.format(msg, type(obj).__name__)
        erros.append(msg)
        if len(erros) >= 3:
            break
    if not erros:
        return 'falhou', 'nenhum objeto do lote oferece {}'.format(aff.__name__)
    return 'falhou', erros[0]


# ---------- humor (moodlets) ----------

_BUFFS = {}         # emoção -> todos os moodlets candidatos
_HUMOR_POSTO = {}   # sim_id -> moodlets que o mod pôs (são trocados na próxima emoção)


def _candidatos_humor(emocao):
    """Todos os moodlets do jogo daquela emoção (temporários e visíveis; se
    não houver, afrouxa). HUMORES_FIXOS manda; HUMORES_PREFERIDOS vêm antes."""
    if emocao in _BUFFS:
        return _BUFFS[emocao]
    import sims4.resources
    gerente = services.get_instance_manager(sims4.resources.Types.BUFF)
    chaves = EMOCOES_JOGO.get(emocao, [])
    por_nome = {b.__name__.lower(): b for b in gerente.types.values()}
    fixo = HUMORES_FIXOS.get(emocao)
    if fixo and fixo.lower() in por_nome:
        _BUFFS[emocao] = [por_nome[fixo.lower()]]
        return _BUFFS[emocao]
    preferidos = [por_nome[n.lower()] for n in HUMORES_PREFERIDOS.get(emocao, []) if n.lower() in por_nome]
    todos = []
    for b in gerente.types.values():
        humor = getattr(b, 'mood_type', None)
        if humor is None or not any(c in humor.__name__.lower() for c in chaves):
            continue
        if any(x in b.__name__.lower() for x in BUFF_FORA):
            continue
        todos.append((b, getattr(b, 'mood_weight', 0) or 0))
    bons = [(b, p) for b, p in todos
            if p >= 1 and getattr(b, 'visible', True)
            and getattr(b, '_temporary_commodity_info', None) is not None]
    escolhidos = bons or [(b, p) for b, p in todos if p >= 1] or todos
    escolhidos.sort(key=lambda bp: bp[0].__name__)
    _BUFFS[emocao] = preferidos + [b for b, _ in escolhidos if b not in preferidos]
    return _BUFFS[emocao]


def _combina(palavra, palavras_buff):
    """'jealous' combina com 'jealousy'; 'rumor' com 'rumor'."""
    if len(palavra) < 3:
        return False
    for w in palavras_buff:
        if len(w) >= 3 and (w.startswith(palavra[:5]) or palavra.startswith(w[:5])):
            return True
    return False


def _ordenar_humor(emocao, motivo=''):
    """Os candidatos, do que mais combina com o motivo (palavras em inglês
    vindas da IA) ao que menos. Empate (ou sem motivo): os preferidos, e
    depois em ordem aleatória."""
    import random
    candidatos = _candidatos_humor(emocao)
    palavras = [p for p in str(motivo or '').lower().split() if p]
    preferidos = set(n.lower() for n in HUMORES_PREFERIDOS.get(emocao, []))

    def nota(b):
        acertos = sum(1 for p in palavras if _combina(p, _palavras(b.__name__)))
        peso = getattr(b, 'mood_weight', 1) or 1
        return (-acertos, b.__name__.lower() not in preferidos, -min(peso, 3), random.random())
    return sorted(candidatos, key=nota)


def _tirar_buff(info, buff):
    for alvo, metodo in ((info, 'remove_buff_by_type'), (getattr(info, 'Buffs', None), 'remove_buff_by_type')):
        f = getattr(alvo, metodo, None)
        if f is not None:
            try:
                f(buff)
                return
            except Exception:
                pass


def _por_buff(info, buff):
    for alvo, metodo in ((info, 'add_buff_from_op'), (getattr(info, 'Buffs', None), 'add_buff')):
        f = getattr(alvo, metodo, None)
        if f is None:
            continue
        try:
            resultado = f(buff, buff_reason=None)
        except TypeError:
            resultado = f(buff)
        if resultado is not False:
            return True
    return False


def _aplicar_humor(info, emocao, intensidade=1, motivo=''):
    """Põe no Sim moodlets da emoção pedida, tirando os que o mod pôs antes.
    Intensidade 2 ou 3 = 2 ou 3 moodlets DIFERENTES da mesma emoção: o jogo
    soma os pesos, e o Sim fica "muito irritado" em vez de só "irritado"."""
    candidatos = _ordenar_humor(emocao, motivo)
    if not candidatos:
        return 'falhou', 'nenhum moodlet de {} achado'.format(emocao)
    for anterior in _HUMOR_POSTO.pop(info.sim_id, []):
        _tirar_buff(info, anterior)
    try:
        quantos = min(max(int(intensidade or 1), 1), 3)
    except (TypeError, ValueError):
        quantos = 1
    postos = []
    restantes = list(candidatos)

    def por_mais_um():
        while restantes:
            buff = restantes.pop(0)
            try:
                if _por_buff(info, buff) and _tem_buff(info, buff):
                    postos.append(buff)
                    return True
                _log('humor {}: {} não ficou no Sim'.format(emocao, buff.__name__))
            except Exception:
                _log('humor {} {}\n'.format(emocao, buff.__name__) + traceback.format_exc())
        return False

    while len(postos) < quantos and por_mais_um():
        pass
    # Confere o que o jogo mostra: outro humor forte (tensão das fofocas...)
    # pode estar ganhando. Aí empilha mais moodlets da emoção pedida.
    while postos and not _humor_bate(info, emocao) and len(postos) < MAX_MOODLETS and por_mais_um():
        pass
    if not postos:
        return 'falhou', 'o jogo recusou os moodlets de {}'.format(emocao)
    _HUMOR_POSTO[info.sim_id] = postos
    nomes = ', '.join(b.__name__ for b in postos)
    if not _humor_bate(info, emocao):
        return 'fraco', '{} x{} ({}), mas o jogo mostra {}'.format(emocao, len(postos), nomes, _humor_atual(info))
    return 'ok', '{} x{} ({})'.format(emocao, len(postos), nomes)


def _humor_atual(info):
    try:
        humor = info.get_mood()
        return humor.__name__ if humor is not None else '?'
    except Exception:
        return '?'


def _humor_bate(info, emocao):
    atual = _humor_atual(info).lower()
    return atual == '?' or any(c in atual for c in EMOCOES_JOGO.get(emocao, []))


def _tem_buff(info, buff):
    """O moodlet continua no Sim? (alguns o jogo tira na hora, como os de roupa)"""
    try:
        for b in list(info.Buffs):
            if getattr(b, 'buff_type', type(b)) is buff:
                return True
        return False
    except Exception:
        return True  # sem como conferir: confia que entrou


# ---------- tom da conversa ----------

_MIXERS_TOM = {}


def _palavras(nome):
    """'mixer_social_ComplainAboutProblems_targeted' -> {'mixer', 'social', 'complain', 'about', 'problems', 'targeted'}"""
    import re
    return {w.lower() for parte in nome.split('_')
            for w in re.findall(r'[A-Z]+(?![a-z])|[A-Z]?[a-z]+|[0-9]+', parte)}


def _mixers_do_tom(tom):
    """Mixers sociais (com alvo) do jogo cujo nome combina com o tom."""
    if tom in _MIXERS_TOM:
        return _MIXERS_TOM[tom]
    import sims4.resources
    gerente = services.get_instance_manager(sims4.resources.Types.INTERACTION)
    chaves = TONS_JOGO.get(tom, [])
    achados = []
    for t in gerente.types.values():
        nome = t.__name__.lower()
        if not nome.startswith('mixer_social') or 'targeted' not in nome:
            continue
        palavras = _palavras(t.__name__)
        if not any(p.startswith(c) for c in chaves for p in palavras):
            continue
        if any(x in nome for x in TOM_FORA + IGNORAR_NO_MAPA + TOM_FORA_POR_TOM.get(tom, ())):
            continue
        if not getattr(t, 'allow_user_directed', True) or not _eh_mixer(t):
            continue
        achados.append(t)
    achados.sort(key=lambda t: t.__name__)
    _MIXERS_TOM[tom] = achados
    return achados


def _candidatas(acao, tom, motivo=''):
    """Interações a tentar, em ordem: as do tom e depois as da ação. Entre as
    do tom: primeiro as que combinam com o motivo (ex.: 'jealous'), depois as
    gerais (funcionam em quase toda situação), sorteadas."""
    import random
    lista = []
    if tom and acao in ACOES_COM_TOM:
        palavras = [p for p in str(motivo or '').lower().split() if p]

        def nota(t):
            nome = t.__name__.lower()
            acertos = sum(1 for p in palavras if _combina(p, _palavras(t.__name__)))
            return (-acertos, any(x in nome for x in CONTEXTO_ESPECIFICO), random.random())
        lista += sorted(_mixers_do_tom(tom), key=nota)[:MAX_TENTATIVAS_TOM]
    lista += [c for c in INTERACOES.get(acao, []) if c not in lista]
    reserva = RESERVA_DA_ACAO.get(acao)
    if reserva and reserva != tom:
        gerais = [t for t in _mixers_do_tom(reserva)
                  if not any(x in t.__name__.lower() for x in CONTEXTO_ESPECIFICO)]
        random.shuffle(gerais)
        lista += [t for t in gerais if t not in lista][:MAX_TENTATIVAS_TOM]
    return lista


_PENDENTES = []  # ações esperando a conversa começar


def _fazer_acao(sim, acao, alvo_sim, nome, alvo_nome, pode_iniciar_conversa=True, tom=None, motivo=''):
    """Tenta as interações da ação em ordem (com tom: primeiro as do tom).
    Devolve (estado, mensagem), com estado em: ok, esperando, nada, falhou."""
    candidatas = _candidatas(acao, tom, motivo)
    if not candidatas or alvo_sim is None:
        return 'nada', 'fica na sua'
    erros = []
    for candidata in candidatas:
        afordancia = candidata if not isinstance(candidata, (str, int)) else _interacao(candidata)
        if afordancia is None:
            erros.append('{} não existe'.format(candidata))
            continue
        if not _eh_mixer(afordancia):
            ok, msg = _empurrar_super(sim, afordancia, alvo_sim)
            if ok:
                return 'ok', msg
            erros.append(msg)
            continue
        conversa = _conversa_com(sim, alvo_sim)
        if conversa is None:
            if not pode_iniciar_conversa:
                return 'esperando', 'conversa ainda não começou'
            ok, msg = _empurrar_super(sim, _interacao(CONVERSA), alvo_sim)
            if not ok:
                return 'falhou', 'não consegui iniciar a conversa: ' + msg
            _PENDENTES.append({'sim': nome, 'alvo': alvo_nome, 'acao': acao, 'tom': tom, 'motivo': motivo, 'voltas': 0})
            return 'esperando', 'conversa iniciada, {} em seguida'.format(acao)
        ok, msg = _empurrar_mixer(sim, afordancia, alvo_sim, conversa)
        if ok:
            return 'ok', msg
        erros.append(msg)
    _log('{} {} {} (tom {}): nenhuma interação aceita: {}'.format(nome, acao, alvo_nome, tom, erros))
    return 'falhou', _resumir_erros(erros)


def _resumir_erros(erros):
    """Os motivos distintos das recusas ('Missing relationship bit has_met',
    'skill level not in desired range'...), mais úteis que a lista toda."""
    import re
    motivos = []
    for e in erros:
        m = re.search(r'EnqueueResult: (.*?) <ExecuteResult', e)
        if m:
            motivo = re.sub(r"<class '(?:[\w]+\.)*(\w+)'>", r'\1', m.group(1))
            motivo = re.sub(r'\s+between .*$', '', motivo).rstrip('. ')
        else:
            motivo = 'não existe no jogo' if 'não existe' in e else e[-80:]
        if motivo not in motivos:
            motivos.append(motivo)
    return '{} tentativas recusadas: {}'.format(len(erros), '; '.join(motivos[:3]))


def _processar_pendentes(output):
    """Dispara as ações que estavam esperando a conversa começar."""
    if not _PENDENTES:
        return
    sims = _sims_no_lote()
    for p in list(_PENDENTES):
        p['voltas'] += 1
        par = sims.get(p['sim'].lower()), sims.get(p['alvo'].lower())
        if None in par:
            _PENDENTES.remove(p)
            continue
        estado, msg = _fazer_acao(par[0][1], p['acao'], par[1][1], p['sim'], p['alvo'],
                                  pode_iniciar_conversa=False, tom=p.get('tom'), motivo=p.get('motivo', ''))
        if estado == 'esperando' and p['voltas'] < MAX_ESPERA_CONVERSA:
            continue
        _PENDENTES.remove(p)
        output('{} -> {} -> {}: {} ({})'.format(p['sim'], p['acao'], p['alvo'], estado, msg))
        _log('pendente {} {} {}: {} {}'.format(p['sim'], p['acao'], p['alvo'], estado, msg))
        _evento_resultado(p['sim'], p['acao'], p['alvo'], p.get('tom'), estado, msg)


# ---------- comandos de cheat ----------

@sims4.commands.Command('npcgen.ola', command_type=sims4.commands.CommandType.Live)
def cmd_ola(_connection=None):
    _rodar(_connection, ola)


@sims4.commands.Command('npcgen.sims', command_type=sims4.commands.CommandType.Live)
def cmd_sims(_connection=None):
    _rodar(_connection, listar_sims)


@sims4.commands.Command('npcgen.criar', command_type=sims4.commands.CommandType.Live)
def cmd_criar(_connection=None):
    _rodar(_connection, criar, True)


@sims4.commands.Command('npcgen.limpar', command_type=sims4.commands.CommandType.Live)
def cmd_limpar(_connection=None):
    _rodar(_connection, limpar)


@sims4.commands.Command('npcgen.tracos', command_type=sims4.commands.CommandType.Live)
def cmd_tracos(_connection=None):
    _rodar(_connection, diagnostico_tracos)


@sims4.commands.Command('npcgen.auto', command_type=sims4.commands.CommandType.Live)
def cmd_auto(_connection=None):
    _rodar(_connection, alternar_auto)


@sims4.commands.Command('npcgen.veraspiracao', command_type=sims4.commands.CommandType.Live)
def cmd_veraspiracao(_connection=None):
    _rodar(_connection, ver_aspiracao)


@sims4.commands.Command('npcgen.trilhas', command_type=sims4.commands.CommandType.Live)
def cmd_trilhas(_connection=None):
    _rodar(_connection, trilhas)


@sims4.commands.Command('npcgen.listar', command_type=sims4.commands.CommandType.Live)
def cmd_listar(tipo: str = None, texto: str = None, _connection=None):
    _rodar(_connection, listar, tipo, texto)


@sims4.commands.Command('npcgen.buscar', command_type=sims4.commands.CommandType.Live)
def cmd_buscar(texto: str = None, _connection=None):
    _rodar(_connection, buscar, texto)


@sims4.commands.Command('npcgen.testar', command_type=sims4.commands.CommandType.Live)
def cmd_testar(qual: str = None, nome: str = None, alvo: str = None, _connection=None):
    _rodar(_connection, testar, qual, nome, alvo)


@sims4.commands.Command('npcgen.catalogo', command_type=sims4.commands.CommandType.Live)
def cmd_catalogo(_connection=None):
    _rodar(_connection, catalogo)


@sims4.commands.Command('npcgen.mapear', command_type=sims4.commands.CommandType.Live)
def cmd_mapear(_connection=None):
    _rodar(_connection, mapear)


@sims4.commands.Command('npcgen.acoes', command_type=sims4.commands.CommandType.Live)
def cmd_acoes(_connection=None):
    _rodar(_connection, acoes)


@sims4.commands.Command('npcgen.humores', command_type=sims4.commands.CommandType.Live)
def cmd_humores(_connection=None):
    _rodar(_connection, humores)


@sims4.commands.Command('npcgen.humor', command_type=sims4.commands.CommandType.Live)
def cmd_humor(emocao: str = None, nome: str = None, intensidade: str = '1', motivo: str = '', _connection=None):
    # motivo com várias palavras: junte com + (ex.: rumor+jealous)
    _rodar(_connection, testar_humor, emocao, nome, intensidade, motivo.replace('+', ' ').replace(',', ' '))


@sims4.commands.Command('npcgen.tons', command_type=sims4.commands.CommandType.Live)
def cmd_tons(tom: str = None, _connection=None):
    _rodar(_connection, tons, tom)


@sims4.commands.Command('npcgen.jogo', command_type=sims4.commands.CommandType.Live)
def cmd_jogo(_connection=None):
    _rodar(_connection, descrever_jogo)


@sims4.commands.Command('npcgen.lacos', command_type=sims4.commands.CommandType.Live)
def cmd_lacos(_connection=None):
    _rodar(_connection, lacos, True)


@sims4.commands.Command('npcgen.estado', command_type=sims4.commands.CommandType.Live)
def cmd_estado(_connection=None):
    _rodar(_connection, observar)


@sims4.commands.Command('npcgen.executar', command_type=sims4.commands.CommandType.Live)
def cmd_executar(_connection=None):
    _rodar(_connection, executar)


# ---------- o que cada comando faz ----------

def ola(output):
    output('npcgen vivo!')
    output('pasta troca: ' + PASTA_TROCA)
    output('casa.json existe? {}  comandos.json existe? {}'.format(
        os.path.isfile(ARQ_CASA), os.path.isfile(ARQ_COMANDOS)))
    output('automático: {}'.format('LIGADO' if _ALARME is not None else 'desligado'))


def listar_sims(output):
    sims = _sims_no_lote()
    if not sims:
        output('npcgen: nenhum Sim instanciado no lote.')
    for nome, (info, _sim) in sorted(sims.items()):
        output('- {} {}'.format(info.first_name, info.last_name))


def diagnostico_tracos(output):
    faltando = [r for r in TRACOS_JOGO if _traco(r) is None]
    faltando_asp = [r for r in ASPIRACOES_JOGO if _aspiracao(r) is None]
    for r in TRACOS_JOGO:
        t = _traco(r)
        _log('traço {} -> {}'.format(r, t.__name__ if t else 'NÃO ACHEI'))
    for r in ASPIRACOES_JOGO:
        a = _aspiracao(r)
        _log('aspiração {} -> {}'.format(r, a.__name__ if a else 'NÃO ACHEI'))
    output('traços achados: {}/{}'.format(len(TRACOS_JOGO) - len(faltando), len(TRACOS_JOGO)))
    output('aspirações achadas: {}/{}'.format(len(ASPIRACOES_JOGO) - len(faltando_asp), len(ASPIRACOES_JOGO)))
    if faltando or faltando_asp:
        output('faltando: ' + ', '.join(faltando + faltando_asp))
    try:
        faltando_emp = [r for r in EMPREGOS_JOGO if _carreira(r) is None]
        for r in EMPREGOS_JOGO:
            c = _carreira(r)
            _log('emprego {} -> {}'.format(r, c.__name__ if c else 'NÃO ACHEI'))
        output('empregos achados: {}/{}{}'.format(
            len(EMPREGOS_JOGO) - len(faltando_emp), len(EMPREGOS_JOGO),
            ' (faltando: {})'.format(', '.join(faltando_emp)) if faltando_emp else ''))
    except Exception:
        _log('diagnóstico de empregos\n' + traceback.format_exc())
        output('empregos: não consegui ler as carreiras do jogo (detalhes no log)')
    output('mapa completo em npcgen_log.txt')


_VERIFICACAO = {'passo': -1, 'original': None}


def ver_aspiracao(output):
    """Coloca no Sim ativo, uma por vez, cada aspiração do mapa. A cada
    chamada avança uma; você confere no painel se é a esperada. No fim,
    devolve a aspiração original."""
    client = services.client_manager().get_first_client()
    ativo = client.active_sim if client is not None else None
    if ativo is None:
        output('npcgen: selecione um Sim no lote primeiro.')
        return
    info = ativo.sim_info
    lista = sorted(ASPIRACOES_JOGO.items(), key=lambda par: par[1][0])

    if _VERIFICACAO['passo'] == -1:
        _VERIFICACAO['original'] = info.primary_aspiration
    _VERIFICACAO['passo'] += 1
    passo = _VERIFICACAO['passo']

    if passo >= len(lista):
        info.primary_aspiration = _VERIFICACAO['original']
        _VERIFICACAO['passo'], _VERIFICACAO['original'] = -1, None
        output('npcgen: fim da verificação. Aspiração original devolvida.')
        return

    rotulo, nomes = lista[passo]
    trilha = _aspiracao(rotulo)
    if trilha is None:
        output('{}/{}: {} não existe no jogo, pulei. Digite de novo.'.format(passo + 1, len(lista), nomes[0]))
        return
    info.primary_aspiration = trilha
    linha = '{}/{}: {} -> esperado "{}"'.format(passo + 1, len(lista), trilha.__name__, rotulo)
    output(linha)
    output('Confira no painel de aspiração do Sim e digite npcgen.veraspiracao de novo.')
    _log('veraspiracao ' + linha)


def trilhas(output):
    """Para cada trilha de aspiração, mostra as etapas dela. As etapas têm
    nomes descritivos e revelam qual aspiração é cada Track_X_A/B/C."""
    import sims4.resources
    gerente = services.get_instance_manager(sims4.resources.Types.ASPIRATION_TRACK)
    linhas = []
    for trilha in sorted(gerente.types.values(), key=lambda t: t.__name__):
        if not trilha.__name__.startswith('Track_'):
            continue
        etapas = getattr(trilha, 'aspirations', None) or {}
        try:
            itens = list(etapas.values()) if hasattr(etapas, 'values') else list(etapas)
            nomes = [getattr(a, '__name__', str(a)) for a in itens]
        except Exception:
            nomes = ['(não consegui ler as etapas)']
        linhas.append('{}: {}'.format(trilha.__name__, ', '.join(nomes[:2]) or '(sem etapas)'))
    _log('--- trilhas ---\n' + '\n'.join(linhas))
    for linha in linhas:
        output(linha)
    output('Lista também em npcgen_log.txt')


def listar(output, tipo=None, texto=None):
    """Lista os nomes internos do jogo (para corrigir TRACOS_JOGO e ASPIRACOES_JOGO)."""
    tipos = {'tracos': 'TRAIT', 'aspiracoes': 'ASPIRATION_TRACK', 'interacoes': 'INTERACTION',
             'empregos': 'CAREER'}
    if tipo not in tipos:
        output('uso: npcgen.listar tracos|aspiracoes|interacoes|empregos [texto]')
        return
    import sims4.resources
    gerente = services.get_instance_manager(getattr(sims4.resources.Types, tipos[tipo]))
    itens = sorted((t.__name__, getattr(t, 'guid64', '?')) for t in gerente.types.values()
                   if not texto or texto.lower() in t.__name__.lower())
    linhas = ['{}  {}'.format(guid, nome) for nome, guid in itens]
    _log('--- listar {} {} ---\n'.format(tipo, texto or '') + '\n'.join(linhas))
    for linha in linhas[:20]:
        output(linha)
    output('{} encontrados. Lista completa em npcgen_log.txt'.format(len(linhas)))


def buscar(output, texto=None):
    """Lista interações do jogo cujo nome interno contém `texto`, com o ID."""
    if not texto:
        output('uso: npcgen.buscar <parte do nome em inglês>, ex.: npcgen.buscar chat')
        return
    import sims4.resources
    gerente = services.get_instance_manager(sims4.resources.Types.INTERACTION)
    achados = sorted(
        (t.__name__, getattr(t, 'guid64', '?'))
        for t in gerente.types.values()
        if texto.lower() in t.__name__.lower()
    )
    for nome, guid in achados[:25]:
        output('{}  {}'.format(guid, nome))
    output('{} encontrados{}. Lista completa em npcgen_log.txt'.format(
        len(achados), ' (mostrando 25)' if len(achados) > 25 else ''))
    _log('--- buscar {} ---\n'.format(texto) + '\n'.join('{}  {}'.format(g, n) for n, g in achados))


def testar(output, qual=None, nome=None, alvo=None):
    """qual = uma ação do bot (abracar, discutir...), um nome de interação ou um ID.
    Sem Alvo: interação com um objeto do lote (ex.: npcgen.testar 13192 Ana)."""
    if qual is None or nome is None:
        output('uso: npcgen.testar <ação|nome|ID> <Sim> [Alvo]')
        output('  social: npcgen.testar abracar Ana Rui   objeto: npcgen.testar <ID> Ana')
        return
    sims = _sims_no_lote()
    for n in (nome, alvo):
        if n is not None and n.lower() not in sims:
            output('não achei o Sim ' + n)
            return
    if alvo is None:
        estado, msg = _fazer_objeto(sims[nome.lower()][1], qual)
        output('{}: {}'.format(estado.upper(), msg))
        _log('testar objeto {} {}: {} {}'.format(qual, nome, estado, msg))
        return
    (info, sim), (info_alvo, alvo_sim) = sims[nome.lower()], sims[alvo.lower()]
    acao = qual if qual in INTERACOES else '_teste'
    if acao == '_teste':
        INTERACOES['_teste'] = [qual]
    estado, msg = _fazer_acao(sim, acao, alvo_sim, info.first_name, info_alvo.first_name)
    output('{}: {}'.format(estado.upper(), msg))
    if estado == 'esperando':
        output('Conversa iniciada. Com npcgen.auto ligado, a ação sai sozinha em alguns segundos;'
               ' sem ele, rode npcgen.executar.')
    _log('testar {} {} {}: {} {}'.format(qual, nome, alvo, estado, msg))


def acoes(output):
    """Para cada ação do bot, quais interações candidatas existem no jogo."""
    for acao, candidatas in INTERACOES.items():
        if acao.startswith('_'):
            continue
        if not candidatas:
            output('{}: (nada, o Sim fica na dele)'.format(acao))
            continue
        partes = []
        for c in candidatas:
            a = _interacao(c)
            partes.append('{} [{}]'.format(c, 'NÃO EXISTE' if a is None else
                                           ('mixer' if _eh_mixer(a) else 'super')))
        linha = '{}: {}'.format(acao, ' | '.join(partes))
        output(linha)
        _log('acoes ' + linha)


def humores(output):
    """Qual moodlet o mod vai usar para cada emoção (e quantas opções achou)."""
    for emocao in EMOCOES_JOGO:
        c = _candidatos_humor(emocao)
        linha = '{}: {}'.format(emocao, '{} opções (ex.: {})'.format(
            len(c), ', '.join(b.__name__ for b in c[:2])) if c else 'NADA ACHADO')
        output(linha)
        _log('humores ' + linha + ('\n   ' + ', '.join(b.__name__ for b in c) if c else ''))
    output('Todas as opções em npcgen_log.txt. O mod escolhe a que combina com o motivo.')


def testar_humor(output, emocao=None, nome=None, intensidade='1', motivo=''):
    if emocao not in EMOCOES_JOGO or nome is None:
        output('uso: npcgen.humor <emoção> <Sim> [1|2|3] [motivo+em+inglês]   emoções: ' + ', '.join(EMOCOES_JOGO))
        return
    sims = _sims_no_lote()
    if nome.lower() not in sims:
        output('não achei o Sim ' + nome)
        return
    estado, msg = _aplicar_humor(sims[nome.lower()][0], emocao, intensidade, motivo)
    output('{}: {}'.format(estado.upper(), msg))
    _log('testar humor {} {}: {} {}'.format(emocao, nome, estado, msg))


def tons(output, tom=None):
    """Quantas interações sociais o jogo tem para cada tom."""
    for t in ([tom] if tom else TONS_JOGO):
        if t not in TONS_JOGO:
            output('tons: ' + ', '.join(TONS_JOGO))
            return
        achados = _mixers_do_tom(t)
        output('{}: {} interações{}'.format(t, len(achados), ' (ex.: ' + ', '.join(
            a.__name__ for a in achados[:3]) + ')' if achados else ''))
        _log('tons {}: {}'.format(t, ', '.join(a.__name__ for a in achados)))
    output('Listas completas em npcgen_log.txt. Teste: npcgen.testar <nome da interação> <Sim> <Alvo>')


def executar(output, silencioso=False):
    comandos = _ler_json(ARQ_COMANDOS, {'comandos': []}).get('comandos', [])
    estado = _ler_json(ARQ_EXECUTADO, None)
    if estado is None:
        # Primeira vez: não repete o histórico antigo do bot.
        ultimo = max([c['id'] for c in comandos] or [0])
        _escrever_json(ARQ_EXECUTADO, {'ultimo': ultimo})
        output('npcgen: {} comandos antigos ignorados.'.format(len(comandos)))
        return

    _processar_pendentes(output)

    ultimo = estado.get('ultimo', 0)
    novos = [c for c in comandos if c['id'] > ultimo]
    if not novos:
        if not silencioso:
            output('npcgen: nada novo.')
        return

    sims = _sims_no_lote()
    for c in novos:
        ultimo = c['id']
        nome, acao, alvo = c['sim'], c['acao'], c.get('alvo')
        linha = '#{} {} -> {}{}'.format(c['id'], nome, acao, ' -> ' + alvo if alvo else '')
        if nome.lower() not in sims or (alvo and alvo.lower() not in sims):
            output(linha + '  (Sim fora do lote)')
            continue
        info, sim = sims[nome.lower()]
        alvo_sim = sims[alvo.lower()][1] if alvo else None
        if c.get('humor'):
            try:
                estado_humor, msg_humor = _aplicar_humor(info, c['humor'], c.get('intensidade', 1),
                                                         c.get('motivo', ''))
            except Exception:
                _log('humor #{}\n'.format(c['id']) + traceback.format_exc())
                estado_humor, msg_humor = 'erro', 'detalhes no log'
            if output is not _log:
                output('#{} {} humor: {} {}'.format(c['id'], nome, estado_humor, msg_humor))
            if estado_humor == 'ok':
                _evento('{} ficou {} (intensidade {}, o mod pôs a emoção)'.format(
                    nome, c['humor'], c.get('intensidade', 1)))
            elif estado_humor == 'fraco':
                _evento('{} deveria ficar {}, mas no jogo o humor dele continua {}'.format(
                    nome, c['humor'], _humor_atual(info)))
            _log('#{} {} humor: {} {}'.format(c['id'], nome, estado_humor, msg_humor))
        if c.get('tom'):
            linha += ' (tom {})'.format(c['tom'])
        try:
            if acao == 'usar_objeto':
                linha = '#{} {} -> {}'.format(c['id'], nome, c.get('interacao_nome') or c.get('interacao_id'))
                estado_acao, msg = _fazer_objeto(sim, c.get('interacao_id'))
            else:
                estado_acao, msg = _fazer_acao(sim, acao, alvo_sim, nome, alvo, tom=c.get('tom'),
                                               motivo=c.get('motivo', ''))
        except Exception:
            _log(linha + '\n' + traceback.format_exc())
            estado_acao, msg = 'erro', 'detalhes no log'
        if output is not _log:
            output('{}  {}: {}'.format(linha, estado_acao, msg))
        if estado_acao != 'esperando':  # quem espera a conversa gera o evento depois
            _evento_resultado(nome, acao, alvo or c.get('interacao_nome') or c.get('interacao_id'),
                              c.get('tom'), estado_acao, msg)
        _log('{} {}: {}'.format(linha, estado_acao, msg))

    _escrever_json(ARQ_EXECUTADO, {'ultimo': ultimo})


# ---------- o que está acontecendo no jogo (troca/estado.json) ----------
#
# A cada volta do automático o mod fotografa os moradores (humor, moodlets,
# o que estão fazendo, necessidades, relações entre eles) e anota o que mudou
# como "eventos". O bot manda isso para a IA em toda rodada, para ela decidir
# com base no que DE FATO aconteceu no jogo, e não só no que ela mandou fazer.

ARQ_ESTADO = os.path.join(PASTA_TROCA, 'estado.json')
MAX_EVENTOS = 80
MOTIVOS = {'fome': 'motive_Hunger', 'energia': 'motive_Energy', 'diversao': 'motive_Fun',
           'social': 'motive_Social', 'higiene': 'motive_Hygiene', 'bexiga': 'motive_Bladder'}
TRILHAS_RELACAO = {'amizade': 'LTR_Friendship_Main', 'romance': 'LTR_Romance_Main'}
MUDANCA_RELACAO = 5  # pontos de amizade/romance que viram evento
# Interações que são só "ficar parado/andar": não viram evento.
RUIDO = ('stand', 'idle', 'route', 'wait', 'carry', 'putdown', 'put_down', 'pickup', 'pick_up',
         'sit_passive', 'look', 'react', 'socialpickers', 'social_super_interaction', 'join', 'leave',
         'walk', 'go_here', 'gohere', 'reaction', 'buff_', 'broadcaster', 'autonomous_')

_EVENTOS = []
_ANTES = {}


def _evento(texto):
    n = int(time.time() * 1000)
    if _EVENTOS and n <= _EVENTOS[-1]['n']:
        n = _EVENTOS[-1]['n'] + 1
    _EVENTOS.append({'n': n, 't': int(time.time()), 'texto': texto})
    del _EVENTOS[:-MAX_EVENTOS]


def _evento_resultado(nome, acao, alvo, tom, estado, msg):
    """'Ana -> discutir com Davi (tom irritado): FEZ mixer_social_YellAT...'"""
    feito = msg.split(' -> ')[0] if estado == 'ok' else msg
    alvo_txt = ' com {}'.format(alvo) if alvo and acao != 'usar_objeto' else (' ({})'.format(alvo) if alvo else '')
    tom_txt = ' (tom {})'.format(tom) if tom else ''
    if estado == 'ok':
        texto = '{} -> {}{}{}: FEZ ({})'.format(nome, acao, alvo_txt, tom_txt, feito)
    elif estado == 'nada':
        texto = '{} -> {}{}: não fez nada no jogo'.format(nome, acao, alvo_txt)
    else:
        texto = '{} -> {}{}{}: NÃO CONSEGUIU ({})'.format(nome, acao, alvo_txt, tom_txt, feito[:120])
    _evento(texto)


def _nome_de(obj):
    info = getattr(obj, 'sim_info', None)
    if info is not None:
        return info.first_name
    return type(obj).__name__ if obj is not None else None


def _estatistica(nome):
    return _resolver('STATISTIC', nome, [nome], '')


def _moodlets(info):
    lista = []
    try:
        for b in list(info.Buffs):
            humor = getattr(b, 'mood_type', None)
            if not getattr(b, 'visible', True) or humor is None:
                continue
            tipo = getattr(b, 'buff_type', type(b))
            lista.append((getattr(b, 'mood_weight', 0) or 0, tipo.__name__, humor.__name__))
    except Exception:
        _log('moodlets\n' + traceback.format_exc())
    lista.sort(reverse=True)
    return [{'nome': n, 'humor': h, 'peso': p} for p, n, h in lista[:6]]


def _fazendo(sim):
    agora, fila = [], []
    try:
        for si in list(sim.si_state):
            nome = si.affordance.__name__
            if any(r in nome.lower() for r in RUIDO):
                continue
            alvo = _nome_de(getattr(si, 'target', None))
            agora.append(nome + (' -> ' + alvo if alvo and alvo != _nome_de(sim) else ''))
    except Exception:
        _log('si_state\n' + traceback.format_exc())
    try:
        running = getattr(sim.queue, 'running', None)
        for i in list(sim.queue):
            if i is running:
                continue
            nome = i.affordance.__name__
            if not any(r in nome.lower() for r in RUIDO):
                fila.append(nome)
    except Exception:
        pass
    return agora[:3], fila[:3]


def _necessidades(info):
    valores = {}
    rastreador = getattr(info, 'commodity_tracker', None)
    for chave, nome in MOTIVOS.items():
        stat = _estatistica(nome)
        if stat is None or rastreador is None:
            continue
        try:
            v = rastreador.get_value(stat)
            if v is not None:
                valores[chave] = int(round(v))
        except Exception:
            pass
    return valores


def _relacao(a, b):
    valores = {}
    servico = None
    try:
        servico = services.relationship_service()
    except Exception:
        pass
    for chave, nome in TRILHAS_RELACAO.items():
        trilha = _estatistica(nome)
        if trilha is None:
            continue
        v = None
        try:
            if servico is not None:
                v = servico.get_relationship_score(a.sim_id, b.sim_id, trilha)
        except Exception:
            v = None
        if v is None:
            try:
                v = a.relationship_tracker.get_relationship_score(b.sim_id, trilha)
            except Exception:
                v = None
        if v is not None:
            valores[chave] = int(round(v))
    return valores


def _hora_do_jogo():
    try:
        agora = services.time_service().sim_now
        dias = ['domingo', 'segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado']
        return '{} {:02d}:{:02d}'.format(dias[int(agora.day()) % 7], int(agora.hour()), int(agora.minute()))
    except Exception:
        return None


def observar(output=None):
    """Fotografa os moradores, anota o que mudou e salva troca/estado.json."""
    nomes_casa = [f['nome'] for f in (_ler_json(ARQ_CASA, {}) or {}).get('sims', [])]
    no_lote = _sims_no_lote()
    fotos = {}
    for nome in nomes_casa:
        par = no_lote.get(nome.lower())
        if par is None:
            fotos[nome] = {'no_lote': False}
            continue
        info, sim = par
        foto = {'no_lote': True}
        try:
            humor = info.get_mood()
            foto['humor'] = humor.__name__ if humor is not None else None
            foto['intensidade'] = int(info.get_mood_intensity() or 0)
        except Exception:
            pass
        foto['moodlets'] = _moodlets(info)
        foto['fazendo'], foto['fila'] = _fazendo(sim)
        foto['necessidades'] = _necessidades(info)
        rel = {}
        for outro in nomes_casa:
            par_outro = no_lote.get(outro.lower())
            if outro != nome and par_outro is not None:
                rel[outro] = _relacao(info, par_outro[0])
        foto['relacoes'] = rel
        fotos[nome] = foto

    # O que mudou desde a última foto vira evento.
    for nome, foto in fotos.items():
        antes = _ANTES.get(nome)
        if antes is None:
            continue
        if antes.get('no_lote') != foto.get('no_lote'):
            _evento('{} {} lote'.format(nome, 'chegou ao' if foto.get('no_lote') else 'saiu do'))
            continue
        if not foto.get('no_lote'):
            continue
        if foto.get('humor') != antes.get('humor') and foto.get('humor'):
            _evento('{} agora está {} (intensidade {})'.format(nome, foto['humor'], foto.get('intensidade')))
        novos = [f for f in foto.get('fazendo', []) if f not in antes.get('fazendo', [])]
        for f in novos[:2]:
            _evento('{} começou: {}'.format(nome, f))
        for outro, rel in foto.get('relacoes', {}).items():
            if nome > outro:  # cada par uma vez só
                continue
            velho = antes.get('relacoes', {}).get(outro, {})
            for chave, v in rel.items():
                if chave in velho and abs(v - velho[chave]) >= MUDANCA_RELACAO:
                    _evento('{} {} <-> {}: {} -> {}'.format(chave.capitalize(), nome, outro, velho[chave], v))
    _ANTES.clear()
    _ANTES.update(fotos)

    outros = sorted(info.first_name for n, (info, sim) in no_lote.items()
                    if info.first_name not in nomes_casa)
    _escrever_json(ARQ_ESTADO, {
        't': int(time.time()), 'hora_jogo': _hora_do_jogo(),
        'sims': fotos, 'tambem_no_lote': outros, 'eventos': _EVENTOS,
    })
    if output is not None:
        for nome, foto in fotos.items():
            if not foto.get('no_lote'):
                output('{}: fora do lote'.format(nome))
                continue
            output('{}: {} ({}) | fazendo: {} | {}'.format(
                nome, foto.get('humor'), foto.get('intensidade'), ', '.join(foto.get('fazendo', [])) or '-',
                ' '.join('{}={}'.format(k, v) for k, v in foto.get('necessidades', {}).items())))
        output('{} eventos guardados. Tudo em estado.json'.format(len(_EVENTOS)))


# ---------- o seu Sim e o lote (troca/jogo.json) ----------
#
# O /gerar usa isto: o Sim que você controla vira o Sim inicial da casa (com
# os traços, aspiração e emprego reais dele) e a casa nova é inventada para
# ESTE lote (nome, bairro, características, o que tem dentro).

ARQ_JOGO = os.path.join(PASTA_TROCA, 'jogo.json')
OBJETOS_DESTAQUE = {
    'camas': ['bed'], 'banheiros': ['toilet'], 'chuveiros': ['shower'], 'banheiras': ['bathtub', 'tub_'],
    'piscina': ['pool'], 'hidromassagem': ['hottub', 'hot_tub'], 'piano': ['piano'], 'violão': ['guitar'],
    'violino': ['violin'], 'computadores': ['computer'], 'TVs': ['television', '_tv'], 'cavalete de pintura': ['easel'],
    'estantes de livros': ['bookshelf'], 'fogão': ['stove', 'oven'], 'geladeira': ['fridge'], 'xadrez': ['chess'],
    'aparelhos de ginástica': ['treadmill', 'workout', 'weight'], 'horta/jardim': ['garden', 'planter'],
    'churrasqueira': ['grill'], 'bar': ['bar_'], 'microscópio': ['microscope'], 'telescópio': ['telescope'],
    'mesa de jantar': ['table_dining', 'dining'], 'sofás': ['sofa', 'loveseat'], 'escrivaninhas': ['desk'],
}
IDADES_JOGO = {'YOUNGADULT': 'jovem adulto', 'ADULT': 'adulto', 'ELDER': 'idoso', 'TEEN': 'adolescente',
               'CHILD': 'criança', 'TODDLER': 'criança pequena', 'BABY': 'bebê', 'INFANT': 'bebê'}


def _legivel(nome):
    import re
    partes = re.sub(r'([a-z])([A-Z])', r'\1 \2', nome).replace('_', ' ').split()
    return ' '.join(p for p in partes if p.lower() not in ('lot', 'trait', 'lottrait', 'zone', 'modifier')).lower()


def _ficha_do_sim(info):
    """O seu Sim, com os nomes que o bot usa (os mesmos do /gerar)."""
    ficha = {'nome': info.first_name, 'sobrenome': info.last_name, 'sim_id': info.sim_id}
    ficha['genero'] = 'feminino' if 'FEMALE' in str(getattr(info, 'gender', '')).upper() else 'masculino'
    idade = str(getattr(info, 'age', '')).upper().split('.')[-1]
    ficha['idade'] = IDADES_JOGO.get(idade, 'adulto')
    tracos = []
    try:
        do_sim = set(getattr(info.trait_tracker, 'equipped_traits', None) or info.get_traits())
        for rotulo in TRACOS_JOGO:
            t = _traco(rotulo)
            if t is not None and t in do_sim:
                tracos.append(rotulo)
    except Exception:
        _log('traços do Sim ativo\n' + traceback.format_exc())
    ficha['tracos'] = tracos
    ficha['aspiracao'] = ''
    try:
        trilha = info.primary_aspiration
        for rotulo in ASPIRACOES_JOGO:
            if _aspiracao(rotulo) is trilha:
                ficha['aspiracao'] = rotulo
                break
    except Exception:
        pass
    ficha['emprego'] = 'Desempregado'
    try:
        for carreira in list(info.career_tracker.careers.values()):
            nome = _chave(type(carreira).__name__)
            ficha['emprego'] = next((r for r, chaves in EMPREGOS_JOGO.items()
                                     if any(_chave(c) in nome for c in chaves)), _legivel(type(carreira).__name__))
            break
    except Exception:
        pass
    return ficha


def _info_lote():
    lote = {'id': _lote_atual()}
    zona = _lote_atual()
    try:
        pers = services.get_persistence_service()
        dados = pers.get_zone_proto_buff(zona)
        lote['nome'] = dados.name
        try:
            lote['bairro'] = pers.get_neighborhood_proto_buff(dados.neighborhood_id).name
        except Exception:
            pass
    except Exception:
        pass
    try:
        venue = services.get_current_venue() if hasattr(services, 'get_current_venue') else services.venue_service().active_venue
        lote['tipo'] = _legivel(type(venue).__name__ if not isinstance(venue, type) else venue.__name__).replace('venue ', '')
    except Exception:
        pass
    try:
        mods = services.get_zone_modifier_service().get_zone_modifiers(zona)
        lote['caracteristicas'] = sorted(_legivel(m.__name__) for m in mods)
    except Exception:
        pass
    try:
        terreno = services.active_lot()
        lote['tamanho'] = '{}x{}'.format(terreno.size_x, terreno.size_z)
    except Exception:
        pass
    contagem = {}
    for obj in _objetos_do_lote():
        nome = type(obj).__name__.lower()
        for rotulo, chaves in OBJETOS_DESTAQUE.items():
            if any(c in nome for c in chaves):
                contagem[rotulo] = contagem.get(rotulo, 0) + 1
                break
    lote['tem'] = contagem
    return lote


def descrever_jogo(output=None):
    """Salva em jogo.json o seu Sim (o que você controla) e o lote atual."""
    client = services.client_manager().get_first_client()
    ativo = client.active_sim if client is not None else None
    dados = {'t': int(time.time()), 'lote': _info_lote()}
    if ativo is not None:
        dados['sim_ativo'] = _ficha_do_sim(ativo.sim_info)
        try:
            casa = ativo.household
            dados['familia'] = {'nome': getattr(casa, 'name', ''), 'dinheiro': int(casa.funds.money)}
        except Exception:
            pass
    _escrever_json(ARQ_JOGO, dados)
    if output is not None:
        s, l = dados.get('sim_ativo', {}), dados['lote']
        output('Seu Sim: {} ({}, {}; {}; {}; {})'.format(
            s.get('nome', '?'), s.get('genero', '?'), s.get('idade', '?'), ', '.join(s.get('tracos', [])) or 'traços?',
            s.get('aspiracao') or 'aspiração?', s.get('emprego', '?')))
        output('Lote: {} ({}), {}, {}'.format(l.get('nome', '?'), l.get('bairro', '?'), l.get('tipo', '?'),
                                             l.get('tamanho', '?')))
        if l.get('caracteristicas'):
            output('Características: ' + ', '.join(l['caracteristicas']))
        output('Tem: ' + ', '.join('{} {}'.format(n, k) for k, n in sorted(l.get('tem', {}).items())))


# ---------- laços entre os moradores (barras de amizade e romance) ----------
#
# O /gerar diz como cada par se dá ("lacos" em cada ficha do casa.json:
# primos, melhores amigos, ex-namorados... com amizade -100..100 e romance
# 0..100). O mod apresenta todos uns aos outros (sem isso, para o jogo eles
# são estranhos e as interações maldosas são recusadas: "has_met") e põe as
# barras nesses valores.

BIT_CONHECEU = 'has_met'


def _bit(nome):
    return _resolver('RELATIONSHIP_BIT', nome, [nome], '')


def _tem_bit(a, b, bit):
    try:
        return bool(services.relationship_service().has_bit(a.sim_id, b.sim_id, bit))
    except Exception:
        pass
    try:
        return bool(a.relationship_tracker.has_bit(b.sim_id, bit))
    except Exception:
        return False


def _por_bit(a, b, bit):
    try:
        services.relationship_service().add_relationship_bit(a.sim_id, b.sim_id, bit)
        return True
    except Exception:
        pass
    try:
        a.relationship_tracker.add_relationship_bit(b.sim_id, bit)
        return True
    except Exception:
        _log('bit {} {}->{}\n'.format(bit.__name__, a.first_name, b.first_name) + traceback.format_exc())
        return False


def _definir_barra(a, b, chave, valor):
    """Põe a barra (amizade/romance) entre a e b em `valor`. Tenta 'definir'
    e, se esta versão do jogo não tiver, soma a diferença."""
    trilha = _estatistica(TRILHAS_RELACAO[chave])
    if trilha is None:
        return False
    servico = services.relationship_service()
    tentativas = (
        lambda: servico.set_relationship_score(a.sim_id, b.sim_id, valor, trilha),
        lambda: a.relationship_tracker.set_relationship_score(b.sim_id, valor, trilha),
    )
    for f in tentativas:
        try:
            f()
            if abs(_relacao(a, b).get(chave, valor) - valor) <= 1:
                return True
        except Exception:
            continue
    atual = _relacao(a, b).get(chave, 0)
    for f in (lambda: servico.add_relationship_score(a.sim_id, b.sim_id, valor - atual, trilha),
              lambda: a.relationship_tracker.add_relationship_score(b.sim_id, valor - atual, trilha)):
        try:
            f()
            return True
        except Exception:
            continue
    _log('barra {} {}<->{} = {}: o jogo recusou\n'.format(chave, a.first_name, b.first_name, valor)
         + traceback.format_exc())
    return False


def _moradores_infos():
    """{nome: sim_info} dos moradores da casa atual que o mod criou."""
    casa = _ler_json(ARQ_CASA, {}) or {}
    ids = set(_ler_json(ARQ_CRIADOS, {}).get('ids', []))
    ids |= {f['sim_id'] for f in casa.get('sims', []) if f.get('existente') and f.get('sim_id')}
    nomes = {f['nome'].lower(): f for f in casa.get('sims', [])}
    achados = {}
    for info in services.sim_info_manager().get_all():
        if info.sim_id in ids and info.first_name.lower() in nomes:
            achados[info.first_name] = info
    return casa, achados


def _limpar_relacoes_antigas(removidos):
    """Relacionamentos que sobraram com Sims de casas antigas (removidos antes
    de o mod apagar relações): some com eles do painel dos moradores atuais."""
    if not removidos:
        return
    try:
        servico = services.relationship_service()
    except Exception:
        return
    _, infos = _moradores_infos()
    client = services.client_manager().get_first_client()
    ativo = getattr(client, 'active_sim', None) if client is not None else None
    vivos = {i.sim_id for i in infos.values()} | ({ativo.sim_info.sim_id} if ativo is not None else set())
    apagados = 0
    for sim_id in vivos:
        for velho in set(removidos) - vivos:
            try:
                if servico.has_relationship(sim_id, velho):
                    servico.destroy_relationship(sim_id, velho)
                    apagados += 1
            except Exception:
                continue
    if apagados:
        _log('relações antigas apagadas: {}'.format(apagados))


def lacos(output=None, forcar=False):
    """Apresenta os moradores uns aos outros (sempre que faltar) e, uma vez
    por casa, põe as barras de amizade e romance que o /gerar definiu."""
    casa, infos = _moradores_infos()
    if len(infos) < 2:
        if output:
            output('npcgen: a casa ainda não foi criada.')
        return
    conheceu = _bit(BIT_CONHECEU)
    apresentados = 0
    nomes = sorted(infos)
    for i, a in enumerate(nomes):
        for b in nomes[i + 1:]:
            if conheceu is not None and not _tem_bit(infos[a], infos[b], conheceu):
                if _por_bit(infos[a], infos[b], conheceu):
                    _por_bit(infos[b], infos[a], conheceu)
                    apresentados += 1
    if apresentados:
        _log('laços: {} pares apresentados (has_met)'.format(apresentados))
    criados = _ler_json(ARQ_CRIADOS, {})
    if not forcar and criados.get('lacos_casa') == casa.get('id'):
        return
    _limpar_relacoes_antigas(criados.get('removidos', []))
    linhas, falhas = [], 0
    for f in casa.get('sims', []):
        a = infos.get(f['nome'])
        for l in f.get('lacos', []):
            b = infos.get(l.get('com'))
            if a is None or b is None or f['nome'] > l['com']:  # cada par uma vez
                continue
            ok = [_definir_barra(a, b, 'amizade', int(l.get('amizade', 10)))]
            if int(l.get('romance', 0)):
                ok.append(_definir_barra(a, b, 'romance', int(l.get('romance', 0))))
            falhas += ok.count(False)
            agora = _relacao(a, b)
            linhas.append('{} e {} ({}): amizade {} romance {}'.format(
                f['nome'], l['com'], l.get('tipo', ''), agora.get('amizade', '?'), agora.get('romance', '?')))
    criados = _ler_json(ARQ_CRIADOS, {})
    criados['lacos_casa'] = casa.get('id')
    _escrever_json(ARQ_CRIADOS, criados)
    _log('laços aplicados:\n  ' + '\n  '.join(linhas) + ('\n  ({} barras recusadas)'.format(falhas) if falhas else ''))
    for l in linhas:
        _evento('Laço no jogo: ' + l)
    if output:
        for l in linhas:
            output(l)
        if falhas:
            output('npcgen: {} barras o jogo recusou (detalhes no log)'.format(falhas))


# ---------- criar a casa gerada pela IA ----------

def _instancia(info):
    """O Sim no lote, inclusive quando o jogo o considera 'escondido'."""
    try:
        from objects import ALL_HIDDEN_REASONS
        return info.get_sim_instance(allow_hidden_flags=ALL_HIDDEN_REASONS)
    except Exception:
        return info.get_sim_instance()


def _sumir(sim, motivo):
    """Tira o corpo do Sim do lote (agenda; o jogo tira logo depois).
    Testado no jogo em 21/10: schedule_destroy_asap(source, cause) funciona
    para Sims de FORA da família ativa; destroy() não tira o corpo."""
    try:
        sim.schedule_destroy_asap(source=sim, cause=motivo)
        return 'schedule_destroy_asap'
    except Exception:
        _log('schedule_destroy_asap\n' + traceback.format_exc())
    try:
        sim.destroy(source=sim, cause=motivo)
        return 'destroy'
    except Exception:
        _log('destroy\n' + traceback.format_exc())
    return None


def _tirar_da_barra(sim_id):
    """Tira o retrato do Sim da barra da família. A barra mostra a lista de
    Sims controláveis do jogador, que não se atualiza sozinha quando alguém
    sai da família (testado em 21/10)."""
    client = services.client_manager().get_first_client()
    if client is None:
        return False
    for jeito in ('remove_selectable_sim_by_id',):
        try:
            getattr(client, jeito)(sim_id)
            return True
        except Exception:
            _log('{}\n{}'.format(jeito, traceback.format_exc()))
    try:
        info = services.sim_info_manager().get(sim_id)
        if info is not None:
            client.remove_selectable_sim_info(info)
            return True
    except Exception:
        _log('remove_selectable_sim_info\n' + traceback.format_exc())
    return False


def _limpar_barra(household, output):
    """Tira da barra todo retrato de quem não é mais da família."""
    client = services.client_manager().get_first_client()
    if client is None:
        return
    membros = set(info.sim_id for info in household.sim_info_gen())
    try:
        na_barra = [getattr(i, 'sim_id', i) for i in list(client.selectable_sims)]
    except Exception:
        _log('selectable_sims\n' + traceback.format_exc())
        return
    for sim_id in na_barra:
        if sim_id not in membros and _tirar_da_barra(sim_id):
            _log('barra: retrato {} removido'.format(sim_id))
            output('- saiu da barra ' + str(sim_id))


def _apagar_relacoes(info):
    """Apaga todos os relacionamentos do Sim que vai sair (com o seu Sim e com
    qualquer outro), para não sobrarem no painel de relacionamentos."""
    sim_id = info.sim_id
    servico = None
    try:
        servico = services.relationship_service()
    except Exception:
        pass
    for f in (lambda: servico.destroy_all_relationships(sim_id),
              lambda: info.relationship_tracker.destroy_all_relationships()):
        try:
            f()
            return 'todos de uma vez'
        except Exception:
            continue
    # Plano B: um por um, com cada Sim com quem ele tem relação.
    try:
        alvos = list(info.relationship_tracker.target_sim_gen())
    except Exception:
        alvos = []
    apagados = 0
    for alvo in alvos:
        alvo_id = getattr(alvo, 'sim_id', alvo)
        for f in (lambda: servico.destroy_relationship(sim_id, alvo_id),
                  lambda: info.relationship_tracker.destroy_relationship(alvo_id)):
            try:
                f()
                apagados += 1
                break
            except Exception:
                continue
    if alvos and apagados < len(alvos):
        _log('relações de {}: só {} de {} apagadas\n{}'.format(
            info.first_name, apagados, len(alvos), traceback.format_exc()))
    return '{} de {}'.format(apagados, len(alvos))


def _apagar_ficha(info, household):
    """Tira o Sim da família (e do jogo), sem deixar relacionamentos para trás."""
    nome = info.first_name
    try:
        _log('relações de {} apagadas: {}'.format(nome, _apagar_relacoes(info)))
    except Exception:
        _log('apagar relações {}\n{}'.format(nome, traceback.format_exc()))
    _tirar_da_barra(info.sim_id)  # antes, enquanto o jogo ainda conhece o Sim
    try:
        info.remove_permanently()
        return
    except Exception:
        _log('remove_permanently {}\n{}'.format(nome, traceback.format_exc()))
    try:
        household.remove_sim_info(info)
    except Exception:
        _log('remove_sim_info {}\n{}'.format(nome, traceback.format_exc()))


def _remover(ids, household, output):
    """Tira do jogo (lote e família) os Sims criados pela casa anterior.
    Ordem do próprio jogo: primeiro o corpo some, depois a ficha é apagada."""
    gerente = services.sim_info_manager()
    removidos = []
    for sim_id in ids:
        info = gerente.get(sim_id)
        if info is None:
            continue
        nome = info.first_name
        sim = _instancia(info)
        # Ordem que funciona no jogo (testado em 21/10): o jogo não deixa sumir
        # o corpo de um Sim da família ativa. Então primeiro sai da família e
        # depois o corpo (agora já de fora da família) sai do lote.
        _apagar_ficha(info, household)
        jeito = _sumir(sim, 'npcgen: casa nova') if sim is not None else 'sem corpo no lote'
        removidos.append(sim_id)
        _log('remover {}: corpo={} via {}'.format(nome, sim is not None, jeito))
        output('- saiu ' + nome)
    if removidos:
        estado = _ler_json(ARQ_CRIADOS, {})
        estado['removidos'] = (estado.get('removidos', []) + removidos)[-200:]
        _escrever_json(ARQ_CRIADOS, estado)


def _varrer(output, todos_fora_da_familia=False):
    """Procura no lote Sims que o mod já removeu da família (ou, com
    todos_fora_da_familia, qualquer Sim de fora da família) e os tira."""
    client = services.client_manager().get_first_client()
    ativo = client.active_sim if client is not None else None
    if ativo is None:
        return 0
    household = ativo.household
    removidos = set(_ler_json(ARQ_CRIADOS, {}).get('removidos', []))
    # Rede de segurança: removido pelo mod, sem corpo no lote, mas ainda na família.
    for info in list(household.sim_info_gen()):
        if info.sim_id in removidos and _instancia(info) is None:
            _apagar_ficha(info, household)
            _log('varrer: {} tirado da família (sem corpo)'.format(info.first_name))
            output('- saiu da família ' + info.first_name)
    try:
        _limpar_barra(household, output)
    except Exception:
        _log('limpar barra\n' + traceback.format_exc())
    membros = set(info.sim_id for info in household.sim_info_gen())
    gerente = services.sim_info_manager()
    tirados = 0
    for obj in list(services.object_manager().get_all()):
        if not getattr(obj, 'is_sim', False):
            continue
        info = getattr(obj, 'sim_info', None)
        sim_id = getattr(info, 'sim_id', None)
        if sim_id in membros:
            continue
        orfao = info is None or gerente.get(sim_id) is None  # ficha apagada, corpo ficou
        if todos_fora_da_familia or sim_id in removidos or orfao:
            nome = getattr(info, 'first_name', '?')
            jeito = _sumir(obj, 'npcgen: limpeza do lote')
            _log('varrer {}: via {}'.format(nome, jeito))
            output('- sumiu do lote ' + nome)
            tirados += 1
    return tirados


def limpar(output):
    """Remove da família todos os Sims, menos o que você está controlando.
    Para recuperar quando o mod perdeu a conta de quem criou."""
    client = services.client_manager().get_first_client()
    ativo = client.active_sim if client is not None else None
    if ativo is None:
        output('npcgen: selecione o Sim que deve FICAR e rode de novo.')
        return
    household = ativo.household
    fica = ativo.sim_info.sim_id
    ids = [info.sim_id for info in household.sim_info_gen() if info.sim_id != fica]
    _remover(ids, household, output)
    # Quem já estava sem corpo (limpo antes) sai da família agora.
    for info in list(household.sim_info_gen()):
        if info.sim_id != fica and _instancia(info) is None:
            _apagar_ficha(info, household)
    estado = _ler_json(ARQ_CRIADOS, {})
    estado['ids'], estado['historico'] = [], []
    _escrever_json(ARQ_CRIADOS, estado)
    _varrer(output)  # só os que o mod tirou da família; vizinhos de passagem não são afetados
    output('npcgen: {} Sims saíram da família; ficou {}. Os corpos somem do lote em seguida.'.format(
        len(ids), ativo.sim_info.first_name))


def _aplicar_tracos(info, rotulos):
    try:  # tira os traços de personalidade sorteados pelo jogo
        for t in list(info.trait_tracker.personality_traits):
            info.remove_trait(t)
    except Exception:
        _log('limpar traços {}\n{}'.format(info.first_name, traceback.format_exc()))
    for rotulo in rotulos:
        t = _traco(rotulo)
        if t is None:
            _log('traço sem correspondente no jogo: ' + rotulo)
            continue
        try:
            info.add_trait(t)
        except Exception:
            _log('add_trait {} {}\n{}'.format(info.first_name, rotulo, traceback.format_exc()))


def _bonus_de_todas_aspiracoes():
    """O traço bônus de cada trilha de aspiração do jogo (atributo primary_trait)."""
    import sims4.resources
    gerente = services.get_instance_manager(sims4.resources.Types.ASPIRATION_TRACK)
    bonus = set()
    for trilha in gerente.types.values():
        traco = getattr(trilha, 'primary_trait', None)
        if traco is not None:
            bonus.add(traco)
    return bonus


def _tem_traco(info, traco):
    try:
        return info.has_trait(traco)
    except Exception:
        return False


def _aplicar_aspiracao(info, rotulo):
    """Troca a aspiração e o traço bônus junto (visto em 21/10: ao trocar só a
    aspiração, ficava o bônus da aspiração sorteada pelo jogo na criação)."""
    trilha = _aspiracao(rotulo)
    if trilha is None:
        _log('aspiração sem correspondente no jogo: ' + rotulo)
        return
    try:
        info.primary_aspiration = trilha
    except Exception:
        _log('aspiração {} {}\n{}'.format(info.first_name, rotulo, traceback.format_exc()))
        return
    novo_bonus = getattr(trilha, 'primary_trait', None)
    try:
        for traco in _bonus_de_todas_aspiracoes():
            if traco is not novo_bonus and _tem_traco(info, traco):
                info.remove_trait(traco)
                _log('bônus antigo {} tirado de {}'.format(traco.__name__, info.first_name))
        if novo_bonus is not None and not _tem_traco(info, novo_bonus):
            info.add_trait(novo_bonus)
    except Exception:
        _log('bônus da aspiração {} {}\n{}'.format(info.first_name, rotulo, traceback.format_exc()))


# Etiqueta do gerador -> trechos prováveis do nome da carreira no jogo.
# Os nomes saíram dos traços "CAS_Story_Career_*" do seu jogo; os da carreira em
# si ainda precisam ser conferidos com `npcgen.listar empregos` / `npcgen.tracos`.
EMPREGOS_JOGO = {
    'Astronauta': ['Astronaut'], 'Atleta': ['Athletic', 'Athlete'], 'Negócios': ['Business'],
    'Criminoso': ['Criminal'], 'Culinária': ['Culinary'], 'Artista do Entretenimento': ['Entertainer'],
    'Pintor': ['Painter'], 'Agente Secreto': ['SecretAgent', 'Secret_Agent'],
    'Influenciador de Estilo': ['StyleInfluencer', 'Style_Influencer'],
    'Guru da Tecnologia': ['TechGuru', 'Tech_Guru'], 'Escritor': ['Writer'],
}


def _carreira(rotulo):
    """A carreira adulta do jogo que contém a palavra-chave (a de nome mais curto)."""
    if ('CAREER', rotulo) in _CACHE:
        return _CACHE[('CAREER', rotulo)]
    import sims4.resources
    gerente = services.get_instance_manager(sims4.resources.Types.CAREER)
    chaves = [_chave(c) for c in EMPREGOS_JOGO.get(rotulo, [])]
    candidatas = sorted(
        (len(t.__name__), t.__name__, t) for t in gerente.types.values()
        if any(c in _chave(t.__name__) for c in chaves)
        and 'adult' in t.__name__.lower()
        and not any(x in t.__name__.lower() for x in ('teen', 'child', 'parttime', 'part_time', 'volunteer'))
    )
    achada = candidatas[0][2] if candidatas else None
    _CACHE[('CAREER', rotulo)] = achada
    return achada


def _aplicar_emprego(info, rotulo):
    if not rotulo or rotulo == 'Desempregado':
        return
    carreira = _carreira(rotulo)
    if carreira is None:
        _log('emprego sem correspondente no jogo: ' + rotulo)
        return
    try:
        rastreador = info.career_tracker
        try:
            rastreador.add_career(carreira(info), show_confirmation_dialog=False)
        except TypeError:
            rastreador.add_career(carreira(info))
    except Exception:
        _log('emprego {} {}\n{}'.format(info.first_name, rotulo, traceback.format_exc()))


def _criadores(fichas, sobrenome):
    from sims.sim_info_types import Age, Gender
    from sims.sim_spawner import SimCreator
    idades = {'jovem adulto': Age.YOUNGADULT, 'adulto': Age.ADULT, 'idoso': Age.ELDER}
    return [
        SimCreator(
            age=idades.get(f.get('idade'), Age.ADULT),
            gender=Gender.FEMALE if f.get('genero') == 'feminino' else Gender.MALE,
            first_name=f['nome'],
            last_name=sobrenome,
        )
        for f in fichas
    ]


def _instanciar(criadores, household, client, posicao):
    from sims.sim_spawner import SimSpawner
    try:
        SimSpawner.create_sims(criadores, household=household, tgt_client=client,
                               account=client.account, sim_position=posicao,
                               creation_source='npcgen')
    except TypeError:
        # Plano B, caso esta versão do jogo tenha outra assinatura.
        _log('create_sims recusou os argumentos, tentando plano B\n' + traceback.format_exc())
        infos, _h = SimSpawner.create_sim_infos(criadores, household=household,
                                                account=client.account, creation_source='npcgen')
        for info in infos:
            SimSpawner.spawn_sim(info, sim_position=posicao)


def criar(output, forcar=False):
    """Cria na casa do Sim ativo os Sims de troca/casa.json, tirando os da
    casa anterior. A aparência fica por conta do sorteio do jogo."""
    casa = _ler_json(ARQ_CASA, None)
    if not casa or not casa.get('sims'):
        output('npcgen: casa.json vazio. Use /gerar no Telegram.')
        return
    estado = _ler_json(ARQ_CRIADOS, {})
    if not forcar and estado.get('casa') == casa.get('id'):
        return

    client = services.client_manager().get_first_client()
    ativo = client.active_sim if client is not None else None
    if ativo is None:
        output('npcgen: entre num lote com um Sim ativo antes de criar a casa.')
        return
    household = ativo.household

    # Remove os da casa anterior e qualquer outro que o mod já tenha criado.
    anteriores = set(estado.get('ids', [])) | set(estado.get('historico', []))
    anteriores.discard(ativo.sim_info.sim_id)
    _remover(sorted(anteriores), household, output)
    _passo('varrer', _varrer, output)  # se a limpeza falhar, a casa nova chega mesmo assim

    # A remoção termina depois (o corpo some primeiro, a ficha depois). Espera a
    # família esvaziar antes de criar, para a casa nova caber inteira no limite de 8.
    ainda = [info.first_name for info in household.sim_info_gen() if info.sim_id in anteriores]
    if ainda:
        espera = estado.get('espera', {})
        voltas = espera.get('voltas', 0) + 1 if espera.get('casa') == casa.get('id') else 1
        if voltas < ESPERA_SAIDA:
            estado = _ler_json(ARQ_CRIADOS, {})
            estado['espera'] = {'casa': casa.get('id'), 'voltas': voltas}
            _escrever_json(ARQ_CRIADOS, estado)
            output('npcgen: esperando {} saírem da família para criar a casa nova...'.format(', '.join(ainda)))
            if _ALARME is None:
                output('npcgen: rode npcgen.criar de novo em alguns segundos (ou ligue npcgen.auto).')
            return
        _log('criar: {} não saíram a tempo; criando assim mesmo'.format(ainda))
    desconhecidos = [info.first_name for info in household.sim_info_gen()
                     if info.sim_id != ativo.sim_info.sim_id and info.sim_id not in anteriores]
    if desconhecidos:
        output('npcgen: AVISO: a família tem Sims que o mod não criou ou perdeu o registro: {}. '
               'Se forem de casas antigas, selecione o seu Sim e rode npcgen.limpar.'.format(
                   ', '.join(desconhecidos)))
    ocupados = len(list(household.sim_info_gen()))
    # O seu Sim (existente) já está na casa: só os outros são criados.
    a_criar = [f for f in casa['sims'] if not f.get('existente')]
    fichas = a_criar[:max(0, LIMITE_CASA - ocupados)]
    if len(fichas) < len(a_criar):
        output('npcgen: a casa só cabe {} Sims; criando {} de {}.'.format(
            LIMITE_CASA, len(fichas), len(a_criar)))

    antes = set(info.sim_id for info in household.sim_info_gen())
    sobrenome = getattr(household, 'name', '') or 'Silva'
    _instanciar(_criadores(fichas, sobrenome), household, client, ativo.position)

    novos = [info for info in household.sim_info_gen() if info.sim_id not in antes]
    por_nome = dict((info.first_name.lower(), info) for info in novos)
    for f in fichas:
        info = por_nome.get(f['nome'].lower())
        if info is None:
            output('npcgen: não consegui criar ' + f['nome'])
            continue
        _aplicar_tracos(info, f.get('tracos', []))
        _aplicar_aspiracao(info, f.get('aspiracao', ''))
        _aplicar_emprego(info, f.get('emprego', ''))
        output('+ chegou {} ({}, {}; {})'.format(f['nome'], f.get('idade'), ', '.join(f.get('tracos', [])),
                                                f.get('emprego') or 'sem emprego'))

    ids_novos = [info.sim_id for info in novos]
    _LACOS_PENDENTES['casa'] = casa.get('id')  # aplicados na próxima volta, com o criados.json já salvo
    # 'historico' guarda todo Sim já criado e ainda não removido com certeza.
    restantes = [i for i in anteriores if services.sim_info_manager().get(i) is not None]
    _escrever_json(ARQ_CRIADOS, {'casa': casa.get('id'), 'ids': ids_novos,
                                 'historico': restantes + ids_novos,
                                 'removidos': _ler_json(ARQ_CRIADOS, {}).get('removidos', [])})
    _log('casa {} criada: {}'.format(casa.get('id'), [f['nome'] for f in fichas]))
    _passo('lacos', lacos, output)  # apresenta todos e põe as barras de amizade/romance


# ---------- modo automático ----------

class _Dono(object):
    pass


_DONO = _Dono()
_LACOS_PENDENTES = {'casa': None}
_ALARME = None
_VOLTAS = {'n': 0, 'lote': None}


def _passo(nome, func, *args, **kwargs):
    """Roda um passo da volta; um erro nele vai para o log sem parar os outros."""
    try:
        func(*args, **kwargs)
    except Exception:
        _log('{}\n{}'.format(nome, traceback.format_exc()))


def _tique(_handle=None):
    _VOLTAS['n'] += 1
    if _VOLTAS['n'] == 1:  # refeito a cada vez que o automático liga (pega atualizações do jogo)
        _passo('catalogo', catalogo, _log)
    lote = _lote_atual()
    mudou_lote = lote != _VOLTAS['lote']
    _VOLTAS['lote'] = lote
    casa = _ler_json(ARQ_CASA, None)
    if casa and casa.get('id') and casa.get('id') != _ler_json(ARQ_CRIADOS, {}).get('casa'):
        _passo('criar', criar, _log)
        _passo('mapear', mapear, _log)
    elif mudou_lote or _VOLTAS['n'] % MAPEAR_A_CADA == 0:
        _passo('mapear', mapear, _log)
    if mudou_lote or _VOLTAS['n'] % MAPEAR_A_CADA == 1:
        _passo('jogo', descrever_jogo)  # o seu Sim e o lote, para o próximo /gerar
    _passo('varrer', _varrer, _log)  # Sims removidos que continuaram andando pelo lote
    if _LACOS_PENDENTES['casa'] or _VOLTAS['n'] % 10 == 1:
        _LACOS_PENDENTES['casa'] = None
        _passo('lacos', lacos)
    _passo('executar', executar, _log, silencioso=True)
    _passo('observar', observar)


def alternar_auto(output):
    global _ALARME
    import alarms
    import clock
    if _ALARME is not None:
        alarms.cancel_alarm(_ALARME)
        _ALARME = None
        output('npcgen: automático DESLIGADO.')
        return
    _VOLTAS['n'], _VOLTAS['lote'] = 0, None  # a 1ª volta refaz o catálogo e o mapa do lote
    _ALARME = alarms.add_alarm_real_time(_DONO, clock.interval_in_real_seconds(3), _tique, repeating=True)
    output('npcgen: automático LIGADO (a cada 3 s). Digite npcgen.auto de novo para desligar.')
