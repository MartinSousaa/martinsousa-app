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

# Salário só para ilustrar quando a pessoa ainda não digitou o dela.
SALARIO_EXEMPLO = 2000.0

# São DOIS pagamentos separados: o salário fecha no último dia do mês, e o valor
# das metas vem depois, porque o mês precisa terminar para dar para apurar.
DIA_UTIL_PAGAMENTO = 5

# Os nomes que a equipe usa. A tela inteira fala nestes quatro termos — antes
# dizia "a parte do time" e "a parte sua", que ninguem reconhecia.
NOME_COL = "meta coletiva"
NOME_COL_MAXX = "meta coletiva MAXX"
NOME_IND = "meta individual"
NOME_IND_MAXX = "meta individual MAXX"

# Limites dos cinco indicadores. Moram aqui, junto da explicacao que os
# descreve, para que mudar um numero mude tambem o texto que a equipe le.
OCIO_META_NORMAL = 10
OCIO_META_MAXX = 5
EXEC_META_NORMAL = 80
EXEC_META_MAXX = 90


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
    (False, False, False, False, "Não bateu",              "Não bateu"),
    (True,  False, False, False, "Bateu a coletiva",       "Não bateu"),
    (False, False, True,  False, "Não bateu",              "Bateu a individual"),
    (True,  False, True,  False, "Bateu a coletiva",       "Bateu a individual"),
    (True,  True,  False, False, "Bateu a coletiva MAXX",  "Não bateu"),
    (True,  False, True,  True,  "Bateu a coletiva",       "Bateu a individual MAXX"),
    (True,  True,  True,  True,  "Bateu a coletiva MAXX",  "Bateu a individual MAXX"),
]


def _reais(v):
    return f"R$ {v:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")


def _linha_meta(emoji, nome, pct, cor):
    return (f'<div style="display:flex;align-items:baseline;gap:9px;'
            f'margin-bottom:6px;">'
            f'<span style="font-size:20px;font-weight:800;color:{cor};'
            f'min-width:60px;">+{pct:.0f}%</span>'
            f'<span style="font-size:14px;color:var(--ms-texto);">'
            f'{emoji} <b>{nome}</b></span></div>')


def _bloco_nivel(titulo, subtitulo, cor, nome_col, pct_col, nome_ind, pct_ind):
    """Um nivel de meta: as duas metas que o compoem e quanto elas somam.

    Antes os quadros eram divididos por DONO (metas do time / metas suas), e o
    total de cada nivel — 20% no mes, 30% na MAXX — nao aparecia em lugar nenhum.
    """
    total = pct_col + pct_ind
    return (
        f'<div style="flex:1;min-width:260px;background:var(--ms-metric-bg);'
        f'border:1px solid {cor}55;border-left:4px solid {cor};border-radius:10px;'
        f'padding:14px 16px;">'
        f'<div style="font-size:15px;font-weight:700;color:{cor};margin-bottom:2px;">'
        f'{titulo}</div>'
        f'<div style="font-size:12px;color:var(--ms-texto-sec);margin-bottom:11px;">'
        f'{subtitulo}</div>'
        + _linha_meta("🤝", nome_col, pct_col, cor)
        + _linha_meta("🙋", nome_ind, pct_ind, cor)
        + f'<div style="border-top:1px solid var(--ms-divisor);margin-top:10px;'
        f'padding-top:9px;display:flex;align-items:baseline;gap:9px;">'
        f'<span style="font-size:24px;font-weight:800;color:{cor};'
        f'min-width:60px;">+{total:.0f}%</span>'
        f'<span style="font-size:13px;color:var(--ms-texto);">'
        f'se bater <b>as duas</b></span></div>'
        f'</div>'
    )


def _topico(emoji, titulo, o_que, como, cor):
    return (
        f'<div style="border-left:3px solid {cor};padding:2px 0 2px 12px;'
        f'margin-bottom:14px;">'
        f'<div style="font-size:14px;font-weight:700;color:{cor};'
        f'margin-bottom:3px;">{emoji} {titulo}</div>'
        f'<div style="font-size:14px;line-height:1.6;color:var(--ms-texto);">'
        f'{o_que}</div>'
        f'<div style="font-size:13px;line-height:1.6;'
        f'color:var(--ms-texto-sec);margin-top:4px;">{como}</div></div>')


