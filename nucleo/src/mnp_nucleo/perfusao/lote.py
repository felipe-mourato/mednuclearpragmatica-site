"""Processamento em lote no computador, a partir de protocolos salvos pela interface.

Na ferramenta web, trace os eixos, pontue os segmentos e baixe o protocolo
(.json). No computador, com os mesmos DICOMs numa pasta::

    mnp-perfusao exame.json --pasta dicoms/ --csv resultado.csv --laudo laudo.html

ou ``python -m mnp_nucleo.perfusao ...``. Para vários exames::

    mnp-perfusao protocolos/*.json --pasta dicoms/ --csv todos.csv

O cálculo é o mesmo código que roda no navegador: mesma reconstrução,
mesmos eixos (gravados em mm no protocolo) e mesmos escores.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

from .. import __version__
from .polar import SEGMENTOS
from .gated import escores_funcao
from .sessao import PONTUADOS, ErroSessao, Sessao

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


def processar_protocolo(protocolo: dict, pasta: Path) -> Sessao:
    """Recria a sessão de um exame a partir do protocolo."""
    return Sessao.de_protocolo(protocolo, _localizador(Path(pasta)))


def linha_csv(nome: str, s: Sessao) -> dict:
    r = s.calcular_escores()
    linha = {"protocolo": nome, "versao_nucleo": __version__, "filtro_corte_nyquist": s.filtro.corte_nyquist,
             "filtro_ordem": s.filtro.ordem, "SSS": r.sss, "SRS": r.srs, "SDS": r.sds}
    for e in PONTUADOS:
        valores = s.mapa_polar(e).valores_segmentos() if s._fonte(e) and e in s.eixos else {}
        for seg in SEGMENTOS:
            linha[f"{e}_escore_{seg}"] = s.escores[e].get(seg)
            linha[f"{e}_captacao_{seg}"] = round(valores[seg], 1) if seg in valores else None
    # gated: FE, volumes e escores de função (colunas sempre presentes, para o CSV consolidado)
    for e in PONTUADOS:
        res = s.funcao(e) if s._fonte_gated(e) is not None and e in s.eixos else None
        linha[f"{e}_fe"] = round(res.fe, 1) if res else None
        linha[f"{e}_vdf_ml"] = round(res.vdf_ml, 1) if res else None
        linha[f"{e}_vsf_ml"] = round(res.vsf_ml, 1) if res else None
        for tipo, sigla in (("motilidade", "SMS"), ("espessamento", "STS")):
            soma = escores_funcao(s.escores_funcao[tipo][e], tipo)
            linha[f"{e}_{sigla}"] = soma["soma"] if soma else None
    tid = s.tid()
    linha["TID"] = tid["tid"] if tid else None
    return linha


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="mnp-perfusao", description="Perfusão miocárdica (SPECT) em lote (mnp-nucleo).")
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
            s = processar_protocolo(protocolo, args.pasta)
            linha = linha_csv(caminho.name, s)
        except ErroSessao as erro:
            print(f"{caminho.name}: {erro}", file=sys.stderr)
            return 1
        if protocolo.get("versao_nucleo") != __version__:
            print(f"{caminho.name}: protocolo gerado com o núcleo {protocolo.get('versao_nucleo')}, recalculado com {__version__}.", file=sys.stderr)
        saida.append(linha)
        print(f"{caminho.name}: SSS {linha['SSS']} · SRS {linha['SRS']} · SDS {linha['SDS']}")
        if args.laudo:
            html = s.laudo()
            args.laudo.write_text(
                f'<!doctype html><html lang="pt-BR"><meta charset="utf-8"><title>Laudo de perfusão</title><body>{html}</body></html>',
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
