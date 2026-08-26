"""
explicacao_metas.py — A regra do bônus, escrita uma vez só.

Aqui moram DUAS coisas que precisam concordar sempre:

  1. bonus_percentuais() — a conta que decide quanto entra no salário.
  2. render() — a explicação que a equipe lê na tela.

Estavam separadas antes: a calculadora pagava 5% pela MAXX coletiva e 5% pela
MAXX individual, enquanto a regra combinada é 18% e 12%. Ninguém percebeu
porque a regra não estava escrita em lugar nenhum. Agora a explicação é gerada
a partir das mesmas constantes que a conta usa — mudar uma muda a outra.

A REGRA, em uma frase: o bônus tem duas metades, a do time e a sua, e cada
metade paga o nível MAIS ALTO que foi alcançado — nunca os dois somados.

  Metade do time (60%)        Metade do colaborador (40%)
    Meta MAXX .... 18%          Meta MAXX .... 12%
    Meta mensal .. 12%          Meta mensal ..  8%
    Nenhuma ......  0%          Nenhuma ......  0%

Tudo batido = 18 + 12 = 30%. É por isso que "bater a MAXX sobe de 20% para
30%": a MAXX não se soma à mensal, ela toma o lugar dela.
"""
import streamlit as st

# Quanto cada nível vale, em % do salário base.
PCT_COLETIVO_MENSAL = 12.0
PCT_COLETIVO_MAXX = 18.0
PCT_INDIVIDUAL_MENSAL = 8.0
PCT_INDIVIDUAL_MAXX = 12.0

# Salário usado só nos exemplos da tela — número redondo para a conta ficar fácil
# de acompanhar de cabeça.
SALARIO_EXEMPLO = 2000.0


def bonus_percentuais(col_mensal, col_maxx, ind_mensal, ind_maxx):
    """Quanto o salário aumenta, em pontos percentuais.

    Devolve (pct_time, pct_seu). Cada metade paga o nível mais alto alcançado:
    quem bate a MAXX recebe a MAXX no lugar da mensal, não as duas.
    """
    pct_time = (PCT_COLETIVO_MAXX if col_maxx
                else PCT_COLETIVO_MENSAL if col_mensal else 0.0)
    pct_seu = (PCT_INDIVIDUAL_MAXX if ind_maxx
               else PCT_INDIVIDUAL_MENSAL if ind_mensal else 0.0)
    return pct_time, pct_seu


# Os sete cenários possíveis, do pior para o melhor. (o time fez, você fez)
CENARIOS = [
    (False, False, False, False, "Não bateu nada",        "Não bateu a sua"),
    (True,  False, False, False, "Bateu a meta mensal",   "Não bateu a sua"),
    (False, False, True,  False, "Não bateu",             "Bateu a sua mensal"),
    (True,  False, True,  False, "Bateu a meta mensal",   "Bateu a sua mensal"),
    (True,  True,  False, False, "Bateu a meta MAXX",     "Não bateu a sua"),
    (True,  False, True,  True,  "Bateu a meta mensal",   "Bateu a sua MAXX"),
    (True,  True,  True,  True,  "Bateu a meta MAXX",     "Bateu a sua MAXX"),
]


def _reais(v):
    return f"R$ {v:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")


def _bloco(titulo, emoji, cor, mensal_pct, maxx_pct, quem):
    return (
        f'<div style="flex:1;min-width:230px;background:var(--ms-metric-bg);'
        f'border:1px solid {cor}55;border-left:4px solid {cor};border-radius:10px;'
        f'padding:14px 16px;">'
        f'<div style="font-size:15px;font-weight:700;color:{cor};margin-bottom:2px;">'
        f'{emoji} {titulo}</div>'
        f'<div style="font-size:12px;color:var(--ms-texto-sec);margin-bottom:10px;">'
        f'{quem}</div>'
        f'<div style="display:flex;align-items:baseline;gap:8px;margin-bottom:4px;">'
        f'<span style="font-size:22px;font-weight:800;color:{cor};">+{maxx_pct:.0f}%</span>'
        f'<span style="font-size:13px;color:var(--ms-texto);">se bater a <b>meta MAXX</b></span></div>'
        f'<div style="display:flex;align-items:baseline;gap:8px;">'
        f'<span style="font-size:22px;font-weight:800;color:var(--ms-texto);">+{mensal_pct:.0f}%</span>'
        f'<span style="font-size:13px;color:var(--ms-texto);">se bater a <b>meta mensal</b></span></div>'
        f'<div style="font-size:12px;color:var(--ms-texto-sec);margin-top:8px;">'
        f'Se não bater nenhuma das duas: <b>+0%</b></div>'
        f'</div>'
    )


