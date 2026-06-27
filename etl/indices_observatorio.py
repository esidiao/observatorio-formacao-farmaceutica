"""
indices_observatorio.py
Calcula ICT, IAF, ICON e E por UF a partir dos dados agregados.
Apêndice A1, Tabela A1.1 — fórmulas canônicas.

Uso:
    python indices_observatorio.py --autoteste
    python indices_observatorio.py --dados dual.json --qualidade qualidade_uf.csv --saida final.json
"""
import argparse
import json
import csv
import sys
import math

# --------------------------------------------------------------------------- #
# FÓRMULAS CANÔNICAS (Apêndice A1)
# --------------------------------------------------------------------------- #

def _ict(vagas_capital, vagas_total, mun_oferta, mun_total):
    """ICT ↓ melhor: ½·(vagas_capital/vagas_total) + ½·(1 − mun_oferta/mun_total)"""
    if vagas_total == 0 or mun_total == 0:
        return None
    return 0.5 * (vagas_capital / vagas_total) + 0.5 * (1 - mun_oferta / mun_total)


def _q(cc, enade, idd):
    """Q = média[(CC−1)/4, (ENADE−1)/4, (IDD−1)/4] sobre valores não-nulos."""
    partes = [(v - 1) / 4 for v in [cc, enade, idd] if v is not None]
    return sum(partes) / len(partes) if partes else None


def _iaf(cc, enade, idd, vagas_avaliadas, vagas_total, ict):
    """IAF ↑ 0–100: 100·média(Q, V, E)"""
    if vagas_total is None or vagas_total == 0 or ict is None:
        return None
    q = _q(cc, enade, idd)
    if q is None:
        return None
    v = vagas_avaliadas / vagas_total if vagas_avaliadas is not None else None
    if v is None:
        return None
    e = 1 - ict
    return round(100 * (q + v + e) / 3, 1)


def _icon(mun_fp, mun_oferta):
    """ICON: mun_com_Farmácia_Popular / mun_com_oferta_formativa"""
    if mun_oferta is None or mun_oferta == 0:
        return None
    if mun_fp is None:
        return None
    return round(mun_fp / mun_oferta, 1)


# --------------------------------------------------------------------------- #
# AUTOTESTE — portão de correção (GO canônico)
# --------------------------------------------------------------------------- #

AUTOTESTE_GO = {
    # estrutural — microdados
    "uf": "GO",
    "vagas_total": 5000,
    "vagas_capital": 3807,
    "municipios_total": 246,
    "municipios_oferta": 20,
    # qualidade — ENADE/IDD
    "CC": 2.0,
    "ENADE": 1.84,
    "IDD": 1.68,
    "vagas_avaliadas": 2500,
    # assistência — Farmácia Popular
    "municipios_fp": 226,
}

CANONICO_GO = {"ICT": 0.840, "IAF": 29.0, "ICON": 11.3, "E": 0.16}
TOLERANCIA = 0.05


def autoteste():
    d = AUTOTESTE_GO
    ict = _ict(d["vagas_capital"], d["vagas_total"], d["municipios_oferta"], d["municipios_total"])
    iaf = _iaf(d["CC"], d["ENADE"], d["IDD"], d["vagas_avaliadas"], d["vagas_total"], ict)
    icon = _icon(d["municipios_fp"], d["municipios_oferta"])
    e = round(1 - ict, 2) if ict is not None else None

    resultados = {"ICT": round(ict, 3), "IAF": iaf, "ICON": icon, "E": e}
    ok = True
    print("=== AUTOTESTE GO ===")
    for ind, calc in resultados.items():
        esperado = CANONICO_GO[ind]
        passou = calc is not None and abs(calc - esperado) <= TOLERANCIA
        status = "OK" if passou else "FALHOU"
        if not passou:
            ok = False
        print(f"  {ind}: calculado={calc}  esperado={esperado}  [{status}]")

    if ok:
        print("\n[PASSOU] Autoteste OK. Pode prosseguir.")
        sys.exit(0)
    else:
        print("\n[FALHOU] Autoteste FALHOU. Verificar formulas antes de prosseguir.")
        sys.exit(1)


# --------------------------------------------------------------------------- #
# CARGA DE DADOS
# --------------------------------------------------------------------------- #

def carregar_dados(path_json):
    with open(path_json, encoding="utf-8") as f:
        return json.load(f)


