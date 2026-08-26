"""
planilha.py — De qual planilha este Studio lê e escreve, e em que ambiente ele está.

O nome da planilha estava escrito na mão em nove arquivos. Enquanto houve um
ambiente só isso não incomodava; com um ambiente de homologação passa a ser o
que separa o teste da produção — e um lugar esquecido escreveria na planilha de
verdade sem ninguém perceber.

Configuração no ambiente de teste (secrets do Railway):

    AMBIENTE = "homologacao"
    PLANILHA_NOME = "MartinSousa - Financeiro (TESTE)"
    DRIVE_PASTA_IMAGENS_ID = "<id da pasta de teste>"

Em produção nada precisa ser configurado: sem os secrets, os padrões são os de
produção. É de propósito — esquecer de configurar o teste faz o teste falhar,
não a produção.

Trello e RHiD ficam apontando para os reais nos dois ambientes: o Studio só LÊ
os dois (todas as chamadas ao Trello são GET, e o único POST da RHiD é o login),
então o teste roda com dados de verdade sem risco de sujar nada.
"""
import streamlit as st

NOME_PADRAO = "MartinSousa - Financeiro"


def _secret(chave, padrao=""):
    try:
        return str(st.secrets.get(chave, padrao) or padrao).strip()
    except Exception:
        return padrao


def nome():
    """Nome da planilha deste ambiente."""
    return _secret("PLANILHA_NOME", NOME_PADRAO) or NOME_PADRAO


def ambiente():
    """'producao' ou 'homologacao'."""
    return (_secret("AMBIENTE", "producao") or "producao").lower()


def eh_homologacao():
    return ambiente() != "producao"


def aviso_ambiente():
    """Faixa no topo da tela quando NÃO é produção.

    Sem ela, as duas telas são idênticas: dá para passar meia hora testando na
    produção achando que é o teste, ou o contrário.
    """
    if not eh_homologacao():
        return
    st.markdown(
        '<div style="background:#EDA100;color:#111;font-weight:700;'
        'text-align:center;padding:6px 12px;border-radius:6px;'
        'margin-bottom:10px;font-size:13px;letter-spacing:.3px;">'
        f'🧪 AMBIENTE DE TESTE — planilha "{nome()}" · '
        'nada aqui afeta o Studio de verdade</div>',
        unsafe_allow_html=True)
