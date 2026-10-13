"""Processamento em lote no computador, a partir de protocolos salvos pela interface.

Fluxo para estudos de validação: na ferramenta web, desenhe as ROIs e baixe
o protocolo (.json). No computador, com os mesmos DICOMs numa pasta::

    mnp-dmsa exame.json --pasta dicoms/ --csv resultado.csv --laudo laudo.html

ou ``python -m mnp_nucleo.dmsa ...``. Para vários exames::

    mnp-dmsa protocolos/*.json --pasta dicoms/ --csv todos.csv

O cálculo é o mesmo código que roda no navegador, com as mesmas regiões de
fundo gravadas no protocolo.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

from .. import __version__, versoes
from . import relatorio
from .sessao import ErroSessao, Sessao

__all__ = ["processar_protocolo", "main"]


def _localizador(pasta: Path):
    indice: dict[str, list[Path]] = {}
    for caminho in pasta.rglob("*"):
        if caminho.is_file():
            indice.setdefault(caminho.name, []).append(caminho)

    def ler(nome: str, sha256: str) -> bytes:
        for c in indice.get(nome, []):
            dados = c.read_bytes()
            if hashlib.sha256(dados).hexdigest() == sha256:
                return dados
        for lista in indice.values():
            for c in lista:
                dados = c.read_bytes()
                if hashlib.sha256(dados).hexdigest() == sha256:
                    return dados
        raise ErroSessao(f"{nome}: arquivo não encontrado em {pasta} (procurado pelo nome e pelo SHA-256).")

    return ler


def processar_protocolo(protocolo: dict, pasta: Path):
    """Recalcula um exame. Devolve (sessão, resultado)."""
    sessao = Sessao.de_protocolo(protocolo, _localizador(Path(pasta)))
    return sessao, sessao.calcular()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="mnp-dmsa", description="Cintilografia renal com DMSA em lote (mnp-nucleo).")
    ap.add_argument("protocolos", nargs="+", type=Path, help="arquivos .json salvos pela ferramenta web")
    ap.add_argument("--pasta", type=Path, required=True, help="pasta com os DICOMs (busca em subpastas)")
    ap.add_argument("--csv", type=Path, help="CSV consolidado (uma linha por exame)")
    ap.add_argument("--laudo", type=Path, help="laudo HTML (só com um protocolo)")
    args = ap.parse_args(argv)
    if args.laudo and len(args.protocolos) > 1:
        ap.error("--laudo aceita um protocolo por vez.")

    saida = []
    for caminho in args.protocolos:
        protocolo = json.loads(caminho.read_text(encoding="utf-8"))
        try:
            sessao, r = processar_protocolo(protocolo, args.pasta)
        except ErroSessao as erro:
            print(f"{caminho.name}: {erro}", file=sys.stderr)
            return 1
        if protocolo.get("versao_nucleo") != __version__:
            print(
                f"{caminho.name}: protocolo gerado com o núcleo {protocolo.get('versao_nucleo')}, "
                f"recalculado com {__version__}.",
                file=sys.stderr,
            )
        linha = {"protocolo": caminho.name, "versao_nucleo": __version__, "fundo": sessao.metodo_fundo}
        for p in r.parametros:
            linha[f"{p.chave}_D"] = p.d_arred
            linha[f"{p.chave}_E"] = p.e_arred
        saida.append(linha)
        print(f"{caminho.name}: função relativa posterior D {r.parametro('frr_post').d_arred}%")
        if args.laudo:
            html = relatorio.laudo_html(
                r,
                sessao.metodo_fundo,
                sessao._manuais_texto(),
                versoes(),
                sessao._arquivos_info(),
                imagens=sessao._imagens_laudo(False, None),
                avisos=sessao._avisos(),
            )
            args.laudo.write_text(
                f'<!doctype html><html lang="pt-BR"><meta charset="utf-8"><title>Laudo DMSA</title><body>{html}</body></html>',
                encoding="utf-8",
            )

    if args.csv and saida:
        with args.csv.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(saida[0].keys()))
            w.writeheader()
            w.writerows(saida)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
