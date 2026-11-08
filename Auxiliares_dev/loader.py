"""
loader.py — leitura e preparação dos dados do projeto.

Funções:
    carregar_dados(pasta)          lê os 12 CSVs de uma pasta (parsing das datas incluído)
    construir_pedidos(dados)       cria a tabela de pedidos de transporte (um por item)
    paragem_armazem(dados)         devolve o location_id do armazém
    matriz_paragens(dados, coluna) devolve a matriz origem x destino de km ou minutos
    criar_estruturas(dados)        converte as tabelas em dicionários e listas para os algoritmos
"""
import pandas as pd

# colunas de order_items que têm de ser convertidas de texto para data e hora
COLUNAS_DATA = ["availability_start", "availability_end", "delivery_start", "delivery_end"]


def carregar_dados(pasta):
    """Lê todos os ficheiros CSV de uma pasta e devolve um dicionário {nome: DataFrame}."""
    dados = {}
    dados["localities"]         = pd.read_csv(pasta + "localities.csv")
    dados["producers"]          = pd.read_csv(pasta + "producers.csv")
    dados["products"]           = pd.read_csv(pasta + "products.csv")
    dados["collection_centers"] = pd.read_csv(pasta + "collection_centers.csv")
    dados["vehicles"]           = pd.read_csv(pasta + "vehicles.csv")
    dados["customers"]          = pd.read_csv(pasta + "customers.csv")
    dados["delivery_locations"] = pd.read_csv(pasta + "delivery_locations.csv")
    dados["orders"]             = pd.read_csv(pasta + "orders.csv", parse_dates=["order_datetime"])
    dados["order_items"]        = pd.read_csv(pasta + "order_items.csv", parse_dates=COLUNAS_DATA)
    dados["locations"]          = pd.read_csv(pasta + "locations.csv")
    dados["distance_matrix"]    = pd.read_csv(pasta + "distance_matrix.csv")
    dados["rules"]              = pd.read_csv(pasta + "rules.csv")
    return dados


def paragem_armazem(dados):
    """Devolve o location_id do centro de recolha (armazém)."""
    locations = dados["locations"]
    armazem = locations[locations["location_type"] == "collection_center"]
    return int(armazem["location_id"].iloc[0])


def construir_pedidos(dados):
    """
    Cria a tabela de pedidos de transporte: uma linha por item, com o produtor,
    o local de entrega, as paragens de recolha e de entrega (location_id usado
    na matriz de distâncias) e o dia de recolha e de entrega.
    """
    products = dados["products"]
    orders = dados["orders"]
    locations = dados["locations"]

    # produtor de cada produto e local de entrega de cada encomenda
    pedidos = dados["order_items"].merge(products[["product_id", "producer_id", "name"]], on="product_id")
    pedidos = pedidos.merge(orders[["order_id", "delivery_location_id"]], on="order_id")

    # location_id de cada produtor
    paragens_produtores = locations[locations["location_type"] == "producer"]
    paragens_produtores = paragens_produtores[["ref_id", "location_id"]].rename(
        columns={"ref_id": "producer_id", "location_id": "paragem_recolha"})
    pedidos = pedidos.merge(paragens_produtores, on="producer_id")

    # location_id de cada local de entrega
    paragens_entrega = locations[locations["location_type"] == "delivery_location"]
    paragens_entrega = paragens_entrega[["ref_id", "location_id"]].rename(
        columns={"ref_id": "delivery_location_id", "location_id": "paragem_entrega"})
    pedidos = pedidos.merge(paragens_entrega, on="delivery_location_id")

    # dia de recolha e dia de entrega de cada item
    pedidos["dia_recolha"] = pedidos["availability_start"].dt.date
    pedidos["dia_entrega"] = pedidos["delivery_start"].dt.date

    return pedidos.sort_values("order_item_id").reset_index(drop=True)


def matriz_paragens(dados, coluna):
    """
    Devolve uma tabela origem x destino com os valores de `coluna`
    ("distance_km" ou "duration_min"). A diagonal (de uma paragem para si própria) é 0.
    """
    matriz = dados["distance_matrix"].pivot(index="origin_location_id",
                                            columns="destination_location_id",
                                            values=coluna)
    return matriz.fillna(0)


def criar_estruturas(dados):
    """
    Converte as tabelas em estruturas simples do Python (dicionários e listas),
    prontas a usar pelos algoritmos de pesquisa e pelo CSP:

        paragens   {location_id: {"tipo", "nome", "latitude", "longitude"}}
        veiculos   {vehicle_id: {"capacidade_kg", "refrigerado"}}
        pedidos    [ {"item", "encomenda", "produto", "peso_kg", "recolha", "entrega",
                      "recolha_inicio", "recolha_fim", "entrega_inicio", "entrega_fim"}, ... ]
        distancia  {(origem, destino): km}
        tempo      {(origem, destino): minutos}
        regras     {nome da regra: valor}
    """
    estruturas = {}

    # paragens: location_id -> dados da paragem
    estruturas["paragens"] = {}
    for _, paragem in dados["locations"].iterrows():
        estruturas["paragens"][int(paragem["location_id"])] = {
            "tipo": paragem["location_type"],
            "nome": paragem["name"],
            "latitude": float(paragem["latitude"]),
            "longitude": float(paragem["longitude"]),
        }

    # veículos: vehicle_id -> capacidade e se é refrigerado
    estruturas["veiculos"] = {}
    for _, veiculo in dados["vehicles"].iterrows():
        estruturas["veiculos"][int(veiculo["vehicle_id"])] = {
            "capacidade_kg": float(veiculo["capacity_kg"]),
            "refrigerado": bool(veiculo["refrigerated"]),
        }

    # pedidos: um dicionário por item, com as paragens e as janelas temporais
    estruturas["pedidos"] = []
    for _, item in construir_pedidos(dados).iterrows():
        estruturas["pedidos"].append({
            "item": int(item["order_item_id"]),
            "encomenda": int(item["order_id"]),
            "produto": item["name"],
            "peso_kg": float(item["weight_kg"]),
            "recolha": int(item["paragem_recolha"]),
            "entrega": int(item["paragem_entrega"]),
            "recolha_inicio": item["availability_start"].to_pydatetime(),
            "recolha_fim": item["availability_end"].to_pydatetime(),
            "entrega_inicio": item["delivery_start"].to_pydatetime(),
            "entrega_fim": item["delivery_end"].to_pydatetime(),
        })

    # distância e tempo: (origem, destino) -> valor
    estruturas["distancia"] = {}
    estruturas["tempo"] = {}
    for _, par in dados["distance_matrix"].iterrows():
        chave = (int(par["origin_location_id"]), int(par["destination_location_id"]))
        estruturas["distancia"][chave] = float(par["distance_km"])
        estruturas["tempo"][chave] = float(par["duration_min"])
    for paragem in estruturas["paragens"]:              # de uma paragem para si própria: 0
        estruturas["distancia"][(paragem, paragem)] = 0.0
        estruturas["tempo"][(paragem, paragem)] = 0.0

    # regras: os valores vêm como texto; os que são números passam a float
    estruturas["regras"] = {}
    for _, regra in dados["rules"].iterrows():
        valor = regra["value"]
        try:
            valor = float(valor)                       # ex.: "10" -> 10.0
        except ValueError:
            pass                                       # ex.: "service_start" fica como texto
        estruturas["regras"][regra["rule"]] = valor

    return estruturas
