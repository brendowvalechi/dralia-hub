"""Testes unitários do motor Spintax — não precisa de banco."""
import pytest
from app.services.spintax_engine import render


def test_simple_spintax():
    result = render("{Olá|Oi}")
    assert result in ["Olá", "Oi"]


def test_variable_substitution():
    result = render("Olá, {{nome}}!", {"nome": "João"})
    assert result == "Olá, João!"


def test_variable_before_spintax():
    """Variáveis devem ser substituídas ANTES do spintax."""
    result = render("{oi|olá} {{nome}}", {"nome": "Maria"})
    assert result in ["oi Maria", "olá Maria"]


def test_unknown_variable_empty():
    """Variáveis desconhecidas viram string vazia."""
    result = render("Olá, {{sobrenome}}!", {})
    assert result == "Olá, !"


def test_nested_spintax():
    result = render("{bom {dia|tarde}|boa noite}")
    assert result in ["bom dia", "bom tarde", "boa noite"]


def test_no_spintax():
    result = render("Mensagem simples sem spintax.")
    assert result == "Mensagem simples sem spintax."


def test_multiple_variables():
    result = render("{{greeting}}, {{nome}}!", {"greeting": "Olá", "nome": "Pedro"})
    assert result == "Olá, Pedro!"


def test_empty_template():
    result = render("")
    assert result == ""
