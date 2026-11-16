"""Mapa polar de perfusão em 17 segmentos, territórios coronarianos e valores por segmento.

AMOSTRAGEM (desvio declarado): o QPS (Germano et al., J Nucl Med
2000;41:712-9) amostra o miocárdio a partir da segmentação automática do
VE e das superfícies endo e epicárdica (Germano et al., J Nucl Med
1995;36:2138-47). Enquanto essa parte não é implementada (fase do gated),
esta versão usa uma amostragem própria, simples e determinística, sobre o
eixo traçado pelo usuário:

* parede (do fim da cavidade à base): perfis radiais perpendiculares ao
  eixo, a cada 5° em volta e em 24 posições ao longo do eixo; em cada raio,
  a contagem máxima até ``RAIO_MAX_MM`` do eixo (perfil de contagem
  máxima);
* ápice: raios a partir de um centro C no eixo, a ``r_c`` do ápice,
  com ângulo polar de 0° (para o ápice) a 90° (perpendicular ao eixo),
  12 passos, também com a contagem máxima até ``r_c + 20 mm``.
  r_c = 30% do comprimento do eixo, limitado entre 10 e 40 mm.

Segmentação (Cerqueira et al., J Nucl Cardiol 2002;9:240-5; figura e
tabela reproduzidas na diretriz ASNC de laudos, J Nucl Cardiol
2017;24:2064-128, Apêndice 6, e na diretriz SBC 2020, Tabela 18): o VE é
dividido em terços perpendiculares ao eixo longo (basal, médio e apical),
e a região além do fim da cavidade é o ápice (segmento 17). Aqui: o fim
da cavidade é o centro C; a parede de C até a base é dividida em terços
iguais; os raios a partir de C formam o segmento 17. No mapa, o ápice
ocupa o centro e a base a periferia; anterior em cima, septo à esquerda,
lateral à direita e inferior embaixo. Basal e médio: 6 segmentos de 60°;
apical: 4 de 90°.

Territórios (mesma figura): DA = 1, 2, 7, 8, 13, 14 e 17; CD = 3, 4, 9,
10 e 15; Cx = 5, 6, 11, 12 e 16.

Valores: cada amostra em % do máximo de todas as amostras do estudo; o
valor do segmento é a média das amostras dele. Sem banco de normalidade,
esses valores não classificam nada como anormal: servem para conferir a
pontuação visual.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .eixos import Eixo, base_vetorial
from .reconstrucao import Volume

__all__ = [
    "SEGMENTOS",
    "NOMES",
    "TERRITORIOS",
    "TERRITORIO_DO_SEGMENTO",
    "MapaPolar",
    "amostrar_polar",
    "segmento_em",
    "geometria_segmentos",
    "N_AZIMUTE",
    "N_PAREDE",
    "N_APICE",
    "RAIO_MAX_MM",
]

SEGMENTOS = tuple(range(1, 18))
NOMES = {
    1: "Basal anterior",
    2: "Basal anterosseptal",
    3: "Basal inferosseptal",
    4: "Basal inferior",
    5: "Basal inferolateral",
    6: "Basal anterolateral",
    7: "Médio anterior",
    8: "Médio anterosseptal",
    9: "Médio inferosseptal",
    10: "Médio inferior",
    11: "Médio inferolateral",
    12: "Médio anterolateral",
    13: "Apical anterior",
    14: "Apical septal",
    15: "Apical inferior",
    16: "Apical lateral",
    17: "Ápice",
}
TERRITORIOS = {"DA": (1, 2, 7, 8, 13, 14, 17), "CD": (3, 4, 9, 10, 15), "Cx": (5, 6, 11, 12, 16)}
TERRITORIO_DO_SEGMENTO = {s: t for t, segs in TERRITORIOS.items() for s in segs}
NOME_TERRITORIO = {"DA": "Descendente anterior", "CD": "Coronária direita", "Cx": "Circunflexa"}

N_AZIMUTE = 72
N_PAREDE = 24
N_APICE = 12
RAIO_MAX_MM = 45.0
PASSO_RAIO_MM = 1.0



def _seg_anel6(ang: float, primeiro: int) -> int:
    """Segmento de um anel de 6 (basal: 1–6; médio: 7–12) pelo ângulo no mapa (graus)."""
    a = ang % 360.0
    # 1/7: 60–120, 2/8: 120–180, 3/9: 180–240, 4/10: 240–300, 5/11: 300–360, 6/12: 0–60
    idx = int(((a - 60.0) % 360.0) // 60.0)
    return primeiro + idx


def _seg_anel4(ang: float) -> int:
    """Apical: 13 anterior (45–135), 14 septal (135–225), 15 inferior (225–315), 16 lateral (315–45)."""
    a = ang % 360.0
    idx = int(((a - 45.0) % 360.0) // 90.0)
    return 13 + idx


def segmento_em(rho: float, ang: float, rho_apice: float) -> int:
    """Segmento no mapa polar: raio normalizado ``rho`` (0 centro, 1 borda) e ângulo (graus)."""
    if rho <= rho_apice:
        return 17
    terco = (rho - rho_apice) / (1.0 - rho_apice)
    if terco <= 1.0 / 3.0:
        return _seg_anel4(ang)
    if terco <= 2.0 / 3.0:
        return _seg_anel6(ang, 7)
    return _seg_anel6(ang, 1)


@dataclass
class MapaPolar:
    """Amostras do mapa polar de um estudo.

    ``parede``: (N_PAREDE, N_AZIMUTE), do fim da cavidade (0) para a base;
    ``apice``: (N_APICE, N_AZIMUTE), do ápice (ângulo polar 0) até 90°.
    Valores em % do máximo do estudo. ``rho_apice``: fração do raio do mapa
    ocupada pelo ápice (proporcional ao comprimento de arco).
    """

    parede: np.ndarray
    apice: np.ndarray
    maximo: float
    r_c_mm: float
    rho_apice: float
    azimutes: np.ndarray

    def amostras_por_segmento(self) -> dict[int, np.ndarray]:
        segs: dict[int, list] = {s: [] for s in SEGMENTOS}
        for j, az in enumerate(self.azimutes):
            for v in self.apice[:, j]:
                segs[17].append(v)
            for i in range(self.parede.shape[0]):
                terco = (i + 0.5) / self.parede.shape[0]
                if terco <= 1.0 / 3.0:
                    s = _seg_anel4(az)
                elif terco <= 2.0 / 3.0:
                    s = _seg_anel6(az, 7)
                else:
                    s = _seg_anel6(az, 1)
                segs[s].append(self.parede[i, j])
        return {s: np.asarray(v) for s, v in segs.items()}

    def valores_segmentos(self) -> dict[int, float]:
        """Média (% do máximo) das amostras de cada segmento."""
        return {s: float(np.mean(v)) for s, v in self.amostras_por_segmento().items()}

    def imagem(self, lado: int = 192) -> np.ndarray:
        """Mapa em grade quadrada (lado × lado), NaN fora do círculo. Linha 0 = em cima (anterior)."""
        m = (lado - 1) / 2.0
        yy, xx = np.mgrid[0:lado, 0:lado]
        x = (xx - m) / (m + 0.5)
        y = (m - yy) / (m + 0.5)
        rho = np.hypot(x, y)
        ang = np.degrees(np.arctan2(y, x)) % 360.0
        passo_az = 360.0 / len(self.azimutes)
        col = (ang / passo_az) % len(self.azimutes)
        j0 = np.floor(col).astype(int) % len(self.azimutes)
        j1 = (j0 + 1) % len(self.azimutes)
        wj = col - np.floor(col)
        saida = np.full((lado, lado), np.nan)
        # ápice
        ap = rho <= self.rho_apice
        f = np.clip(rho[ap] / self.rho_apice * (self.apice.shape[0] - 1), 0, self.apice.shape[0] - 1)
        saida[ap] = _bilinear(self.apice, f, j0[ap], j1[ap], wj[ap])
        pa = (rho > self.rho_apice) & (rho <= 1.0)
        f = np.clip((rho[pa] - self.rho_apice) / (1.0 - self.rho_apice) * self.parede.shape[0] - 0.5, 0, self.parede.shape[0] - 1)
        saida[pa] = _bilinear(self.parede, f, j0[pa], j1[pa], wj[pa])
        return saida


def _bilinear(grade, f, j0, j1, wj):
    i0 = np.floor(f).astype(int)
    i1 = np.minimum(i0 + 1, grade.shape[0] - 1)
    wi = f - i0
    return (grade[i0, j0] * (1 - wi) + grade[i1, j0] * wi) * (1 - wj) + (grade[i0, j1] * (1 - wi) + grade[i1, j1] * wi) * wj


def amostrar_polar(vol: Volume, eixo: Eixo) -> MapaPolar:
    """Perfis de contagem máxima ao longo de raios (ver o texto do módulo)."""
    a, w, h = base_vetorial(eixo.base, eixo.apice)
    comp = eixo.comprimento
    r_c = float(np.clip(0.3 * comp, 10.0, 40.0))
    centro = eixo.apice - r_c * a
    az = (np.arange(N_AZIMUTE) + 0.5) * (360.0 / N_AZIMUTE)
    t = np.deg2rad(az)
    dirs = np.cos(t)[:, None] * h[None, :] + np.sin(t)[:, None] * w[None, :]  # (az, 3); 0° = lateral, 90° = anterior
    raios = np.arange(0.0, RAIO_MAX_MM + 1e-9, PASSO_RAIO_MM)
    # parede: do fim da cavidade (C) até a base
    s = r_c + (np.arange(N_PAREDE) + 0.5) / N_PAREDE * max(comp - r_c, 1e-6)
    centros = eixo.apice[None, :] - s[:, None] * a[None, :]  # (parede, 3)
    pts = centros[:, None, None, :] + dirs[None, :, None, :] * raios[None, None, :, None]
    parede = vol.amostrar(pts).max(axis=-1)
    # ápice: ângulo polar 0..90° a partir de C
    psi = np.deg2rad((np.arange(N_APICE)) / (N_APICE - 1) * 90.0)
    dir_ap = np.cos(psi)[:, None, None] * a[None, None, :] + np.sin(psi)[:, None, None] * dirs[None, :, :]
    raios_ap = np.arange(0.0, r_c + 20.0 + 1e-9, PASSO_RAIO_MM)
    pts_ap = centro[None, None, None, :] + dir_ap[:, :, None, :] * raios_ap[None, None, :, None]
    apice = vol.amostrar(pts_ap).max(axis=-1)
    maximo = float(max(parede.max(), apice.max()))
    if maximo <= 0:
        raise ValueError("Não há contagens em volta do eixo: confira o eixo traçado.")
    arco_ap = np.pi / 2.0 * r_c
    rho_apice = arco_ap / (arco_ap + max(comp - r_c, 1e-6))
    return MapaPolar(parede=100.0 * parede / maximo, apice=100.0 * apice / maximo, maximo=maximo, r_c_mm=r_c, rho_apice=float(rho_apice), azimutes=az)


def geometria_segmentos(rho_apice: float, lado: int = 192) -> list[dict]:
    """Contornos dos 17 segmentos em coordenadas da imagem do mapa (SVG ``path``), com o ponto do rótulo."""
    m = (lado - 1) / 2.0
    R = m + 0.5

    def ponto(rho, ang):
        a = np.deg2rad(ang)
        return (m + rho * R * np.cos(a), m - rho * R * np.sin(a))

    def setor(r0, r1, a0, a1):
        n = max(2, int(abs(a1 - a0) / 6))
        externos = [ponto(r1, a0 + (a1 - a0) * k / n) for k in range(n + 1)]
        internos = [ponto(r0, a1 - (a1 - a0) * k / n) for k in range(n + 1)] if r0 > 0 else [ponto(0, 0)]
        pts = externos + internos
        return "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in pts) + " Z"

    r_ap = rho_apice
    r1 = r_ap + (1 - r_ap) / 3
    r2 = r_ap + 2 * (1 - r_ap) / 3
    saida = []
    for s, a0 in zip(range(13, 17), (45, 135, 225, 315)):
        lx, ly = ponto((r_ap + r1) / 2, a0 + 45)
        saida.append({"segmento": s, "caminho": setor(r_ap, r1, a0, a0 + 90), "rotulo": [round(lx, 2), round(ly, 2)]})
    for primeiro, (ri, re) in ((7, (r1, r2)), (1, (r2, 1.0))):
        for k, a0 in enumerate((60, 120, 180, 240, 300, 0)):
            lx, ly = ponto((ri + re) / 2, a0 + 30)
            saida.append({"segmento": primeiro + k, "caminho": setor(ri, re, a0, a0 + 60), "rotulo": [round(lx, 2), round(ly, 2)]})
    # ápice: círculo
    n = 36
    circ = [ponto(r_ap, 360 * k / n) for k in range(n)]
    saida.append({"segmento": 17, "caminho": "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in circ) + " Z", "rotulo": [round(m, 2), round(m, 2)]})
    return sorted(saida, key=lambda d: d["segmento"])
