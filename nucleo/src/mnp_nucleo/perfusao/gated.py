"""Função do VE no gated SPECT pelo método do QGS: bordas, volumes, FE, TID, motilidade e espessamento.

MÉTODO. Germano et al., Automatic quantification of ejection fraction from
gated myocardial perfusion SPECT, J Nucl Med 1995;36:2138-47 (texto
completo enviado pelo Mourato em 17 nov 2026), seção "Methods" das
páginas 2138–2140. Cada passo abaixo resume o que o artigo diz e, quando
o artigo não dá o número ou a regra exata, a escolha desta ferramenta vem
marcada como [escolha].

1. Segmentação do VE (imagem não sincronizada = soma dos intervalos).
   Artigo: limiar de 50% da contagem máxima, binarização, clusters
   conectados; descarta clusters < 50 mL; se o retângulo que circunscreve
   o cluster nos cortes de eixo curto tiver lados com diferença > 1 cm
   (fígado ou alça colados), sobe o limiar de 5 em 5% até o cluster se
   partir, escolhe o VE e o fígado e dilata os dois camada a camada, sem
   reconectar, até voltar ao limiar original.
   [escolha] O artigo procura o máximo na metade superior do volume de eixo
   curto e escolhe o cluster mais perto do centro do quadrante superior
   direito; aqui o volume de eixo curto vem do eixo traçado pelo usuário
   (cubo de 150 mm em volta do meio do eixo), o máximo é procurado a até
   50 mm do meio do eixo e o VE é o cluster mais perto dele. A extensão por
   transformada de Hough (quando a segmentação falha) não foi implementada:
   nesse caso a máscara é a esfera de 45 mm em volta do meio do eixo, com
   aviso. Na erosão, se os dois pedaços ficam a menos de 30 mm do meio do
   eixo, eles são o próprio VE (oval ou com defeito), e fica o cluster
   original.
2. Superfície mediomiocárdica inicial. Artigo: origem no centro de massa
   da máscara; perfis radiais a cada 10° (18 × 36 = 684 perfis) sobre
   máscara × imagem; o primeiro máximo de cada perfil é a superfície de
   contagem máxima (aproximação da mediomiocárdica); ajuste de elipsoide;
   nova origem = projeção do centro de massa no eixo longo do elipsoide;
   repete até o eixo longo variar menos de 0,5° (2 a 3 iterações).
3. Superfície de soma. Artigo: perfis normais ao elipsoide na imagem sem
   máscara (24 × 32), convoluídos com o detector −K e^(−x²/2σ²)(x² − σ²),
   σ = 10 mm; máximos locais; um ponto por perfil minimizando o custo
   (desvio da normal da superfície em relação à do elipsoide + distância e
   magnitude dos máximos); novo elipsoide ajustado a esses pontos = base de
   amostragem. [escolha] Custo: ((x − mediana dos 4 vizinhos)/5 mm)² −
   magnitude relativa + 0,2 (x/15 mm)², minimizado por iterações locais
   (ICM); a mediana dos vizinhos faz o papel do desvio da normal. Grade:
   24 azimutes de 15° e 32 ângulos do ápice (0°) à base (180°), em
   direções a partir do centro do elipsoide.
4. Superfície de cada intervalo. Artigo: mesmos perfis normais ao
   elipsoide, mesmo detector, com continuidade temporal (pontos homólogos
   de intervalos vizinhos penalizados pela distância). [escolha] Termo
   temporal ((x − média dos intervalos vizinhos)/5 mm)².
5. Plano valvar. Artigo: na geometria da diástole final, com a contagem
   média de todos os intervalos, limiar de 25%; plano ajustado aos pontos
   da borda da maior e mais basal área abaixo do limiar, minimizando o
   desvio da normal do plano em relação a uma direção preferida mais a
   soma das distâncias, com pontos apicais ao plano a no máximo 20 mm; se
   a área abaixo do limiar e basal ao plano for < 10% da superfície, o
   limiar sobe. As normais apicais ao plano na diástole final são o
   miocárdio em todos os intervalos; o plano acompanha os pontos da borda.
   [escolha] Direção preferida = eixo longo; peso de 30 mm por unidade de
   inclinação; mínimos desvios absolutos por mínimos quadrados repesados;
   passo do limiar de 5%.
6. Endocárdio e epicárdio. Artigo: perfis normais à superfície
   mediomiocárdica, 20 mm para cada lado; gaussiana assimétrica (σ interno
   e externo); perfis com pico < 50% do máximo miocárdico do intervalo
   são inválidos e recebem os σ que minimizam a diferença absoluta com os
   4 vizinhos; endocárdio a 65% do σ interno para dentro e epicárdio a uma
   fração do σ externo para fora (65% calibrado num fantoma de 63 mL).
   Nos intervalos que não a diástole final, endo e epicárdio são
   refinados para manter constante o volume miocárdico. [escolha] A
   mesma fração de 65% para o σ externo (o artigo não dá o número); ajuste
   com fundo constante por Levenberg-Marquardt; o lado interno do perfil
   para no eixo longo (na sístole, 20 mm para dentro passariam da cavidade
   e pegariam a parede oposta) e o endocárdio não cruza o eixo; o
   refinamento da massa escala as duas distâncias por um fator único por
   intervalo.
7. Volumes e FE. Volume endocárdico = limitado pelo endocárdio e pelo
   plano valvar; VDF e VSF = maior e menor da curva; FE = (VDF − VSF)/VDF
   (equação 1 do artigo).
8. Motilidade e espessamento (Germano et al., J Am Coll Cardiol
   1997;30:1360-7, só o resumo): motilidade do endocárdio entre diástole
   e sístole (linha central modificada) e espessamento por geometria
   (gaussiana) e volume parcial. [escolha] Motilidade = deslocamento do
   ponto endocárdico ao longo da normal da diástole (mm, positivo para
   dentro); espessamento = (espessura na sístole ÷ espessura na diástole −
   1) × 100, com a espessura geométrica do passo 6. Escalas dos mapas
   (manual do QGS): 0–10 mm e 0–100%.
9. TID (Abidov et al., J Nucl Med 2004;45:1999-2007): volume endocárdico
   do estresse ÷ do repouso nas imagens não sincronizadas, pelos passos 1
   a 6 (sem o refinamento da massa). Sem ponto de corte.

Escores visuais de motilidade (0–5) e espessamento (0–3) por segmento,
pontuados pelo médico (SBC 2020, Tabela 19), com as somas SMS e STS.
Mapa polar de função [escolha]: cada coluna de azimute, do ápice ao plano
valvar, reamostrada em 24 linhas; as 4 primeiras formam o ápice (17).
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field

import numpy as np

from .eixos import Eixo, base_vetorial
from .polar import SEGMENTOS, MapaPolar
from .reconstrucao import Volume

__all__ = [
    "Superficies",
    "ResultadoGated",
    "Elipsoide",
    "analisar_gated",
    "volume_nao_sincronizado",
    "calcular_tid",
    "escores_funcao",
    "validar_escore_funcao",
    "superficie_corporal",
    "ajustar_elipsoide",
    "segmentar",
    "paineis_contorno",
    "intersecao_malha",
    "N_AZIMUTE",
    "N_LINHAS",
    "N_APICE",
    "FRACAO_SD",
    "LIMIAR_VALVA",
    "MOTILIDADE_MAX",
    "ESPESSAMENTO_MAX",
]

# ---------------------------------------------------------------- parâmetros
#: Germano 1995: limiar da segmentação, volume mínimo de cluster e retângulo.
LIMIAR_SEGMENTACAO = 0.5
VOLUME_MINIMO_ML = 50.0
LADO_RETANGULO_MM = 10.0
#: Germano 1995: amostragem esférica a cada 10° e critério de 0,5° do eixo longo.
PASSO_ESFERICO_GRAUS = 10.0
TOLERANCIA_EIXO_GRAUS = 0.5
#: Germano 1995: detector de bordas (segunda derivada da gaussiana) com σ = 10 mm.
SIGMA_DETECTOR_MM = 10.0
#: Germano 1995: grade de 24 × 32 normais ao elipsoide.
N_AZIMUTE = 24
N_POLAR = 32
#: Germano 1995: plano valvar com limiar de 25%, 20 mm e 10% da superfície.
LIMIAR_VALVA = 0.25
APICAL_MAX_MM = 20.0
AREA_MINIMA_VALVA = 0.10
#: Germano 1995: perfis de ±20 mm, validade a 50% do máximo e 65% do σ.
MEIA_LARGURA_PERFIL_MM = 20.0
PICO_VALIDO = 0.5
FRACAO_SD = 0.65
#: Escolhas desta ferramenta (ver o texto do módulo).
LADO_CUBO_MM = 150.0
DISTANCIA_EXTRACARDIACA_MM = 30.0
RAIO_BUSCA_MM = 50.0
RAIO_SEM_SEGMENTACAO_MM = 45.0
ALCANCE_NORMAL_MM = 25.0
PESO_INCLINACAO_MM = 30.0
N_LINHAS = 24
N_APICE = 4
#: Escalas de exibição dos mapas (manual do QGS): 0–10 mm e 0–100%.
MOTILIDADE_MAX = 10.0
ESPESSAMENTO_MAX = 100.0
MOTILIDADE_ESCORE_MAX = 5
ESPESSAMENTO_ESCORE_MAX = 3


# ------------------------------------------------------------- utilidades
def _volume_soma(volumes: list[Volume]) -> Volume:
    return Volume(dados=np.sum([v.dados for v in volumes], axis=0), pixel_mm=volumes[0].pixel_mm, z_mm=volumes[0].z_mm,
                  filtro=volumes[0].filtro)


def _deslocar(m: np.ndarray, d: int, eixo: int, fundo=0):
    v = np.roll(m, d, axis=eixo)
    borda = [slice(None)] * m.ndim
    borda[eixo] = 0 if d == 1 else -1
    v[tuple(borda)] = fundo
    return v


def _rotular(mascara: np.ndarray) -> np.ndarray:
    """Componentes conectados (vizinhança de 6) por propagação do menor rótulo. 0 = fundo."""
    rot = np.where(mascara, np.arange(1, mascara.size + 1).reshape(mascara.shape), 0)
    for _ in range(5000):
        novo = rot.copy()
        for eixo in range(3):
            for d in (1, -1):
                viz = _deslocar(rot, d, eixo)
                novo = np.where(mascara & (viz > 0) & (viz < novo), viz, novo)
        if np.array_equal(novo, rot):
            break
        rot = novo
    return rot


def _dilatar(m: np.ndarray) -> np.ndarray:
    out = m.copy()
    for eixo in range(3):
        for d in (1, -1):
            out |= _deslocar(m, d, eixo, False)
    return out


def ajustar_elipsoide(pts: np.ndarray):
    """Elipsoide (centro, Q com (p−c)ᵀQ(p−c) = 1, semieixos, eixos) por quádrica algébrica; PCA se não der elipsoide."""
    p = np.asarray(pts, float)
    m = p.mean(axis=0)
    s = p.std() or 1.0
    q = (p - m) / s
    x, y, z = q.T
    D = np.stack([x * x, y * y, z * z, 2 * x * y, 2 * x * z, 2 * y * z, 2 * x, 2 * y, 2 * z], axis=1)
    try:
        v, *_ = np.linalg.lstsq(D, np.ones(len(q)), rcond=None)
        a, b, c, d, e, f, g, h, i = v
        A3 = np.array([[a, d, e], [d, b, f], [e, f, c]])
        centro = -np.linalg.solve(A3, np.array([g, h, i]))
        k = 1.0 + centro @ A3 @ centro
        if k <= 0:
            raise np.linalg.LinAlgError
        ev, vec = np.linalg.eigh(A3 / k)
        if np.any(ev <= 0):
            raise np.linalg.LinAlgError
        semi = s / np.sqrt(ev)
        centro = m + centro * s
    except np.linalg.LinAlgError:
        ev, vec = np.linalg.eigh(np.cov((p - m).T))
        semi = np.sqrt(np.maximum(3.0 * ev, 1.0))
        centro = m
    Q = vec @ np.diag(1.0 / semi**2) @ vec.T
    return centro, Q, semi, vec


def _angulo(u, v) -> float:
    return float(np.degrees(np.arccos(np.clip(abs(u @ v) / (np.linalg.norm(u) * np.linalg.norm(v)), -1, 1))))


def _suavizar_grade(m: np.ndarray) -> np.ndarray:
    """Média 3 × 3 na grade (polar, azimute), com volta no azimute e bordas repetidas no polar."""
    pad = np.concatenate([m[:1], m, m[-1:]], axis=0)
    viz = np.stack([np.roll(pad, dj, axis=1)[1 + di: pad.shape[0] - 1 + di] for di in (-1, 0, 1) for dj in (-1, 0, 1)])
    return np.nanmean(viz, axis=0)


def _mediana_vizinhos(m: np.ndarray) -> np.ndarray:
    """Mediana dos 4 vizinhos na grade, com volta no azimute (eixo 1)."""
    up = np.concatenate([m[:1], m[:-1]], axis=0)
    dn = np.concatenate([m[1:], m[-1:]], axis=0)
    st = np.stack([up, dn, np.roll(m, 1, 1), np.roll(m, -1, 1)])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # célula sem vizinho válido: fica NaN
        return np.nanmedian(st, axis=0)


# ------------------------------------------------------------ segmentação
@dataclass
class _Cubo:
    origem: np.ndarray  # meio do eixo do usuário
    a: np.ndarray
    w: np.ndarray
    h: np.ndarray
    passo: float
    n: int

    def coords(self):
        o = (np.arange(self.n) - (self.n - 1) / 2.0) * self.passo
        return np.meshgrid(o, o, o, indexing="ij")  # ao longo de a, de w, de h

    def pontos(self) -> np.ndarray:
        A, W, H = self.coords()
        return self.origem + A[..., None] * self.a + W[..., None] * self.w + H[..., None] * self.h


def _retangulo_ok(m: np.ndarray, cubo: _Cubo) -> bool:
    """Germano 1995: lados do retângulo que circunscreve o cluster nos cortes de eixo curto com diferença < 1 cm."""
    if not m.any():
        return False
    _, W, H = cubo.coords()
    lw = W[m].max() - W[m].min() + cubo.passo
    lh = H[m].max() - H[m].min() + cubo.passo
    return abs(lw - lh) < LADO_RETANGULO_MM


def segmentar(vol: Volume, eixo: Eixo) -> tuple[np.ndarray, _Cubo, list[str]]:
    """Máscara binária do miocárdio do VE num cubo de eixo curto em volta do eixo do usuário (passo 1)."""
    avisos: list[str] = []
    a, w, h = base_vetorial(np.asarray(eixo.base, float), np.asarray(eixo.apice, float))
    passo = max(vol.pixel_mm / 2.0, 2.5)
    n = int(np.ceil(LADO_CUBO_MM / passo)) | 1
    cubo = _Cubo((np.asarray(eixo.base, float) + np.asarray(eixo.apice, float)) / 2.0, a, w, h, passo, n)
    C = vol.amostrar(cubo.pontos())
    A, W, H = cubo.coords()
    dist = np.sqrt(A**2 + W**2 + H**2)
    cmax = float(C[dist <= RAIO_BUSCA_MM].max())
    if cmax <= 0:
        raise ValueError("Sem contagens em volta do eixo: confira o eixo traçado.")
    voxel_ml = passo**3 / 1000.0

    def clusters(limiar, dentro=None):
        m = C >= limiar * cmax
        if dentro is not None:
            m &= dentro
        rot = _rotular(m)
        ids, tam = np.unique(rot[rot > 0], return_counts=True)
        return rot, ids, tam

    rot, ids, tam = clusters(LIMIAR_SEGMENTACAO)
    validos = [(i, t) for i, t in zip(ids, tam) if t * voxel_ml >= VOLUME_MINIMO_ML]
    if not validos:
        avisos.append("Segmentação automática do VE não encontrou um cluster de pelo menos 50 mL; usada a esfera de 45 mm em volta do eixo.")
        return (dist <= RAIO_SEM_SEGMENTACAO_MM) & (C >= LIMIAR_SEGMENTACAO * cmax), cubo, avisos
    perto = min(validos, key=lambda it: dist[rot == it[0]].min())
    ve = rot == perto[0]
    if _retangulo_ok(ve, cubo):
        return ve, cubo, avisos
    original = ve
    for lim in np.arange(LIMIAR_SEGMENTACAO + 0.05, 0.951, 0.05):
        r2, i2, t2 = clusters(lim, original)
        if len(i2) < 2:
            continue
        ordem = np.argsort(t2)[::-1][:2]
        dois = [i2[k] for k in ordem]
        d0, d1 = (dist[r2 == i].min() for i in dois)
        ve = r2 == (dois[0] if d0 <= d1 else dois[1])
        outro = r2 == (dois[1] if d0 <= d1 else dois[0])
        if max(d0, d1) < DISTANCIA_EXTRACARDIACA_MM:
            # [escolha] os dois pedaços estão em volta do meio do eixo: é o próprio VE (oval ou com defeito), não fígado
            return original, cubo, avisos
        for lim2 in np.arange(lim - 0.05, LIMIAR_SEGMENTACAO - 1e-9, -0.05):
            permitido = original & (C >= lim2 * cmax)
            for _ in range(n):
                cand_ve = _dilatar(ve) & permitido & ~ve & ~_dilatar(outro)
                cand_ou = _dilatar(outro) & permitido & ~outro & ~_dilatar(ve) & ~cand_ve
                mudou = False
                if cand_ve.any() and _retangulo_ok(ve | cand_ve, cubo):
                    ve = ve | cand_ve
                    mudou = True
                if cand_ou.any():
                    outro = outro | cand_ou
                    mudou = True
                if not mudou:
                    break
        if ve.sum() * voxel_ml < VOLUME_MINIMO_ML:
            break  # a erosão partiu o próprio VE: fica o cluster original
        avisos.append(f"Segmentação: atividade extracardíaca colada ao VE separada por erosão (limiar de {lim * 100:.0f}%) e dilatação.")
        return ve, cubo, avisos
    avisos.append("Segmentação: o cluster do VE parece colado a outra estrutura e a erosão não o separou; confira os contornos.")
    return original, cubo, avisos


def _mascara_em(cubo: _Cubo, mascara: np.ndarray, pts: np.ndarray) -> np.ndarray:
    """Valor da máscara (vizinho mais próximo) em pontos 3D; fora do cubo = 0."""
    d = pts - cubo.origem
    c = (cubo.n - 1) / 2.0
    ia = np.rint(d @ cubo.a / cubo.passo + c).astype(int)
    iw = np.rint(d @ cubo.w / cubo.passo + c).astype(int)
    ih = np.rint(d @ cubo.h / cubo.passo + c).astype(int)
    ok = (ia >= 0) & (ia < cubo.n) & (iw >= 0) & (iw < cubo.n) & (ih >= 0) & (ih < cubo.n)
    out = np.zeros(pts.shape[:-1])
    out[ok] = mascara[ia[ok], iw[ok], ih[ok]]
    return out


# --------------------------------------------- superfície e elipsoide (passos 2 e 3)
@dataclass
class Elipsoide:
    centro: np.ndarray
    Q: np.ndarray
    semi: np.ndarray
    longo: np.ndarray  # unitário, para o ápice
    lateral: np.ndarray  # 0° do azimute
    anterior: np.ndarray  # 90° do azimute

    def direcoes(self) -> np.ndarray:
        """Direções (polar, azimute, 3) a partir do centro: 32 ângulos do ápice à base × 24 azimutes."""
        th = (np.arange(N_POLAR) + 0.5) / N_POLAR * np.pi
        ph = (np.arange(N_AZIMUTE) + 0.5) * (2 * np.pi / N_AZIMUTE)
        TH, PH = np.meshgrid(th, ph, indexing="ij")
        return (np.cos(TH)[..., None] * self.longo
                + np.sin(TH)[..., None] * (np.cos(PH)[..., None] * self.lateral + np.sin(PH)[..., None] * self.anterior))

    def superficie(self):
        """Pontos da superfície e normais unitárias na grade (polar, azimute)."""
        u = self.direcoes()
        t = 1.0 / np.sqrt(np.einsum("...i,ij,...j->...", u, self.Q, u))
        p = self.centro + u * t[..., None]
        nrm = (p - self.centro) @ self.Q
        nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True)
        return p, nrm


def _quadro_anatomico(longo: np.ndarray, eixo: Eixo):
    _, w, h = base_vetorial(np.asarray(eixo.base, float), np.asarray(eixo.apice, float))
    lat = h - (h @ longo) * longo
    lat /= np.linalg.norm(lat)
    ant = np.cross(longo, lat)
    if ant @ w < 0:
        ant = -ant
    return lat, ant


def _elipsoide(pts: np.ndarray, preferido: np.ndarray, eixo: Eixo) -> Elipsoide:
    c, Q, semi, vec = ajustar_elipsoide(pts)
    longo = vec[:, int(np.argmax(semi))]
    if longo @ preferido < 0:
        longo = -longo
    lat, ant = _quadro_anatomico(longo, eixo)
    return Elipsoide(c, Q, semi, longo, lat, ant)


def _primeiros_maximos(perf: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Índice do primeiro máximo local (> 0) de cada perfil e se existe."""
    dif = np.diff(perf, axis=-1)
    sobe = np.concatenate([np.ones(perf.shape[:-1] + (1,), bool), dif > 0], -1)
    desce = np.concatenate([dif <= 0, np.ones(perf.shape[:-1] + (1,), bool)], -1)
    pico = sobe & desce & (perf > 0)
    return np.argmax(pico, axis=-1), pico.any(axis=-1)


