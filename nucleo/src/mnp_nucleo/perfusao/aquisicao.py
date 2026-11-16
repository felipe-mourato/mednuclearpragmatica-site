"""Leitura das projeções de SPECT (DICOM NM) e geometria da aquisição.

O que se lê do cabeçalho (DICOM PS3.3, módulos NM Multi-frame, NM Detector,
NM TOMO Acquisition e NM Multi-gated Acquisition):

* vetores de quadro: EnergyWindowVector (0054,0010), DetectorVector
  (0054,0020), RotationVector (0054,0050), RRIntervalVector (0054,0060),
  TimeSlotVector (0054,0070) e AngularViewVector (0054,0090). Eles dizem,
  para cada quadro do arquivo, de que detector, vista angular e intervalo
  do ciclo cardíaco ele é;
* por detector (DetectorInformationSequence, 0054,0022): StartAngle
  (0054,0200), ImageOrientationPatient (0020,0037) e
  ImagePositionPatient (0020,0032);
* da rotação (RotationInformationSequence, 0054,0052): AngularStep
  (0018,1144), RotationDirection (0018,1140), ScanArc (0018,1143) e
  ActualFrameDuration (0018,1242);
* do gated, o que vier: BeatRejectionFlag (0018,1080), SkipBeats
  (0018,1086), HeartRate (0018,1088) e, na GatedInformationSequence
  (0054,0062) / DataInformationSequence (0054,0063): FrameTime
  (0018,1063), NominalInterval (0018,1062), LowRRValue (0018,1081),
  HighRRValue (0018,1082), IntervalsAcquired (0018,1083) e
  IntervalsRejected (0018,1084).

Ângulo do detector (DICOM, StartAngle): zero nas costas do paciente,
crescendo no sentido anti-horário visto dos pés (das costas para o lado
esquerdo). Assim: 0° posterior, 90° esquerda, 180° anterior, 270° direita.
Rotação horária ("CW") diminui o ângulo. Ângulo da vista v (1, 2, …) do
detector d::

    θ = StartAngle_d ∓ (v − 1) × AngularStep     (− para CW, + para CC)

Coordenadas do paciente usadas na ferramenta (mm): x para a esquerda (L),
y para trás (P), z para a cabeça (S), como no DICOM (LPS). Posição do
detector: p(θ) = (sen θ, cos θ). Direção em que cresce a coluna da
projeção: u(θ) = σ (−cos θ, sen θ), com σ = ±1 tirado do
ImageOrientationPatient do detector (σ = +1 se ausente, com aviso).
Linha da projeção: segue a coluna do ImageOrientationPatient (em geral
(0, 0, −1): a linha cresce para os pés); z da linha r = z₀ + r × Δ × c_z.

Dados do paciente (nome, nascimento, prontuário) não são lidos.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field

import numpy as np

from ..comum.dicom import ErroDicom, abrir_dataset, como_bytes, pixels_brutos

__all__ = ["Aquisicao", "ler_aquisicao", "TIPOS", "ROTULOS_TIPO", "adivinhar_tipo", "direcao_coluna"]

#: Tipos de aquisição que o usuário atribui a cada arquivo.
TIPOS = ("estresse", "repouso", "gated_estresse", "gated_repouso", "prona_estresse", "prona_repouso", "ignorar")
ROTULOS_TIPO = {
    "estresse": "Estresse",
    "repouso": "Repouso",
    "gated_estresse": "Gated do estresse",
    "gated_repouso": "Gated do repouso",
    "prona_estresse": "Prona do estresse",
    "prona_repouso": "Prona do repouso",
    "ignorar": "Não usar",
}


def direcao_coluna(theta_graus, sigma: float = 1.0) -> np.ndarray:
    """u(θ) = σ (−cos θ, sen θ): direção (x, y) em que cresce a coluna da projeção."""
    t = np.deg2rad(np.asarray(theta_graus, dtype=np.float64))
    return sigma * np.stack([-np.cos(t), np.sin(t)], axis=-1)


@dataclass
class Aquisicao:
    """Projeções de uma aquisição tomográfica, já organizadas por ângulo.

    ``projecoes``: (intervalos, ângulos, linhas, colunas), float64 com rescale;
    intervalos = 1 sem gated. ``angulos``: θ de cada projeção (graus), em
    ordem crescente. ``u``: (ângulos, 2), direção da coluna em (x, y).
    """

    projecoes: np.ndarray
    angulos: np.ndarray
    u: np.ndarray
    pixel_mm: float
    linha_mm: float
    z0_mm: float
    passo_z: float  # +1: a linha cresce para a cabeça; −1: para os pés
    deslocamento_centro_mm: float
    tipo_imagem: str
    gated: bool
    descricao: str
    posicao_paciente: str
    sha256: str
    sintaxe: str
    info: dict = field(default_factory=dict)
    info_gated: dict = field(default_factory=dict)
    avisos: list = field(default_factory=list)

    @property
    def n_intervalos(self) -> int:
        return int(self.projecoes.shape[0])

    @property
    def n_angulos(self) -> int:
        return int(self.projecoes.shape[1])

    @property
    def linhas(self) -> int:
        return int(self.projecoes.shape[2])

    @property
    def colunas(self) -> int:
        return int(self.projecoes.shape[3])

    def somadas(self) -> np.ndarray:
        """Projeções somando os intervalos do gated: (ângulos, linhas, colunas)."""
        return self.projecoes.sum(axis=0)

    def z_linhas(self) -> np.ndarray:
        """z (mm, para a cabeça) do centro de cada linha da projeção (= cada corte transaxial)."""
        return self.z0_mm + self.passo_z * self.linha_mm * np.arange(self.linhas)


def _texto(ds, nome, padrao=""):
    v = ds.get(nome, None)
    if v is None:
        return padrao
    if isinstance(v, (list, tuple)) or v.__class__.__name__ == "MultiValue":
        return "\\".join(str(x) for x in v)
    return str(v).strip()


def _num(item, nome):
    v = item.get(nome, None) if item is not None else None
    if v is None or str(v).strip() == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _vetor(ds, nome, n):
    v = ds.get(nome, None)
    if v is None:
        return None
    arr = np.asarray([int(x) for x in (v if hasattr(v, "__len__") else [v])], dtype=np.int64)
    if arr.size != n:
        raise ErroDicom(f"{nome} tem {arr.size} valores, mas o arquivo tem {n} quadros.")
    return arr


def adivinhar_tipo(descricao: str, gated: bool, posicao: str) -> str:
    """Sugere o tipo pela descrição da série, pelo Image Type e pela posição do paciente.

    "rest", "repouso", "rep" → repouso; "stress", "estresse", "esf" → estresse.
    Posição HFP/FFP (decúbito ventral) → prona. Sem pista, estresse. O
    usuário sempre confirma.
    """
    t = (descricao or "").lower()
    repouso = re.search(r"rest|repous|\brep\b|basal", t) is not None
    base = "repouso" if repouso else "estresse"
    if (posicao or "").upper() in ("HFP", "FFP") or re.search(r"pron", t):
        return f"prona_{base}"
    return f"gated_{base}" if gated else base


def ler_aquisicao(dados) -> Aquisicao:
    """Lê um DICOM NM de projeções tomográficas (TOMO ou GATED TOMO).

    Raises
    ------
    ErroDicom
        Arquivo que não é de projeções (ex.: já reconstruído), vetores de
        quadro ausentes ou geometria incompleta. Mensagens para o usuário.
    """
    dados = como_bytes(dados)
    ds, sintaxe = abrir_dataset(dados)
    tipo_imagem = [str(x).upper() for x in (ds.get("ImageType", None) or [])]
    tipo3 = tipo_imagem[2] if len(tipo_imagem) > 2 else ""
    if tipo3 in ("RECON TOMO", "RECON GATED TOMO"):
        raise ErroDicom(
            "Este arquivo já vem reconstruído (cortes). A ferramenta reconstrói a partir das projeções: "
            "exporte as projeções brutas (Image Type TOMO ou GATED TOMO)."
        )
    if tipo3 and tipo3 not in ("TOMO", "GATED TOMO"):
        raise ErroDicom(
            f"Este arquivo não é de projeções tomográficas (Image Type: {tipo3}). Exporte as projeções "
            "brutas do SPECT (TOMO ou GATED TOMO)."
        )
    if str(ds.get("SamplesPerPixel", 1) or 1) != "1":
        raise ErroDicom("Imagem colorida (provavelmente uma captura de tela). Use o DICOM original da gama-câmara.")
    if "PixelData" not in ds:
        raise ErroDicom("DICOM sem dados de pixel.")
    brutos = pixels_brutos(ds)
    n_quadros, linhas, colunas = brutos.shape
    inclinacao = _num(ds, "RescaleSlope") or 1.0
    intercepto = _num(ds, "RescaleIntercept") or 0.0
    quadros = brutos.astype(np.float64) * inclinacao + intercepto

    detector = _vetor(ds, "DetectorVector", n_quadros)
    vista = _vetor(ds, "AngularViewVector", n_quadros)
    if detector is None or vista is None:
        raise ErroDicom(
            "Faltam no DICOM os vetores que dizem o detector e o ângulo de cada quadro (DetectorVector e "
            "AngularViewVector). Exporte as projeções originais da gama-câmara."
        )
    janela = _vetor(ds, "EnergyWindowVector", n_quadros)
    rotacao = _vetor(ds, "RotationVector", n_quadros)
    intervalo = _vetor(ds, "TimeSlotVector", n_quadros)
    rr = _vetor(ds, "RRIntervalVector", n_quadros)
    avisos: list[str] = []
    selecao = np.ones(n_quadros, dtype=bool)
    if janela is not None and len(set(janela.tolist())) > 1:
        selecao &= janela == 1
        avisos.append("O arquivo tem mais de uma janela de energia: foi usada só a janela 1 (fotopico).")
    if rotacao is not None and len(set(rotacao.tolist())) > 1:
        selecao &= rotacao == 1
        avisos.append("O arquivo tem mais de uma rotação: foi usada só a primeira.")
    if rr is not None and len(set(rr.tolist())) > 1:
        selecao &= rr == 1
        avisos.append("O arquivo tem mais de uma janela R-R: foi usada só a primeira.")
    gated = tipo3 == "GATED TOMO" or (intervalo is not None and len(set(intervalo.tolist())) > 1)
    if intervalo is None:
        intervalo = np.ones(n_quadros, dtype=np.int64)

    rot_seq = ds.get("RotationInformationSequence", None)
    rot = rot_seq[0] if rot_seq else None
    passo = _num(rot, "AngularStep")
    if not passo:
        raise ErroDicom("Falta no DICOM o passo angular (AngularStep, na RotationInformationSequence).")
    sentido_txt = str(rot.get("RotationDirection", "CW") if rot is not None else "CW").strip().upper()
    sentido = -1.0 if sentido_txt != "CC" else 1.0
    det_seq = list(ds.get("DetectorInformationSequence", None) or [])
    n_det = int(detector.max())
    inicio = {}
    sigma = {}
    z0 = {}
    passo_z = {}
    for d in range(1, n_det + 1):
        item = det_seq[d - 1] if d - 1 < len(det_seq) else None
        a0 = _num(item, "StartAngle")
        if a0 is None:
            a0 = _num(rot, "StartAngle")
            if d > 1 or a0 is None:
                raise ErroDicom(f"Falta o ângulo inicial (StartAngle) do detector {d}.")
        inicio[d] = a0
        iop = item.get("ImageOrientationPatient", None) if item is not None else None
        ipp = item.get("ImagePositionPatient", None) if item is not None else None
        if iop is not None and len(iop) == 6:
            linha_vet = np.array([float(iop[0]), float(iop[1])])
            col_z = float(iop[5])
            esperado = direcao_coluna(a0)
            produto = float(linha_vet @ esperado)
            if abs(produto) < 0.7:
                avisos.append(
                    f"A orientação do detector {d} não bate com o ângulo inicial; a lateralidade foi deduzida "
                    "do ângulo. Confira se o coração aparece à direita da imagem transaxial."
                )
                sigma[d] = 1.0
            else:
                sigma[d] = 1.0 if produto > 0 else -1.0
            passo_z[d] = 1.0 if col_z > 0 else -1.0
        else:
            sigma[d] = 1.0
            passo_z[d] = -1.0
            avisos.append(
                "O DICOM não traz a orientação dos detectores: a lateralidade segue a convenção mais comum. "
                "Confira se o coração aparece à direita da imagem transaxial (lado esquerdo do paciente)."
            )
        z0[d] = float(ipp[2]) if ipp is not None and len(ipp) == 3 else 0.0
    if len(set(sigma.values())) > 1:
        avisos.append("Os detectores têm orientações de imagem diferentes: confira a reconstrução.")

    ang_quadro = np.array([inicio[int(d)] + sentido * (int(v) - 1) * passo for d, v in zip(detector, vista)]) % 360.0
    sig_quadro = np.array([sigma[int(d)] for d in detector])

    # Organiza em (intervalo, ângulo): um quadro por par.
    intervalos = sorted(set(intervalo[selecao].tolist()))
    chaves = sorted({(round(float(a), 4), float(s)) for a, s in zip(ang_quadro[selecao], sig_quadro[selecao])})
    angulos = np.array([c[0] for c in chaves])
    sig_ang = np.array([c[1] for c in chaves])
    proj = np.zeros((len(intervalos), len(angulos), linhas, colunas))
    preenchido = np.zeros((len(intervalos), len(angulos)), dtype=bool)
    idx_ang = {c: i for i, c in enumerate(chaves)}
    idx_int = {g: i for i, g in enumerate(intervalos)}
    for q in np.nonzero(selecao)[0]:
        i = idx_int[int(intervalo[q])]
        j = idx_ang[(round(float(ang_quadro[q]), 4), float(sig_quadro[q]))]
        if preenchido[i, j]:
            raise ErroDicom("Dois quadros com o mesmo ângulo e intervalo: o arquivo tem projeções repetidas.")
        proj[i, j] = quadros[q]
        preenchido[i, j] = True
    if not preenchido.all():
        raise ErroDicom("Faltam projeções para alguns ângulos ou intervalos do gated.")
    if len(angulos) < 16:
        raise ErroDicom(f"Só {len(angulos)} projeções: poucas para reconstruir (são necessárias pelo menos 16).")

    espac = ds.get("PixelSpacing", None)
    if espac is None or len(espac) != 2:
        raise ErroDicom("Falta o tamanho do pixel (PixelSpacing) no DICOM.")
    linha_mm, pixel_mm = float(espac[0]), float(espac[1])
    det1 = det_seq[0] if det_seq else None
    cor = _num(det1, "CenterOfRotationOffset") or 0.0

    arco = float(np.ptp(angulos) + passo)
    if arco < 170:
        avisos.append(f"Arco total de {arco:.0f}°: menor que 180°, a reconstrução pode ter distorções.")

    info = {
        "fabricante": _texto(ds, "Manufacturer"),
        "modelo": _texto(ds, "ManufacturerModelName"),
        "descricao": _texto(ds, "SeriesDescription"),
        "tipo_imagem": tipo3 or "não informado",
        "detectores": n_det,
        "projecoes": int(len(angulos)),
        "passo_graus": float(passo),
        "arco_graus": arco,
        "angulo_inicial": float(angulos[0]),
        "angulo_final": float(angulos[-1]),
        "sentido": "horário" if sentido < 0 else "anti-horário",
        "matriz": f"{colunas}×{linhas}",
        "pixel_mm": pixel_mm,
        "duracao_vista_s": (_num(rot, "ActualFrameDuration") or 0.0) / 1000.0 or None,
        "orbita": _texto(ds, "TypeOfDetectorMotion"),
        "posicao": _texto(ds, "PatientPosition"),
        "colimador": _texto(det1, "CollimatorType") if det1 is not None else "",
        "janela_energia": _janela_energia(ds),
        "radiofarmaco": _radiofarmaco(ds),
        "sintaxe": sintaxe,
    }
    info_gated = _info_gated(ds) if gated else {}
    if gated:
        info_gated["intervalos"] = len(intervalos)

    sig = float(sig_ang[0])
    return Aquisicao(
        projecoes=proj,
        angulos=angulos,
        u=direcao_coluna(angulos, 1.0) * sig_ang[:, None],
        pixel_mm=pixel_mm,
        linha_mm=linha_mm,
        z0_mm=z0[1] if 1 in z0 else 0.0,
        passo_z=passo_z.get(1, -1.0),
        deslocamento_centro_mm=float(cor),
        tipo_imagem=tipo3 or "TOMO",
        gated=bool(gated),
        descricao=_texto(ds, "SeriesDescription"),
        posicao_paciente=_texto(ds, "PatientPosition"),
        sha256=hashlib.sha256(dados).hexdigest(),
        sintaxe=sintaxe,
        info=info | {"sigma": sig},
        info_gated=info_gated,
        avisos=avisos,
    )


def _janela_energia(ds) -> str:
    seq = ds.get("EnergyWindowInformationSequence", None)
    if not seq:
        return ""
    partes = []
    for item in seq:
        nome = str(item.get("EnergyWindowName", "") or "").strip()
        faixa = item.get("EnergyWindowRangeSequence", None)
        if faixa:
            lo, hi = _num(faixa[0], "EnergyWindowLowerLimit"), _num(faixa[0], "EnergyWindowUpperLimit")
            if lo and hi:
                nome = (nome + " " if nome else "") + f"{lo:.0f}–{hi:.0f} keV"
        if nome:
            partes.append(nome)
    return "; ".join(partes)


def _radiofarmaco(ds) -> str:
    seq = ds.get("RadiopharmaceuticalInformationSequence", None)
    if not seq:
        return ""
    return str(seq[0].get("Radiopharmaceutical", "") or "").strip()


def _info_gated(ds) -> dict:
    """Campos do gated que o fabricante tiver preenchido (os ausentes ficam de fora)."""
    saida: dict = {}
    for nome, chave in (("BeatRejectionFlag", "rejeicao_batimentos"), ("SkipBeats", "batimentos_pulados"), ("HeartRate", "frequencia_cardiaca"),
                        ("PVCRejection", "rejeicao_extrassistoles"), ("CardiacFramingType", "tipo_divisao")):
        v = ds.get(nome, None)
        if v is not None and str(v).strip():
            saida[chave] = str(v).strip()
    seq = ds.get("GatedInformationSequence", None)
    if seq:
        g = seq[0]
        for nome, chave in (("TriggerTime", "tempo_disparo_ms"), ("CardiacFramingType", "tipo_divisao")):
            v = g.get(nome, None)
            if v is not None and str(v).strip():
                saida[chave] = str(v).strip()
        dados = g.get("DataInformationSequence", None)
        if dados:
            d = dados[0]
            for nome, chave in (
                ("FrameTime", "duracao_intervalo_ms"),
                ("NominalInterval", "intervalo_rr_nominal_ms"),
                ("LowRRValue", "rr_minimo_ms"),
                ("HighRRValue", "rr_maximo_ms"),
                ("IntervalsAcquired", "batimentos_aceitos"),
                ("IntervalsRejected", "batimentos_rejeitados"),
            ):
                v = d.get(nome, None)
                if v is not None and str(v).strip():
                    saida[chave] = str(v).strip()
    for chave in ("batimentos_aceitos", "batimentos_rejeitados"):
        if chave in saida:
            try:
                saida[chave] = int(float(saida[chave]))
            except ValueError:
                pass
    a, r = saida.get("batimentos_aceitos"), saida.get("batimentos_rejeitados")
    if isinstance(a, int) and isinstance(r, int) and a + r > 0:
        saida["percentual_rejeitado"] = round(100.0 * r / (a + r), 1)
    if not any(k in saida for k in ("batimentos_aceitos", "batimentos_rejeitados", "intervalo_rr_nominal_ms", "frequencia_cardiaca")):
        saida["observacao"] = "O fabricante não gravou no DICOM os batimentos aceitos e rejeitados."
    return saida
