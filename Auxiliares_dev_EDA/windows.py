"""
windows.py — cálculos com as janelas temporais.

Funções:
    hora_decimal(data)             hora do dia em número decimal (09:45 -> 9.75)
    duracao_horas(inicio, fim)     duração de cada janela, em horas
    tempo_viagem(minutos, a, b)    minutos de viagem entre duas paragens
    calcular_folgas(...)           folga no melhor caso dos itens entregues no próprio dia (direto e com armazém)
    calcular_permanencias(...)     permanência mínima e máxima no armazém dos itens entregues no dia seguinte
"""
import pandas as pd


def hora_decimal(data):
    """Converte uma data na hora do dia em número decimal (ex.: 09:45 -> 9.75)."""
    return data.hour + data.minute / 60


def duracao_horas(inicio, fim):
    """Duração, em horas, entre duas colunas de datas."""
    return (fim - inicio).dt.total_seconds() / 3600


def tempo_viagem(minutos, origem, destino):
    """Minutos de viagem entre duas paragens, lidos da matriz de tempos."""
    return minutos.loc[origem, destino]


def calcular_folgas(pedidos, minutos, armazem, tempo_servico, tempo_armazem):
    """
    Para os itens recolhidos e entregues no mesmo dia, calcula a folga no melhor caso:
    o veículo recolhe assim que o produto fica disponível e segue sem desvios.
    Folga = fecho da janela de entrega - hora de chegada (em minutos).
    São calculados dois percursos:
      - direto:       produtor -> cliente (sem as regras, apenas para comparação);
      - com armazém:  produtor -> armazém -> cliente (o percurso obrigatório).
    """
    linhas = []
    for _, item in pedidos.iterrows():
        if item["dia_recolha"] == item["dia_entrega"]:
            duracao = (tempo_servico                                                # recolha no produtor
                       + tempo_viagem(minutos, item["paragem_recolha"], armazem)    # viagem até ao armazém
                       + 2 * tempo_armazem                                           # descarregar + carregar
                       + tempo_viagem(minutos, armazem, item["paragem_entrega"]))   # viagem até ao cliente
            chegada = item["availability_start"] + pd.Timedelta(minutes=duracao)
            folga = (item["delivery_end"] - chegada).total_seconds() / 60

            # comparação: ir diretamente do produtor ao cliente, sem passar pelo armazém
            duracao_direta = tempo_viagem(minutos, item["paragem_recolha"], item["paragem_entrega"])
            chegada_direta = item["availability_start"] + pd.Timedelta(minutes=duracao_direta)
            folga_direta = (item["delivery_end"] - chegada_direta).total_seconds() / 60

            linhas.append({"item": item["order_item_id"], "duracao_min": round(duracao, 1),
                           "chegada": chegada.round("min"), "fecho_entrega": item["delivery_end"],
                           "folga_direta_min": round(folga_direta, 1), "folga_min": round(folga, 1)})
    return pd.DataFrame(linhas).sort_values("folga_min")


def calcular_permanencias(pedidos, minutos, armazem, tempo_servico, tempo_armazem):
    """
    Para os itens entregues no dia seguinte, calcula quanto tempo (em horas) podem
    ficar no armazém, entre a chegada e o início do carregamento:
      - mínima: recolher o mais tarde possível e carregar só a tempo da abertura da entrega;
      - máxima: recolher o mais cedo possível e carregar o mais tarde possível.
    """
    linhas = []
    for _, item in pedidos.iterrows():
        if item["dia_recolha"] != item["dia_entrega"]:
            ida = tempo_servico + tempo_viagem(minutos, item["paragem_recolha"], armazem)    # recolha + viagem
            volta = tempo_armazem + tempo_viagem(minutos, armazem, item["paragem_entrega"])  # carregar + viagem

            chega_cedo = item["availability_start"] + pd.Timedelta(minutes=ida)
            chega_tarde = item["availability_end"] + pd.Timedelta(minutes=ida)
            carrega_cedo = item["delivery_start"] - pd.Timedelta(minutes=volta)
            carrega_tarde = item["delivery_end"] - pd.Timedelta(minutes=volta)

            minima = (carrega_cedo - chega_tarde).total_seconds() / 3600
            maxima = (carrega_tarde - chega_cedo).total_seconds() / 3600
            linhas.append({"item": item["order_item_id"], "encomenda": item["order_id"],
                           "permanencia_min_h": round(minima, 2), "permanencia_max_h": round(maxima, 2)})
    return pd.DataFrame(linhas)
