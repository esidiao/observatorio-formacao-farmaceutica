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