def carregar_qualidade(path_csv):
    """
    CSV com colunas: UF, CC, ENADE, IDD, vagas_avaliadas, municipios_fp
    Linhas em branco para campos sem dado (respeito ao princípio de dado real).
    """
    qual = {}
    with open(path_csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            uf = row["UF"].strip().upper()
            def _float(key):
                v = row.get(key, "").strip()
                return float(v.replace(",", ".")) if v else None
            def _int(key):
                v = row.get(key, "").strip()
                return int(v) if v else None
            qual[uf] = {
                "CC": _float("CC"),
                "ENADE": _float("ENADE"),
                "IDD": _float("IDD"),
                "vagas_avaliadas": _int("vagas_avaliadas"),
                "municipios_fp": _int("municipios_fp"),
            }
    return qual


# --------------------------------------------------------------------------- #
# PROCESSAMENTO
# --------------------------------------------------------------------------- #

def processar(dados, qualidade):
    resultado = {}
    nulos_report = {}

    for uf, d in dados.items():
        uf = uf.upper()
        q = qualidade.get(uf, {})

        vagas_total = d.get("vagas_total")
        vagas_capital = d.get("vagas_capital")
        mun_total = d.get("municipios_total")
        mun_oferta = d.get("municipios_oferta")

        cc = q.get("CC")
        enade = q.get("ENADE")
        idd = q.get("IDD")
        vagas_av = q.get("vagas_avaliadas")
        mun_fp = q.get("municipios_fp")

        ict = _ict(vagas_capital, vagas_total, mun_oferta, mun_total)
        iaf = _iaf(cc, enade, idd, vagas_av, vagas_total, ict)
        icon = _icon(mun_fp, mun_oferta)
        e = round(1 - ict, 4) if ict is not None else None

        resultado[uf] = {
            **d,
            "CC": cc, "ENADE": enade, "IDD": idd,
            "vagas_avaliadas": vagas_av,
            "municipios_fp": mun_fp,
            "ICT": round(ict, 4) if ict is not None else None,
            "IAF": iaf,
            "ICON": icon,
            "E": e,
        }

        # rastrear nulos
        nulos = []
        if ict is None:
            if vagas_total is None: nulos.append("vagas_total (microdados)")
            if vagas_capital is None: nulos.append("vagas_capital (microdados)")
            if mun_total is None: nulos.append("municipios_total (referência IBGE)")
            if mun_oferta is None: nulos.append("municipios_oferta (microdados)")
        if iaf is None:
            if cc is None: nulos.append("CC (microdados ENADE)")
            if enade is None: nulos.append("ENADE (microdados ENADE)")
            if idd is None: nulos.append("IDD (microdados ENADE)")
            if vagas_av is None: nulos.append("vagas_avaliadas (microdados ENADE)")
        if icon is None:
            if mun_fp is None: nulos.append("municipios_fp (Farmácia Popular / dados.gov.br)")
        if nulos:
            nulos_report[uf] = list(set(nulos))

    return resultado, nulos_report


# --------------------------------------------------------------------------- #
# MAIN
# --------------------------------------------------------------------------- #

def main():
    parser = argparse.ArgumentParser(description="Calcula índices do Observatório Nacional")
    parser.add_argument("--autoteste", action="store_true", help="Roda portão de correção GO e sai")
    parser.add_argument("--dados", default="dual.json", help="JSON de entrada (default: dual.json)")
    parser.add_argument("--qualidade", default="qualidade_uf.csv", help="CSV de qualidade (default: qualidade_uf.csv)")
    parser.add_argument("--saida", default="final.json", help="JSON de saída (default: final.json)")
    args = parser.parse_args()

    if args.autoteste:
        autoteste()
        return

    dados = carregar_dados(args.dados)
    qualidade = carregar_qualidade(args.qualidade)
    resultado, nulos = processar(dados, qualidade)

    # verificação: soma de municípios deve fechar em 5570
    soma_mun = sum(
        v.get("municipios_total", 0) or 0
        for v in resultado.values()
    )
    print(f"[CHECK] Soma municípios por UF: {soma_mun} (esperado: 5570)")
    if soma_mun != 5570:
        print("  [AVISO] Divergencia na contagem de municipios. Verificar referencia IBGE.")

    with open(args.saida, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)
    print(f"[OK] {args.saida} gerado com {len(resultado)} UFs.")

    if nulos:
        print("\n[TRANSPARÊNCIA] Indicadores nulos por ausência de fonte:")
        for uf, fontes in sorted(nulos.items()):
            print(f"  {uf}: {'; '.join(fontes)}")


if __name__ == "__main__":
    main()
