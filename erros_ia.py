"""Traduz falhas dos provedores de IA em mensagem que o colaborador entende.

Por que este módulo existe
--------------------------
As falhas mais comuns aqui não são de código — são de conta: chave revogada,
crédito acabado, limite de requisições. Todas chegam como JSON cru da API, e é
isso que o colaborador via na tela:

    Erro ao gerar palavras-chave: Error code: 401 - {'type': 'error', 'error':
    {'type': 'authentication_error', 'message': 'API key is invalid.'}, ...}

Isso é ruim por dois motivos. O colaborador não tem como agir — a correção é do
administrador — e, pior, parece defeito do sistema. Já aconteceu de o problema
ser saldo da conta e a leitura ser "o site quebrou".

A mensagem certa diz três coisas: o que houve, de quem é a ação, e se o trabalho
foi perdido.
"""


def mensagem(exc, acao="gerar o conteúdo"):
    """Mensagem em português para uma falha de provedor de IA.

    `acao` descreve o que estava sendo feito, para a frase ficar específica
    ("não consegui gerar as palavras-chave" em vez de "erro").
    """
    texto = str(exc)
    t = texto.lower()

    if "authentication_error" in t or "api key" in t or "401" in texto:
        return (
            f"⚠️ Não consegui {acao}: a chave de acesso da IA foi recusada.\n\n"
            "**Isso é ajuste de administrador — avise o Léo.** A chave provavelmente "
            "foi trocada ou revogada e precisa ser atualizada no painel de hospedagem. "
            "Nada do que você preencheu foi perdido."
        )

    if "credit balance" in t or "billing" in t or "insufficient_quota" in t:
        return (
            f"⚠️ Não consegui {acao}: a conta da IA está sem crédito.\n\n"
            "**Isso é ajuste de administrador — avise o Léo.** "
            "Nada do que você preencheu foi perdido."
        )

    if "rate_limit" in t or "429" in texto or "too many requests" in t:
        return (
            f"⚠️ Não consegui {acao}: muitas solicitações ao mesmo tempo. "
            "Aguarde um minuto e tente de novo — costuma resolver sozinho."
        )

    if "overloaded" in t or "529" in texto or "503" in texto:
        return (
            f"⚠️ Não consegui {acao}: o serviço de IA está sobrecarregado no momento. "
            "Tente de novo em alguns minutos."
        )

    if "timeout" in t or "timed out" in t or "connection" in t:
        return (
            f"⚠️ Não consegui {acao}: falha de conexão com o serviço de IA. "
            "Tente de novo; se persistir, avise o administrador."
        )

    # Desconhecido: mostra o texto original, que ainda é a melhor pista para
    # quem for investigar. Inventar mensagem amigável aqui esconderia o problema.
    return f"⚠️ Não consegui {acao}.\n\nDetalhe técnico: {texto[:300]}"
