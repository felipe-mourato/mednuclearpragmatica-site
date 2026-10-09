"""Gera os pacotes Python que as ferramentas web carregam do próprio site.

Chamado pelo build.sh. Só usa a biblioteca padrão, mais o pip do Python indicado.

1. Constrói a wheel do núcleo (pasta nucleo/).
2. Baixa o pydicom com o hash conferido (nucleo/pacotes-web.txt).
3. Copia cada wheel para  <saída>/w/<12 primeiros dígitos do SHA-256>/<arquivo>.whl
   (a pasta muda quando o conteúdo muda, então o cache longo do navegador é seguro).
4. Escreve <saída>/pacotes.json, que as ferramentas leem ao abrir.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
NUCLEO = RAIZ / "nucleo"


def versao_do_nucleo() -> str:
    texto = (NUCLEO / "src" / "mnp_nucleo" / "__init__.py").read_text(encoding="utf-8")
    m = re.search(r'^__version__\s*=\s*"([^"]+)"', texto, re.M)
    if not m:
        sys.exit("ERRO: __version__ não encontrado em nucleo/src/mnp_nucleo/__init__.py")
    return m.group(1)


def rodar(*args: str) -> None:
    print("   $", " ".join(args))
    subprocess.run(args, check=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--python", default=sys.executable, help="Python com pip para construir e baixar")
    ap.add_argument("--saida", required=True, type=Path)
    a = ap.parse_args()

    versao = versao_do_nucleo()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        rodar(a.python, "-m", "pip", "wheel", "--quiet", "--no-deps", "--wheel-dir", str(tmp), str(NUCLEO))
        rodar(
            a.python, "-m", "pip", "download", "--quiet", "--no-deps", "--only-binary=:all:",
            "--require-hashes", "-r", str(NUCLEO / "pacotes-web.txt"), "--dest", str(tmp),
        )
        rodas = sorted(tmp.glob("*.whl"), key=lambda p: (not p.name.startswith("pydicom"), p.name))
        nucleo = [p for p in rodas if p.name.startswith("mnp_nucleo-")]
        if len(nucleo) != 1 or not nucleo[0].name.startswith(f"mnp_nucleo-{versao}-"):
            sys.exit(f"ERRO: wheel do núcleo {versao} não foi gerada ({[p.name for p in rodas]}).")

        if a.saida.exists():
            shutil.rmtree(a.saida)
        pacotes = []
        for roda in rodas:
            sha = hashlib.sha256(roda.read_bytes()).hexdigest()
            destino = a.saida / "w" / sha[:12] / roda.name
            destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(roda, destino)
            nome, ver = roda.name.split("-")[:2]
            pacotes.append({"nome": nome, "versao": ver, "caminho": destino.relative_to(a.saida).as_posix(), "sha256": sha})
            print(f"   {roda.name}  sha256 {sha[:12]}…")

    manifesto = {
        "nucleo": versao,
        "gerado_em": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pacotes": pacotes,
    }
    (a.saida / "pacotes.json").write_text(json.dumps(manifesto, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"   pacotes.json: núcleo {versao}, {len(pacotes)} pacotes")


if __name__ == "__main__":
    main()
