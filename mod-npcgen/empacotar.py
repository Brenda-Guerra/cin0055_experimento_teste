"""Compila npcgen.py com Python 3.7 (a versão que o The Sims 4 usa), empacota
como npcgen.ts4script e instala na pasta Mods do jogo.

O bot.py chama isto sozinho ao iniciar (só refaz o pacote se o npcgen.py
mudou). Também dá para rodar à mão:

    python empacotar.py
    python empacotar.py --mods "D:/OneDrive/Documentos/Electronic Arts/The Sims 4/Mods"
    python empacotar.py --python37 "C:/Python37/python.exe"
    python empacotar.py --forcar        (refaz mesmo sem mudança)

Precisa do Python 3.7 instalado (python.org, versão 3.7.9). No Windows ele é
achado sozinho pelo comando "py -3.7".
O jogo só carrega a versão nova do mod quando é reiniciado.
"""
import argparse
import hashlib
import os
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

AQUI = Path(__file__).resolve().parent
FONTE = AQUI / "npcgen.py"

COMPILAR = (
    "import sys, py_compile\n"
    "assert sys.version_info[:2] == (3, 7), 'precisa ser Python 3.7, achei %s' % sys.version\n"
    "py_compile.compile(sys.argv[1], cfile=sys.argv[2], dfile='npcgen.py', doraise=True)\n"
)


class ErroEmpacotar(Exception):
    pass


@dataclass
class Resultado:
    ts4script: Path
    troca: Path
    mudou: bool              # False = já estava atualizado, nada foi feito
    compilado_com: str = ""  # vazio = foi sem compilar (sem Python 3.7)


def achar_mods(caminho=None) -> Path:
    if caminho:
        p = Path(caminho).expanduser()
        if not p.is_dir():
            raise ErroEmpacotar(f"a pasta Mods não existe: {p}")
        return p
    casa = Path.home()
    for docs in ("Documents", "Documentos", "OneDrive/Documents", "OneDrive/Documentos"):
        candidato = casa / docs / "Electronic Arts" / "The Sims 4" / "Mods"
        if candidato.is_dir():
            return candidato
    raise ErroEmpacotar("não achei a pasta Mods do The Sims 4; ponha o caminho em SIMS_MODS no .env")


def compilar(python37, destino_pyc):
    tentativas = [[python37]] if python37 else [["py", "-3.7"], ["python3.7"]]
    for cmd in tentativas:
        try:
            r = subprocess.run(cmd + ["-c", COMPILAR, str(FONTE), str(destino_pyc)],
                               capture_output=True, text=True, timeout=60)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
        if r.returncode == 0:
            return " ".join(cmd)
    return None


def _versao() -> str:
    return hashlib.sha256(FONTE.read_bytes() + COMPILAR.encode()).hexdigest()


def empacotar(mods=None, python37=None, forcar=False) -> Resultado:
    """Instala o mod em <Mods>/npcgen/. Só refaz se o npcgen.py mudou desde o
    último pacote (ou com forcar=True)."""
    pasta_mods = achar_mods(mods)
    destino = pasta_mods / "npcgen"
    troca = destino / "troca"
    troca.mkdir(parents=True, exist_ok=True)
    ts4script = destino / "npcgen.ts4script"
    marca = destino / "npcgen.versao"

    versao = _versao()
    if not forcar and ts4script.exists() and marca.exists() and marca.read_text().strip() == versao:
        return Resultado(ts4script, troca, mudou=False)

    with tempfile.TemporaryDirectory() as tmp:
        pyc = Path(tmp) / "npcgen.pyc"
        usado = compilar(python37, pyc)
        novo = destino / "npcgen.ts4script.novo"
        with zipfile.ZipFile(novo, "w", zipfile.ZIP_STORED) as z:
            z.write(FONTE, "npcgen.py")
            if usado:
                z.write(pyc, "npcgen.pyc")
        try:
            os.replace(novo, ts4script)
        except PermissionError as e:
            novo.unlink(missing_ok=True)
            raise ErroEmpacotar("o arquivo do mod está em uso (o jogo está aberto?). "
                                "Feche o jogo e reinicie o bot.") from e
    # Sem Python 3.7 o jogo não carrega o mod: não marca como atualizado,
    # para tentar de novo da próxima vez.
    if usado:
        marca.write_text(versao)
    return Resultado(ts4script, troca, mudou=True, compilado_com=usado or "")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mods", help="pasta Mods do The Sims 4")
    p.add_argument("--python37", help="caminho do python.exe da versão 3.7")
    p.add_argument("--forcar", action="store_true", help="refaz o pacote mesmo sem mudança")
    args = p.parse_args()
    try:
        r = empacotar(args.mods, args.python37, args.forcar)
    except ErroEmpacotar as e:
        raise SystemExit(f"Erro: {e}")
    if not r.mudou:
        print("O mod já estava atualizado:", r.ts4script)
    else:
        print("Mod instalado em:", r.ts4script)
        if r.compilado_com:
            print("Compilado com:", r.compilado_com)
        else:
            print("\n*** ATENÇÃO: não achei o Python 3.7, então o mod foi SEM compilar.")
            print("*** O jogo não vai carregar o mod. Instale o Python 3.7.9 (python.org)")
            print("*** ou indique o caminho: --python37 \"C:/.../python.exe\"\n")
    print("Pasta de troca:", r.troca.as_posix())


if __name__ == "__main__":
    main()
