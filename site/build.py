"""
build.py — Gerador de site estático do Observatório Nacional
Lê data/nacional.json e gera site/dist/*.html

Uso:
    python site/build.py
    python site/build.py --dados data/nacional.json --out site/dist
"""
import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

try:
    from jinja2 import Environment, FileSystemLoader, select_autoescape
except ImportError:
    sys.exit("Instale jinja2: pip install jinja2")

# ── Nomes das UFs ──────────────────────────────────────────────────────────────
NOMES_UF = {
    "AC": "Acre", "AL": "Alagoas", "AM": "Amazonas", "AP": "Amapá",
    "BA": "Bahia", "CE": "Ceará", "DF": "Distrito Federal",
    "ES": "Espírito Santo", "GO": "Goiás", "MA": "Maranhão",
    "MG": "Minas Gerais", "MS": "Mato Grosso do Sul", "MT": "Mato Grosso",
    "PA": "Pará", "PB": "Paraíba", "PE": "Pernambuco", "PI": "Piauí",
    "PR": "Paraná", "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte",
    "RO": "Rondônia", "RR": "Roraima", "RS": "Rio Grande do Sul",
    "SC": "Santa Catarina", "SE": "Sergipe", "SP": "São Paulo",
    "TO": "Tocantins",
}

# Código IBGE das UFs (para a API IBGE de malhas)
IBGE_UF = {
    "AC":"12","AL":"27","AM":"13","AP":"16","BA":"29","CE":"23",
    "DF":"53","ES":"32","GO":"52","MA":"21","MG":"31","MS":"50",
    "MT":"51","PA":"15","PB":"25","PE":"26","PI":"22","PR":"41",
    "RJ":"33","RN":"24","RO":"11","RR":"14","RS":"43","SC":"42",
    "SE":"28","SP":"35","TO":"17",
}


def _mediana(lst):
    lst = sorted(x for x in lst if x is not None)
    if not lst:
        return None
    n = len(lst)
    mid = n // 2
    return lst[mid] if n % 2 else (lst[mid - 1] + lst[mid]) / 2


def _gerar_swot(sigla, d):
    """Gera SWOT automático baseado nos indicadores."""
    forcas, fraquezas, oportunidades, ameacas = [], [], [], []

    ict = d.get("ICT")
    iaf = d.get("IAF")
    icon = d.get("ICON")
    hhi = d.get("HHI")
    mun_oferta = d.get("municipios_oferta", 0)
    mun_total = d.get("municipios_total", 1)
    mun_deserto = d.get("municipios_deserto", 0)
    vagas = d.get("vagas_total", 0)

    cobertura = mun_oferta / mun_total if mun_total else 0

    # Forças
    if ict is not None and ict < 0.5:
        forcas.append(f"Boa distribuição territorial (ICT = {ict:.3f})")
    if iaf is not None and iaf >= 40:
        forcas.append(f"Alta adequação formativa (IAF = {iaf:.1f}/100)")
    if hhi is not None and hhi < 0.15:
        forcas.append("Mercado descentralizado (HHI baixo)")
    if cobertura >= 0.3:
        forcas.append(f"{mun_oferta} municípios com oferta ({cobertura:.0%} do total)")
    idd = d.get("IDD")
    if idd is not None and idd >= 2.7:
        forcas.append(f"Alto valor agregado pelo curso (IDD = {idd:.2f})")

    if not forcas:
        forcas.append("Presença de oferta formativa no estado")

    # Fraquezas
    if ict is not None and ict >= 0.75:
        fraquezas.append(f"Alta concentração territorial (ICT = {ict:.3f})")
    if iaf is not None and iaf < 25:
        fraquezas.append(f"Baixa adequação formativa (IAF = {iaf:.1f}/100)")
    if mun_deserto and mun_total:
        pct = mun_deserto / mun_total
        fraquezas.append(f"{mun_deserto} municípios sem oferta ({pct:.0%} do total)")
    if hhi is not None and hhi >= 0.25:
        fraquezas.append("Mercado altamente concentrado (HHI elevado)")
    idd = d.get("IDD")
    if idd is not None and idd < 2.0:
        fraquezas.append(f"Baixo valor agregado pelo curso (IDD = {idd:.2f}, abaixo do esperado)")
    pct_ead = d.get("pct_ead")
    if pct_ead is not None and pct_ead >= 70:
        fraquezas.append(f"Capacidade dominada por EaD ({pct_ead:.0f}% das vagas) — risco para práticas presenciais")

    if not fraquezas:
        fraquezas.append("Nenhuma fraqueza crítica identificada com os dados disponíveis")

    # Oportunidades
    oportunidades.append("Expansão da EaD para municípios desertos")
    if icon is not None and icon > 5:
        oportunidades.append(f"Alta presença do Farmácia Popular (ICON = {icon:.1f}) como ancoragem de práticas")
    oportunidades.append("Parcerias com prefeituras para estágios em municípios sem oferta")
    if iaf is not None and iaf < 50:
        oportunidades.append("Potencial de melhora nos indicadores de qualidade ENADE")

    # Ameaças
    if ict is not None and ict >= 0.7:
        ameacas.append("Risco de perpetuação de desertos farmacêuticos se não houver política de expansão")
    ameacas.append("Dependência de dados ENADE trianuais (lacuna entre ciclos)")
    if hhi is not None and hhi >= 0.2:
        ameacas.append("Concentração institucional pode reduzir diversidade de práticas pedagógicas")

    return dict(forcas=forcas, fraquezas=fraquezas, oportunidades=oportunidades, ameacas=ameacas)