def _superficie_inicial(vol: Volume, mascara: np.ndarray, cubo: _Cubo, eixo: Eixo) -> Elipsoide:
    """Passo 2: centro de massa, perfis radiais a cada 10°, primeiros máximos, elipsoide, iterado."""
    A, W, H = cubo.coords()
    com = cubo.origem + A[mascara].mean() * cubo.a + W[mascara].mean() * cubo.w + H[mascara].mean() * cubo.h
    origem, longo = com, cubo.a
    r = np.arange(0.0, 70.0 + 1e-9, 1.0)
    th = np.deg2rad(np.arange(PASSO_ESFERICO_GRAUS / 2, 180.0, PASSO_ESFERICO_GRAUS))
    ph = np.deg2rad(np.arange(0.0, 360.0, PASSO_ESFERICO_GRAUS))
    TH, PH = np.meshgrid(th, ph, indexing="ij")
    eli = None
    for _ in range(8):
        lat, ant = _quadro_anatomico(longo, eixo)
        u = np.cos(TH)[..., None] * longo + np.sin(TH)[..., None] * (np.cos(PH)[..., None] * lat + np.sin(PH)[..., None] * ant)
        pts = origem + u[..., None, :] * r[None, None, :, None]
        perf = vol.amostrar(pts) * _mascara_em(cubo, mascara, pts)
        k, tem = _primeiros_maximos(perf)
        pontos = (origem + u * r[k][..., None])[tem]
        if len(pontos) < 20:
            raise ValueError("Poucos pontos de miocárdio na segmentação: confira o eixo traçado.")
        novo = _elipsoide(pontos, cubo.a, eixo)
        variacao = _angulo(novo.longo, longo) if eli is not None else 90.0
        eli, longo = novo, novo.longo
        origem = novo.centro + ((com - novo.centro) @ longo) * longo
        if variacao < TOLERANCIA_EIXO_GRAUS:
            break
    return eli


