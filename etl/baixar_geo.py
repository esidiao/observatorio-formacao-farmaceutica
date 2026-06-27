"""
etl/baixar_geo.py
Baixa GeoJSONs IBGE para site/static/geo/ para servir localmente.

Uso:
    python etl/baixar_geo.py
"""
import gzip
import json
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).parent.parent
GEO_DIR = REPO / "site" / "static" / "geo"

# Código IBGE → sigla
IBGE_SIGLA = {
    "11":"RO","12":"AC","13":"AM","14":"RR","15":"PA",
    "16":"AP","17":"TO","21":"MA","22":"PI","23":"CE",
    "24":"RN","25":"PB","26":"PE","27":"AL","28":"SE",
    "29":"BA","31":"MG","32":"ES","33":"RJ","35":"SP",
    "41":"PR","42":"SC","43":"RS","50":"MS","51":"MT",
    "52":"GO","53":"DF",
}


def baixar(url: str, dest: Path, descricao: str) -> bool:
    """Baixa URL para dest. Retorna True se ok."""
    if dest.exists():
        print(f"  [SKIP] {descricao} já existe ({dest.stat().st_size//1024} KB)")
        return True
    print(f"  [GET] {descricao} ...", end=" ", flush=True)
    try:
        req = urllib.request.Request(url, headers={"Accept-Encoding": "gzip, identity"})
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            enc = r.headers.get("Content-Encoding", "")
        # descomprime se necessário
        if enc == "gzip" or raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        data = raw
        # valida JSON
        json.loads(data)
        dest.write_bytes(data)
        print(f"ok ({len(data)//1024} KB)")
        return True
    except Exception as e:
        print(f"ERRO: {e}")
        return False


def main():
    GEO_DIR.mkdir(parents=True, exist_ok=True)
    (GEO_DIR / "estados").mkdir(exist_ok=True)

    # ── 1. Brasil (contornos dos estados, 1 feature por UF) ───
    print("\n[1/2] Mapa nacional (contornos dos estados)")
    brasil_dest = GEO_DIR / "brasil.json"
    if brasil_dest.exists():
        print(f"  [SKIP] brasil.json já existe ({brasil_dest.stat().st_size//1024} KB)")
    else:
        # Baixa o contorno de cada UF individualmente e monta FeatureCollection
        features = []
        print("  Baixando contorno de cada UF para montar brasil.json ...")
        for cod, sigla in sorted(IBGE_SIGLA.items()):
            url = (
                f"https://servicodados.ibge.gov.br/api/v3/malhas/estados/{cod}"
                f"?resolucao=2&formato=application/vnd.geo%2Bjson"
            )
            print(f"    {sigla} ...", end=" ", flush=True)
            try:
                req = urllib.request.Request(url, headers={"Accept-Encoding": "gzip, identity"})
                with urllib.request.urlopen(req, timeout=60) as r:
                    raw = r.read()
                    enc = r.headers.get("Content-Encoding", "")
                if enc == "gzip" or raw[:2] == b"\x1f\x8b":
                    raw = gzip.decompress(raw)
                geo = json.loads(raw)
                for f in geo.get("features", []):
                    # garante que codarea seja o código da UF (2 dígitos)
                    f["properties"]["codarea"] = str(cod)
                    f["properties"]["sigla"] = sigla
                    features.append(f)
                print("ok")
            except Exception as e:
                print(f"ERRO: {e}")
            time.sleep(0.3)
        brasil = {"type": "FeatureCollection", "features": features}
        brasil_dest.write_text(json.dumps(brasil, ensure_ascii=False), encoding="utf-8")
        print(f"  [OK] brasil.json: {len(features)} features ({brasil_dest.stat().st_size//1024} KB)")

    # ── 2. Municípios por UF ───────────────────────────────────
    print(f"\n[2/2] Municípios por UF ({len(IBGE_SIGLA)} arquivos)")
    ok = 0
    for cod, sigla in sorted(IBGE_SIGLA.items()):
        url_uf = (
            f"https://servicodados.ibge.gov.br/api/v3/malhas/estados/{cod}"
            f"?resolucao=5&formato=application/vnd.geo%2Bjson"
        )
        dest = GEO_DIR / "estados" / f"{cod}.json"
        if baixar(url_uf, dest, f"{sigla} ({cod}.json)"):
            ok += 1
        time.sleep(0.4)  # respeita rate-limit IBGE

    print(f"\n[OK] {ok}/{len(IBGE_SIGLA)} arquivos salvos em {GEO_DIR.resolve()}")

    # Sumário de tamanhos
    total = sum(f.stat().st_size for f in GEO_DIR.rglob("*.json"))
    print(f"[OK] Tamanho total: {total//1024} KB ({total//1024//1024} MB)")


if __name__ == "__main__":
    main()
