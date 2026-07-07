# parametros_oficiais.py
# Todas as taxas validadas com dados reais - nunca alterar sem nova validação

# ── FIXOS ──────────────────────────────────────────────────────────────────────
LPV_OFICIAL = 22.00   # Custo operacional por venda (fixo, nunca solicitar)
NF_OFICIAL  = 0.10    # Nota fiscal 10% (fixo, nunca solicitar)

# ── SHOPEE ─────────────────────────────────────────────────────────────────────
# Tabela oficial março/2026 - Frete Grátis obrigatório
# (comissao_pct, adicional_fixo, frete_liquido_vendedor)
SHOPEE_FAIXAS = [
    (8.00,   79.99, 0.20, 4.00, 0.00),
    (80.00, 159.99, 0.18, 0.00, 0.00),
    (160.00,999999, 0.15, 0.00, 0.00),
]
SHOPEE_FRETE_LIQUIDO = 0.00  # vendedor não paga frete (Frete Grátis ML obrigatório)

# ── SHEIN ──────────────────────────────────────────────────────────────────────
# Comissão: 18% flat (validado em 4 prints reais)
SHEIN_COMISSAO = 0.18

# Frete por peso (tabela oficial conta do vendedor Shein)
SHEIN_FRETE_TABELA = [
    (0.300,   4.00),
    (0.500,   5.00),
    (1.000,   7.00),
    (2.000,  10.00),
    (3.000,  13.00),
    (5.000,  18.00),
    (7.000,  23.00),
    (10.000, 31.00),
    (15.000, 44.00),
    (23.000, 62.00),
    (999.0, 106.00),
]

# ── MERCADO LIVRE ──────────────────────────────────────────────────────────────
# Frete: tabela oficial ajuda/40538 - divisor cubagem 6000
ML_FAIXAS_PRECO = [29, 49, 79, 129, 199, 299, 999999]

# (peso_maximo_kg, [frete por faixa de preco acima])
ML_FRETE_TABELA = [
    (0.100, [5.80, 6.50, 7.50, 8.50, 9.50, 10.50, 12.00]),
    (0.200, [6.20, 7.00, 8.00, 9.00,10.00, 11.00, 13.00]),
    (0.300, [6.70, 7.50, 8.50, 9.50,10.50, 11.50, 13.50]),
    (0.500, [7.50, 8.50, 9.50,10.50,11.50, 12.50, 14.50]),
    (0.700, [8.50, 9.50,10.50,11.50,12.50, 13.50, 15.50]),
    (1.000, [9.50,10.50,11.50,12.50,13.50, 14.50, 16.50]),
    (1.500,[11.00,12.00,13.00,14.00,15.00, 16.00, 18.00]),
    (2.000,[12.50,13.50,14.50,15.50,16.50, 17.50, 19.50]),
    (2.500,[14.00,15.00,16.00,17.00,18.00, 19.00, 21.00]),
    (3.000,[15.50,16.50,17.50,18.50,19.50, 20.50, 22.50]),
    (5.000,[19.00,20.00,21.00,22.00,23.00, 24.00, 26.00]),
    (7.000,[23.00,24.00,25.00,26.00,27.00, 28.00, 30.00]),
    (10.00,[28.00,29.00,30.00,31.00,32.00, 33.00, 35.00]),
    (15.00,[35.00,36.00,37.00,38.00,39.00, 40.00, 42.00]),
    (20.00,[43.00,44.00,45.00,46.00,47.00, 48.00, 50.00]),
    (30.00,[55.00,56.00,57.00,58.00,59.00, 60.00, 62.00]),
    (999.0,[70.00,71.00,72.00,73.00,74.00, 75.00, 77.00]),
]

# Comissões ML por categoria - sempre usa Premium (regra operacional fixa)
# Formato: 'Categoria': (classico_pct, premium_pct)
ML_COMISSAO_POR_CATEGORIA = {
    'Acessórios para Veículos': (0.10, 0.16),
    'Agro': (0.10, 0.16),
    'Alimentos e Bebidas': (0.12, 0.16),
    'Animais e Mascotas': (0.10, 0.16),
    'Antiguidades e Coleções': (0.10, 0.16),
    'Arte, Papelaria e Armarinho': (0.12, 0.16),
    'Bebês': (0.10, 0.16),
    'Beleza e Cuidado Pessoal': (0.12, 0.16),
    'Brinquedos e Hobbies': (0.12, 0.16),
    'Calçados, Roupas e Bolsas': (0.12, 0.16),
    'Câmeras e Acessórios': (0.10, 0.16),
    'Casa, Móveis e Decoração': (0.12, 0.16),
    'Celulares e Telefones': (0.08, 0.13),
    'Computadores': (0.08, 0.13),
    'Construção': (0.10, 0.16),
    'Cosméticos e Perfumaria': (0.12, 0.16),
    'Eletrodomésticos': (0.10, 0.16),
    'Eletrônicos, Áudio e Vídeo': (0.10, 0.16),
    'Esportes e Fitness': (0.12, 0.16),
    'Ferramentas': (0.10, 0.16),
    'Games e Consoles': (0.10, 0.16),
    'Iluminação': (0.12, 0.16),
    'Indústria e Comércio': (0.10, 0.16),
    'Informática': (0.08, 0.13),
    'Ingressos': (0.10, 0.16),
    'Instrumentos Musicais': (0.10, 0.16),
    'Joias e Relógios': (0.12, 0.16),
    'Livros, Revistas e Comics': (0.10, 0.16),
    'Música, Filmes e Seriados': (0.10, 0.16),
    'Saúde': (0.12, 0.16),
    'Serviços': (0.10, 0.16),
    'Souvenirs e Artesanato': (0.12, 0.16),
    'TV, Vídeo e DVD': (0.10, 0.16),
    'Outros': (0.10, 0.16),
}