def _detector(x: np.ndarray, sigma: float = SIGMA_DETECTOR_MM) -> np.ndarray:
    """−e^(−x²/2σ²)(x² − σ²) (Germano 1995, equação 3), cortado em ±3σ; [escolha] média zero (fundo constante não
    responde) e soma dos valores absolutos igual a 1."""
    g = -np.exp(-(x**2) / (2 * sigma**2)) * (x**2 - sigma**2)
    g = g - g.mean()
    return g / np.abs(g).sum()


def _perfis_normais(vol: Volume, p: np.ndarray, nrm: np.ndarray, x: np.ndarray) -> np.ndarray:
    return vol.amostrar(p[..., None, :] + nrm[..., None, :] * x[..., None])


def _candidatos(vol: Volume, p: np.ndarray, nrm: np.ndarray):
    """Perfis normais convoluídos com o detector; até 4 máximos locais por perfil (posição em mm, magnitude)."""
    xk = np.arange(-3 * SIGMA_DETECTOR_MM, 3 * SIGMA_DETECTOR_MM + 1e-9, 1.0)
    meio = len(xk) // 2
    x = np.arange(-ALCANCE_NORMAL_MM - xk[-1], ALCANCE_NORMAL_MM + xk[-1] + 1e-9, 1.0)
    perf = _perfis_normais(vol, p, nrm, x)
    k = _detector(xk)
    L = len(x) - len(xk) + 1
    conv = np.zeros(perf.shape[:-1] + (L,))
    for i, kv in enumerate(k):
        conv += kv * perf[..., i:i + L]
    xs = x[meio: meio + L]
    dif = np.diff(conv, axis=-1)
    loc = np.zeros(conv.shape, bool)
    loc[..., 1:-1] = (dif[..., :-1] > 0) & (dif[..., 1:] <= 0)
    loc &= conv > 0
    mag = np.where(loc, conv, -np.inf)
    ordem = np.argsort(-mag, axis=-1)[..., :4]
    pos = np.take_along_axis(np.broadcast_to(xs, conv.shape), ordem, -1).astype(float)
    mg = np.take_along_axis(mag, ordem, -1)
    pos[~np.isfinite(mg)] = np.nan
    mg[~np.isfinite(mg)] = np.nan
    return pos, mg


