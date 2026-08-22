"""Do texto impresso para o texto falado.

A ordem das transformações é o que mais quebra aqui: moeda antes de
milhar, data antes de barra, ordinal antes de cardinal. Cada teste que
mistura duas regras está testando a ordem, não só a regra.
"""

from __future__ import annotations

import pytest

from audiolivro.texto.normalizar import (
    converter_numeros,
    expandir_abreviacoes,
    limpar,
    normalizar,
    ritmo,
    soletrar_siglas,
)


def test_limpeza_tira_o_que_e_so_tipografia() -> None:
    assert limpar("o­fi​cina") == "oficina"       # hífen suave, largura zero
    assert limpar("“aspas” e ‘apóstrofo’") == '"aspas" e \'apóstrofo\''
    assert limpar("ﬁm da ﬂor") == "fim da flor"            # ligaduras
    assert limpar("nota¹ do rodapé") == "nota do rodapé"    # expoente de nota
    assert limpar("linha um\nlinha dois") == "linha um linha dois"
    assert limpar("estreita , entre") == "estreita, entre"


@pytest.mark.parametrize(
    "entrada, esperado",
    [
        ("O Sr. Silva", "O senhor Silva"),
        ("a Dra. Ana", "a doutora Ana"),
        ("pág. 37", "página 37"),
        ("séc. XX", "século XX"),
        ("etc.", "et cetera"),
        ("p. ex. isto", "por exemplo isto"),
        ("em 44 a.C.", "em 44 antes de Cristo"),
        ("nº 37", "número 37"),
    ],
)
def test_abreviacoes(entrada: str, esperado: str) -> None:
    assert expandir_abreviacoes(entrada) == esperado


def test_d_maiusculo_so_vira_dom_diante_de_monarca() -> None:
    # "D." é dom ou dona e o texto não diz qual. O numeral romano logo
    # depois do nome resolve a dúvida; sem ele, não chutamos.
    assert "Dom Pedro II" in expandir_abreviacoes("D. Pedro II")
    assert expandir_abreviacoes("D. Maria trouxe o bolo") == "D. Maria trouxe o bolo"


@pytest.mark.parametrize(
    "entrada, esperado",
    [
        ("R$ 1.250,50", "mil duzentos e cinquenta reais e cinquenta centavos"),
        ("R$ 1,00", "um real"),
        ("US$ 40", "quarenta dólares"),
        ("12/03/1998", "doze de março de mil novecentos e noventa e oito"),
        ("1º/05/2020", "primeiro de maio de dois mil e vinte"),
        ("45%", "quarenta e cinco por cento"),
        ("14h30", "catorze horas e trinta"),
        ("3h", "três horas"),
        ("5º", "quinto"),
        ("3ª", "terceira"),
        ("30 km", "trinta quilômetros"),
        ("3,14", "três vírgula um quatro"),
        ("1.250", "mil duzentos e cinquenta"),
        ("1914-1918", "de mil novecentos e catorze a mil novecentos e dezoito"),
        ("de 1914-1918", "de mil novecentos e catorze a mil novecentos e dezoito"),
        ("entre 1914-1918", "entre mil novecentos e catorze e mil novecentos e dezoito"),
        ("3,5 milhões", "três vírgula cinco milhões"),
        ("007", "zero zero sete"),
    ],
)
def test_numeros_em_contexto(entrada: str, esperado: str) -> None:
    assert converter_numeros(entrada) == esperado


def test_moeda_vem_antes_do_milhar() -> None:
    # Se a regra de milhar rodasse primeiro, o "R$" ficaria órfão e o
    # valor sairia sem a palavra "reais".
    assert "reais" in converter_numeros("custou R$ 1.250")


def test_romano_so_converte_com_contexto() -> None:
    assert converter_numeros("capítulo XIV") == "capítulo catorze"
    assert converter_numeros("século XIX") == "século dezenove"
    assert converter_numeros("Luís XIV") == "Luís décimo quarto"
    # Sem contexto, a sigla fica intacta — "MIX" é um romano válido.
    assert converter_numeros("o MIX de produtos") == "o MIX de produtos"


@pytest.mark.parametrize(
    "sigla, esperado",
    [
        ("ONU", "Onu"),        # pronunciável: lê-se como palavra
        ("OTAN", "Otan"),
        ("IBGE", "i-bê-gê-é"),  # "BG" não abre sílaba em português
        ("CNPJ", "cê-êne-pê-jota"),  # sem vogal nenhuma
        ("UFRJ", "u-éfe-érre-jota"),
    ],
)
def test_siglas(sigla: str, esperado: str) -> None:
    assert soletrar_siglas(sigla) == esperado


def test_caixa_alta_corrida_nao_e_sigla() -> None:
    """Um título gritado não é uma sequência de siglas.

    Soletrá-lo palavra por palavra — "ó éfe i eme" — seria o pior erro
    possível, e acontece justamente nas aberturas de capítulo.
    """
    assert soletrar_siglas("O FIM DA TARDE") == "O fim da tarde"


def test_ritmo_troca_marca_visual_por_prosodia() -> None:
    # O motor não entende parêntese nem travessão, mas entende vírgula.
    assert ritmo("ele (que era alto) saiu") == "ele, que era alto, saiu"
    assert ritmo("— Sim — disse") == "Sim, disse"
    assert ritmo("veja em https://exemplo.com/x hoje") == (
        "veja em um endereço na internet hoje"
    )
    assert ritmo("guarda-chuva azul-claro") == "guarda-chuva azul-claro"


def test_pipeline_completo_fecha_a_frase() -> None:
    # Sem pontuação final o motor não baixa a entonação e a frase
    # seguinte cola nesta.
    assert normalizar("uma frase sem ponto").endswith(".")
    assert normalizar("uma pergunta?").endswith("?")


def test_pipeline_completo() -> None:
    entrada = 'O Sr. Silva pagou R$ 1.250,50 ao IBGE no cap. XIV — sem reclamar'
    assert normalizar(entrada) == (
        "O senhor Silva pagou mil duzentos e cinquenta reais e cinquenta centavos "
        "ao i-bê-gê-é no capítulo catorze, sem reclamar."
    )
