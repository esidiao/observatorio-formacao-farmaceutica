"""
etl/historico.py
Gera data/historico.json: a variacao de cada indicador por UF entre o ciclo do Censo
anterior e o atual, que o site mostra como delta e seta de tendencia.

Uso:
    python etl/historico.py --anterior data/nacional_2024.json
    python etl/historico.py --anterior data/nacional_2023.json --atual data/nacional.json --saida /tmp/h.json

Ate 2026-11-26 o arquivo nao tinha gerador: foi montado a mao num commit antigo e so
tinha o ICON recalculado por farmacia_popular.py. Rolar o ciclo para 2025 sem um
gerador versionado repetiria a montagem manual, entao a regra ficou aqui, e a direcao
de cada indicador sai da MESMA fonte que o site usa (site/static/js/glossario.js,
campo `dir`), nao de uma tabela paralela.

Convencoes preservadas do arquivo anterior (conferidas em 27 UFs x 9 indicadores):
  - delta = atual - anterior, arredondado a 4 casas;
  - tendencia "estavel" quando delta == 0;
  - ICON de cada ano = municipios_fp ATUAL / municipios_oferta DAQUELE ano (a Farmacia
    Popular entra como retrato do presente nos dois anos; ver farmacia_popular.py).

Correcao em relacao ao arquivo antigo: `municipios_deserto` tinha a queda rotulada
como "piora". O glossario do site diz `dir:'menor'` (menos desertos e melhor), entao
a tendencia correta e o oposto. Isto afeta so o rotulo, nao o delta.
"""
import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GLOSSARIO = REPO / "site" / "static" / "js" / "glossario.js"

INDICADORES = ["ICT", "IAF", "ICON", "E", "HHI", "vagas_total",
               "municipios_oferta", "municipios_deserto", "n_ies"]


# Sentido em que cada indicador melhora. Tres deles (vagas_total, municipios_oferta,
# n_ies) sao `contextual` no glossario, mas o historico publicado sempre tratou o
# aumento como melhora; a tabela fixa essa convencao em vez de adivinha-la.
DIRECAO = {"ICT": "menor", "IAF": "maior", "ICON": "maior", "E": "maior",
           "HHI": "menor", "vagas_total": "maior", "municipios_oferta": "maior",
           "municipios_deserto": "menor", "n_ies": "maior"}


def direcoes():
    """
    Devolve DIRECAO depois de conferi-la contra o glossario do site: onde o
    glossario declara `maior`/`menor`, os dois TEM de concordar, senao a seta da
    tendencia contradiria o texto que o leitor ve no tooltip.
    """
    texto = GLOSSARIO.read_text(encoding="utf-8")
    achados = dict(re.findall(r"key:'([^']+)'.*?dir:'([^']+)'", texto, flags=re.S))
    conflitos = [f"{k}: tabela={DIRECAO[k]} glossario={achados[k]}" for k in DIRECAO
                 if achados.get(k) in ("maior", "menor") and achados[k] != DIRECAO[k]]
    if conflitos:
        sys.exit("[ERRO] DIRECAO contradiz glossario.js -> " + "; ".join(conflitos))
    return DIRECAO


def tendencia(delta, direcao):
    if delta == 0:
        return "estavel"
    melhora = delta > 0 if direcao == "maior" else delta < 0
    return "melhora" if melhora else "piora"


def gerar(anterior, atual):
    ano_a = str(anterior["metadados"]["versao_censo"])
    ano_b = str(atual["metadados"]["versao_censo"])
    if ano_a == ano_b:
        sys.exit(f"[ERRO] Os dois arquivos sao do mesmo Censo ({ano_a}).")
    dirs = direcoes()

    ufs = {}
    for uf, now in atual["ufs"].items():
        ant = anterior["ufs"].get(uf)
        if ant is None:
            sys.exit(f"[ERRO] {uf} ausente no arquivo anterior.")
        d_uf = {}
        fp = now.get("municipios_fp")
        for k in INDICADORES:
            if k == "ICON":
                va = round(fp / ant["municipios_oferta"], 1) if fp and ant.get("municipios_oferta") else None
                vb = round(fp / now["municipios_oferta"], 1) if fp and now.get("municipios_oferta") else None
            else:
                va, vb = ant.get(k), now.get(k)
            if va is None or vb is None:
                continue
            delta = round(vb - va, 4)
            d_uf[k] = {ano_a: va, ano_b: vb, "delta": delta,
                       "tendencia": tendencia(delta, dirs[k])}
        ufs[uf] = d_uf
    return {"series": [ano_a, ano_b], "ufs": ufs}


def main():
    ap = argparse.ArgumentParser(description="Gera data/historico.json")
    ap.add_argument("--anterior", required=True, help="nacional.json do ciclo anterior")
    ap.add_argument("--atual", default=str(REPO / "data" / "nacional.json"))
    ap.add_argument("--saida", default=str(REPO / "data" / "historico.json"))
    a = ap.parse_args()
    with open(a.anterior, encoding="utf-8") as f:
        anterior = json.load(f)
    with open(a.atual, encoding="utf-8") as f:
        atual = json.load(f)
    h = gerar(anterior, atual)
    with open(a.saida, "w", encoding="utf-8") as f:
        json.dump(h, f, ensure_ascii=False, indent=2)
    print(f"[OK] {a.saida}: {len(h['ufs'])} UFs, serie {h['series']}")


if __name__ == "__main__":
    main()