def _escolher(pos: np.ndarray, mag: np.ndarray, referencia: np.ndarray | None = None, peso_ref: float = 0.0, iteracoes: int = 8):
    """Um ponto por perfil: ICM com suavidade espacial, magnitude e (opcional) uma referência (continuidade temporal)."""
    validos = np.isfinite(pos)
    mmax = np.nanmax(mag) if validos.any() else 1.0
    rel = np.where(validos, mag / mmax, 0.0)
    p0 = np.where(validos, pos, 0.0)
    custo0 = np.where(validos, -rel + 0.2 * (p0 / 15.0) ** 2, np.inf)
    escolha = np.argmin(custo0, axis=-1)
    x = np.take_along_axis(np.where(validos, pos, np.nan), escolha[..., None], -1)[..., 0]
    x = np.where(np.isfinite(x), x, 0.0)
    for _ in range(iteracoes):
        viz = np.nan_to_num(_mediana_vizinhos(x))
        c = custo0 + ((p0 - viz[..., None]) / 5.0) ** 2
        if referencia is not None:
            c = c + peso_ref * ((p0 - referencia[..., None]) / 5.0) ** 2
        c = np.where(validos, c, np.inf)
        escolha = np.argmin(c, axis=-1)
        novo = np.take_along_axis(np.where(validos, pos, np.nan), escolha[..., None], -1)[..., 0]
        novo = np.where(np.isfinite(novo), novo, viz)
        if np.allclose(novo, x):
            return novo
        x = novo
    return x


