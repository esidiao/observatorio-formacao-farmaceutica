"""
tests/test_validacao.py
Portão de qualidade: roda o autoteste GO e verifica integridade do nacional.json.

Uso:
    python tests/test_validacao.py
    python -m pytest tests/test_validacao.py -v
"""
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).parent.parent
DADOS = REPO / "data" / "nacional.json"
ETL   = REPO / "etl" / "indices_observatorio.py"


def test_autoteste_go():
    """Portão GO: fórmulas devem reproduzir ICT 0.840 / IAF 29.0 / ICON 11.3."""
    result = subprocess.run(
        [sys.executable, str(ETL), "--autoteste"],
        capture_output=True, text=True
    )
    assert result.returncode == 0, (
        f"FALHOU — Portão GO não passou.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_nacional_json_existe():
    assert DADOS.exists(), f"data/nacional.json não encontrado em {DADOS}"


def test_nacional_json_valido():
    with open(DADOS, encoding="utf-8") as f:
        dados = json.load(f)
    ufs = dados.get("ufs", dados)
    assert len(ufs) > 0, "nacional.json não tem dados de UFs"


def test_nenhuma_vaga_negativa():
    with open(DADOS, encoding="utf-8") as f:
        dados = json.load(f)
    ufs = dados.get("ufs", dados)
    for sigla, d in ufs.items():
        vagas = d.get("vagas_total")
        assert vagas is None or vagas >= 0, f"{sigla}: vagas_total negativo ({vagas})"


def test_nenhum_campo_estimado():
    """Verifica que nenhum campo contém a string 'estimado' (dado inventado é proibido)."""
    with open(DADOS, encoding="utf-8") as f:
        conteudo = f.read()
    assert "estimado" not in conteudo.lower(), (
        "nacional.json contém a palavra 'estimado' — dados inventados são proibidos."
    )


def test_proveniencia_existe():
    prov = REPO / "data" / "_proveniencia.json"
    assert prov.exists(), "data/_proveniencia.json não encontrado"
    with open(prov, encoding="utf-8") as f:
        p = json.load(f)
    assert "fontes" in p, "_proveniencia.json não tem campo 'fontes'"


def test_go_soma_municipios():
    """GO deve ter 246 municípios no total (IBGE 2023)."""
    with open(DADOS, encoding="utf-8") as f:
        dados = json.load(f)
    ufs = dados.get("ufs", dados)
    go = ufs.get("GO", {})
    assert go.get("municipios_total") == 246, (
        f"GO.municipios_total = {go.get('municipios_total')} (esperado: 246)"
    )


def test_soma_total_municipios_brasil():
    """Soma de municipios_total das 27 UFs deve estar entre 5570 e 5572 (IBGE 2023).
    Tolerância de ±2 devido a eventuais diferenças de edição do IBGE (criações/desmembramentos).
    """
    with open(DADOS, encoding="utf-8") as f:
        dados = json.load(f)
    ufs = dados.get("ufs", dados)
    soma = sum(d.get("municipios_total", 0) or 0 for d in ufs.values())
    assert 5568 <= soma <= 5572, (
        f"Soma de municípios = {soma} (esperado: próximo de 5570 ± 2). "
        f"Verifique MUN_TOTAL_UF em etl/ingestao_observatorio_nacional.py."
    )


def test_modalidades_somam_o_total_real():
    """
    As modalidades tem de somar a capacidade total. A semipresencial (nova em 2025)
    sumiria sem erro de qualquer script que so conhecesse presencial + EaD.
    """
    with open(DADOS, encoding="utf-8") as f:
        ufs = json.load(f)["ufs"]
    for sigla, d in ufs.items():
        partes = (d.get("vagas_presencial") or 0) + (d.get("vagas_ead") or 0)             + (d.get("vagas_semipresencial") or 0)
        assert partes == (d.get("vagas_total_real") or 0), (
            f"{sigla}: presencial+EaD+semipresencial = {partes}, "
            f"vagas_total_real = {d.get('vagas_total_real')}")


def test_metadados_publicados_seguem_a_proveniencia():
    """
    nacional.json carrega um retrato de _proveniencia.json. Adotar uma fonte nova e
    esquecer esse retrato deixaria o arquivo publicado afirmando a edicao anterior
    (aconteceu com a Farmacia Popular 202607).
    """
    with open(DADOS, encoding="utf-8") as f:
        meta = json.load(f)["metadados"]
    with open(REPO / "data" / "_proveniencia.json", encoding="utf-8") as f:
        prov = json.load(f)
    assert str(meta["versao_censo"]) == str(prov["versao_censo"]), (
        f"versao_censo: nacional.json={meta['versao_censo']} proveniencia={prov['versao_censo']}")
    for fonte in ("censo", "farmacia_popular"):
        assert meta["fontes"][fonte] == prov["fontes"][fonte], (
            f"metadados.fontes.{fonte} difere da proveniencia")


def test_historico_termina_no_censo_publicado():
    """O delta mostrado no site tem de comparar o Censo publicado com o anterior."""
    with open(DADOS, encoding="utf-8") as f:
        versao = str(json.load(f)["metadados"]["versao_censo"])
    with open(REPO / "data" / "historico.json", encoding="utf-8") as f:
        series = json.load(f)["series"]
    assert [str(a) for a in series][-1] == versao, (
        f"historico.json termina em {series[-1]}, mas o Censo publicado e {versao}")
    with open(REPO / "data" / "serie_historica.json", encoding="utf-8") as f:
        anos = json.load(f)["series"]
    assert str(anos[-1]) == versao, (
        f"serie_historica.json termina em {anos[-1]}, mas o Censo publicado e {versao}")


def _serie_uf():
    with open(REPO / "data" / "serie_uf.json", encoding="utf-8") as f:
        return json.load(f)


def test_serie_uf_sem_buracos_e_alinhada_aos_indicadores():
    """Todo indicador tem um valor (ou null) por ano, e nenhum ano falta no intervalo."""
    s = _serie_uf()
    anos = s["series"]
    assert anos == list(range(anos[0], anos[-1] + 1)), f"anos com buraco: {anos}"
    assert len(s["ufs"]) == 27, f"serie_uf tem {len(s['ufs'])} UFs (esperado 27)"
    for uf, inds in s["ufs"].items():
        for k, v in inds.items():
            assert len(v) == len(anos), f"{uf}.{k}: {len(v)} valores para {len(anos)} anos"


def test_serie_uf_termina_no_valor_publicado():
    """O ultimo ponto da serie tem de ser o numero mostrado no restante do site."""
    s = _serie_uf()
    with open(DADOS, encoding="utf-8") as f:
        dados = json.load(f)
    assert s["series"][-1] == int(dados["metadados"]["versao_censo"]), (
        f"serie_uf termina em {s['series'][-1]}, Censo publicado e {dados['metadados']['versao_censo']}")
    for uf, d in dados["ufs"].items():
        for k in ("vagas_total", "vagas_ead", "vagas_total_real", "n_cursos_presencial",
                  "matriculas_total", "concluintes_total", "n_ies", "municipios_oferta", "pct_ead"):
            assert s["ufs"][uf][k][-1] == d.get(k), (
                f"{uf}.{k}: serie={s['ufs'][uf][k][-1]} publicado={d.get(k)}")


def test_serie_uf_soma_igual_a_serie_nacional():
    """A soma das UFs de cada ano reproduz serie_historica.json (vagas e concluintes)."""
    s = _serie_uf()
    with open(REPO / "data" / "serie_historica.json", encoding="utf-8") as f:
        nac = {r["ano"]: r for r in json.load(f)["nacional"]}
    for i, ano in enumerate(s["series"]):
        vagas = sum(u["vagas_total_real"][i] or 0 for u in s["ufs"].values())
        conc = sum(u["concluintes_total"][i] or 0 for u in s["ufs"].values())
        assert vagas == nac[ano]["vagas_total"], f"{ano}: UFs somam {vagas} vagas, serie nacional {nac[ano]['vagas_total']}"
        assert conc == nac[ano]["concluintes"], f"{ano}: UFs somam {conc} concluintes, serie nacional {nac[ano]['concluintes']}"


def test_semipresencial_so_existe_a_partir_de_2025():
    """Categoria nova de 2025: antes disso e null (ausencia de categoria), nunca zero."""
    s = _serie_uf()
    for i, ano in enumerate(s["series"]):
        for uf, u in s["ufs"].items():
            v = u["vagas_semipresencial"][i]
            if ano < 2025:
                assert v is None, f"{uf} {ano}: vagas_semipresencial = {v} (esperado null antes de 2025)"


if __name__ == "__main__":
    testes = [
        test_autoteste_go,
        test_nacional_json_existe,
        test_nacional_json_valido,
        test_nenhuma_vaga_negativa,
        test_nenhum_campo_estimado,
        test_proveniencia_existe,
        test_go_soma_municipios,
        test_soma_total_municipios_brasil,
        test_modalidades_somam_o_total_real,
        test_metadados_publicados_seguem_a_proveniencia,
        test_historico_termina_no_censo_publicado,
        test_serie_uf_sem_buracos_e_alinhada_aos_indicadores,
        test_serie_uf_termina_no_valor_publicado,
        test_serie_uf_soma_igual_a_serie_nacional,
        test_semipresencial_so_existe_a_partir_de_2025,
    ]
    falhas = 0
    for t in testes:
        try:
            t()
            print(f"  [OK] {t.__name__}")
        except AssertionError as e:
            print(f"  [FALHOU] {t.__name__}: {e}")
            falhas += 1
        except Exception as e:
            print(f"  [ERRO] {t.__name__}: {e}")
            falhas += 1

    print()
    if falhas:
        print(f"[FALHOU] {falhas} teste(s) com falha — build abortado.")
        sys.exit(1)
    else:
        print("[PASSOU] Todos os testes passaram.")
        sys.exit(0)