def render(expandido=True):
    """Painel didático: como as metas viram dinheiro no salário."""
    with st.expander("📘 Como as metas viram dinheiro no seu salário — leia aqui",
                     expanded=expandido):

        st.markdown(
            '<div style="font-size:16px;line-height:1.7;margin-bottom:4px;">'
            'Todo mês o seu salário <b>pode aumentar</b>.<br>'
            'O aumento tem <b>duas partes</b>, e elas são independentes: '
            'uma parte depende do <b>time inteiro</b>, a outra depende '
            '<b>só de você</b>.'
            '</div>', unsafe_allow_html=True)

        st.markdown(
            f'<div style="display:flex;gap:14px;flex-wrap:wrap;margin:14px 0;">'
            + _bloco("A parte do TIME", "🤝", "#1BAF7A",
                     PCT_COLETIVO_MENSAL, PCT_COLETIVO_MAXX,
                     "Depende do resultado de todo mundo junto")
            + _bloco("A parte SUA", "🙋", "#EDA100",
                     PCT_INDIVIDUAL_MENSAL, PCT_INDIVIDUAL_MAXX,
                     "Depende só da sua pontuação")
            + '</div>', unsafe_allow_html=True)

        st.markdown(
            '<div style="background:#EDA10018;border:1px solid #EDA10055;'
            'border-radius:10px;padding:12px 16px;font-size:15px;line-height:1.7;">'
            '⚠️ <b>A regra mais importante de todas:</b><br>'
            'Cada parte paga <b>um nível só</b> — o mais alto que você alcançou.<br>'
            'A meta MAXX <b>não soma</b> com a mensal: ela <b>toma o lugar</b> dela.<br>'
            '<span style="color:var(--ms-texto-sec);">Exemplo: se você bateu a sua '
            'meta MAXX, você ganha os 12% da MAXX. Você <b>não</b> ganha 12% + 8%.</span>'
            '</div>', unsafe_allow_html=True)

        st.markdown(
            f'<div style="font-size:16px;font-weight:700;margin:18px 0 6px 0;">'
            f'💰 Na prática, com um salário de {_reais(SALARIO_EXEMPLO)}</div>',
            unsafe_allow_html=True)

        linhas = ""
        for i, (cm, cx, im, ix, txt_time, txt_voce) in enumerate(CENARIOS):
            p_time, p_seu = bonus_percentuais(cm, cx, im, ix)
            total_pct = p_time + p_seu
            ganho = SALARIO_EXEMPLO * total_pct / 100
            recebe = SALARIO_EXEMPLO + ganho
            cor = ("#1BAF7A" if total_pct >= 30 else
                   "#EDA100" if total_pct >= 20 else
                   "var(--ms-texto)" if total_pct > 0 else "var(--ms-texto-sec)")
            fundo = "background:var(--ms-metric-bg);" if i % 2 else ""
            linhas += (
                f'<tr style="{fundo}">'
                f'<td style="padding:9px 12px;font-size:14px;">{txt_time}</td>'
                f'<td style="padding:9px 12px;font-size:14px;">{txt_voce}</td>'
                f'<td style="padding:9px 12px;font-size:15px;font-weight:700;'
                f'color:{cor};text-align:center;white-space:nowrap;">'
                f'{"+" if total_pct else ""}{total_pct:.0f}%</td>'
                f'<td style="padding:9px 12px;font-size:14px;color:var(--ms-texto-sec);'
                f'text-align:right;white-space:nowrap;">'
                f'{"+ " + _reais(ganho) if ganho else "—"}</td>'
                f'<td style="padding:9px 12px;font-size:15px;font-weight:700;'
                f'color:{cor};text-align:right;white-space:nowrap;">{_reais(recebe)}</td>'
                f'</tr>')

        st.markdown(
            '<div style="overflow-x:auto;">'
            '<table style="width:100%;border-collapse:collapse;'
            'border:1px solid var(--ms-metric-bd);border-radius:10px;overflow:hidden;">'
            '<thead><tr style="background:var(--ms-metric-bg);">'
            '<th style="padding:10px 12px;font-size:11px;text-transform:uppercase;'
            'text-align:left;color:var(--ms-texto-sec);">🤝 O time fez</th>'
            '<th style="padding:10px 12px;font-size:11px;text-transform:uppercase;'
            'text-align:left;color:var(--ms-texto-sec);">🙋 Você fez</th>'
            '<th style="padding:10px 12px;font-size:11px;text-transform:uppercase;'
            'text-align:center;color:var(--ms-texto-sec);">Aumento</th>'
            '<th style="padding:10px 12px;font-size:11px;text-transform:uppercase;'
            'text-align:right;color:var(--ms-texto-sec);">A mais</th>'
            '<th style="padding:10px 12px;font-size:11px;text-transform:uppercase;'
            'text-align:right;color:var(--ms-texto-sec);">Você recebe</th>'
            '</tr></thead><tbody>' + linhas + '</tbody></table></div>',
            unsafe_allow_html=True)

        st.markdown(
            '<div style="font-size:15px;line-height:1.8;margin-top:16px;">'
            '<b>Resumindo em quatro frases:</b><br>'
            '1️⃣ O time bater a meta já coloca dinheiro no seu bolso, mesmo que '
            'você não bata a sua.<br>'
            '2️⃣ Você bater a sua meta já coloca dinheiro no seu bolso, mesmo que '
            'o time não bata a dele.<br>'
            '3️⃣ Bater a MAXX vale mais do que bater a mensal — mas vale '
            '<b>no lugar</b> dela, não além dela.<br>'
            '4️⃣ O melhor mês possível é o time na MAXX e você na sua MAXX: '
            f'<b>+30%</b>, que num salário de {_reais(SALARIO_EXEMPLO)} são '
            f'<b>{_reais(SALARIO_EXEMPLO * 0.30)} a mais</b>.'
            '</div>', unsafe_allow_html=True)

        st.caption("Logo abaixo, informe seu salário para ver esta conta com o "
                   "seu número real e com as metas deste mês.")