# ------------------------------------------------------------ plano valvar (passo 5)
def _plano(pts: np.ndarray, eli: Elipsoide) -> np.ndarray:
    """Plano z = p0 + p1 x + p2 y (coordenadas do elipsoide, z para o ápice): mínimos desvios absolutos + inclinação."""
    d = pts - eli.centro
    x, y, z = d @ eli.lateral, d @ eli.anterior, d @ eli.longo
    p = np.array([np.median(z), 0.0, 0.0])
    ok = np.ones(len(z), bool)
    for _ in range(3):
        for _ in range(15):
            r = z - (p[0] + p[1] * x + p[2] * y)
            wgt = np.where(ok, 1.0 / np.maximum(np.abs(r), 0.5), 0.0)
            A = np.stack([np.ones_like(x), x, y], axis=1) * np.sqrt(wgt)[:, None]
            reg = np.diag([0.0, 1.0, 1.0]) * PESO_INCLINACAO_MM * max(ok.sum(), 1) / 50.0
            p = np.linalg.solve(A.T @ A + reg, A.T @ (z * np.sqrt(wgt)))
        r = z - (p[0] + p[1] * x + p[2] * y)
        novo = ok & (r <= APICAL_MAX_MM)  # pontos apicais ao plano a no máximo 20 mm
        if novo.sum() < 6 or np.array_equal(novo, ok):
            break
        ok = novo
    return p


def _z_plano(p, eli: Elipsoide, pts: np.ndarray) -> np.ndarray:
    """Distância (mm, positiva = apical) de pontos ao plano, ao longo do eixo longo."""
    d = pts - eli.centro
    return d @ eli.longo - (p[0] + p[1] * (d @ eli.lateral) + p[2] * (d @ eli.anterior))


def _componentes_grade(m: np.ndarray) -> np.ndarray:
    rot = np.where(m, np.arange(1, m.size + 1).reshape(m.shape), 0)
    for _ in range(m.size):
        novo = rot.copy()
        for viz in (np.roll(rot, 1, 1), np.roll(rot, -1, 1), _deslocar(rot, 1, 0), _deslocar(rot, -1, 0)):
            novo = np.where(m & (viz > 0) & (viz < novo), viz, novo)
        if np.array_equal(novo, rot):
            break
        rot = novo
    return rot


def _area_celulas(P: np.ndarray) -> np.ndarray:
    dt = np.gradient(P, axis=0)
    dp = (np.roll(P, -1, 1) - np.roll(P, 1, 1)) / 2.0
    return np.linalg.norm(np.cross(dt, dp), axis=-1)


def _valva(P_ed: np.ndarray, contagens: np.ndarray, eli: Elipsoide):
    """Plano valvar na diástole final e os índices da borda (passo 5)."""
    area = _area_celulas(P_ed)
    total = area.sum()
    c = contagens / max(float(np.nanmax(contagens)), 1e-9)
    linhas = np.repeat(np.arange(N_POLAR)[:, None], N_AZIMUTE, axis=1)
    lim = LIMIAR_VALVA
    while lim <= 0.751:
        abaixo = c < lim
        rot = _componentes_grade(abaixo)
        basais = [i for i in np.unique(rot[rot > 0]) if linhas[rot == i].mean() >= N_POLAR / 2]
        if basais:
            alvo = max(basais, key=lambda i: (area[rot == i].sum(), linhas[rot == i].mean()))
            regiao = rot == alvo
            fora = ~regiao
            borda = regiao & (np.roll(fora, 1, 1) | np.roll(fora, -1, 1) | _deslocar(fora, 1, 0, False) | _deslocar(fora, -1, 0, False))
            if borda.sum() >= 6:
                p = _plano(P_ed[borda], eli)
                zb = _z_plano(p, eli, P_ed)
                if area[regiao & (zb < 0)].sum() >= AREA_MINIMA_VALVA * total:
                    return p, borda, lim
        lim += 0.05
    z = (P_ed - eli.centro) @ eli.longo
    return np.array([float(np.percentile(z, 10)), 0.0, 0.0]), np.zeros(P_ed.shape[:2], bool), None


