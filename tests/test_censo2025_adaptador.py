"""
tests/test_censo2025_adaptador.py
Trava a traducao das tabelas do Censo 2025 para o layout legado do ETL
(etl/censo2025_adaptador.py). Usa tabelas sinteticas minimas: nada aqui depende
dos 800 MB reais do INEP.

    python tests/test_censo2025_adaptador.py

Cada teste mira um erro que passaria SEM ruido se o adaptador estivesse errado:
somar 9,731 em vez de 9.731 mulheres, contar semipresencial como EaD, tratar
"suprimido" como zero, ou perder vagas de uma modalidade.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "etl"))
import pandas as pd  # noqa: E402
import censo2025_adaptador as ad  # noqa: E402

falhas = []


def checar(cond, msg):
    if not cond:
        falhas.append(msg)


LO = ["NO_REGIAO_LO", "CO_REGIAO_LO", "NO_UF_LO", "SG_UF_LO", "CO_UF_LO",
      "NO_MUNICIPIO_LO", "CO_MUNICIPIO_LO", "IN_CAPITAL_LO"]


def geo(uf, mun="X", cod="1"):
    if uf is None:
        return {c: None for c in LO}
    return {"NO_REGIAO_LO": "R", "CO_REGIAO_LO": "1", "NO_UF_LO": uf, "SG_UF_LO": uf,
            "CO_UF_LO": "1", "NO_MUNICIPIO_LO": mun, "CO_MUNICIPIO_LO": cod,
            "IN_CAPITAL_LO": "0"}


BASE = {"NU_ANO_CENSO": "2025", "TP_ORGANIZACAO_ACADEMICA": "1", "TP_REDE": "2",
        "TP_CATEGORIA_ADMINISTRATIVA": "4", "IN_COMUNITARIA": "0", "IN_CONFESSIONAL": "0",
        "NO_CURSO": "Farmácia", "NO_CINE_ROTULO": "Farmácia", "CO_CINE_ROTULO": "0916",
        "CO_CINE_AREA_GERAL": "09", "NO_CINE_AREA_GERAL": "Saúde",
        "CO_CINE_AREA_ESPECIFICA": "091", "NO_CINE_AREA_ESPECIFICA": "Saúde",
        "CO_CINE_AREA_DETALHADA": "0916", "NO_CINE_AREA_DETALHADA": "Farmácia",
        "TP_GRAU_ACADEMICO": "1", "TP_NIVEL_ACADEMICO": "1"}


def tabelas(tmp, fem_pres="40", fem_ead="1.200", polos_mat=(30, 20), mat_ead="50"):
    """Presencial SP; EaD (sede sem UF, 2 polos SP/GO); semipresencial com 1 polo."""
    curso, aluno = [], []

    def c(co, mod, uf, vagas, mat, ing, conc, ies="10", semi=0, ead=0):
        curso.append({**BASE, **geo(uf), "CO_CURSO": co, "CO_IES": ies,
                      "TP_MODALIDADE_ENSINO": mod, "TP_SITUACAO": "1", "IN_GRATUITO": "0",
                      "QT_CURSO": "1", "QT_VAGA_TOTAL": str(vagas),
                      "QT_VAGAS_TOTAL_DIURNO": str(vagas if mod == "1" else 0),
                      "QT_VAGAS_TOTAL_NOTURNO": "0", "QT_VAGAS_TOTAL_EAD": str(ead),
                      "QT_VAGAS_TOTAL_SEMI_PRES": str(semi), "QT_INSCRITO_TOTAL": "9",
                      "QT_MATRICULA_TOTAL": str(mat), "QT_CONCLUINTE_TOTAL": str(conc),
                      "QT_INGRESSO_TOTAL": str(ing)})

    def a(nivel, co, mod, uf, ing, fem, masc, mat, conc):
        aluno.append({**BASE, **geo(uf), "CO_CURSO": co, "CO_IES": "10",
                      "TP_NIVEL_AGREGACAO": nivel, "TP_MODALIDADE_ENSINO": mod,
                      "QT_ING": str(ing), "QT_ING_FEM": fem, "QT_ING_MASC": masc,
                      "QT_MAT": str(mat), "QT_CONC": str(conc)})

    c("1", "1", "SP", 100, 50, 60, 5)                        # presencial
    a("2", "1", "1", "SP", 60, fem_pres, "20", 50, 5)
    c("2", "2", "SP", 1000, mat_ead, 1500, 7, ead=1000)      # EaD (sede com UF no 2025)
    a("2", "2", "2", "SP", 1500, fem_ead, "300", 50, 7)
    a("3", "2", "2", "SP", 900, "-", "-", polos_mat[0], 4)   # polos: recortes suprimidos
    a("3", "2", "2", "GO", 600, "-", "-", polos_mat[1], 3)
    c("3", "3", "SP", 200, 8, 9, 0, semi=200)                # semipresencial
    a("2", "3", "3", "SP", 9, "5", "4", 8, 0)
    a("3", "3", "3", "SP", 9, "-", "-", 8, 0)
    d = Path(tmp)
    pd.DataFrame(curso).to_csv(d / ad.ARQ["curso"], sep=";", index=False, encoding="utf-8-sig")
    pd.DataFrame(aluno).to_csv(d / ad.ARQ["aluno"], sep=";", index=False, encoding="utf-8-sig")
    pd.DataFrame([{"CO_IES": "10", "NO_IES": "IES", "SG_UF_IES": "SP",
                   "CO_MANTENEDORA": "99"}]).to_csv(d / ad.ARQ["ies"], sep=";", index=False,
                                                    encoding="utf-8-sig")


def montar(**kw):
    with tempfile.TemporaryDirectory() as tmp:
        tabelas(tmp, **kw)
        return ad.montar(tmp, "FARMACIA", rel=lambda *_: None)


def test_contagem_trata_milhar_supressao_e_formato_novo():
    s = ad.contagem(pd.Series(["928", "9.731", "1.234.567", "-", None, ""]))
    checar(s.iloc[0] == 928 and s.iloc[1] == 9731 and s.iloc[2] == 1234567,
           f"separador de milhar mal lido: {s.tolist()}")
    checar(s.iloc[3:].isna().all(), "'-', vazio e nulo devem ser NaN, nunca 0")
    try:
        ad.contagem(pd.Series(["12,5"]))
        checar(False, "formato desconhecido ('12,5') deveria levantar erro")
    except ValueError:
        pass


def test_camadas_do_layout_legado():
    saida, _ = montar()
    dim = saida.groupby("TP_DIMENSAO").size().to_dict()
    checar(dim == {"1": 1, "2": 3, "3": 2}, f"linhas por dimensao inesperadas: {dim}")
    sede = saida[saida["TP_DIMENSAO"] == "3"]
    checar(sede["SG_UF"].isna().all(),
           "sede EaD/semipresencial tem de ficar sem UF (a UF vem da IES), como no 2024")
    checar((sede["QT_MAT"] == 0).all(), "sede nao carrega alunos (so os polos carregam)")
    polos = saida[saida["TP_DIMENSAO"] == "2"]
    checar((polos["QT_VG_TOTAL"] == 0).all() and (polos["QT_CURSO"] == 0).all(),
           "polo nao carrega vagas nem cursos")
    checar(set(polos["SG_UF"]) == {"SP", "GO"}, "polos devem manter a UF do local de oferta")


def test_semipresencial_nao_vira_ead_e_vagas_se_conservam():
    saida, _ = montar()
    v = pd.to_numeric(saida["QT_VG_TOTAL"]).groupby(saida["TP_MODALIDADE_ENSINO"]).sum().to_dict()
    checar(v == {"1": 100, "2": 1000, "3": 200}, f"vagas por modalidade: {v}")
    checar(int(pd.to_numeric(saida["QT_VG_TOTAL"]).sum()) == 1300, "vagas totais nao conservadas")


def test_milhar_dentro_da_celula_nao_quebra_o_recorte():
    saida, _ = montar()
    ead = saida[(saida["TP_DIMENSAO"] == "3") & (saida["TP_MODALIDADE_ENSINO"] == "2")]
    # o recorte por sexo do EaD vem do nivel de curso ("1.200" -> 1200), nao das sedes
    d1 = saida[saida["TP_DIMENSAO"] == "1"]
    checar(float(d1["QT_ING_FEM"].iloc[0]) == 40.0, "recorte presencial mal lido")
    # Se "1.200" virasse 1,2 a conferencia FEM+MASC=ING falharia: aqui precisa passar.
    checar(len(ead) == 1, "sede EaD ausente")


def test_recorte_suprimido_nos_polos_fica_nan_nao_zero():
    saida, _ = montar()
    polos = saida[saida["TP_DIMENSAO"] == "2"]
    checar(polos["QT_ING_FEM"].isna().all(),
           "recorte suprimido ('-') nos polos deve ser NaN; 0 subestimaria o perfil")
    checar(pd.to_numeric(polos["QT_ING"]).sum() > 0, "total de ingressantes nao e suprimido")


def test_traducao_que_nao_fecha_aborta_sem_gerar_arquivos():
    # polos somam 70 > 50 matriculas do curso: tem de abortar
    try:
        montar(polos_mat=(40, 30))
        checar(False, "polos acima do total do curso deveriam abortar")
    except SystemExit as e:
        checar("NAO gerou" in str(e), f"mensagem de aborto inesperada: {e}")
    # recorte inconsistente (FEM+MASC != ING) tambem
    try:
        montar(fem_ead="1.2")
        checar(False, "FEM+MASC != ING deveria abortar")
    except (SystemExit, ValueError):
        pass


def main():
    for t in (test_contagem_trata_milhar_supressao_e_formato_novo,
              test_camadas_do_layout_legado,
              test_semipresencial_nao_vira_ead_e_vagas_se_conservam,
              test_milhar_dentro_da_celula_nao_quebra_o_recorte,
              test_recorte_suprimido_nos_polos_fica_nan_nao_zero,
              test_traducao_que_nao_fecha_aborta_sem_gerar_arquivos):
        antes = len(falhas)
        t()
        print(f"  [{'OK' if len(falhas) == antes else 'FALHOU'}] {t.__name__}")
    if falhas:
        print(f"\n[FALHOU] {len(falhas)} problema(s):")
        for f in falhas:
            print(f"  - {f}")
        sys.exit(1)
    print("\n[PASSOU] Adaptador do Censo 2025 traduz e confere.")


if __name__ == "__main__":
    main()
