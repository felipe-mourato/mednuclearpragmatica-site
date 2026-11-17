"""Função do VE no gated SPECT: bordas, volumes, FE, TID, motilidade e espessamento.

MÉTODO (implementação própria, no estilo do QGS). O QGS (Germano et al.,
J Nucl Med 1995;36:2138-47; motilidade e espessamento em Germano et al.,
J Am Coll Cardiol 1997;30:1360-7) primeiro acha a superfície mediomiocárdica e
depois as superfícies endo e epicárdica a partir dos perfis de contagem e
do espessamento, combinando a conservação da massa miocárdica com o
aumento de contagem causado pelo efeito de volume parcial (manual de
referência do QGS/QPS, Cedars-Sinai, seção de análise de fase). O artigo
original não é de acesso livre; os passos e parâmetros abaixo são escolhas
desta ferramenta e estão declarados:

0. Centralização do eixo: o eixo traçado à mão raramente passa pelo centro
   da cavidade. Em 9 cortes de eixo curto (do fim da cavidade até 60% do
   caminho para a base, onde o anel é completo),
   os pontos de contagem máxima de 36 raios (até 40 mm) caem no anel
   miocárdico mesmo com o eixo fora do centro; um círculo ajustado a eles
   (mínimos quadrados, com rejeição de pontos a mais de 6 mm) dá o centro
   do anel, sem depender da intensidade (um defeito não desloca o centro).
   Uma reta ajustada a esses centros (ponderada pela fração de pontos
   aceitos) vira o novo eixo; cada ponta anda no máximo 12 mm por iteração. Três iterações, sobre a soma dos intervalos do gated (o mesmo eixo
   para todos os intervalos) ou sobre a imagem não sincronizada (TID).
1. Amostragem sobre o eixo centralizado: um centro C
   no eixo, a r_c do ápice (30% do comprimento, entre 10 e 40 mm); ápice com
   raios a partir de C (ângulo polar de 0° a 90°) e parede com raios
   perpendiculares ao eixo, de C até o plano valvar. Perfis de 0 a
   ``RAIO_MAX_MM`` de 1 em 1 mm, ``N_AZIMUTE`` azimutes.
2. Plano valvar, em cada intervalo: em cada azimute, a base é onde a
   contagem máxima do perfil cai abaixo de ``LIMIAR_VALVA`` (50%) do
   máximo da metade basal da parede naquele azimute (assim um defeito
   basal não encurta o VE), procurando da metade do eixo para a base e
   até 20 mm além da base traçada; ajuste de um plano
   (s = p0 + p1 cos φ + p2 sen φ) por mínimos quadrados, com rejeição de
   pontos discrepantes. As linhas da parede são reamostradas entre C e o
   plano (frações fixas do comprimento), o que acompanha a descida da base.
3. Superfície mediomiocárdica: em cada raio, o ponto de contagem máxima
   (interpolação parabólica), com mediana espacial 3 × 3 e nova busca perto
   da mediana quando o ponto se afasta mais de 6 mm.
   Correção de curvatura: borrar uma casca curva desloca o máximo para
   dentro de cerca de σ² H (H = curvatura média; esfera: σ²/R; cilindro:
   σ²/2R). σ² do sistema = σ² medido no perfil (meia largura a meia altura
   ÷ 1,177) − T²/12 (a variância de uma parede de espessura T). H: 1/r no
   ápice; na parede, 1/(2r) mais metade da curvatura meridional da própria
   superfície.
4. Espessura na diástole final: a resolução do SPECT (10–20 mm) não deixa
   medir uma parede de ~10 mm pela largura do perfil (a largura medida é
   quase toda borramento). Esta versão assume ``ESPESSURA_DIASTOLE_MM``
   (10 mm, parede normal do VE) em toda a parede na diástole final; é a
   principal suposição do método e fica declarada no laudo. Em VE
   hipertrófico, a cavidade sai superestimada.
5. Nos outros intervalos: a espessura local acompanha a contagem máxima
   normalizada pelo total do intervalo (efeito de volume parcial:
   contagem ∝ espessura) e um fator global por intervalo mantém o volume
   miocárdico igual ao da diástole final (massa constante).
6. Endocárdio = meio − espessura/2; epicárdio = meio + espessura/2.
   Volume da cavidade: integral em coordenadas cilíndricas (parede) e
   esféricas (ápice) até o plano valvar.
7. Diástole final (VDF) e sístole final (VSF): maior e menor volume da
   curva. FE = (VDF − VSF) / VDF.
8. Motilidade: distância (mm) entre o ponto endocárdico da diástole final e
   o da sístole final na mesma amostra (positiva para dentro). Espessamento:
   aumento relativo da espessura da diástole para a sístole final (%). O
   manual do QGS satura a escala de motilidade em 10 mm e a de espessamento
   em 100%, com valores negativos mostrados como 0; os números por segmento
   aqui não são cortados.
9. TID: razão entre os volumes da cavidade nas imagens não sincronizadas
   (estresse ÷ repouso), pelo mesmo método (sem o passo 5). Abidov et al.,
   J Nucl Med 2004;45:1999-2007 (referência do manual); sem ponto de corte.

Sem banco de normalidade: nada é classificado como anormal. Escores visuais
de motilidade (0–5) e espessamento (0–3) por segmento, pontuados pelo
médico (SBC 2020, Tabela 19; manual do QGS), com as somas SMS e STS.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .eixos import Eixo, base_vetorial
from .polar import MapaPolar, SEGMENTOS
from .reconstrucao import Volume

__all__ = [
    "Superficies",
    "ResultadoGated",
    "analisar_gated",
    "volume_nao_sincronizado",
    "calcular_tid",
    "escores_funcao",
    "validar_escore_funcao",
    "superficie_corporal",
    "N_AZIMUTE",
    "N_PAREDE",
    "N_APICE",
    "LIMIAR_VALVA",
    "ESPESSURA_DIASTOLE_MM",
    "MOTILIDADE_MAX",
    "ESPESSAMENTO_MAX",
]

N_AZIMUTE = 36
N_PAREDE = 20
N_APICE = 8
RAIO_MAX_MM = 45.0
RAIO_MIN_MM = 2.0
PASSO_MM = 1.0
PASSO_VALVA_MM = 2.0
EXTRA_VALVA_MM = 20.0
LIMIAR_VALVA = 0.5
ESPESSURA_DIASTOLE_MM = 10.0
ESPESSURA_MIN_MM = 3.0
ESPESSURA_MAX_MM = 25.0
DESVIO_MEIO_MM = 6.0
#: Escalas de exibição dos mapas (manual do QGS): 0–10 mm e 0–100%.
MOTILIDADE_MAX = 10.0
ESPESSAMENTO_MAX = 100.0
MOTILIDADE_ESCORE_MAX = 5
ESPESSAMENTO_ESCORE_MAX = 3


# ----------------------------------------------------------------- geometria
@dataclass
class _Grade:
    """Geometria fixa da amostragem de um estudo (a partir do eixo)."""

    a: np.ndarray  # base → ápice
    w: np.ndarray  # anterior
    h: np.ndarray  # lateral
    apice: np.ndarray
    comp: float
    r_c: float
    phi: np.ndarray  # azimutes (rad), 0 = lateral, π/2 = anterior
    psi: np.ndarray  # ângulos polares do ápice (rad), 0 = para o ápice
    raios: np.ndarray

    @property
    def centro(self) -> np.ndarray:
        return self.apice - self.r_c * self.a

    @property
    def dirs(self) -> np.ndarray:  # (az, 3)
        return np.cos(self.phi)[:, None] * self.h[None, :] + np.sin(self.phi)[:, None] * self.w[None, :]

    @property
    def dirs_apice(self) -> np.ndarray:  # (psi, az, 3)
        return np.cos(self.psi)[:, None, None] * self.a[None, None, :] + np.sin(self.psi)[:, None, None] * self.dirs[None, :, :]


def _grade(eixo: Eixo) -> _Grade:
    return _grade_de_pontos(np.asarray(eixo.base, float), np.asarray(eixo.apice, float))


RAIO_CENTRO_MM = 40.0
PASSO_CENTRO_MM = 12.0


def _grade_de_pontos(base: np.ndarray, apice: np.ndarray, r_c: float | None = None) -> _Grade:
    a, w, h = base_vetorial(base, apice)
    comp = float(np.linalg.norm(apice - base))
    r_c = float(np.clip(0.3 * comp, 10.0, 40.0)) if r_c is None else r_c
    phi = np.deg2rad((np.arange(N_AZIMUTE) + 0.5) * (360.0 / N_AZIMUTE))
    psi = (np.arange(N_APICE) + 0.5) / N_APICE * (np.pi / 2.0)
    raios = np.arange(0.0, RAIO_MAX_MM + 1e-9, PASSO_MM)
    return _Grade(a, w, h, np.asarray(apice, float), comp, r_c, phi, psi, raios)


def _ajustar_circulo(x: np.ndarray, y: np.ndarray):
    """Círculo por mínimos quadrados algébricos (Kåsa), com uma rodada de rejeição (resíduo > 6 mm)."""
    ok = np.ones_like(x, dtype=bool)
    for _ in range(2):
        if ok.sum() < 6:
            return None
        A = np.stack([x[ok], y[ok], np.ones(ok.sum())], axis=1)
        b = -(x[ok] ** 2 + y[ok] ** 2)
        (D, E, F), *_ = np.linalg.lstsq(A, b, rcond=None)
        cx, cy = -D / 2, -E / 2
        r2 = cx**2 + cy**2 - F
        if r2 <= 0:
            return None
        r = np.sqrt(r2)
        ok = np.abs(np.hypot(x - cx, y - cy) - r) <= 6.0
    return cx, cy, r, ok.mean()


def _centralizar(vol: Volume, g: _Grade, iteracoes: int = 3) -> _Grade:
    """Eixo pelo centro do anel miocárdico (ver o passo 0 do texto do módulo)."""
    for _ in range(iteracoes):
        s = np.linspace(g.r_c, g.r_c + 0.6 * (g.comp - g.r_c), 9)
        perfis = _perfis_parede(vol, g, s)  # (linhas, az, raios)
        dentro = g.raios <= RAIO_CENTRO_MM
        p = perfis[..., dentro]
        k = np.argmax(p, axis=-1)
        r = g.raios[dentro][k]
        cs, us, vs, ws = [], [], [], []
        for i, si in enumerate(s):
            # pontos sobre o próprio eixo (eixo encostado na parede) entram uma vez só
            longe = r[i] >= 3.0
            x = np.concatenate([r[i][longe] * np.cos(g.phi[longe]), [0.0] if (~longe).any() else []])
            y = np.concatenate([r[i][longe] * np.sin(g.phi[longe]), [0.0] if (~longe).any() else []])
            fit = _ajustar_circulo(x, y)
            if fit is None or not (5.0 <= fit[2] <= 45.0):
                continue
            cs.append(si)
            us.append(fit[0])
            vs.append(fit[1])
            ws.append(fit[3])
        if len(cs) < 3:
            return g
        S, W = np.asarray(cs), np.asarray(ws)
        A = np.stack([np.ones_like(S), S], axis=1) * W[:, None]
        pu, *_ = np.linalg.lstsq(A, np.asarray(us) * W, rcond=None)
        pv, *_ = np.linalg.lstsq(A, np.asarray(vs) * W, rcond=None)
        # passo limitado (até 12 mm por iteração em cada ponta)
        d_ap = np.array([pu[0], pv[0]])
        d_ba = np.array([pu[0] + pu[1] * g.comp, pv[0] + pv[1] * g.comp])
        d_ap *= min(1.0, PASSO_CENTRO_MM / max(np.linalg.norm(d_ap), 1e-9))
        d_ba *= min(1.0, PASSO_CENTRO_MM / max(np.linalg.norm(d_ba), 1e-9))
        p_ap = g.apice + d_ap[0] * g.h + d_ap[1] * g.w
        p_ba = g.apice - g.comp * g.a + d_ba[0] * g.h + d_ba[1] * g.w
        if np.linalg.norm(p_ap - p_ba) < 20.0:
            return g
        g = _grade_de_pontos(p_ba, p_ap, g.r_c)
    return g


def _perfis_parede(vol: Volume, g: _Grade, s: np.ndarray) -> np.ndarray:
    """Perfis radiais (…, raios) para distâncias ``s`` do ápice (forma (linhas, az) ou (linhas,))."""
    s = np.asarray(s, float)
    if s.ndim == 1:
        s = np.repeat(s[:, None], N_AZIMUTE, axis=1)
    centros = g.apice[None, None, :] - s[..., None] * g.a[None, None, :]  # (linhas, az, 3)
    pts = centros[:, :, None, :] + g.dirs[None, :, None, :] * g.raios[None, None, :, None]
    return vol.amostrar(pts)


def _perfis_apice(vol: Volume, g: _Grade) -> np.ndarray:
    pts = g.centro[None, None, None, :] + g.dirs_apice[:, :, None, :] * g.raios[None, None, :, None]
    return vol.amostrar(pts)  # (psi, az, raios)


# ------------------------------------------------------------ plano valvar
def _ajustar_plano(s_base: np.ndarray, phi: np.ndarray) -> np.ndarray:
    """s(φ) = p0 + p1 cos φ + p2 sen φ, mínimos quadrados com uma rodada de rejeição (3 × MAD)."""
    A = np.stack([np.ones_like(phi), np.cos(phi), np.sin(phi)], axis=1)
    ok = np.isfinite(s_base)
    if ok.sum() < 4:
        return np.full_like(phi, np.nanmedian(s_base) if ok.any() else np.nan)
    p, *_ = np.linalg.lstsq(A[ok], s_base[ok], rcond=None)
    res = s_base - A @ p
    mad = np.nanmedian(np.abs(res[ok])) + 1e-6
    ok2 = ok & (np.abs(res) <= 3.0 * 1.4826 * mad + 2.0)
    if ok2.sum() >= 4:
        p, *_ = np.linalg.lstsq(A[ok2], s_base[ok2], rcond=None)
    return A @ p


def _plano_valvar(vol: Volume, g: _Grade) -> np.ndarray:
    """Distância do ápice ao plano valvar (mm) em cada azimute."""
    s = np.arange(g.r_c, g.comp + EXTRA_VALVA_MM + 1e-9, PASSO_VALVA_MM)
    p = _perfis_parede(vol, g, s)  # (linhas, az, raios)
    dentro = g.raios >= RAIO_MIN_MM
    M = p[..., dentro].max(axis=-1)  # (linhas, az)
    s_base = np.full(N_AZIMUTE, np.nan)
    inicio = int(np.searchsorted(s, 0.5 * g.comp))
    for j in range(N_AZIMUTE):
        col = M[:, j]
        # referência: a parede da metade basal do próprio azimute (um defeito basal não encurta o VE)
        fim_ref = max(int(np.searchsorted(s, g.comp)), inicio + 1)
        ref = col[inicio:fim_ref].max() if fim_ref > inicio else col.max()
        if ref <= 0:
            continue
        lim = LIMIAR_VALVA * ref
        abaixo = np.nonzero(col[inicio:] < lim)[0]
        if abaixo.size == 0:
            s_base[j] = s[-1]
            continue
        k = inicio + int(abaixo[0])
        if k == 0:
            s_base[j] = s[0]
            continue
        c0, c1 = col[k - 1], col[k]
        f = (c0 - lim) / (c0 - c1) if c0 != c1 else 0.5
        s_base[j] = s[k - 1] + f * (s[k] - s[k - 1])
    plano = _ajustar_plano(s_base, g.phi)
    return np.clip(np.nan_to_num(plano, nan=g.comp), g.r_c + 0.4 * (g.comp - g.r_c), g.comp + EXTRA_VALVA_MM)


# ------------------------------------------------------- perfis e superfícies
def _suavizar(m: np.ndarray, mediana: bool = True) -> np.ndarray:
    """Mediana (ou média) 3 × 3, com volta no azimute (eixo 1) e bordas repetidas nas linhas (eixo 0)."""
    pad = np.concatenate([m[:1], m, m[-1:]], axis=0)
    viz = [np.roll(pad, dj, axis=1)[1 + di : pad.shape[0] - 1 + di] for di in (-1, 0, 1) for dj in (-1, 0, 1)]
    st = np.stack(viz)
    return np.nanmedian(st, axis=0) if mediana else np.nanmean(st, axis=0)


def _juntar(ap: np.ndarray, pa: np.ndarray) -> np.ndarray:
    """Ápice (ψ do centro para fora) + parede (de C para a base), numa grade só (linhas, az)."""
    return np.concatenate([ap, pa], axis=0)


def _pico(perfis: np.ndarray, raios: np.ndarray, lo: np.ndarray | None = None, hi: np.ndarray | None = None):
    """Posição (mm, parabólica) e valor do máximo de cada perfil, opcionalmente dentro de [lo, hi]."""
    p = perfis.copy()
    r = raios
    mask = r[None, None, :] < RAIO_MIN_MM
    if lo is not None:
        mask = mask | (r[None, None, :] < lo[..., None]) | (r[None, None, :] > hi[..., None])
    p[np.broadcast_to(mask, p.shape)] = -np.inf
    k = np.argmax(p, axis=-1)
    k = np.clip(k, 1, len(r) - 2)
    y0 = np.take_along_axis(perfis, (k - 1)[..., None], -1)[..., 0]
    y1 = np.take_along_axis(perfis, k[..., None], -1)[..., 0]
    y2 = np.take_along_axis(perfis, (k + 1)[..., None], -1)[..., 0]
    den = y0 - 2 * y1 + y2
    d = np.where(den < 0, 0.5 * (y0 - y2) / np.where(den == 0, -1, den), 0.0)
    d = np.clip(d, -0.5, 0.5)
    pos = r[k] + d * (r[1] - r[0])
    val = y1 - 0.25 * (y0 - y2) * d
    return pos, val


def _meio(perfis: np.ndarray, raios: np.ndarray):
    """Superfície mediomiocárdica regularizada: (posição mm, contagem máxima)."""
    pos, val = _pico(perfis, raios)
    ref = _suavizar(pos)
    longe = np.abs(pos - ref) > DESVIO_MEIO_MM
    if longe.any():
        p2, v2 = _pico(perfis, raios, ref - DESVIO_MEIO_MM, ref + DESVIO_MEIO_MM)
        pos = np.where(longe, p2, pos)
        val = np.where(longe, v2, val)
    pos = _suavizar(_suavizar(pos), mediana=False)
    return pos, np.maximum(val, 0.0)


def _amostrar_perfil(perfis: np.ndarray, raios: np.ndarray, r: np.ndarray) -> np.ndarray:
    f = np.clip((r - raios[0]) / (raios[1] - raios[0]), 0, len(raios) - 1.000001)
    k = np.floor(f).astype(int)
    t = f - k
    v0 = np.take_along_axis(perfis, k[..., None], -1)[..., 0]
    v1 = np.take_along_axis(perfis, np.minimum(k + 1, len(raios) - 1)[..., None], -1)[..., 0]
    return v0 * (1 - t) + v1 * t


def _sigma_perfil(perfis: np.ndarray, raios: np.ndarray, meio: np.ndarray) -> np.ndarray:
    """σ (mm) do perfil em volta do meio: meia largura a meia altura ÷ √(2 ln 2), suavizado."""
    pico = _amostrar_perfil(perfis, raios, meio)
    meia = 0.5 * pico
    passo = raios[1] - raios[0]
    hw_in = np.full(meio.shape, np.nan)
    hw_out = np.full(meio.shape, np.nan)
    for sentido, alvo in ((-1, hw_in), (1, hw_out)):
        d = np.arange(passo, 30.0 + 1e-9, passo * 0.5)
        r = meio[..., None] + sentido * d[None, None, :]
        dentro = (r >= raios[0]) & (r <= raios[-1])
        v = _amostrar_perfil(np.repeat(perfis[..., None, :], len(d), axis=-2), raios, np.clip(r, raios[0], raios[-1]))
        v = np.where(dentro, v, np.inf)
        abaixo = v < meia[..., None]
        tem = abaixo.any(axis=-1)
        k = np.argmax(abaixo, axis=-1)
        km = np.maximum(k - 1, 0)
        vk = np.take_along_axis(v, k[..., None], -1)[..., 0]
        vkm = np.where(k > 0, np.take_along_axis(v, km[..., None], -1)[..., 0], pico)
        dk = d[k]
        dkm = np.where(k > 0, d[km], 0.0)
        f = np.where(vkm != vk, (vkm - meia) / np.where(vkm != vk, vkm - vk, 1), 0.5)
        alvo[...] = np.where(tem, dkm + np.clip(f, 0, 1) * (dk - dkm), np.nan)
    hw = np.where(np.isfinite(hw_in) & np.isfinite(hw_out), 0.5 * (hw_in + hw_out), np.where(np.isfinite(hw_in), hw_in, hw_out))
    hw = np.where(np.isfinite(hw), hw, np.nanmedian(hw) if np.isfinite(hw).any() else 6.0)
    sigma = hw / np.sqrt(2.0 * np.log(2.0))
    return np.clip(_suavizar(_suavizar(sigma), mediana=False), 1.0, 20.0)


def _curvatura_media(meio: np.ndarray, s: np.ndarray) -> np.ndarray:
    """Curvatura média aproximada (1/mm) da superfície mediomiocárdica (linhas = ápice + parede)."""
    r = np.maximum(meio, 3.0)
    H = np.empty_like(r)
    H[:N_APICE] = 1.0 / r[:N_APICE]
    rp = r[N_APICE:]
    if rp.shape[0] >= 3:
        d1 = np.gradient(rp, axis=0) / np.maximum(np.gradient(s, axis=0), 1e-6)
        d2 = np.gradient(d1, axis=0) / np.maximum(np.gradient(s, axis=0), 1e-6)
        km = np.clip(-d2 / (1.0 + d1**2) ** 1.5, 0.0, 1.0 / rp)
    else:
        km = np.zeros_like(rp)
    H[N_APICE:] = 0.5 / rp + 0.5 * km
    return _suavizar(H, mediana=False)


def _corrigir_curvatura(meio: np.ndarray, s: np.ndarray, sigma: np.ndarray) -> np.ndarray:
    """Desloca o meio para fora de σ²_sistema H (ver o texto do módulo)."""
    s2 = np.maximum(sigma**2 - ESPESSURA_DIASTOLE_MM**2 / 12.0, 0.0)
    return meio + np.clip(s2 * _curvatura_media(meio, s), 0.0, 8.0)


# --------------------------------------------------------------- volumes
def _volume(r: np.ndarray, g: _Grade, plano: np.ndarray) -> float:
    """Volume (mL) dentro da superfície r (linhas = ápice + parede, az) até o plano valvar."""
    ap = np.clip(r[:N_APICE], 0, None)
    pa = np.clip(r[N_APICE:], 0, None)
    dphi = 2 * np.pi / N_AZIMUTE
    dpsi = (np.pi / 2) / N_APICE
    v_ap = np.sum(ap**3 / 3.0 * np.sin(g.psi)[:, None]) * dpsi * dphi
    ds = (plano - g.r_c) / N_PAREDE  # (az,)
    v_pa = np.sum(0.5 * pa**2 * ds[None, :]) * dphi
    return float((v_ap + v_pa) / 1000.0)


def _linhas_parede(g: _Grade, plano: np.ndarray) -> np.ndarray:
    """Distâncias do ápice (linhas, az): frações (i + 0,5)/N entre C e o plano valvar."""
    f = (np.arange(N_PAREDE) + 0.5) / N_PAREDE
    return g.r_c + f[:, None] * (plano[None, :] - g.r_c)


@dataclass
class _Quadro:
    plano: np.ndarray
    s: np.ndarray  # (N_PAREDE, az)
    perfis: np.ndarray  # (linhas, az, raios)
    meio: np.ndarray
    pico: np.ndarray


def _quadro(vol: Volume, g: _Grade) -> _Quadro:
    plano = _plano_valvar(vol, g)
    s = _linhas_parede(g, plano)
    perfis = _juntar(_perfis_apice(vol, g), _perfis_parede(vol, g, s))
    meio, pico = _meio(perfis, g.raios)
    meio = _corrigir_curvatura(meio, s, _sigma_perfil(perfis, g.raios, meio))
    return _Quadro(plano, s, perfis, meio, pico)


def _pontos(g: _Grade, s: np.ndarray, r: np.ndarray) -> np.ndarray:
    """Pontos 3D (linhas, az, 3) em mm do paciente."""
    ap = g.centro[None, None, :] + g.dirs_apice * r[:N_APICE, :, None]
    pa = g.apice[None, None, :] - s[..., None] * g.a[None, None, :] + g.dirs[None, :, :] * r[N_APICE:, :, None]
    return np.concatenate([ap, pa], axis=0)


def _local(g: _Grade, pts: np.ndarray) -> np.ndarray:
    """Coordenadas do VE: x lateral, y anterior, z do plano da base (0) para o ápice (+)."""
    d = pts - (g.apice - g.comp * g.a)
    return np.stack([d @ g.h, d @ g.w, d @ g.a], axis=-1)


# --------------------------------------------------------------- resultado
@dataclass
class Superficies:
    """Superfícies de um intervalo, em coordenadas do VE (mm): (linhas, az, 3)."""

    endo: np.ndarray
    epi: np.ndarray
    meio: np.ndarray


@dataclass
class ResultadoGated:
    volumes_ml: list[float]
    ed: int
    es: int
    vdf_ml: float
    vsf_ml: float
    fe: float
    superficies: list[Superficies]
    motilidade: MapaPolar
    espessamento: MapaPolar
    planos_mm: list[list[float]]
    massa_ml: float
    avisos: list[str] = field(default_factory=list)

    @property
    def volume_sistolico_ml(self) -> float:
        return self.vdf_ml - self.vsf_ml

    def segmentos(self) -> dict:
        mot = self.motilidade.valores_segmentos()
        esp = self.espessamento.valores_segmentos()
        return {s: {"motilidade_mm": float(mot[s]), "espessamento": float(esp[s])} for s in SEGMENTOS}

    def resumo(self) -> dict:
        return {
            "volumes_ml": [round(v, 2) for v in self.volumes_ml],
            "ed": self.ed + 1,
            "es": self.es + 1,
            "vdf_ml": round(self.vdf_ml, 1),
            "vsf_ml": round(self.vsf_ml, 1),
            "vs_ml": round(self.volume_sistolico_ml, 1),
            "fe": round(self.fe, 1),
            "massa_ml": round(self.massa_ml, 1),
            "avisos": self.avisos,
            "segmentos": {str(s): {k: round(v, 1) for k, v in d.items()} for s, d in self.segmentos().items()},
        }

    def malha(self) -> dict:
        """Superfícies para a malha 3D (coordenadas do VE, mm, arredondadas a 0,1)."""
        r = lambda x: np.round(x, 1).tolist()  # noqa: E731
        return {
            "linhas": N_APICE + N_PAREDE,
            "azimutes": N_AZIMUTE,
            "endo": [r(s.endo) for s in self.superficies],
            "epi_ed": r(self.superficies[self.ed].epi),
            "ed": self.ed,
            "es": self.es,
            "volumes_ml": [round(v, 2) for v in self.volumes_ml],
        }


def _mapa(valores: np.ndarray, g: _Grade, plano: np.ndarray) -> MapaPolar:
    """Mapa polar (mesma geometria do de perfusão): ápice com ψ do centro para fora, parede de C à base."""
    comp_pa = float(np.mean(plano) - g.r_c)
    arco = np.pi / 2 * g.r_c
    return MapaPolar(
        parede=valores[N_APICE:],
        apice=valores[:N_APICE],
        maximo=1.0,
        r_c_mm=g.r_c,
        rho_apice=float(arco / (arco + max(comp_pa, 1e-6))),
        azimutes=np.degrees(g.phi),
    )


def analisar_gated(volumes: list[Volume], totais: list[float], eixo: Eixo) -> ResultadoGated:
    """Bordas, volumes, FE e mapas de função de um gated (um volume por intervalo)."""
    if len(volumes) < 4:
        raise ValueError("O gated precisa de pelo menos 4 intervalos.")
    soma = Volume(dados=np.sum([v.dados for v in volumes], axis=0), pixel_mm=volumes[0].pixel_mm, z_mm=volumes[0].z_mm, filtro=volumes[0].filtro)
    g = _centralizar(soma, _grade(eixo))
    quadros = [_quadro(v, g) for v in volumes]
    tot = np.asarray(totais, float)
    tot = tot / tot.mean()
    picos_n = [q.pico / max(t, 1e-9) for q, t in zip(quadros, tot)]
    avisos = []

    def resolver(ref: int):
        q0 = quadros[ref]
        t0 = np.full_like(q0.meio, ESPESSURA_DIASTOLE_MM)
        endo0 = np.maximum(q0.meio - t0 / 2, 0.5)
        epi0 = q0.meio + t0 / 2
        massa = _volume(epi0, g, q0.plano) - _volume(endo0, g, q0.plano)
        esp, endos, epis, vols = [], [], [], []
        for k, q in enumerate(quadros):
            razao = np.clip(picos_n[k] / np.maximum(picos_n[ref], 1e-9), 0.5, 2.5)
            t = t0 * _suavizar(razao, mediana=False)

            def massa_com(lam):
                en = np.maximum(q.meio - lam * t / 2, 0.5)
                return _volume(q.meio + lam * t / 2, g, q.plano) - _volume(en, g, q.plano)

            lo, hi = 0.2, 5.0
            if k == ref:
                lam = 1.0
            else:
                for _ in range(40):
                    mid = 0.5 * (lo + hi)
                    if massa_com(mid) < massa:
                        lo = mid
                    else:
                        hi = mid
                lam = 0.5 * (lo + hi)
            tk = lam * t
            en = np.maximum(q.meio - tk / 2, 0.5)
            ep = q.meio + tk / 2
            esp.append(tk)
            endos.append(en)
            epis.append(ep)
            vols.append(_volume(en, g, q.plano))
        return esp, endos, epis, vols, massa

    ref = 0
    esp, endos, epis, vols, massa = resolver(ref)
    ed = int(np.argmax(vols))
    if ed != ref:
        esp, endos, epis, vols, massa = resolver(ed)
        ed = int(np.argmax(vols))
    es = int(np.argmin(vols))
    n = len(vols)
    if not (min(abs(ed - 0), abs(ed - n), abs(ed - (n - 1))) <= 1):
        avisos.append(f"A diástole final caiu no intervalo {ed + 1} de {n}; o esperado é o primeiro ou o último. Confira o gatilho do ECG.")
    if not (0.2 * n <= es <= 0.7 * n):
        avisos.append(f"A sístole final caiu no intervalo {es + 1} de {n}; o esperado é perto de um terço a metade do ciclo. Confira o gatilho do ECG.")

    pts_endo = [_pontos(g, q.s, e) for q, e in zip(quadros, endos)]
    pts_epi = [_pontos(g, q.s, e) for q, e in zip(quadros, epis)]
    pts_meio = [_pontos(g, q.s, q.meio) for q in quadros]
    sup = [Superficies(_local(g, en), _local(g, ep), _local(g, me)) for en, ep, me in zip(pts_endo, pts_epi, pts_meio)]

    # motilidade: deslocamento do endocárdio da diástole para a sístole final, positivo para dentro
    desloc = pts_endo[es] - pts_endo[ed]
    dist = np.linalg.norm(desloc, axis=-1)
    meio_ed = pts_meio[ed]
    centro_cav = np.concatenate([
        np.broadcast_to(g.centro, (N_APICE, N_AZIMUTE, 3)),
        g.apice[None, None, :] - quadros[ed].s[..., None] * g.a[None, None, :],
    ])
    para_fora = meio_ed - centro_cav
    para_fora /= np.maximum(np.linalg.norm(para_fora, axis=-1, keepdims=True), 1e-9)
    sinal = np.where(np.sum(desloc * para_fora, axis=-1) > 0, -1.0, 1.0)
    mot = sinal * dist
    esp_rel = 100.0 * (esp[es] / np.maximum(esp[ed], 1e-9) - 1.0)
    plano_ed = quadros[ed].plano
    return ResultadoGated(
        volumes_ml=[float(v) for v in vols],
        ed=ed,
        es=es,
        vdf_ml=float(vols[ed]),
        vsf_ml=float(vols[es]),
        fe=float(100.0 * (vols[ed] - vols[es]) / max(vols[ed], 1e-9)),
        superficies=sup,
        motilidade=_mapa(mot, g, plano_ed),
        espessamento=_mapa(esp_rel, g, plano_ed),
        planos_mm=[[round(float(x), 2) for x in q.plano] for q in quadros],
        massa_ml=float(massa),
        avisos=avisos,
    )


def volume_nao_sincronizado(vol: Volume, eixo: Eixo) -> float:
    """Volume da cavidade (mL) numa imagem não sincronizada (para a TID)."""
    g = _centralizar(vol, _grade(eixo))
    q = _quadro(vol, g)
    return _volume(np.maximum(q.meio - ESPESSURA_DIASTOLE_MM / 2, 0.5), g, q.plano)


def calcular_tid(v_estresse: float, v_repouso: float) -> float:
    """TID = volume da cavidade no estresse ÷ no repouso (imagens não sincronizadas)."""
    if v_repouso <= 0:
        raise ValueError("Volume do repouso inválido.")
    return float(v_estresse / v_repouso)


# --------------------------------------------------------------- escores
def validar_escore_funcao(tipo: str, valor) -> int:
    lim = {"motilidade": MOTILIDADE_ESCORE_MAX, "espessamento": ESPESSAMENTO_ESCORE_MAX}[tipo]
    v = int(valor)
    if not 0 <= v <= lim:
        raise ValueError(f"Escore de {tipo} vai de 0 a {lim}.")
    return v


def escores_funcao(escores: dict, tipo: str) -> dict | None:
    """Soma (SMS ou STS) e % do máximo (17 × 5 = 85 ou 17 × 3 = 51), se todos os 17 estiverem pontuados."""
    lim = {"motilidade": MOTILIDADE_ESCORE_MAX, "espessamento": ESPESSAMENTO_ESCORE_MAX}[tipo]
    vals = [escores.get(s, escores.get(str(s))) for s in SEGMENTOS]
    if any(v is None for v in vals):
        return None
    soma = int(sum(int(v) for v in vals))
    return {"soma": soma, "percentual": round(100.0 * soma / (17 * lim), 1)}


def superficie_corporal(peso_kg: float, altura_cm: float) -> float:
    """Superfície corporal (m²) de Mosteller: √(altura × peso / 3600)."""
    if not (peso_kg > 0 and altura_cm > 0):
        raise ValueError("Peso e altura precisam ser positivos.")
    return float(np.sqrt(peso_kg * altura_cm / 3600.0))