# ------------------------------------------------ gaussiana assimétrica (passo 6)
def _gaussiana_assimetrica(perf: np.ndarray, x: np.ndarray, peso: np.ndarray | None = None):
    """y = B + A exp(−(x−μ)²/2σ²), σ = σ_in (x < μ) ou σ_out (x ≥ μ), por Levenberg-Marquardt vetorizado.

    ``peso`` (0 ou 1 por ponto) tira do ajuste a parte do perfil que passa do eixo longo (parede oposta).
    """
    n = perf.shape[0]
    peso = np.ones_like(perf) if peso is None else peso.astype(float)
    perf = perf * peso
    primeiro = np.argmax(peso > 0, axis=1)
    B = np.maximum(np.minimum(perf[np.arange(n), primeiro], perf[:, -1]), 0.0)
    k = np.argmax(perf, axis=1)
    th = np.stack([np.maximum(perf[np.arange(n), k] - B, 1e-6), x[k].astype(float), np.full(n, 6.0), np.full(n, 6.0), B], 1)
    lam = np.full(n, 1e-2)

    def modelo(t):
        Aa, m, s1, s2, b = t.T
        d = x[None, :] - m[:, None]
        s = np.where(d < 0, s1[:, None], s2[:, None])
        e = np.exp(-(d**2) / (2 * s**2))
        f = b[:, None] + Aa[:, None] * e
        J = np.stack([e, Aa[:, None] * e * d / s**2,
                      np.where(d < 0, Aa[:, None] * e * d**2 / s**3, 0.0),
                      np.where(d >= 0, Aa[:, None] * e * d**2 / s**3, 0.0),
                      np.ones_like(e)], -1)
        return f * peso, J * peso[..., None]

    f, J = modelo(th)
    erro = ((perf - f) ** 2).sum(1)
    for _ in range(30):
        JtJ = np.einsum("npi,npj->nij", J, J)
        g = np.einsum("npi,np->ni", J, perf - f)
        diag = np.einsum("nii->ni", JtJ)
        Dm = JtJ + lam[:, None, None] * (diag[:, :, None] * np.eye(5)[None] + 1e-9 * np.eye(5)[None])
        try:
            delta = np.linalg.solve(Dm, g[..., None])[..., 0]
        except np.linalg.LinAlgError:
            break
        novo = th + delta
        novo[:, 0] = np.maximum(novo[:, 0], 1e-6)
        novo[:, 1] = np.clip(novo[:, 1], x[0], x[-1])
        novo[:, 2:4] = np.clip(novo[:, 2:4], 1.0, 25.0)
        novo[:, 4] = np.maximum(novo[:, 4], 0.0)
        f2, J2 = modelo(novo)
        e2 = ((perf - f2) ** 2).sum(1)
        melhor = e2 < erro
        th = np.where(melhor[:, None], novo, th)
        f = np.where(melhor[:, None], f2, f)
        J = np.where(melhor[:, None, None], J2, J)
        erro = np.where(melhor, e2, erro)
        lam = np.where(melhor, lam * 0.3, lam * 10.0)
    return th  # A, μ, σ_in, σ_out, B


def _substituir_invalidos(v: np.ndarray, invalido: np.ndarray) -> np.ndarray:
    """Valores inválidos recebem a mediana dos 4 vizinhos (minimiza a soma das diferenças absolutas), iterado."""
    if np.all(invalido):
        return np.full_like(v, 6.0)
    out = np.where(invalido, np.nan, v)
    for _ in range(30):
        viz = _mediana_vizinhos(out)
        novo = np.where(invalido, viz, out)
        if np.array_equal(np.isfinite(novo), np.isfinite(out)) and np.allclose(np.nan_to_num(novo), np.nan_to_num(out), atol=1e-3):
            out = novo
            break
        out = novo
    return np.where(np.isfinite(out), out, float(np.median(v[~invalido])))


def paineis_contorno(res: "ResultadoGated", intervalo: int) -> list[tuple[str, np.ndarray, np.ndarray, np.ndarray]]:
    """Planos dos 5 cortes de conferência (Germano 1995, figura 5): eixo curto apical, médio e basal, eixo longo
    vertical e horizontal, no quadro do elipsoide. Cada item: (nome, centro, direção da coluna →, direção da linha ↑).

    Orientação de Cerqueira 2002: eixo curto com anterior em cima e lateral à direita; vertical com o ápice à
    direita e anterior em cima; horizontal com o ápice em cima e lateral à direita.
    """
    eli = res.elipsoide
    en = res.malhas_mm[res.ed][0]
    ponta = en[0].mean(axis=0)
    base = en[-1].mean(axis=0)
    comp = float((ponta - base) @ eli.longo)
    meio = base + 0.5 * comp * eli.longo
    sa = [(nome, base + f * comp * eli.longo, eli.lateral, eli.anterior) for nome, f in (("apical", 0.75), ("médio", 0.5), ("basal", 0.25))]
    return sa + [("vertical", meio, eli.longo, eli.anterior), ("horizontal", meio, eli.lateral, eli.longo)]


def intersecao_malha(M: np.ndarray, centro: np.ndarray, normal: np.ndarray) -> np.ndarray:
    """Segmentos (n, 2, 3) onde a malha (linhas, azimute, 3), fechada no azimute, corta o plano."""
    j2 = np.roll(np.arange(M.shape[1]), -1)
    a, b, c, d = M[:-1], M[1:], M[1:, j2], M[:-1, j2]
    tris = np.concatenate([np.stack([a, b, c], -2).reshape(-1, 3, 3), np.stack([a, c, d], -2).reshape(-1, 3, 3)])
    s = (tris - centro) @ normal  # (n, 3)
    segs = []
    pos = s > 0
    corta = pos.any(1) & (~pos).any(1)
    for tri, sd in zip(tris[corta], s[corta]):
        pts = []
        for i, k in ((0, 1), (1, 2), (2, 0)):
            if (sd[i] > 0) != (sd[k] > 0):
                t = sd[i] / (sd[i] - sd[k])
                pts.append(tri[i] + t * (tri[k] - tri[i]))
        if len(pts) == 2:
            segs.append(pts)
    return np.array(segs).reshape(-1, 2, 3)


def _normais_superficie(P: np.ndarray, nrm_ref: np.ndarray) -> np.ndarray:
    dt = np.gradient(P, axis=0)
    dp = (np.roll(P, -1, 1) - np.roll(P, 1, 1)) / 2.0
    n = np.cross(dt, dp)
    n /= np.maximum(np.linalg.norm(n, axis=-1, keepdims=True), 1e-9)
    n = np.where((np.sum(n * nrm_ref, -1) < 0)[..., None], -n, n)
    n = n + nrm_ref  # média com a normal do elipsoide (estabilidade)
    return n / np.maximum(np.linalg.norm(n, axis=-1, keepdims=True), 1e-9)


# ------------------------------------------------------------ malha e volume
def _malha_cortada(S: np.ndarray, p, eli: Elipsoide, miocardio: np.ndarray, n_linhas: int = N_LINHAS) -> np.ndarray:
    """Superfície (polar, azimute, 3) cortada no plano valvar e reamostrada em ``n_linhas`` por azimute, do ápice ao plano."""
    out = np.zeros((n_linhas, N_AZIMUTE, 3))
    for j in range(N_AZIMUTE):
        col = S[:, j]
        z = _z_plano(p, eli, col)
        cruz = np.nonzero((z[:-1] >= 0) & (z[1:] < 0))[0]
        if cruz.size:
            k = int(cruz[0])
            t = z[k] / (z[k] - z[k + 1])
            poli = np.vstack([col[: k + 1], col[k] + t * (col[k + 1] - col[k])])
        else:
            ult = np.nonzero(miocardio[:, j])[0]
            poli = col[: (int(ult[-1]) + 1 if ult.size else len(col))]
            if len(poli) < 2:
                poli = col[:2]
        s = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(poli, axis=0), axis=1))])
        alvo = np.linspace(0.0, s[-1], n_linhas)
        for d in range(3):
            out[:, j, d] = np.interp(alvo, s, poli[:, d])
    return out


