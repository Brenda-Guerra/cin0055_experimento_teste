# Ponte Telegram ↔ Gemini — NPCs generativos no The Sims 4

A turma fala com os Sims por um grupo do Telegram. Uma IA (Gemini, plano
gratuito) decide o que cada Sim faz, guarda a memória de cada um e escreve
um diário que volta para o grupo. As ações vão para um arquivo que o mod do
The Sims 4 vai ler.

```
grupo do Telegram ──► bot.py ──► motor.py (junta mensagens, rodadas, cota)
                                    │
                                    ├─► cerebro.py ──► Gemini (1 chamada por rodada, para todos os Sims)
                                    │
                                    └─► mundo.py ──► troca/comandos.json ──► mod do The Sims 4
                                                 ◄── troca/estado.json  ◄── (opcional, escrito pelo mod)
```

## Como a turma usa

No grupo, a pessoa começa a mensagem pelo nome do Sim:

```
Ana: o Davi largou a faculdade e não te contou
```

O bot reage com 👀 ("o Sim ouviu"). Na rodada seguinte, cada Sim decide
uma ação (conversar, discutir, fofocar...) e o grupo recebe o diário:

> 📔 **Ana** discutiu com Davi
> *Não acredito que ele jogou fora o dinheiro que eu paguei. Fui tirar satisfação.*

Comandos: `/ajuda`, `/sims` (quem mora na casa), `/cota` (chamadas restantes
hoje), `/id` (ID do grupo e o seu), `/gerar` (só para quem conduz o
experimento, veja abaixo).

## Instalação

1. **Bot.** No Telegram, fale com o @BotFather: `/newbot` (guarde o token)
   e depois `/setprivacy` → escolha o bot → **Disable**. Sem isso, o bot
   não lê as mensagens comuns do grupo. Se ele já estava no grupo, tire e
   adicione de novo depois de mudar.