def _explicar_indicadores():
    """O que cada indicador mede e como e contado, em duas linhas cada.

    Os numeros vem das constantes de verdade — as folgas sao lidas do
    placar_core, que e quem mede. Texto e calculo nao tem como discordar.
    """
    try:
        import placar_core as _pc
        g_ini, g_ent = _pc.GRACA_INICIO_MIN, _pc.GRACA_ENTRE_MIN
        pausa = _pc.PAUSA_PESSOAL_MIN // 60
        f_ent, t_ent = _pc.FOLGA_ENTRADA_MIN, _pc.TOLERANCIA_ENTRADA_MIN
        f_alm, almoco = _pc.FOLGA_ALMOCO_MIN, _pc.ALMOCO_MINUTOS
    except Exception:
        g_ini, g_ent, pausa = 10, 5, 1
        f_ent, t_ent, f_alm, almoco = 5, 10, 5, 60

    st.markdown(
        '<div style="font-size:16px;font-weight:700;margin:20px 0 8px 0;">'
        '📐 O que cada indicador mede</div>', unsafe_allow_html=True)

    blocos = [
        ("📈", "Pontuação", "#1BAF7A",
         "Os pontos dos cartões que você concluiu.",
         "Cada cartão vale os pontos da coluna dele, e conta no mês em que "
         "foi <b>concluído</b>."),

        ("⏱️", "Ociosidade", "#4A90D9",
         "Tempo do seu dia <b>sem nenhum cartão EM ANDAMENTO</b> no seu nome.",
         f"Você tem {g_ini} min ao chegar, {g_ent} min a cada troca de cartão "
         f"e {pausa}h por dia de pausa. Cartão <b>INTERROMPIDO</b> ou "
         f"<b>PENDENTE</b> não conta como atividade. Meta: abaixo de "
         f"{OCIO_META_NORMAL}% ({OCIO_META_MAXX}% na MAXX)."),

        ("⚡", "Tempo de execução", "#EDA100",
         "Quantos dos seus cartões ficaram dentro do tempo previsto.",
         "O tempo é medido pela etiqueta EM ANDAMENTO e comparado com o "
         f"estimado da coluna. Meta: {EXEC_META_NORMAL}% dos cartões dentro "
         f"({EXEC_META_MAXX}% na MAXX)."),

        ("🕐", "Tolerâncias", "#8E7CC3",
         "Os atrasos pequenos na entrada.",
         f"Até {f_ent} min depois do seu horário não conta nada. De {f_ent} a "
         f"{t_ent} min gasta uma tolerância. Quem entra 09:00: livre até "
         f"09:05, tolerância até 09:10."),

        ("⏰", "Atrasos", "#E34948",
         "Os atrasos que pesam na meta.",
         f"Entrada: passou de {t_ent} min (09:11 para quem entra 09:00). "
         f"Almoço: passou de {almoco + f_alm} min fora — aqui não há "
         f"tolerância. Os dois contam separado."),
    ]
    st.markdown("".join(
        _topico(emoji, titulo, o_que, como, cor)
        for emoji, titulo, cor, o_que, como in blocos
    ), unsafe_allow_html=True)