def _volume_fechado(M: np.ndarray) -> float:
    """Volume (mL) da malha (linhas do ápice ao plano, azimute), fechada por uma ponta e por uma tampa no plano."""
    L, A = M.shape[:2]
    ponta = M[0].mean(axis=0)
    tampa = M[-1].mean(axis=0)
    j2 = (np.arange(A) + 1) % A
    tri = [np.stack([np.broadcast_to(ponta, (A, 3)), M[0], M[0, j2]], 1)]
    for i in range(L - 1):
        tri.append(np.stack([M[i], M[i + 1], M[i + 1, j2]], 1))
        tri.append(np.stack([M[i], M[i + 1, j2], M[i, j2]], 1))
    tri.append(np.stack([M[-1], np.broadcast_to(tampa, (A, 3)), M[-1, j2]], 1))
    T = np.concatenate(tri)
    ref = M.reshape(-1, 3).mean(axis=0)
    v = np.einsum("ij,ij->i", T[:, 0] - ref, np.cross(T[:, 1] - ref, T[:, 2] - ref)) / 6.0
    return float(abs(v.sum()) / 1000.0)


# --------------------------------------------------------------- resultado
@dataclass
class Superficies:
    """Superfícies de um intervalo, em coordenadas do VE (mm): (linhas do ápice ao plano, azimute, 3)."""

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
    limiar_valva: float | None = None
    #: Malhas em mm do paciente (endo, epi) por intervalo e o elipsoide de amostragem: contornos sobre os cortes.
    malhas_mm: list = field(default_factory=list, repr=False)
    elipsoide: "Elipsoide | None" = field(default=None, repr=False)

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
        r = lambda x: np.round(x, 1).tolist()  # noqa: E731
        return {
            "linhas": N_LINHAS,
            "azimutes": N_AZIMUTE,
            "endo": [r(s.endo) for s in self.superficies],
            "epi_ed": r(self.superficies[self.ed].epi),
            "ed": self.ed,
            "es": self.es,
            "volumes_ml": [round(v, 2) for v in self.volumes_ml],
        }


def _mapa(colunas: np.ndarray) -> MapaPolar:
    """Mapa polar a partir de valores (linhas do ápice ao plano, azimute)."""
    az = (np.arange(N_AZIMUTE) + 0.5) * (360.0 / N_AZIMUTE)
    return MapaPolar(parede=colunas[N_APICE:], apice=colunas[:N_APICE], maximo=1.0, r_c_mm=0.0, rho_apice=N_APICE / N_LINHAS, azimutes=az)


def _reamostrar_colunas(valores: np.ndarray, S: np.ndarray, miocardio: np.ndarray) -> np.ndarray:
    """Valores por normal (polar, azimute) levados às linhas do ápice ao plano, por fração do comprimento da coluna."""
    out = np.zeros((N_LINHAS, N_AZIMUTE))
    for j in range(N_AZIMUTE):
        idx = np.nonzero(miocardio[:, j])[0]
        if idx.size == 0:
            continue
        if idx.size == 1:
            out[:, j] = valores[idx[0], j]
            continue
        s = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(S[idx, j], axis=0), axis=1))])
        out[:, j] = np.interp(np.linspace(0.0, s[-1], N_LINHAS), s, valores[idx, j])
    return out


def _local(eli: Elipsoide, ref: np.ndarray, pts: np.ndarray) -> np.ndarray:
    """Coordenadas do VE: x lateral, y anterior, z do centro do plano valvar (diástole) para o ápice."""
    d = pts - ref
    return np.stack([d @ eli.lateral, d @ eli.anterior, d @ eli.longo], axis=-1)


def _preparar(soma: Volume, eixo: Eixo):
    """Passos 1 a 3 na imagem não sincronizada: máscara e elipsoide final (base de amostragem)."""
    mascara, cubo, avisos = segmentar(soma, eixo)
    eli0 = _superficie_inicial(soma, mascara, cubo, eixo)
    p0, n0 = eli0.superficie()
    pos, mag = _candidatos(soma, p0, n0)
    x = _escolher(pos, mag)
    eli = _elipsoide((p0 + n0 * x[..., None]).reshape(-1, 3), eli0.longo, eixo)
    return eli, avisos


def _meio_por_intervalo(vols: list[Volume], soma: Volume, eli: Elipsoide):
    """Passo 4: posição do meio (mm ao longo da normal do elipsoide) em cada intervalo, com continuidade temporal."""
    p, nrm = eli.superficie()
    pos_s, mag_s = _candidatos(soma, p, nrm)
    x_soma = _escolher(pos_s, mag_s)
    cands = [_candidatos(v, p, nrm) for v in vols]
    xs = [_escolher(pc, mc, x_soma, 1.0) for pc, mc in cands]
    for _ in range(2):
        xs = [_escolher(pc, mc, 0.5 * (xs[t - 1] + xs[(t + 1) % len(xs)]), 1.0) for t, (pc, mc) in enumerate(cands)]
    return p, nrm, x_soma, xs


def _distancia_ao_eixo(P: np.ndarray, nm: np.ndarray, eixo_longo) -> np.ndarray:
    """Quanto se anda para dentro, ao longo de −normal, até o eixo longo (mm): a projeção radial do ponto."""
    c, a = eixo_longo
    d = P - c
    radial = d - (d @ a)[..., None] * a
    rho = np.linalg.norm(radial, axis=-1)
    cos = np.sum(nm * radial, axis=-1) / np.maximum(rho, 1e-9)
    return np.where(cos > 0.2, rho / np.maximum(cos, 0.2), MEIA_LARGURA_PERFIL_MM)


def _superficies_intervalo(vol: Volume, p, nrm, x, eixo_longo):
    """Meio, normal da superfície, σ interno e externo (gaussiana assimétrica) e pico de cada perfil."""
    P = p + nrm * x[..., None]
    nm = _normais_superficie(p + nrm * _suavizar_grade(x)[..., None], nrm)
    xp = np.arange(-MEIA_LARGURA_PERFIL_MM, MEIA_LARGURA_PERFIL_MM + 1e-9, 1.0)
    perf = _perfis_normais(vol, P, nm, xp).reshape(-1, len(xp))
    # [escolha] o lado interno do perfil para no eixo longo (centro da cavidade): na sístole, 20 mm para dentro
    # passariam da cavidade e pegariam a parede oposta
    ate_eixo = _distancia_ao_eixo(P, nm, eixo_longo).reshape(-1)
    peso = xp[None, :] >= -ate_eixo[:, None]
    th = _gaussiana_assimetrica(perf, xp, peso)
    forma = P.shape[:2]
    pico = perf.max(axis=1).reshape(forma)
    # o endocárdio não passa do eixo longo
    si = np.minimum(th[:, 2].reshape(forma), np.maximum(ate_eixo.reshape(forma) - 1.0, 0.5) / FRACAO_SD)
    # Germano 1995: endo e epicárdio a uma fração de σ a partir da superfície mediomiocárdica (não do centro da gaussiana)
    return P, nm, si, th[:, 3].reshape(forma), pico


