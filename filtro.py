"""Filtro de conteúdo +18 e palavrões, sem gastar chamada da IA.

A lista fica em palavras_bloqueadas.txt (uma por linha, edite à vontade):
  palavra   -> bloqueia a palavra inteira e o plural ("cu" bloqueia "cu"/"cus",
               não "custo")
  ~verbo    -> bloqueia todas as conjugações ("~transar" pega "transamos",
               "transando", "transei"..., mas não "transporte")
  *trecho   -> bloqueia qualquer palavra que contenha o trecho ("*porn" pega "pornhub")
  🍆        -> emojis e símbolos: bloqueia se aparecer em qualquer lugar

Pega também variações comuns: acentos (séxo), letras repetidas (seeexo),
números no lugar de letras (s3x0) e letras separadas (s e x o).
"""
import os
import re
import unicodedata
from pathlib import Path

_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"})
_ARQUIVO = Path(os.getenv("ARQUIVO_PALAVRAS", Path(__file__).with_name("palavras_bloqueadas.txt")))


def _colapsar(palavra: str) -> str:
    return re.sub(r"(.)\1+", r"\1", palavra)


def _tokens(texto: str) -> list[str]:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    pedacos = re.findall(r"[a-z]+", sem_acento.lower().translate(_LEET))
    # junta letras soltas seguidas: "s e x o" -> "sexo"
    juntos, soltas = [], ""
    for p in pedacos:
        if len(p) == 1:
            soltas += p
            continue
        if soltas:
            juntos.append(soltas)
            soltas = ""
        juntos.append(p)
    if soltas:
        juntos.append(soltas)
    return [_colapsar(t) for t in juntos]


# Terminações de todos os tempos e pessoas (sem acento), por grupo de verbo:
# presente, pretéritos, futuros, condicional, subjuntivos, imperativo,
# infinitivo pessoal, gerúndio e particípio (com feminino e plural).
_TERMINACOES = {
    "ar": "o as a amos ais am ei aste ou astes aram ava avas avamos aveis avam "
          "ara aras aramos areis arei aremos arao aria arias ariamos arieis ariam "
          "e es emos eis em asse asses assemos asseis assem ar ares armos ardes arem "
          "ai ando ado ada ados adas",
    "er": "o es e emos eis em i este eu estes eram ia ias iamos ieis iam era eras eramos "
          "ereis erei eremos erao eria erias eriamos erieis eriam a as amos ais am "
          "esse esses essemos esseis essem er eres ermos erdes erem ei endo ido ida idos idas",
    "ir": "o es e imos is em i iste iu istes iram ia ias iamos ieis iam ira iras iramos "
          "ireis irei iremos irao iria irias iriamos irieis iriam a as amos ais am "
          "isse isses issemos isseis issem ir ires irmos irdes irem i indo ido ida idos idas",
}


def conjugar(verbo: str) -> set[str]:
    """'transar' -> {'transo', 'transamos', 'transando', 'transei', ...}"""
    grupo = verbo[-2:]
    if grupo not in _TERMINACOES:
        return {verbo}
    raiz = verbo[:-2]
    return {raiz + t for t in _TERMINACOES[grupo].split()}


def _carregar():
    inteiras, trechos, simbolos = set(), [], []
    for linha in _ARQUIVO.read_text(encoding="utf-8").splitlines():
        linha = linha.split("#", 1)[0].strip()
        if not linha:
            continue
        if not linha.isascii():
            simbolos.append(linha)
        elif linha.startswith("*"):
            trechos.append(_colapsar(linha[1:].lower()))
        elif linha.startswith("~"):
            inteiras.update(_colapsar(f) for f in conjugar(linha[1:].lower()))
        else:
            palavra = linha.lower()
            inteiras.update({_colapsar(palavra), _colapsar(palavra + "s")})
    return inteiras, trechos, simbolos


_INTEIRAS, _TRECHOS, _SIMBOLOS = _carregar()


def bloqueado(texto: str) -> bool:
    if any(s in texto for s in _SIMBOLOS):
        return True
    for t in _tokens(texto):
        if t in _INTEIRAS or any(tr in t for tr in _TRECHOS):
            return True
    return False
