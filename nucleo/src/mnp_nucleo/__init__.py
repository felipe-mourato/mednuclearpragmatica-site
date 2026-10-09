"""Núcleo de processamento das ferramentas de medicina nuclear da MedNuclear Pragmática."""

# Versão do núcleo. É a mesma que aparece nos resultados e no laudo das
# ferramentas. Ao mudar, registre a mudança em nucleo/CHANGELOG.md.
__version__ = "0.2.0"


def versoes() -> dict:
    """Versões do núcleo e das dependências em uso, para o laudo.

    Registrar as versões exatas permite reproduzir um cálculo depois
    (requisito de estudos de validação).
    """
    import platform

    import numpy
    import pydicom

    return {
        "mnp_nucleo": __version__,
        "numpy": numpy.__version__,
        "pydicom": pydicom.__version__,
        "python": platform.python_version(),
    }
