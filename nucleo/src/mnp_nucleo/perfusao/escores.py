"""Escores semiquantitativos de perfusão (pontuação visual do médico, 17 segmentos).

Escala por segmento (diretriz SBC 2020, Arq Bras Cardiol 2020;114(2):325-429,
p. 346; ASNC 2017, Apêndice 6): 0 normal; 1 hipocaptação discreta;
2 moderada; 3 acentuada; 4 ausência de captação.

* SSS = soma dos escores do estresse; SRS = soma dos escores do repouso;
  SDS = SSS − SRS (ASNC 2017, Tabela 12; SBC 2020, p. 347).
* Percentual do VE: SSS ÷ 68, SRS ÷ 68 e SDS ÷ 68 (× 100), porque 68 =
  4 × 17 é o escore máximo; nenhum segmento pode ter escore negativo
  (ASNC 2017, texto e Tabela 12).
* Faixas do SSS (SBC 2020, p. 347, citando Hachamovitch): < 4 normal;
  4 a 8 discretamente anormal; 9 a 13 moderadamente anormal; > 13
  francamente anormal.

Nada aqui é automático: os escores são os que o usuário marcou.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .polar import NOMES, SEGMENTOS, TERRITORIOS

__all__ = ["ESCALA", "ESCORE_MAXIMO", "Escores", "calcular_escores", "faixa_sss", "validar_escore"]

ESCALA = {0: "normal", 1: "hipocaptação discreta", 2: "hipocaptação moderada", 3: "hipocaptação acentuada", 4: "ausência de captação"}
ESCORE_MAXIMO = 4 * len(SEGMENTOS)  # 68


def validar_escore(v) -> int | None:
    if v is None or v == "":
        return None
    try:
        e = int(v)
    except (TypeError, ValueError):
        raise ValueError("Escore deve ser um número inteiro de 0 a 4.") from None
    if e != float(v) or not 0 <= e <= 4:
        raise ValueError("Escore deve ser um número inteiro de 0 a 4.")
    return e


def faixa_sss(sss: int) -> str:
    """Faixa do SSS (SBC 2020, citando Hachamovitch): normal, discreta, moderada ou franca."""
    if sss < 4:
        return "normal (< 4)"
    if sss <= 8:
        return "discretamente anormal (4 a 8)"
    if sss <= 13:
        return "moderadamente anormal (9 a 13)"
    return "francamente anormal (> 13)"


@dataclass
class Escores:
    estresse: dict
    repouso: dict
    sss: int | None
    srs: int | None
    sds: int | None
    faltam_estresse: list = field(default_factory=list)
    faltam_repouso: list = field(default_factory=list)
    territorios: dict = field(default_factory=dict)
    avisos: list = field(default_factory=list)

    def percentual(self, valor: int | None) -> float | None:
        return None if valor is None else 100.0 * valor / ESCORE_MAXIMO


def calcular_escores(estresse: dict, repouso: dict) -> Escores:
    """Somas, diferença, percentuais e somas por território. Segmentos sem escore ficam de fora com aviso."""
    e = {s: validar_escore(estresse.get(s)) for s in SEGMENTOS}
    r = {s: validar_escore(repouso.get(s)) for s in SEGMENTOS}
    faltam_e = [s for s in SEGMENTOS if e[s] is None]
    faltam_r = [s for s in SEGMENTOS if r[s] is None]
    sss = None if faltam_e else sum(e.values())
    srs = None if faltam_r else sum(r.values())
    sds = None if sss is None or srs is None else sss - srs
    avisos = []
    if faltam_e and len(faltam_e) < 17:
        avisos.append(f"Estresse: faltam escores em {len(faltam_e)} segmento(s); o SSS só sai com os 17.")
    if faltam_r and len(faltam_r) < 17:
        avisos.append(f"Repouso: faltam escores em {len(faltam_r)} segmento(s); o SRS só sai com os 17.")
    piores = [s for s in SEGMENTOS if e[s] is not None and r[s] is not None and r[s] > e[s]]
    if piores:
        avisos.append(
            "Escore de repouso maior que o de estresse em: "
            + ", ".join(f"{s} ({NOMES[s].lower()})" for s in piores)
            + ". O SDS (SSS − SRS) desconta essa diferença; confira."
        )
    territorios = {}
    for t, segs in TERRITORIOS.items():
        se = None if any(e[s] is None for s in segs) else sum(e[s] for s in segs)
        sr = None if any(r[s] is None for s in segs) else sum(r[s] for s in segs)
        territorios[t] = {"estresse": se, "repouso": sr, "diferenca": None if se is None or sr is None else se - sr, "segmentos": list(segs)}
    return Escores(e, r, sss, srs, sds, faltam_e, faltam_r, territorios, avisos)
