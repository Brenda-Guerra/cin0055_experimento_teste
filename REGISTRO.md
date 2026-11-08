# Registro do teste

**Experimento:** A casa que se gera em volta de você, um mod de The Sims 4 com NPCs generativos (tema 11, NPCs generativos e mundos vivos, CIN0055 2026.2).
**Teste com a turma:** 05/11/2026.

Durante o teste, a turma mandava mensagens a um grupo do Telegram no formato `Nome: mensagem`. Um bot entregava as mensagens ao Gemini, que decidia o que cada morador fazia e sentia. O mod executava essas decisões no jogo.

## 1. O que a turma fez que eu não esperava

**A turma escreveu mensagens longas.** Eu esperava frases curtas, como recados. Muitas mensagens contavam uma história inteira. O bot cortava tudo depois de 280 caracteres e não avisava. O Sim reagia a meia mensagem, e quem escreveu não sabia que o resto tinha se perdido.

**A turma quis falar com vários Sims de uma vez.** O formato `Nome: mensagem` só endereça um morador. Contar um boato para dois Sims, ou anunciar algo para a casa toda, exigia repetir a mensagem para cada um.

**A turma insistiu nos mesmos conflitos.** As provocações se repetiam contra os mesmos moradores. O mod tinha sido feito para a raiva crescer a cada reincidência, e ela cresceu: a emoção ficou travada no nível máximo, e **dois Sims morreram de raiva**. No The Sims 4, ficar furioso por muito tempo mata. Eu não tinha previsto isso.

**A partir de certo momento, o bot parou de responder.** Ele continuou reagindo às mensagens com 👀, mas parou de gerar ações no jogo, sem nenhum aviso no grupo. Para a turma, os Sims simplesmente pararam.

**Não dava para saber o que tinha acontecido de verdade.** O diário de cada Sim é escrito antes de o jogo executar a ação. Várias ações não aconteceram, e o diário as contava mesmo assim. A turma não tinha como distinguir o que o Sim *quis* fazer do que ele *fez*.

**Os moradores se desencontravam e ficavam parados.** Quando dois Sims tinham reações diferentes na mesma rodada, um ia procurar o outro para conversar enquanto o outro ia dormir. A conversa nunca começava, e os dois ficavam parados. Às vezes um Sim também ficava sem ação por várias rodadas.

## 2. O que mudei por causa disso

| O que aconteceu | O que mudei |
|---|---|
| Mensagens longas cortadas sem aviso | O limite passou de 280 para 1000 caracteres. Se alguém passar disso, o bot avisa quanto o Sim ouviu. Mensagem com foto também conta, pela legenda. |
| Querer falar com vários Sims | A entrada sai do grupo do Telegram e vai para uma **página com a imagem de cada Sim gerado**. A pessoa toca na imagem de um Sim para mandar a mensagem para ele, ou seleciona vários (ou todos) para a mesma mensagem chegar a cada um. |
| Sims mortos de raiva | A emoção que o mod põe vale só para uma rodada: cada comando novo apaga a anterior, e ela também some sozinha depois de 4 minutos. As emoções que matam no nível máximo (raiva, vergonha, riso, energia) ficam no máximo no nível 2. Um vigia derruba o nível máximo a cada 3 segundos, mesmo quando ele vem do próprio jogo, e avisa no grupo. A morte fica desligada no jogo durante o teste. O Gemini passou a saber que emoções esfriam. |
| Bot parou sem aviso | Quando as rodadas param (cota do Gemini, erros seguidos, erro inesperado), o bot avisa no grupo e para quem conduz, com o motivo, e avisa de novo quando volta. A gravação de arquivos entre o bot e o jogo passou a tentar de novo quando o arquivo está em uso no Windows, uma causa provável da parada. |
| Não saber o que aconteceu no jogo | Alguns segundos depois do diário, o bot posta o que de fato aconteceu: "✅ Joao discutiu com Nayara", "❌ Pedro não conseguiu abraçar Lia: o outro estava ocupado". O Gemini também recebe esse resultado e não finge que uma ação falha aconteceu. |
| Interações que não aconteciam | Corrigi as causas encontradas nos logs. Os Sims gerados nunca tinham se conhecido no jogo, e o jogo recusa interações maldosas entre estranhos. Agora o mod apresenta todos uns aos outros e põe as barras de amizade e romance que a geração definiu. Também troquei as interações de "discutir", que não existiam no jogo, e criei uma reserva para quando todas as opções de uma ação falham. |
| Sims desencontrados e parados | Quem vai ser procurado por alguém na mesma rodada espera a conversa acontecer antes de ir dormir ou tomar banho. Se a conversa não começa, o outro Sim também puxa conversa. O Gemini passou a ser instruído a fazer quem vai ser procurado reagir a quem veio falar com ele. |

## 3. O que decidi não mudar, e por quê

**O modelo continua sendo o Gemini gratuito.** O experimento precisa poder ser instalado e repetido por qualquer pessoa sem custo. Em vez de pagar um modelo, o bot troca sozinho para outro modelo gratuito quando o principal está sobrecarregado.

**Continua sendo uma chamada à IA por rodada para todos os Sims.** Uma chamada por Sim multiplicaria o gasto de cota. Além disso, é decidir todos juntos que permite aos moradores se coordenarem: um provoca, o outro responde na mesma rodada.

**O diário continua sendo escrito antes de o jogo executar.** O diário é a intenção do Sim, e esperar o jogo atrasaria tudo. Em vez de mudar isso, acrescentei o resultado real logo depois. A diferença entre o que o Sim quis e o que o jogo deixou fazer virou parte do que dá para observar.

**O conflito continua.** A raiva, a vergonha e a escalada a cada reincidência ficaram. Limitei o nível e desliguei a morte, mas tirar o conflito tiraria justamente o que o experimento observa: se os moradores guardam rancor, se tomam partido, se a família se divide.

**O filtro de conteúdo adulto continua,** mesmo barrando algumas mensagens inocentes. O teste é com a turma inteira e a casa é para todas as idades.

**Os laços continuam só nas barras de relacionamento.** O mod não cria casamento, namoro oficial nem árvore genealógica. Mexer nessas estruturas do jogo arrisca corromper o save, e as barras já bastam para os Sims agirem como amigos, inimigos ou ex.

**O Sim do jogador continua morando na casa.** O jogo exige pelo menos um Sim na família controlada. Em vez de esconder esse Sim, ele virou o Sim inicial: a casa é gerada em volta dele, no lote em que ele está.

**Gerar uma casa nova continua sendo só de quem conduz.** Se a turma pudesse trocar a casa, uma história seria apagada no meio, e cada geração gasta cota.

---

**A pergunta mudou:** deixou de ser se os moradores agem como família ou como figurantes. Eles formaram laços, guardaram rancor e espalharam boatos entre si. A pergunta passou a ser quem manda nessa família: a história que a IA escreve, ou as regras do jogo que a executa. A IA mandava os Sims brigarem, e o jogo recusava porque eles nunca tinham se conhecido. A IA mandava raiva, e o jogo transformava em morte.