def _sigmas_validos(si, so, pico, miocardio):
    ref = float(np.max(pico[miocardio])) if miocardio.any() else float(np.max(pico))
    inval = (pico < PICO_VALIDO * ref) | ~miocardio
    return _substituir_invalidos(si, inval), _substituir_invalidos(so, inval)


def analisar_gated(volumes: list[Volume], totais, eixo: Eixo) -> ResultadoGated:
    """Método do QGS (Germano 1995) num gated: um volume reconstruído por intervalo."""
    if len(volumes) < 4:
        raise ValueError("O gated precisa de pelo menos 4 intervalos.")
    soma = _volume_soma(volumes)
    eli, avisos = _preparar(soma, eixo)
    p, nrm, _, xs = _meio_por_intervalo(volumes, soma, eli)
    n = len(volumes)
    quadros = [_superficies_intervalo(v, p, nrm, x, (eli.centro, eli.longo)) for v, x in zip(volumes, xs)]
    contagens = np.mean([q[4] for q in quadros], axis=0)  # contagem média de todos os intervalos

    def resolver(ed: int):
        P_ed = quadros[ed][0]
        plano_ed, borda, lim = _valva(P_ed, contagens, eli)
        miocardio = _z_plano(plano_ed, eli, P_ed) >= 0
        planos = [(_plano(q[0][borda], eli) if borda.sum() >= 6 else plano_ed) for q in quadros]
        planos[ed] = plano_ed
        dist = []
        for P, nm, si, so, pico in quadros:
            si2, so2 = _sigmas_validos(si, so, pico, miocardio)
            dist.append((P, nm, FRACAO_SD * si2, FRACAO_SD * so2))

        def calcular(t, lam):
            P, nm, di, do = dist[t]
            en = P - nm * (lam * di)[..., None]
            ep = P + nm * (lam * do)[..., None]
            M_en = _malha_cortada(en, planos[t], eli, miocardio)
            M_ep = _malha_cortada(ep, planos[t], eli, miocardio)
            return _volume_fechado(M_en), _volume_fechado(M_ep), M_en, M_ep, en, ep

        v_en, v_ep, *_ = calcular(ed, 1.0)
        massa = v_ep - v_en
        saida = []
        for t in range(n):
            lam = 1.0
            if t != ed:  # massa constante (Germano 1995)
                lo, hi = 0.2, 4.0
                for _ in range(16):
                    mid = 0.5 * (lo + hi)
                    a, b, *_ = calcular(t, mid)
                    lo, hi = (mid, hi) if b - a < massa else (lo, mid)
                lam = 0.5 * (lo + hi)
            saida.append(calcular(t, lam))
        return saida, planos, miocardio, massa, lim

    ed = 0
    res, planos, miocardio, massa, lim = resolver(ed)
    vols_ml = [r[0] for r in res]
    if int(np.argmax(vols_ml)) != ed:
        ed = int(np.argmax(vols_ml))
        res, planos, miocardio, massa, lim = resolver(ed)
        vols_ml = [r[0] for r in res]
    es = int(np.argmin(vols_ml))
    if lim is None:
        avisos.append("Plano valvar: não houve área basal abaixo do limiar; usado um plano perpendicular ao eixo. Confira os contornos.")
    if not min(ed, n - 1 - ed) <= 1:
        avisos.append(f"A diástole final caiu no intervalo {ed + 1} de {n}; o esperado é o primeiro ou o último. Confira o gatilho do ECG.")
    if not (0.2 * n <= es <= 0.7 * n):
        avisos.append(f"A sístole final caiu no intervalo {es + 1} de {n}; o esperado é perto de um terço a metade do ciclo. Confira o gatilho do ECG.")

    en_ed, ep_ed = res[ed][4], res[ed][5]
    en_es, ep_es = res[es][4], res[es][5]
    mot = -np.sum((en_es - en_ed) * quadros[ed][1], axis=-1)  # positivo = para dentro
    esp_rel = 100.0 * (np.linalg.norm(ep_es - en_es, axis=-1) / np.maximum(np.linalg.norm(ep_ed - en_ed, axis=-1), 1e-6) - 1.0)
    S_ed = quadros[ed][0]
    ref = res[ed][2][-1].mean(axis=0)  # centro da tampa do endocárdio na diástole
    sup = [Superficies(_local(eli, ref, r[2]), _local(eli, ref, r[3]), _local(eli, ref, _malha_cortada(q[0], planos[t], eli, miocardio)))
           for t, (r, q) in enumerate(zip(res, quadros))]
    ponta = eli.centro + float(eli.semi.max()) * eli.longo
    planos_mm = [[round(float(_z_plano(pl, eli, ponta[None])[0]), 2)] for pl in planos]
    return ResultadoGated(
        volumes_ml=[float(v) for v in vols_ml],
        ed=ed,
        es=es,
        vdf_ml=float(vols_ml[ed]),
        vsf_ml=float(vols_ml[es]),
        fe=float(100.0 * (vols_ml[ed] - vols_ml[es]) / max(vols_ml[ed], 1e-9)),
        superficies=sup,
        motilidade=_mapa(_reamostrar_colunas(mot, S_ed, miocardio)),
        espessamento=_mapa(_reamostrar_colunas(esp_rel, S_ed, miocardio)),
        planos_mm=planos_mm,
        massa_ml=float(massa),
        avisos=avisos,
        limiar_valva=lim,
        malhas_mm=[(r[2], r[3]) for r in res],
        elipsoide=eli,
    )


def volume_nao_sincronizado(vol: Volume, eixo: Eixo) -> float:
    """Volume endocárdico (mL) numa imagem não sincronizada (para a TID): passos 1 a 6, sem a massa constante."""
    eli, _ = _preparar(vol, eixo)
    p, nrm = eli.superficie()
    pos, mag = _candidatos(vol, p, nrm)
    P, nm, si, so, pico = _superficies_intervalo(vol, p, nrm, _escolher(pos, mag), (eli.centro, eli.longo))
    plano, _, _ = _valva(P, pico, eli)
    miocardio = _z_plano(plano, eli, P) >= 0
    si2, _ = _sigmas_validos(si, so, pico, miocardio)
    return _volume_fechado(_malha_cortada(P - nm * (FRACAO_SD * si2)[..., None], plano, eli, miocardio))


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