def render(expandido=True, chave_salario="expl_salario"):
    """Painel didático: como as metas viram dinheiro no salário.

    A tabela usa o salário que a própria pessoa digita. Sem isso a explicação
    ficava abstrata: percentual não diz nada até virar reais na conta de quem
    está lendo.
    """
    with st.expander("📘 Como as metas viram dinheiro no seu salário — leia aqui",
                     expanded=expandido):

        st.markdown(
            '<div style="font-size:16px;line-height:1.7;margin-bottom:4px;">'
            'Todo mês o seu salário <b>pode aumentar</b>.<br>'
            'Existem <b>quatro metas</b>, e cada uma vale um valor diferente. '
            'Duas são do <b>time inteiro</b> e duas são <b>só suas</b>.'
            '</div>', unsafe_allow_html=True)

        st.markdown(
            '<div style="display:flex;gap:14px;flex-wrap:wrap;margin:14px 0;">'
            + _bloco_nivel(
                f"📗 Metas do mês — até +{PCT_COLETIVO_MENSAL + PCT_INDIVIDUAL_MENSAL:.0f}%",
                "O primeiro nível. São as metas normais do mês.",
                "#1BAF7A",
                NOME_COL, PCT_COLETIVO_MENSAL,
                NOME_IND, PCT_INDIVIDUAL_MENSAL)
            + _bloco_nivel(
                f"⭐ Metas MAXX — até +{PCT_COLETIVO_MAXX + PCT_INDIVIDUAL_MAXX:.0f}%",
                "O nível mais alto. São metas maiores e pagam mais.",
                "#EDA100",
                NOME_COL_MAXX, PCT_COLETIVO_MAXX,
                NOME_IND_MAXX, PCT_INDIVIDUAL_MAXX)
            + '</div>', unsafe_allow_html=True)

        st.markdown(
            '<div style="background:#EDA10018;border:1px solid #EDA10055;'
            'border-radius:10px;padding:12px 16px;font-size:15px;line-height:1.7;">'
            '⚠️ <b>A regra mais importante de todas:</b><br>'
            'Os dois quadros acima <b>não somam</b> entre si. '
            f'Ninguém recebe {PCT_COLETIVO_MENSAL + PCT_INDIVIDUAL_MENSAL:.0f}% '
            f'+ {PCT_COLETIVO_MAXX + PCT_INDIVIDUAL_MAXX:.0f}%.<br>'
            'Quando uma meta MAXX é batida, ela <b>toma o lugar</b> da meta '
            'normal correspondente:<br>'
            f'<span style="color:var(--ms-texto-sec);">• Bateu a '
            f'<b>{NOME_COL_MAXX}</b>? Vale {PCT_COLETIVO_MAXX:.0f}% no lugar dos '
            f'{PCT_COLETIVO_MENSAL:.0f}% da {NOME_COL}.<br>'
            f'• Bateu a <b>{NOME_IND_MAXX}</b>? Vale {PCT_INDIVIDUAL_MAXX:.0f}% no '
            f'lugar dos {PCT_INDIVIDUAL_MENSAL:.0f}% da {NOME_IND}.</span><br>'
            'Mas uma meta <b>do time</b> e uma meta <b>sua</b> sempre somam entre '
            'si — inclusive de níveis diferentes. Dá para bater a '
            f'{NOME_COL} e a {NOME_IND_MAXX} no mesmo mês.'
            '</div>', unsafe_allow_html=True)

        st.markdown(
            '<div style="font-size:16px;font-weight:700;margin:18px 0 2px 0;">'
            '💰 Veja a conta com o SEU salário</div>', unsafe_allow_html=True)
        salario = st.number_input(
            "Digite aqui o seu salário base:",
            min_value=0.0, value=0.0, step=100.0, format="%.2f",
            key=chave_salario,
            help="Fica só no seu navegador, ninguém mais vê.")
        _proprio = salario > 0
        _base = salario if _proprio else SALARIO_EXEMPLO
        if not _proprio:
            st.caption(f"Enquanto você não digitar, a tabela mostra um exemplo "
                       f"com {_reais(SALARIO_EXEMPLO)}.")

        linhas = ""
        for i, (cm, cx, im, ix, txt_time, txt_voce) in enumerate(CENARIOS):
            p_time, p_seu = bonus_percentuais(cm, cx, im, ix)
            total_pct = p_time + p_seu
            ganho = _base * total_pct / 100
            recebe = _base + ganho
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
            'text-align:left;color:var(--ms-texto-sec);">🤝 Meta coletiva</th>'
            '<th style="padding:10px 12px;font-size:11px;text-transform:uppercase;'
            'text-align:left;color:var(--ms-texto-sec);">🙋 Meta individual</th>'
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
            '<b>Resumindo:</b><br>'
            f'1️⃣ Se o time bater a <b>{NOME_COL}</b>, você ganha '
            f'<b>+{PCT_COLETIVO_MENSAL:.0f}%</b> — mesmo que você não bata a sua.<br>'
            f'2️⃣ Se você bater a sua <b>{NOME_IND}</b>, você ganha '
            f'<b>+{PCT_INDIVIDUAL_MENSAL:.0f}%</b> — mesmo que o time não bata a dele.<br>'
            f'3️⃣ A <b>{NOME_COL_MAXX}</b> paga <b>+{PCT_COLETIVO_MAXX:.0f}%</b> '
            f'e a <b>{NOME_IND_MAXX}</b> paga <b>+{PCT_INDIVIDUAL_MAXX:.0f}%</b> — '
            'sempre no lugar da meta normal, nunca além dela.<br>'
            f'4️⃣ O melhor mês possível é <b>{NOME_COL_MAXX}</b> + '
            f'<b>{NOME_IND_MAXX}</b>: '
            f'<b>+{PCT_COLETIVO_MAXX + PCT_INDIVIDUAL_MAXX:.0f}%</b>, que '
            + (f'no seu salário são <b>{_reais(_base * 0.30)} a mais</b>.'
               if _proprio else
               f'num salário de {_reais(SALARIO_EXEMPLO)} são '
               f'<b>{_reais(SALARIO_EXEMPLO * 0.30)} a mais</b>.')
            + '</div>', unsafe_allow_html=True)

        st.markdown(
            '<div style="background:var(--ms-metric-bg);'
            'border:1px solid var(--ms-metric-bd);border-left:4px solid #6AA9FF;'
            'border-radius:10px;padding:12px 16px;margin-top:16px;'
            'font-size:15px;line-height:1.7;">'
            '📅 <b>Quando esse dinheiro cai na sua conta</b><br>'
            'São <b>dois pagamentos separados</b>, em datas diferentes.<br><br>'
            '💵 <b>O seu salário</b> cai no <b>último dia do mês</b>, como sempre.<br>'
            '🏆 <b>O valor das metas</b> vem <b>depois</b>, e o motivo é simples: '
            'para saber quanto cada um ganhou, o mês precisa <b>terminar</b> — '
            'só depois disso dá para contar tudo o que foi feito. '
            'Essa contagem se chama <b>apuração</b>.<br>'
            f'Por isso o valor das metas é depositado no '
            f'<b>{DIA_UTIL_PAGAMENTO}º dia útil do mês seguinte</b>.<br><br>'
            '<span style="color:var(--ms-texto-sec);">Exemplo com o mês de '
            '<b>agosto</b>: o salário de agosto cai no <b>último dia de agosto</b>. '
            'O que você fez em agosto é apurado quando agosto acaba, e o valor '
            f'das metas cai no {DIA_UTIL_PAGAMENTO}º dia útil de '
            '<b>setembro</b>.</span>'
            '</div>', unsafe_allow_html=True)

        _explicar_indicadores()

        st.caption("Mais abaixo, no seu card, a mesma conta aparece com as "
                   "metas que já estão valendo neste mês.")