2. **Chave do Gemini.** Em [aistudio.google.com](https://aistudio.google.com),
   clique em *Get API key*. A cota é **por projeto**: crie um projeto só
   para o dia do teste, para não gastar a cota testando.
3. **Instalar e configurar:**
   ```
   pip install -r requirements.txt
   copy .env.exemplo .env      (no Linux/Mac: cp .env.exemplo .env)
   ```
   Preencha `TELEGRAM_TOKEN` e `GEMINI_API_KEY` no `.env`. Confira no AI
   Studio o nome do modelo e a cota dele.
4. **Testar a IA sem Telegram:** `python testar_sem_telegram.py`
5. **Ligar o bot:** `python bot.py`. No grupo, mande `/id`. Copie o ID do
   chat para `GRUPO_ID` e o seu ID para `ADMIN_ID` no `.env`, e reinicie.
   Mande `/start` ao bot no privado uma vez, para ele poder te avisar.

   Ao iniciar, o bot:
   - empacota o mod da pasta `mod-npcgen/` (com o Python 3.7) e instala em
     `Mods/npcgen/` do jogo, **só se o `npcgen.py` mudou**. O jogo só carrega
     a versão nova quando é reiniciado. Se não achar a pasta Mods, preencha
     `SIMS_MODS` no `.env`; se não achar o Python 3.7, preencha `PYTHON37`;
   - usa como pasta de troca a `Mods/npcgen/troca` (a não ser que
     `PASTA_TROCA` esteja preenchida);
   - manda "🤖 Bot inicializado" no grupo quando já está recebendo
     mensagens, e para você, no privado, a situação do mod e da cota.
6. **Gerar a casa:** no grupo, mande `/gerar` (veja "Os Sims", abaixo).

## Filtro de conteúdo (+18 e palavrões)

Três camadas:

1. **No bot, antes da IA:** mensagens com palavras de `palavras_bloqueadas.txt`
   são ignoradas. O bot reage com 🙈 e não guarda o texto (o log registra
   só que houve um bloqueio). O filtro pega acento, letra repetida
   (`seeexo`), número no lugar de letra (`s3x0`) e letra separada (`s e x o`).
   Para ajustar, edite o arquivo e reinicie o bot.
2. **No Gemini:** filtro de segurança no nível mais rígido para conteúdo
   sexual. Se ele barrar uma rodada, as mensagens daquela rodada são
   apagadas da memória dos Sims, para não travar as rodadas seguintes.
3. **Na resposta:** uma decisão cuja fala, diário ou opinião contenha
   palavra bloqueada é descartada antes de ir para o grupo ou para o jogo.

Verbos marcados com `~` na lista são barrados em todas as conjugações
(`~transar` pega "transamos", "transando", "transei"...), sem pegar palavras
parecidas como "transporte", "trânsito" ou "trans". Toda palavra da lista
também é barrada no plural.

Falsos positivos conhecidos (raros, aceitos): "pau de selfie", "entrou em
transe", "que gozado" e "gozo de férias". Palavras que davam falso positivo
demais ("rola", "pelada", "comer", "chupar", "meter") ficaram de fora.

## Cota gratuita

No plano gratuito do Gemini, os modelos Flash-Lite aguentam bem mais
chamadas por dia do que os Flash. Por isso o bot nunca chama a IA a cada
mensagem:

- a cada `RODADA_SEGUNDOS` (30 s), se chegou mensagem, faz **uma** chamada
  que decide todos os Sims;
- sem mensagens, os Sims agem sozinhos a cada `OCIOSO_SEGUNDOS` (120 s);
- cada pessoa manda no máximo uma mensagem a cada `INTERVALO_POR_PESSOA`;
- `LIMITE_DIARIO` é um freio: o bot para de chamar a IA ao chegar nele.
  A contagem zera à meia-noite do horário do Pacífico, como a do Google.

25 minutos de teste gastam no máximo umas 50 chamadas.

⚠️ No plano gratuito, o Google pode usar as mensagens para melhorar os
produtos dele. O `/ajuda` avisa a turma.

## Arquivos que o programa cria

| Arquivo | Para quê |
|---|---|
| `troca/comandos.json` | Fila de ações para o mod executar |
| `troca/estado.json` | Opcional: o mod escreve o estado do jogo e a IA passa a ver |
| `dados/memoria.json` | Lembranças e opinião de cada Sim (sobrevive a reinícios) |
| `dados/log.jsonl` | Tudo o que a turma mandou e tudo o que a IA decidiu, para o `REGISTRO.md` |
| `dados/cota.json` | Chamadas gastas hoje |

## Contrato com o mod

O mod lê `troca/comandos.json` e executa, em ordem, os comandos com `id`
maior que o último que ele já executou:

```json
{"comandos": [
  {"id": 7, "t": "2026-11-05T11:02:10+00:00", "sim": "Ana", "acao": "discutir", "alvo": "Davi"},
  {"id": 8, "t": "2026-11-05T11:02:10+00:00", "sim": "Davi", "acao": "ficar_sozinho", "alvo": null}
]}
```

Ações possíveis (o mod traduz cada uma para uma interação do jogo):
`conversar`, `elogiar`, `discutir`, `fofocar`, `flertar`, `abracar`,
`pedir_desculpas`, `contar_piada`, `ignorar`, `ficar_sozinho`.

Se quiser, o mod escreve `troca/estado.json` com o que quiser mostrar à IA
(humor, onde cada Sim está, o que está fazendo). O conteúdo vai direto para
o prompt.

## Os Sims

Ninguém é pré-definido: a IA cria a casa.

```
/gerar
/gerar um músico preguiçoso que largou a faculdade
/gerar Davi, um idoso ranzinza que acabou de ficar viúvo
```

Sem descrição, a IA inventa tudo. Com descrição, ela respeita o que foi dito
sobre o Sim inicial (inclusive o nome) e cria de `MORADORES_MIN` a
`MORADORES_MAX` moradores em volta dele, cada um com:

- nome, gênero e idade (jovem adulto, adulto ou idoso);
- 3 traços e 1 aspiração, escolhidos de listas do jogo-base (`gerador.py`),
  para o mod conseguir aplicá-los depois;
- a relação com o Sim inicial e com os outros;
- uma história com um segredo ou mágoa que se cruza com a dos outros.

O grupo recebe as fichas **sem as histórias**: os segredos ficam com os
Sims, e a turma descobre conversando. As histórias completas aparecem no
terminal e em `dados/log.jsonl`.

`/gerar` substitui a casa inteira e apaga a memória dos moradores antigos.
Só a pessoa de `ADMIN_ID` pode usar. A casa fica salva em `sims.json` (o bot
a recarrega ao reiniciar) e em `troca/casa.json` (para o mod).

No jogo, o mod (`npcgen`) cria os Sims sozinho na casa do Sim ativo, com
nome, gênero, idade, traços e aspiração; a aparência é sorteada pelo jogo.
Com `npcgen.auto` ligado no console, cada `/gerar` tira a família anterior e
traz a nova em poucos segundos. O Sim que você controla fica na casa como
anfitrião e não é comandado pela IA.
