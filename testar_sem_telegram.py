"""Testa os Sims + Gemini no terminal, sem Telegram.

    python testar_sem_telegram.py

Comandos:
    /gerar                  -> a IA inventa uma casa nova
    /gerar <descrição>      -> casa nova a partir do Sim inicial descrito
    Nome: texto             -> fala com um Sim
    ENTER vazio             -> rodada sem mensagens (os Sims agem sozinhos)
    sair
Cada geração ou rodada gasta 1 chamada da cota.
Usa a pasta dados_teste/ para não misturar com o bot de verdade.
"""
import asyncio
import os

from dotenv import load_dotenv

from cerebro import Cerebro, ErroCerebro, LimiteAtingido
from gerador import Gerador
from motor import Motor
from mundo import Mundo, descrever


def mostrar_casa(sims):
    for s in sims:
        print(f"\n🏠 {s['nome']} ({s['idade']}) — {', '.join(s['tracos'])}")
        print(f"   aspiração: {s['aspiracao']}")
        print(f"   relação: {s['relacao']}")
        print(f"   história: {s['historia']}")


async def main() -> None:
    load_dotenv()
    mundo = Mundo("dados_teste/sims.json", "dados_teste/troca", "dados_teste")
    cerebro = Cerebro(os.environ["GEMINI_API_KEY"], os.getenv("GEMINI_MODELO", "gemini-3.5-flash-lite"))
    gerador = Gerador(cerebro, int(os.getenv("MORADORES_MIN", 2)), int(os.getenv("MORADORES_MAX", 4)),
                      arquivo_recentes=mundo.dados / "nomes_recentes.json")
    motor = Motor(mundo, cerebro, ocioso_s=0.001, limite_diario=int(os.getenv("LIMITE_DIARIO", 400)))

    if mundo.sims:
        mostrar_casa(mundo.sims)
    else:
        print("A casa está vazia. Use /gerar (com ou sem descrição do Sim inicial).")

    while True:
        linha = (await asyncio.to_thread(input, "\nvocê> ")).strip()
        if linha.lower() == "sair":
            break
        try:
            if linha.startswith("/gerar"):
                mostrar_casa(await motor.nova_casa(gerador, linha[len("/gerar"):].strip()))
                continue
            if not mundo.sims:
                print("Gere a casa primeiro: /gerar")
                continue
            if ":" in linha:
                nome, texto = linha.split(":", 1)
                sim = mundo.achar_sim(nome)
                if not sim:
                    print("Não conheço esse Sim.")
                    continue
                motor.receber("Teste", sim["nome"], texto.strip())
            decisoes = await motor.talvez_rodar()
        except (ErroCerebro, LimiteAtingido) as e:
            print("Erro:", e)
            continue
        for d in decisoes or []:
            print(f"\n📔 {d.sim} {descrever(d)}")
            if d.fala:
                print(f'   disse: "{d.fala}"')
            print(f"   diário: {d.diario}")
            print(f"   opinião: {d.opiniao}")
        print(f"\n(chamadas restantes hoje: {motor.chamadas_restantes()})")


if __name__ == "__main__":
    asyncio.run(main())
