# parametros_oficiais.py
# Todas as taxas validadas com dados reais - nunca alterar sem nova validação

# ── FIXOS ──────────────────────────────────────────────────────────────────────
LPV_OFICIAL = 22.00   # Valor de reserva -- so usado se a aba Financeiro ainda nao tiver LPV informado
NF_OFICIAL  = 0.10    # Valor de reserva -- so usado se a aba Financeiro ainda nao tiver aliquota informada

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
# Frete: tabela oficial de custos de Envios (MercadoLider / reputacao verde / sem
# reputacao), valida a partir da reforma de marco/2026. Divisor de peso cubado: 6000.
# Fonte: pagina oficial de custos de envios do vendedor, colada pelo usuario em 14/07/2026.
ML_FAIXAS_PRECO = [18.99, 48.99, 78.99, 99.99, 119.99, 149.99, 199.99, 999999]

# (peso_maximo_kg, [frete por faixa de preco acima, na mesma ordem de ML_FAIXAS_PRECO])
ML_FRETE_TABELA = [
    (0.3,   [5.65, 6.55, 7.75, 12.35, 14.35, 16.45, 18.45, 20.95]),
    (0.5,   [5.95, 6.65, 7.85, 13.25, 15.45, 17.65, 19.85, 22.55]),
    (1,     [6.05, 6.75, 7.95, 13.85, 16.15, 18.45, 20.75, 23.65]),
    (1.5,   [6.15, 6.85, 8.05, 14.15, 16.45, 18.85, 21.15, 24.65]),
    (2,     [6.25, 6.95, 8.15, 14.45, 16.85, 19.25, 21.65, 24.65]),
    (3,     [6.35, 7.95, 8.55, 15.75, 18.35, 21.05, 23.65, 26.25]),
    (4,     [6.45, 8.15, 8.95, 17.05, 19.85, 22.65, 25.55, 28.35]),
    (5,     [6.55, 8.35, 9.75, 18.45, 21.55, 24.65, 27.75, 30.75]),
    (6,     [6.65, 8.55, 9.95, 25.45, 28.55, 32.65, 35.75, 39.75]),
    (7,     [6.75, 8.75, 10.15, 27.05, 31.05, 36.05, 40.05, 44.05]),
    (8,     [6.85, 8.95, 10.35, 28.85, 33.65, 38.45, 43.25, 48.05]),
    (9,     [6.95, 9.15, 10.55, 29.65, 34.55, 39.55, 44.45, 49.35]),
    (11,    [7.05, 9.55, 10.95, 41.25, 48.05, 54.95, 61.75, 68.65]),
    (13,    [7.15, 9.95, 11.35, 42.15, 49.25, 56.25, 63.25, 70.25]),
    (15,    [7.25, 10.15, 11.55, 45.05, 52.45, 59.95, 67.45, 74.95]),
    (17,    [7.35, 10.35, 11.75, 48.55, 56.05, 63.55, 70.75, 78.65]),
    (20,    [7.45, 10.55, 11.95, 54.75, 63.85, 72.95, 82.05, 91.15]),
    (25,    [7.65, 10.95, 12.15, 64.05, 75.05, 84.75, 95.35, 105.95]),
    (30,    [7.75, 11.15, 12.35, 65.95, 75.45, 85.55, 96.25, 106.95]),
    (40,    [7.85, 11.35, 12.55, 67.75, 78.95, 88.95, 99.15, 107.05]),
    (50,    [7.95, 11.55, 12.75, 70.25, 81.05, 92.05, 102.55, 110.75]),
    (60,    [8.05, 11.75, 12.95, 74.95, 86.45, 98.15, 109.35, 118.15]),
    (70,    [8.15, 11.95, 13.15, 80.25, 92.95, 105.05, 117.15, 126.55]),
    (80,    [8.25, 12.15, 13.35, 83.95, 97.05, 109.85, 122.45, 132.25]),
    (90,    [8.35, 12.35, 13.55, 93.25, 107.45, 122.05, 136.05, 146.95]),
    (100,   [8.45, 12.55, 13.75, 106.55, 123.95, 139.55, 155.55, 167.95]),
    (125,   [8.55, 12.75, 13.95, 119.25, 138.05, 156.05, 173.95, 187.95]),
    (150,   [8.65, 12.75, 14.15, 126.55, 146.15, 165.65, 184.65, 199.45]),
    (999999,[8.75, 12.95, 14.35, 166.15, 192.45, 217.55, 242.55, 261.95]),
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
