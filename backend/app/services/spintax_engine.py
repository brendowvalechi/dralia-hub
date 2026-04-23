"""
Spintax Engine — processa templates no formato {opção1|opção2|opção3}
e substitui variáveis no formato {{nome}}.

Exemplos:
    "{Olá|Oi|E aí}, {{nome}}! {Tudo bem?|Como vai?}"
    → "Oi, João! Como vai?"
"""
import random
import re

_SPINTAX_RE = re.compile(r"\{([^{}]+)\}")
_VAR_RE = re.compile(r"\{\{(\w+)\}\}")


def _resolve_spintax(text: str) -> str:
    """Resolve todos os blocos {a|b|c} de dentro para fora."""
    while True:
        match = _SPINTAX_RE.search(text)
        if not match:
            break
        options = match.group(1).split("|")
        chosen = random.choice(options)
        text = text[: match.start()] + chosen + text[match.end() :]
    return text


def _substitute_vars(text: str, variables: dict) -> str:
    """Substitui {{variavel}} pelos valores do dicionário."""
    def replacer(m: re.Match) -> str:
        key = m.group(1)
        return str(variables.get(key, ""))  # variável desconhecida → string vazia

    return _VAR_RE.sub(replacer, text)


def render(template: str, variables: dict | None = None) -> str:
    """
    Processa um template Spintax com variáveis.

    Ordem: substitui {{variáveis}} primeiro para protegê-las do parser
    de spintax, depois resolve os blocos {opção1|opção2}.

    Args:
        template:  Texto com blocos {a|b} e variáveis {{nome}}
        variables: Dicionário com valores para substituir (ex: {"nome": "João"})

    Returns:
        Texto final renderizado
    """
    # 1. Substitui variáveis antes do spintax para evitar conflito de chaves
    text = _substitute_vars(template, variables or {})
    # 2. Resolve blocos {opção1|opção2}
    text = _resolve_spintax(text)
    return text
