"""Escore automático de perfusão (guia) pelo banco de normalidade espanhol.

FONTE. Cuberas-Borrós G, Aguadé-Bruix S, Boronat-de Ferrater M, et al.
Normal myocardial perfusion SPECT database for the Spanish population.
Rev Esp Cardiol. 2010;63(8):934-42 (PDF enviado pelo Mourato em 17 nov
2026). Média e desvio-padrão da captação (% do máximo do mapa polar) nos
17 segmentos, por sexo, no estresse e no repouso: figuras 2 (mulheres) e
3 (homens), transcritas à mão e conferidas na imagem ampliada, inclusive
os rótulos de cabeça para baixo da metade inferior dos mapas.

Banco: 104 voluntários com probabilidade de doença coronariana < 5% (45
mulheres e 59 homens; idade média 42,5 e 36,9 anos); ⁹⁹ᵐTc-tetrofosmin,
protocolo curto estresse–repouso; órbita circular de 180°, modo passo a
passo, matriz 64 × 64, 30 ou 32 vistas; sem gated e sem correção de
atenuação; reconstrução OSEM e quantificação no 4DM-SPECT; cada mapa
polar normalizado a 100%.

MÉTODO [escolhas desta ferramenta, aprovadas pelo Mourato em 17 nov 2026]:
z = (captação do segmento − média do banco) ÷ DP do banco, com o sexo
escolhido na tela (a ferramenta não lê dados do paciente no DICOM).
Escore: 0 se z > −2; 1 se −3 < z ≤ −2; 2 se −4 < z ≤ −3; 3 se
−5 < z ≤ −4; 4 se z ≤ −5. O escore 1 começa em −2 DP para marcar as áreas
duvidosas (equivocal), como na escala visual; os demais são faixas de 1 DP.
Para comparação, os mapas de extensão costumam usar −2,5 DP como corte de
anormalidade. Não há correspondência
padronizada entre z e a escala visual 0–4.

LIMITAÇÃO, repetida na tela e no laudo: a captação desta ferramenta vem de
outra reconstrução (FBP com Butterworth), de outra amostragem do mapa
polar (perfil de contagem máxima) e de câmeras, radiofármaco e população
possivelmente diferentes; os segmentos basais dependem de onde a base do
eixo foi traçada. O escore automático é guia, não substitui a pontuação
visual e não foi validado nesta ferramenta.
"""

from __future__ import annotations

from .polar import SEGMENTOS

__all__ = ["BANCO_ESPANHOL", "LIMIARES_Z", "SEXOS", "escore_de_z", "escores_automaticos", "DESCRICAO_BANCO", "CITACAO_BANCO"]

SEXOS = ("F", "M")

#: (média, DP) por sexo, estado e segmento (1–17), em % do máximo do mapa polar.
BANCO_ESPANHOL: dict[str, dict[str, dict[int, tuple[float, float]]]] = {
    "F": {
        "estresse": {
            1: (67.42, 7.14), 2: (59.89, 8.24), 3: (62.09, 8.85), 4: (65.04, 7.20), 5: (68.67, 5.69), 6: (69.20, 6.90),
            7: (80.36, 5.37), 8: (79.04, 6.05), 9: (78.98, 5.96), 10: (79.04, 6.08), 11: (87.71, 4.86), 12: (86.00, 5.58),
            13: (82.40, 5.15), 14: (84.33, 5.06), 15: (82.58, 5.33), 16: (88.56, 4.20), 17: (84.73, 6.52),
        },
        "repouso": {
            1: (66.91, 8.30), 2: (59.93, 8.31), 3: (61.40, 9.53), 4: (65.64, 9.67), 5: (68.91, 8.12), 6: (68.16, 8.11),
            7: (78.51, 6.18), 8: (78.13, 5.07), 9: (77.67, 7.29), 10: (81.49, 7.33), 11: (88.44, 5.89), 12: (86.11, 6.05),
            13: (80.02, 6.30), 14: (83.13, 5.34), 15: (84.47, 6.28), 16: (88.98, 4.39), 17: (81.80, 7.82),
        },
    },
    "M": {
        "estresse": {
            1: (50.00, 11.37), 2: (53.90, 7.52), 3: (53.02, 6.18), 4: (57.69, 7.00), 5: (62.34, 7.04), 6: (63.38, 7.30),
            7: (78.34, 7.22), 8: (76.69, 7.98), 9: (70.55, 6.37), 10: (71.34, 6.71), 11: (83.12, 5.50), 12: (86.40, 5.22),
            13: (83.17, 5.55), 14: (82.66, 5.86), 15: (77.24, 5.40), 16: (88.60, 4.02), 17: (82.97, 6.99),
        },
        "repouso": {
            1: (61.97, 7.13), 2: (55.12, 7.92), 3: (53.83, 6.93), 4: (58.57, 6.83), 5: (62.14, 6.26), 6: (63.10, 6.23),
            7: (78.10, 6.62), 8: (78.03, 6.82), 9: (71.62, 6.67), 10: (72.45, 6.66), 11: (82.91, 5.30), 12: (87.24, 4.11),
            13: (82.81, 5.59), 14: (83.48, 5.16), 15: (77.71, 6.02), 16: (89.17, 3.43), 17: (81.67, 6.02),
        },
    },
}

#: Limites superiores de z (exclusivos) para os escores 0, 1, 2 e 3; abaixo do último, 4.
LIMIARES_Z = (-2.0, -3.0, -4.0, -5.0)

CITACAO_BANCO = (
    "Cuberas-Borrós G, Aguadé-Bruix S, Boronat-de Ferrater M, et al. Normal myocardial perfusion SPECT database "
    "for the Spanish population. Rev Esp Cardiol. 2010;63(8):934-42."
)
DESCRICAO_BANCO = (
    "Banco de normalidade espanhol (Cuberas-Borrós et al., Rev Esp Cardiol 2010): 104 voluntários com probabilidade "
    "de doença coronariana < 5% (45 mulheres, 59 homens; idade média 42 e 37 anos), ⁹⁹ᵐTc-tetrofosmin, protocolo curto "
    "estresse–repouso, órbita circular de 180°, matriz 64 × 64, sem correção de atenuação, reconstrução OSEM e "
    "quantificação no 4DM-SPECT. Escore: 0 se z > −2; 1 até −3; 2 até −4; 3 até −5; 4 abaixo de −5 "
    "(z = desvios-padrão abaixo da média do banco para o sexo escolhido). Esta ferramenta usa outra reconstrução "
    "(FBP com Butterworth), outra amostragem do mapa polar e, possivelmente, outra câmera, outro radiofármaco e outra "
    "população; os segmentos basais dependem de onde a base do eixo foi traçada. O escore automático é só guia: não "
    "substitui a pontuação visual e não foi validado nesta ferramenta."
)


def escore_de_z(z: float) -> int:
    """Escore 0–4 a partir do z (ver ``LIMIARES_Z``)."""
    for escore, limite in enumerate(LIMIARES_Z):
        if z > limite:
            return escore
    return 4


def escores_automaticos(valores: dict, sexo: str, estado: str) -> dict[int, dict]:
    """Por segmento: captação, média e DP do banco, z e escore. ``valores``: segmento → % do máximo."""
    if sexo not in SEXOS:
        raise ValueError("Sexo deve ser F ou M.")
    banco = BANCO_ESPANHOL[sexo][estado]
    saida = {}
    for s in SEGMENTOS:
        media, dp = banco[s]
        v = float(valores[s])
        z = (v - media) / dp
        saida[s] = {"captacao": v, "media": media, "dp": dp, "z": z, "escore": escore_de_z(z)}
    return saida