def _icon_adj(d):
    """ICON ajustado: fração de DESERTOS farmacêuticos cobertos por Farmácia Popular.
    Estimativa conservadora (limite inferior): assume que todos os municípios com
    oferta possuem FP, atribuindo o excedente de FP aos desertos.
    Difere do ICON original, que mede FP em municípios que JÁ têm oferta."""
    fp = d.get("municipios_fp")
    deserto = d.get("municipios_deserto")
    oferta = d.get("municipios_oferta") or 0
    if fp is None or not deserto:
        return None
    fp_em_deserto = max(0, fp - oferta)
    return round(min(1.0, fp_em_deserto / deserto), 3)


def construir_site(path_dados: Path, path_out: Path, templates_dir: Path):
    # ── Carregar dados ─────────────────────────────────────────────────────────
    with open(path_dados, encoding="utf-8") as f:
        nacional = json.load(f)

    meta = nacional.get("metadados", {})
    ufs = nacional.get("ufs", nacional)  # suporte a final.json sem wrapper

    # Série histórica (deltas 2023→2024), opcional
    hist_path = path_dados.parent / "historico.json"
    historico = {}
    if hist_path.exists():
        with open(hist_path, encoding="utf-8") as f:
            historico = json.load(f).get("ufs", {})

    # ICON ajustado (cobertura de desertos) — derivado em tempo de build
    for sigla, d in ufs.items():
        d["ICON_adj"] = _icon_adj(d)

    # ── Preparar diretórios de saída ───────────────────────────────────────────
    path_out.mkdir(parents=True, exist_ok=True)
    (path_out / "uf").mkdir(exist_ok=True)

    # Copiar arquivos estáticos
    static_src = templates_dir.parent / "static"
    static_dst = path_out / "static"
    if static_dst.exists():
        shutil.rmtree(static_dst)
    shutil.copytree(static_src, static_dst)

    # ── Jinja2 ─────────────────────────────────────────────────────────────────
    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=select_autoescape(["html"]),
    )

    # ── KPIs nacionais ─────────────────────────────────────────────────────────
    total_vagas      = sum(d.get("vagas_total") or 0 for d in ufs.values())
    total_vagas_real = sum(d.get("vagas_total_real") or d.get("vagas_total") or 0 for d in ufs.values())
    total_vagas_pres = sum(d.get("vagas_presencial") or 0 for d in ufs.values())
    total_vagas_ead  = sum(d.get("vagas_ead") or 0 for d in ufs.values())
    total_ies   = sum(d.get("n_ies") or 0 for d in ufs.values())
    total_pop   = sum(d.get("populacao") or 0 for d in ufs.values())
    vagas_100k_nac = round(total_vagas_real / total_pop * 100000, 1) if total_pop else None
    mun_oferta  = sum(d.get("municipios_oferta") or 0 for d in ufs.values())
    mun_deserto = sum(d.get("municipios_deserto") or 0 for d in ufs.values())
    ict_values  = [d.get("ICT") for d in ufs.values() if d.get("ICT") is not None]
    iaf_values  = [d.get("IAF") for d in ufs.values() if d.get("IAF") is not None]

    ufs_ordenados = sorted(ufs.items(), key=lambda kv: kv[1].get("ICT") or 1.0)

    # ── Render home ────────────────────────────────────────────────────────────
    tmpl_index = env.get_template("index.html.j2")
    html = tmpl_index.render(
        depth="",
        meta=meta,
        n_ufs=len(ufs),
        total_vagas=total_vagas,
        total_vagas_real=total_vagas_real,
        total_vagas_pres=total_vagas_pres,
        total_vagas_ead=total_vagas_ead,
        pct_ead_nacional=round(total_vagas_ead / total_vagas_real * 100, 1) if total_vagas_real else 0,
        vagas_100k_nac=vagas_100k_nac,
        n_ies=total_ies,
        mun_com_oferta=mun_oferta,
        mun_deserto=mun_deserto,
        ict_mediana=_mediana(ict_values) or 0,
        iaf_mediana=_mediana(iaf_values) or 0,
        ufs_ordenados=ufs_ordenados,
        dados_ufs_json=json.dumps(ufs, ensure_ascii=False),
        meta_json=json.dumps(meta, ensure_ascii=False),
    )
    (path_out / "index.html").write_text(html, encoding="utf-8")
    print(f"[OK] index.html")

    # ── Render páginas de UF ───────────────────────────────────────────────────
    tmpl_uf = env.get_template("uf.html.j2")
    municipios_dir = path_dados.parent / "municipios"

    for sigla, d in ufs.items():
        sigla = sigla.upper()
        municipios = d.get("municipios_com_oferta_lista", [])

        # Carregar dados detalhados de municípios, se disponível
        mun_json_path = municipios_dir / f"{sigla}.json"
        tem_drill = mun_json_path.exists()

        html_uf = tmpl_uf.render(
            depth="../",
            meta=meta,
            meta_json=json.dumps(meta, ensure_ascii=False),
            sigla=sigla,
            nome_uf=NOMES_UF.get(sigla, sigla),
            d=d,
            municipios_com_oferta=municipios,
            municipios_com_oferta_json=json.dumps(municipios, ensure_ascii=False),
            dados_uf_json=json.dumps(d, ensure_ascii=False),
            codigo_ibge=IBGE_UF.get(sigla, ""),
            swot=_gerar_swot(sigla, d),
            tem_drill=tem_drill,
            hist=historico.get(sigla, {}),
        )
        (path_out / "uf" / f"{sigla}.html").write_text(html_uf, encoding="utf-8")

    print(f"[OK] {len(ufs)} páginas de UF geradas")

    # ── Render páginas de município ────────────────────────────────────────────
    tmpl_mun = env.get_template("municipio.html.j2") if (templates_dir / "municipio.html.j2").exists() else None
    n_mun_pages = 0
    if tmpl_mun and municipios_dir.exists():
        for mun_file in sorted(municipios_dir.glob("*.json")):
            sigla = mun_file.stem.upper()
            if sigla not in ufs:
                continue
            with open(mun_file, encoding="utf-8") as f:
                dados_mun = json.load(f)

            out_dir = path_out / "municipio" / sigla
            out_dir.mkdir(parents=True, exist_ok=True)

            for nome_norm, d_mun in dados_mun.items():
                # Verifica se há nome_ies em algum curso
                tem_nome_ies = any(c.get("nome_ies") for c in d_mun.get("cursos", []))
                tem_matriculas = any(c.get("matriculas") is not None for c in d_mun.get("cursos", []))

                html_mun = tmpl_mun.render(
                    depth="../../",
                    meta=meta,
                    meta_json=json.dumps(meta, ensure_ascii=False),
                    sigla=sigla,
                    nome_municipio=d_mun.get("nome_original", nome_norm),
                    d=d_mun,
                    dados_mun_json=json.dumps(d_mun, ensure_ascii=False),
                    tem_nome_ies=tem_nome_ies,
                    tem_matriculas=tem_matriculas,
                )
                slug = nome_norm.replace(" ", "_").replace("/", "-")
                (out_dir / f"{slug}.html").write_text(html_mun, encoding="utf-8")
                n_mun_pages += 1

    if n_mun_pages:
        print(f"[OK] {n_mun_pages} páginas de município geradas")

    # ── Render página do autor ─────────────────────────────────────────────────
    tmpl_autor = env.get_template("autor.html.j2") if (templates_dir / "autor.html.j2").exists() else None
    if tmpl_autor:
        html_autor = tmpl_autor.render(
            depth="",
            meta=meta,
            meta_json=json.dumps(meta, ensure_ascii=False),
        )
        (path_out / "autor.html").write_text(html_autor, encoding="utf-8")
        print(f"[OK] autor.html")

    # ── Render página de aviso legal / direitos autorais ───────────────────────
    ano_corrente = (meta.get("data_extracao") or "2026")[:4]
    registro_path = path_dados.parent / "registro_autoral.json"
    registro = None
    if registro_path.exists():
        with open(registro_path, encoding="utf-8") as f:
            registro = json.load(f)
    tmpl_legal = env.get_template("aviso-legal.html.j2") if (templates_dir / "aviso-legal.html.j2").exists() else None
    if tmpl_legal:
        html_legal = tmpl_legal.render(
            depth="",
            meta=meta,
            meta_json=json.dumps(meta, ensure_ascii=False),
            ano_corrente=ano_corrente,
            registro=registro,
        )
        (path_out / "aviso-legal.html").write_text(html_legal, encoding="utf-8")
        print(f"[OK] aviso-legal.html")
    if registro is not None:
        shutil.copy2(registro_path, path_out / "registro_autoral.json")

    # ── Render página de comparação ────────────────────────────────────────────
    tmpl_comp = env.get_template("comparar.html.j2") if (templates_dir / "comparar.html.j2").exists() else None
    if tmpl_comp:
        html_comp = tmpl_comp.render(
            depth="",
            meta=meta,
            meta_json=json.dumps(meta, ensure_ascii=False),
            todas_ufs=sorted(ufs.keys()),
            dados_ufs_json=json.dumps(ufs, ensure_ascii=False),
        )
        (path_out / "comparar.html").write_text(html_comp, encoding="utf-8")
        print(f"[OK] comparar.html")

    print(f"\n[BUILD] Site gerado em: {path_out.resolve()}")
    print(f"  Abra {path_out / 'index.html'} no browser para visualizar localmente.")


def main():
    parser = argparse.ArgumentParser(description="Gera o site estático do Observatório Nacional")
    parser.add_argument("--dados", default=None)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    # Descobrir raiz do projeto (build.py está em site/)
    site_dir = Path(__file__).parent
    repo_root = site_dir.parent

    path_dados = Path(args.dados) if args.dados else repo_root / "data" / "nacional.json"
    path_out   = Path(args.out) if args.out else site_dir / "dist"
    templates  = site_dir / "templates"

    if not path_dados.exists():
        sys.exit(f"[ERRO] Arquivo de dados não encontrado: {path_dados}")

    construir_site(path_dados, path_out, templates)


if __name__ == "__main__":
    main()
