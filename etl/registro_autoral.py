"""
Registro de Anterioridade da Obra (prova de existência/integridade).

Gera data/registro_autoral.json com:
  - SHA-256 de cada arquivo-fonte canônico da Obra;
  - hash-raiz agregado (impressão digital única do conjunto);
  - timestamp UTC de selagem;
  - commit Git corrente (âncora datada e imutável no histórico);
  - instruções de verificação independente.

Reproduzível: rodar novamente sobre os MESMOS arquivos produz o MESMO hash-raiz.
Qualquer alteração de 1 byte muda o hash-raiz — é isso que prova a integridade.

Uso: python etl/registro_autoral.py
"""
import hashlib
import json
import subprocess
import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
AUTOR = "Edson Sidião de Souza Júnior"
OBRA = "Observatório Nacional da Formação Farmacêutica"

# Arquivos canônicos que constituem a Obra (dados tratados + código + apresentação)
PADROES = [
    "data/nacional.json",
    "data/historico.json",
    "data/_proveniencia.json",
    "data/municipios/*.json",
    "site/build.py",
    "site/templates/*.j2",
    "site/static/js/*.js",
    "site/static/css/*.css",
    "etl/*.py",
]


def sha256_arquivo(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for bloco in iter(lambda: f.read(65536), b""):
            h.update(bloco)
    return h.hexdigest()


def git_commit():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO, text=True
        ).strip()
    except Exception:
        return None


def main():
    arquivos = []
    for padrao in PADROES:
        for p in sorted(REPO.glob(padrao)):
            if p.is_file():
                rel = p.relative_to(REPO).as_posix()
                arquivos.append((rel, sha256_arquivo(p)))

    arquivos.sort(key=lambda x: x[0])

    # Hash-raiz: SHA-256 do conjunto canônico "caminho:hash" (1 por linha)
    base = "\n".join(f"{rel}:{h}" for rel, h in arquivos)
    hash_raiz = hashlib.sha256(base.encode("utf-8")).hexdigest()

    ts = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()

    registro = {
        "obra": OBRA,
        "autor": AUTOR,
        "tipo": "Registro de Anterioridade e Integridade (prova de existência)",
        "selado_em_utc": ts,
        "algoritmo": "SHA-256",
        "n_arquivos": len(arquivos),
        "hash_raiz": hash_raiz,
        "git_commit_ancora": git_commit(),
        "fundamento": "Lei 9.610/1998 e Lei 9.609/1998. O hash-raiz é impressão "
                      "digital única do conjunto; o commit Git ancora a data de forma imutável.",
        "como_verificar": [
            "1. Baixe os arquivos listados em 'arquivos'.",
            "2. Calcule o SHA-256 de cada um (ex.: sha256sum, ou Get-FileHash no Windows).",
            "3. Monte as linhas 'caminho:hash' em ordem alfabética de caminho, unidas por \\n.",
            "4. Calcule o SHA-256 dessa string: deve ser igual a 'hash_raiz'.",
            "5. O commit Git ('git_commit_ancora') comprova a data no histórico versionado.",
            "6. (Opcional) Ancore 'hash_raiz' no blockchain via OpenTimestamps: ots stamp.",
        ],
        "arquivos": [{"caminho": rel, "sha256": h} for rel, h in arquivos],
    }

    saida = REPO / "data" / "registro_autoral.json"
    with open(saida, "w", encoding="utf-8") as f:
        json.dump(registro, f, ensure_ascii=False, indent=2)

    print(f"[OK] {saida.relative_to(REPO)}")
    print(f"     Arquivos selados : {len(arquivos)}")
    print(f"     Selado em (UTC)  : {ts}")
    print(f"     Hash-raiz        : {hash_raiz}")
    print(f"     Âncora Git       : {registro['git_commit_ancora']}")


if __name__ == "__main__":
    main()
