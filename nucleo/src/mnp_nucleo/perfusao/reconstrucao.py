"""Reconstrução tomográfica por retroprojeção filtrada (FBP), com filtro de Butterworth.

Sequência (Germano, J Nucl Med 2001;42:1499-507): as projeções passam por
um filtro passa-baixa de Butterworth (2D, na própria projeção, antes da
reconstrução) e depois pela retroprojeção filtrada com o filtro rampa.

Butterworth (Germano 2001; Lyra e Ploussi 2011, eq. 2)::

    B(f) = 1 / (1 + (f / fc)^(2n))

f = frequência espacial radial (ciclos/pixel), fc = frequência de corte e
n = ordem. Amplitude 1 nas baixas frequências, 0,5 em f = fc e 0 nas
altas. O corte é informado em fração da frequência de Nyquist (0 a 1); em
ciclos/pixel, fc = fração × 0,5; em ciclos/cm, fc = fração × 0,5 ÷
(tamanho do pixel em cm). As duas convenções coexistem nas estações
(Germano 2001), por isso a ferramenta mostra as três.

Rampa: núcleo de Ram-Lak discretizado no espaço (Kak e Slaney, Principles
of Computerized Tomographic Imaging, 1988, eq. 61 do cap. 3): h(0) = 1/4,
h(n ímpar) = −1/(π n)², h(n par) = 0; aplicado por FFT com o dobro de
amostras (sem dobra circular).

Retroprojeção: para o voxel (x, y), a coordenada na projeção é
t = x·u_x + y·u_y (mm), coluna = t/Δ + c + deslocamento do centro de
rotação, com interpolação linear; soma em todos os ângulos × π/N.
Nenhuma correção de atenuação, espalhamento ou resolução (como na FBP
clássica). Valores negativos são mantidos no volume e cortados só na
exibição e na amostragem.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .aquisicao import Aquisicao

__all__ = [
    "CORTE_PADRAO",
    "ORDEM_PADRAO",
    "Filtro",
    "butterworth",
    "filtrar_projecoes",
    "nucleo_rampa",
    "fbp",
    "Volume",
    "reconstruir",
]

#: Padrão inicial da tela: Butterworth de ordem 11 e corte de 0,45 da
#: frequência de Nyquist, melhor resultado para ⁹⁹ᵐTc num fantoma de VE
#: (Takavar et al. 2004, citado por Lyra e Ploussi 2011). O usuário ajusta.
CORTE_PADRAO = 0.45
ORDEM_PADRAO = 11


@dataclass(frozen=True)
class Filtro:
    corte_nyquist: float = CORTE_PADRAO
    ordem: int = ORDEM_PADRAO

    def validar(self) -> "Filtro":
        c, n = float(self.corte_nyquist), int(self.ordem)
        if not 0.05 <= c <= 1.0:
            raise ValueError("O corte do Butterworth deve ficar entre 0,05 e 1,0 da frequência de Nyquist.")
        if not 1 <= n <= 20:
            raise ValueError("A ordem do Butterworth deve ficar entre 1 e 20.")
        return Filtro(c, n)

    def ciclos_pixel(self) -> float:
        return self.corte_nyquist * 0.5

    def ciclos_cm(self, pixel_mm: float) -> float:
        return self.corte_nyquist * 0.5 / (pixel_mm / 10.0)


def butterworth(f, fc: float, ordem: int) -> np.ndarray:
    """B(f) = 1 / (1 + (f/fc)^(2n)), com f e fc na mesma unidade."""
    f = np.abs(np.asarray(f, dtype=np.float64))
    return 1.0 / (1.0 + (f / float(fc)) ** (2 * int(ordem)))


def filtrar_projecoes(projecoes: np.ndarray, filtro: Filtro) -> np.ndarray:
    """Butterworth 2D (radial) em cada projeção; forma (..., linhas, colunas) preservada.

    As bordas são completadas com espelhamento até o dobro do tamanho para
    não haver dobra circular; a soma de cada projeção é preservada
    (B(0) = 1).
    """
    p = np.asarray(projecoes, dtype=np.float64)
    linhas, colunas = p.shape[-2:]
    pl, pc = linhas, colunas
    estendido = np.pad(p, [(0, 0)] * (p.ndim - 2) + [(0, pl), (0, pc)], mode="symmetric")
    fy = np.fft.fftfreq(2 * linhas)[:, None]
    fx = np.fft.rfftfreq(2 * colunas)[None, :]
    h = butterworth(np.hypot(fy, fx), filtro.ciclos_pixel(), filtro.ordem)
    saida = np.fft.irfft2(np.fft.rfft2(estendido, axes=(-2, -1)) * h, s=(2 * linhas, 2 * colunas), axes=(-2, -1))
    return saida[..., :linhas, :colunas]


def nucleo_rampa(n_amostras: int) -> np.ndarray:
    """Resposta em frequência do Ram-Lak discretizado (comprimento ``n_amostras``, rfft)."""
    n = np.arange(-(n_amostras // 2), n_amostras // 2)
    h = np.zeros(n_amostras)
    h[n == 0] = 0.25
    impar = n % 2 == 1
    h[impar] = -1.0 / (np.pi * n[impar]) ** 2
    h = np.fft.ifftshift(h)
    return np.real(np.fft.rfft(h))


def fbp(projecoes: np.ndarray, u: np.ndarray, pixel_mm: float, deslocamento_centro_mm: float = 0.0, n: int | None = None) -> np.ndarray:
    """Retroprojeção filtrada (rampa) de todas as linhas de uma vez.

    ``projecoes``: (ângulos, linhas, colunas), já com o Butterworth.
    ``u``: (ângulos, 2), direção (x, y) em que cresce a coluna.
    Devolve o volume (linhas, n, n): corte = linha da projeção; dentro do
    corte, coluna j ↔ x = (j − c)Δ (para a esquerda do paciente) e linha i
    ↔ y = (i − c)Δ (para trás), c = (n − 1)/2: a orientação radiológica
    da tela, com o lado esquerdo do paciente à direita da imagem.
    """
    p = np.asarray(projecoes, dtype=np.float64)
    n_ang, linhas, colunas = p.shape
    n = int(n or colunas)
    tam = 1
    while tam < 2 * colunas:
        tam *= 2
    rampa = nucleo_rampa(tam)
    filtrado = np.fft.irfft(np.fft.rfft(p, tam, axis=-1) * rampa, tam, axis=-1)[..., :colunas]
    c = (n - 1) / 2.0
    cc = (colunas - 1) / 2.0 + deslocamento_centro_mm / pixel_mm
    eixo = (np.arange(n) - c)
    x = eixo[None, :]
    y = eixo[:, None]
    volume = np.zeros((linhas, n, n))
    for a in range(n_ang):
        t = x * u[a, 0] + y * u[a, 1] + cc
        i0 = np.floor(t).astype(np.int64)
        w = t - i0
        dentro0 = (i0 >= 0) & (i0 < colunas)
        dentro1 = (i0 + 1 >= 0) & (i0 + 1 < colunas)
        i0c = np.clip(i0, 0, colunas - 1)
        i1c = np.clip(i0 + 1, 0, colunas - 1)
        perfil = filtrado[a]  # (linhas, colunas)
        volume += perfil[:, i0c] * ((1.0 - w) * dentro0) + perfil[:, i1c] * (w * dentro1)
    return volume * (np.pi / n_ang)


@dataclass
class Volume:
    """Volume transaxial reconstruído.

    ``dados``: (cortes, n, n). Corte k ↔ z_k (mm, para a cabeça); voxel (k, i, j)
    ↔ (x, y, z) = ((j − c)Δ, (i − c)Δ, z_k). Δ = tamanho do pixel.
    """

    dados: np.ndarray
    pixel_mm: float
    z_mm: np.ndarray
    filtro: Filtro

    @property
    def n(self) -> int:
        return int(self.dados.shape[1])

    @property
    def n_cortes(self) -> int:
        return int(self.dados.shape[0])

    def para_indices(self, pontos_mm: np.ndarray) -> np.ndarray:
        """(..., 3) em mm (x, y, z) → (..., 3) em índices fracionários (k, i, j)."""
        p = np.asarray(pontos_mm, dtype=np.float64)
        c = (self.n - 1) / 2.0
        dz = self.z_mm[1] - self.z_mm[0] if self.n_cortes > 1 else -self.pixel_mm
        k = (p[..., 2] - self.z_mm[0]) / dz
        i = p[..., 1] / self.pixel_mm + c
        j = p[..., 0] / self.pixel_mm + c
        return np.stack([k, i, j], axis=-1)

    def para_mm(self, k, i, j) -> np.ndarray:
        c = (self.n - 1) / 2.0
        dz = self.z_mm[1] - self.z_mm[0] if self.n_cortes > 1 else -self.pixel_mm
        return np.array([(float(j) - c) * self.pixel_mm, (float(i) - c) * self.pixel_mm, self.z_mm[0] + float(k) * dz])

    def amostrar(self, pontos_mm: np.ndarray) -> np.ndarray:
        """Interpolação trilinear nos pontos (mm); fora do volume = 0; negativos cortados em 0."""
        idx = self.para_indices(pontos_mm)
        forma = idx.shape[:-1]
        idx = idx.reshape(-1, 3)
        v = np.clip(self.dados, 0.0, None)
        lim = np.array(v.shape) - 1
        base = np.floor(idx).astype(np.int64)
        frac = idx - base
        saida = np.zeros(idx.shape[0])
        for dk in (0, 1):
            for di in (0, 1):
                for dj in (0, 1):
                    k = base[:, 0] + dk
                    i = base[:, 1] + di
                    j = base[:, 2] + dj
                    ok = (k >= 0) & (k <= lim[0]) & (i >= 0) & (i <= lim[1]) & (j >= 0) & (j <= lim[2])
                    peso = (frac[:, 0] if dk else 1 - frac[:, 0]) * (frac[:, 1] if di else 1 - frac[:, 1]) * (frac[:, 2] if dj else 1 - frac[:, 2])
                    saida[ok] += peso[ok] * v[k[ok], i[ok], j[ok]]
        return saida.reshape(forma)


def reconstruir(aq: Aquisicao, filtro: Filtro, intervalo: int | None = None) -> Volume:
    """Reconstrói a aquisição (soma dos intervalos do gated, ou um intervalo)."""
    filtro = filtro.validar()
    proj = aq.somadas() if intervalo is None else aq.projecoes[int(intervalo)]
    filtradas = filtrar_projecoes(proj, filtro)
    dados = fbp(filtradas, aq.u, aq.pixel_mm, aq.deslocamento_centro_mm)
    return Volume(dados=dados, pixel_mm=aq.pixel_mm, z_mm=aq.z_linhas(), filtro=filtro)
