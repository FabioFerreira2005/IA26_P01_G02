
from datetime import datetime
from model import Problem
from pesquisa import (
    selecionar_itens_veiculo_dia,
    comparar_algoritmos
)

# Carregar os dados
problem = Problem("docs/data_tiny")

# Escolher o primeiro dia presente nos dados
dia = min(
    pedido.dia_recolha
    for pedido in problem.pedidos.values()
)

# Selecionar duas encomendas completas para um teste
itens = selecionar_itens_veiculo_dia(
    problem,
    vehicle_id=1,
    dia=dia,
    max_encomendas=2
)

if not itens:
    print("Não existem encomendas elegíveis para este teste.")
else:
    hora_partida = min(
        problem.pedidos[i].availability_start
        for i in itens
    )

    tabela, detalhes = comparar_algoritmos(
        problem,
        vehicle_id=1,
        itens_objetivo=itens,
        hora_partida=hora_partida,
        max_nos_expandidos=50000
    )

    print(tabela.to_string(index=False))

    # Mostrar as rotas com os nomes dos locais
    for nome, resultado in detalhes.items():
        if resultado["sucesso"]:
            rota = [
                problem.paragens[p]["nome"]
                for p in resultado["rota_paragens"]
            ]

            print(f"\n{nome}")
            print("Rota:", " -> ".join(rota))
            print("Ações:", resultado["acoes"])
