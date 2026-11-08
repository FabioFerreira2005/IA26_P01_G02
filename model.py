"""
Módulo model.py — Modelação do problema de routing para distribuição de produtos locais.
Inteligência Artificial 2026/27 · Licenciatura em Engenharia de Sistemas Informáticos (UPCA)
Trabalho Prático 1 · Feito por Grupo 02 (IA26_P01_G02)

Conteúdo:
  1. Leitura e parsing dos dados
  2. Classes do modelo: Request, Vehicle, Problem, State
     - Problem.verificar_viabilidade: verifica UMA rota de um veículo
     - verificar_solucao: verifica uma solução completa (várias rotas e veículos)
  3. Testes manuais (os testes automáticos com assert estão em testes_modelo.py)

É o entregável da modelação pedido no guia ("model.py module + tests with hand-written
routes"). As heurísticas e os algoritmos (pesquisa informada, pesquisa local e CSP) estão
no notebook principal IA26_P01_G02.ipynb, como pede o guia ("code and documentation
merged into a Jupyter Notebook").

"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, FrozenSet, List, Optional, Set, Tuple
import pandas as pd


COLUNAS_DATA = [
    "availability_start",
    "availability_end",
    "delivery_start",
    "delivery_end",
]


# =====================================================================
# 1. FUNÇÕES DE LEITURA E PARSING DOS DADOS
# =====================================================================

def carregar_dados(pasta: str) -> Dict[str, pd.DataFrame]:
    """Lê os 12 ficheiros CSV de uma pasta e devolve um dicionário {nome: DataFrame}."""
    if not pasta.endswith("/"):
        pasta += "/"

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


def paragem_armazem(dados: Dict[str, pd.DataFrame]) -> int:
    """Devolve o location_id do centro de recolha (armazém)."""
    locations = dados["locations"]
    armazem = locations[locations["location_type"] == "collection_center"]
    return int(armazem["location_id"].iloc[0])


def construir_pedidos(dados: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Cria a tabela consolidada de pedidos de transporte: uma linha por item,
    com produtor, local de entrega, peso e paragens (location_id).
    """
    products = dados["products"]
    orders = dados["orders"]
    locations = dados["locations"]
    items = dados["order_items"].copy()

    pedidos = items.merge(
        products[["product_id", "producer_id", "name", "unit_weight_kg"]],
        on="product_id",
        how="left",
    )
    if "weight_kg" not in pedidos.columns:
        pedidos["weight_kg"] = pedidos["quantity"] * pedidos["unit_weight_kg"]

    pedidos = pedidos.merge(
        orders[["order_id", "delivery_location_id", "status"]],
        on="order_id",
        how="left",
    )

    paragens_produtores = locations[locations["location_type"] == "producer"][
        ["ref_id", "location_id"]
    ].rename(columns={"ref_id": "producer_id", "location_id": "paragem_recolha"})
    pedidos = pedidos.merge(paragens_produtores, on="producer_id", how="left")

    paragens_entrega = locations[locations["location_type"] == "delivery_location"][
        ["ref_id", "location_id"]
    ].rename(columns={"ref_id": "delivery_location_id", "location_id": "paragem_entrega"})
    pedidos = pedidos.merge(paragens_entrega, on="delivery_location_id", how="left")

    pedidos["dia_recolha"] = pedidos["availability_start"].dt.date
    pedidos["dia_entrega"] = pedidos["delivery_start"].dt.date

    return pedidos.sort_values("order_item_id").reset_index(drop=True)


# =====================================================================
# 2. CLASSES DO MODELO: Request, Vehicle, Problem, State
# =====================================================================

"""Request e Vehicle: Classes imutáveis (@dataclass(frozen=True)) que guardam os dados de 
cada item de encomenda (IDs, peso, paragens e janelas temporais)
e de cada veículo (capacidade máxima em kg, refrigeração e velocidade)."""

@dataclass(frozen=True)
class Request:
    """Representa um pedido de transporte correspondente a um item de encomenda."""
    item_id: int
    order_id: int
    product_name: str
    weight_kg: float
    pickup_loc: int
    delivery_loc: int
    availability_start: datetime
    availability_end: datetime
    delivery_start: datetime
    delivery_end: datetime

    @property
    def dia_recolha(self):
        return self.availability_start.date()

    @property
    def dia_entrega(self):
        return self.delivery_start.date()


@dataclass(frozen=True)
class Vehicle:
    """Representa um veículo da frota sediado no centro de recolha."""
    vehicle_id: int
    plate: str
    capacity_kg: float
    refrigerated: bool
    avg_speed_kmh: float
    center_loc: int

"""Problem: Recebe o caminho da pasta ("docs/data_tiny/" ou "docs/data_small_30_31oct2026/"), carrega os 
12 ficheiros CSV e cria os dicionários de consulta rápida (paragens, veiculos, pedidos, distancia, tempo e regras)."""

class Problem:
    """
    Guarda todos os dados da instância (paragens, veículos, pedidos, matrizes de
    distância/tempo e regras operacionais) e disponibiliza a função de custo e
    o verificador de viabilidade de rotas.
    """

    def __init__(self, pasta: str):
        dados = carregar_dados(pasta)
        self.armazem: int = paragem_armazem(dados)

        # 1. Dicionário de paragens: location_id -> metadados
        self.paragens: Dict[int, dict] = {}
        for _, p in dados["locations"].iterrows():
            self.paragens[int(p["location_id"])] = {
                "tipo": p["location_type"],
                "nome": p["name"],
                "latitude": float(p["latitude"]),
                "longitude": float(p["longitude"]),
            }

        # 2. Dicionário de regras: rule -> valor (float ou str)
        self.regras: Dict[str, object] = {}
        for _, r in dados["rules"].iterrows():
            val = r["value"]
            try:
                val = float(val)
            except ValueError:
                pass
            self.regras[r["rule"]] = val

        self.tempo_servico_min: float = float(self.regras.get("stop_service_min", 10.0))
        self.tempo_armazem_min: float = float(self.regras.get("warehouse_handling_min", 15.0))
        self.permanencia_max_h: float = float(self.regras.get("max_warehouse_dwell_h", 24.0))

        # 3. Dicionário de veículos: vehicle_id -> objeto Vehicle
        self.veiculos: Dict[int, Vehicle] = {}
        for _, v in dados["vehicles"].iterrows():
            vid = int(v["vehicle_id"])
            self.veiculos[vid] = Vehicle(
                vehicle_id=vid,
                plate=str(v["plate"]),
                capacity_kg=float(v["capacity_kg"]),
                refrigerated=bool(v["refrigerated"]),
                avg_speed_kmh=float(v["avg_speed_kmh"]),
                center_loc=self.armazem,
            )

        # 4. Dicionário de pedidos: item_id -> objeto Request
        self.pedidos: Dict[int, Request] = {}
        tabela_pedidos = construir_pedidos(dados)
        for _, item in tabela_pedidos.iterrows():
            iid = int(item["order_item_id"])
            self.pedidos[iid] = Request(
                item_id=iid,
                order_id=int(item["order_id"]),
                product_name=str(item["name"]),
                weight_kg=float(item["weight_kg"]),
                pickup_loc=int(item["paragem_recolha"]),
                delivery_loc=int(item["paragem_entrega"]),
                availability_start=item["availability_start"].to_pydatetime(),
                availability_end=item["availability_end"].to_pydatetime(),
                delivery_start=item["delivery_start"].to_pydatetime(),
                delivery_end=item["delivery_end"].to_pydatetime(),
            )

        # 5. Matrizes de distância (km) e tempo (min): (origem, destino) -> float
        self.distancia: Dict[Tuple[int, int], float] = {}
        self.tempo: Dict[Tuple[int, int], float] = {}
        for _, par in dados["distance_matrix"].iterrows():
            chave = (int(par["origin_location_id"]), int(par["destination_location_id"]))
            self.distancia[chave] = float(par["distance_km"])
            self.tempo[chave] = float(par["duration_min"])
        for loc_id in self.paragens:
            self.distancia[(loc_id, loc_id)] = 0.0
            self.tempo[(loc_id, loc_id)] = 0.0

        # Matriz de distâncias mínimas: serve apenas como limite inferior
        # para a heurística. O custo real das rotas continua a usar self.distancia.
        locais = list(self.paragens)
        infinito = float("inf")
        self.distancia_minima: Dict[Tuple[int, int], float] = {
            (origem, destino): (
                0.0 if origem == destino
                else self.distancia.get((origem, destino), infinito)
            )
            for origem in locais
            for destino in locais
        }

        # Floyd-Warshall: corrige pequenas violações da desigualdade triangular
        # causadas pelo arredondamento da matriz original.
        for interm in locais:
            for origem in locais:
                dist_origem_interm = self.distancia_minima[(origem, interm)]
                if dist_origem_interm == infinito:
                    continue
                for destino in locais:
                    alternativa = (
                        dist_origem_interm
                        + self.distancia_minima[(interm, destino)]
                    )
                    chave = (origem, destino)
                    if alternativa < self.distancia_minima[chave]:
                        self.distancia_minima[chave] = alternativa

    def distancia_entre(self, origem: int, destino: int) -> float:
        """Devolve a distância em km entre duas paragens."""
        return self.distancia[(origem, destino)]

    def tempo_entre(self, origem: int, destino: int) -> float:
        """Devolve o tempo de condução em minutos entre duas paragens."""
        return self.tempo[(origem, destino)]

    def distancia_inferior_entre(self, origem: int, destino: int) -> float:
        """Devolve uma distância mínima, usada como limite inferior na heurística."""
        return self.distancia_minima[(origem, destino)]

    # -----------------------------------------------------------------
    # FUNÇÃO DE CUSTO
    # -----------------------------------------------------------------
    
    """custo_rota(paragens_rota): Calcula a distância total (distancia_km) e o tempo de 
    condução (tempo_viagem_min) entre uma lista sequencial de paragens."""
    
    def custo_rota(self, paragens_rota: List[int]) -> Dict[str, float]:
        """
        Calcula o custo de uma sequência de paragens [p0, p1, ..., pk]:
          - distancia_km: soma das distâncias percorridas entre paragens consecutivas
          - tempo_viagem_min: soma dos tempos de condução entre paragens consecutivas
        """
        if len(paragens_rota) < 2:
            return {"distancia_km": 0.0, "tempo_viagem_min": 0.0}

        dist_total = 0.0
        tempo_total = 0.0
        for a, b in zip(paragens_rota[:-1], paragens_rota[1:]):
            dist_total += self.distancia[(a, b)]
            tempo_total += self.tempo[(a, b)]

        return {
            "distancia_km": round(dist_total, 2),
            "tempo_viagem_min": round(tempo_total, 2),
        }

    # -----------------------------------------------------------------
    # VERIFICADOR DE VIABILIDADE DE UMA ROTA
    # -----------------------------------------------------------------
    
    """verificar_viabilidade(vehicle_id, acoes, hora_partida): Simula a rota passo a passo 
    (pickup, warehouse, load, delivery) e verifica todas as restrições: limite de carga do veículo, fluxo obrigatório 
    produtor → armazém → cliente, tempos de serviço (10 min por paragem e 15 min para descarregar/carregar no armazém), 
    janelas temporais (service_start) e permanência máxima de 24 h no armazém."""
    
    def verificar_viabilidade(
        self,
        vehicle_id: int,
        acoes: List[Tuple[str, int]],
        hora_partida: datetime,
        chegada_armazem_previa: Optional[Dict[int, datetime]] = None,
        itens_objetivo: Optional[Set[int]] = None,
        exigir_rota_completa: bool = False,
    ) -> Dict[str, object]:
        """
        Simula uma rota mantendo o formato atual das ações:
          ("pickup", item_id), ("warehouse", armazem_id),
          ("load", item_id), ("delivery", item_id).

        Ações consecutivas de pickup/delivery na mesma localização são tratadas
        como uma única visita (10 min de serviço). Ações consecutivas de load
        são tratadas como um único lote (15 min de manuseamento).

        Por omissão, valida também rotas parciais. Para exigir uma rota completa,
        usar exigir_rota_completa=True e, preferencialmente, indicar itens_objetivo.
        """
        if vehicle_id not in self.veiculos:
            raise KeyError(f"Veículo desconhecido: {vehicle_id}")

        veiculo = self.veiculos[vehicle_id]
        erros: List[str] = []

        paragem_atual = self.armazem
        relogio = hora_partida
        carga_atual = 0.0
        distancia_total = 0.0

        na_carrinha_recolhidos: Set[int] = set()
        na_carrinha_para_entrega: Set[int] = set()
        no_armazem: Dict[int, datetime] = (
            dict(chegada_armazem_previa) if chegada_armazem_previa else {}
        )
        entregues: Set[int] = set()

        # Caso não seja fornecido um conjunto explícito, consideramos como
        # objetivo os itens mencionados nas ações desta rota.
        if itens_objetivo is None:
            itens_objetivo = {
                alvo for acao, alvo in acoes
                if acao in {"pickup", "load", "delivery"}
            }
        else:
            itens_objetivo = set(itens_objetivo)

        def deslocar(destino: int) -> None:
            """Atualiza relógio, distância e localização após uma deslocação."""
            nonlocal paragem_atual, relogio, distancia_total
            if paragem_atual != destino:
                relogio += timedelta(minutes=self.tempo_entre(paragem_atual, destino))
                distancia_total += self.distancia_entre(paragem_atual, destino)
                paragem_atual = destino

        i = 0
        while i < len(acoes):
            acao, alvo = acoes[i]

            # -------------------------------------------------------------
            # PICKUP: agrupar ações consecutivas no mesmo produtor.
            # -------------------------------------------------------------
            if acao == "pickup":
                if alvo not in self.pedidos:
                    erros.append(f"Item desconhecido na recolha: {alvo}.")
                    i += 1
                    continue

                destino = self.pedidos[alvo].pickup_loc
                grupo: List[Request] = []
                j = i
                while j < len(acoes) and acoes[j][0] == "pickup":
                    item_id = acoes[j][1]
                    if item_id not in self.pedidos:
                        break
                    req = self.pedidos[item_id]
                    if req.pickup_loc != destino:
                        break
                    grupo.append(req)
                    j += 1
                i = j

                candidatos: List[Request] = []
                ids_grupo: Set[int] = set()
                for req in grupo:
                    if req.item_id in ids_grupo:
                        erros.append(f"Item {req.item_id}: recolha repetida na mesma rota.")
                        continue
                    ids_grupo.add(req.item_id)
                    if (
                        req.item_id in na_carrinha_recolhidos
                        or req.item_id in no_armazem
                        or req.item_id in na_carrinha_para_entrega
                        or req.item_id in entregues
                    ):
                        erros.append(f"Item {req.item_id}: o produto já foi recolhido ou entregue.")
                        continue
                    candidatos.append(req)

                if not candidatos:
                    continue

                deslocar(destino)

                # A janela limita o INÍCIO do serviço. Como é uma única visita,
                # o início comum tem de respeitar todas as janelas do grupo.
                inicio_servico = max(
                    [relogio] + [req.availability_start for req in candidatos]
                )
                validos = [req for req in candidatos if inicio_servico <= req.availability_end]
                for req in candidatos:
                    if inicio_servico > req.availability_end:
                        erros.append(
                            f"Item {req.item_id}: recolha não cabe na janela; "
                            f"o serviço começaria às {inicio_servico:%d/%m %H:%M}, "
                            f"mas a janela fecha às {req.availability_end:%d/%m %H:%M}."
                        )

                if validos:
                    relogio = inicio_servico + timedelta(minutes=self.tempo_servico_min)
                    for req in validos:
                        carga_atual += req.weight_kg
                        na_carrinha_recolhidos.add(req.item_id)
                        if carga_atual > veiculo.capacity_kg + 1e-6:
                            erros.append(
                                f"Item {req.item_id}: excesso de capacidade no veículo {vehicle_id} "
                                f"({carga_atual:.1f} kg > {veiculo.capacity_kg:.1f} kg)."
                            )
                continue

            # -------------------------------------------------------------
            # WAREHOUSE: regressar ao armazém e descarregar as recolhas.
            # -------------------------------------------------------------
            if acao == "warehouse":
                if alvo != self.armazem:
                    erros.append(
                        f"Ação warehouse inválida: foi indicado {alvo}, "
                        f"mas o armazém é {self.armazem}."
                    )
                    i += 1
                    continue

                deslocar(self.armazem)

                if na_carrinha_recolhidos:
                    # A permanência no armazém começa na chegada, antes dos
                    # 15 minutos de descarga. Todos os itens deste lote partilham
                    # a mesma hora de chegada.
                    hora_chegada = relogio
                    relogio += timedelta(minutes=self.tempo_armazem_min)
                    for item_id in list(na_carrinha_recolhidos):
                        no_armazem[item_id] = hora_chegada
                        carga_atual -= self.pedidos[item_id].weight_kg
                    na_carrinha_recolhidos.clear()
                i += 1
                continue

            # -------------------------------------------------------------
            # LOAD: agrupar ações consecutivas de carregamento num lote.
            # -------------------------------------------------------------
            if acao == "load":
                grupo_ids: List[int] = []
                j = i
                while j < len(acoes) and acoes[j][0] == "load":
                    grupo_ids.append(acoes[j][1])
                    j += 1
                i = j

                if paragem_atual != self.armazem:
                    for item_id in grupo_ids:
                        erros.append(
                            f"Item {item_id}: tentativa de carregar fora do armazém "
                            f"(paragem {paragem_atual})."
                        )
                    continue

                # O prazo das 24 h termina quando o carregamento COMEÇA,
                # não depois de terminarem os 15 minutos de manuseamento.
                inicio_carregamento = relogio
                candidatos: List[Request] = []
                ids_grupo = set()

                for item_id in grupo_ids:
                    if item_id not in self.pedidos:
                        erros.append(f"Item desconhecido no carregamento: {item_id}.")
                        continue
                    req = self.pedidos[item_id]

                    if item_id in ids_grupo:
                        erros.append(f"Item {item_id}: carregamento repetido no mesmo lote.")
                        continue
                    ids_grupo.add(item_id)

                    if item_id not in no_armazem:
                        erros.append(
                            f"Item {item_id}: não se encontra no armazém para carregamento "
                            f"(violação do fluxo produtor -> armazém -> cliente)."
                        )
                        continue

                    hora_chegada = no_armazem[item_id]
                    permanencia_h = (inicio_carregamento - hora_chegada).total_seconds() / 3600.0
                    if permanencia_h < -1e-6:
                        erros.append(
                            f"Item {item_id}: hora de carregamento anterior à chegada ao armazém."
                        )
                        continue
                    if permanencia_h > self.permanencia_max_h + 1e-6:
                        erros.append(
                            f"Item {item_id}: permanência no armazém ({permanencia_h:.2f} h) "
                            f"excede o máximo de {self.permanencia_max_h:.1f} h."
                        )
                        continue

                    candidatos.append(req)

                if candidatos:
                    # Os 15 minutos são contados uma vez para o lote inteiro.
                    relogio += timedelta(minutes=self.tempo_armazem_min)
                    for req in candidatos:
                        del no_armazem[req.item_id]
                        carga_atual += req.weight_kg
                        na_carrinha_para_entrega.add(req.item_id)
                        if carga_atual > veiculo.capacity_kg + 1e-6:
                            erros.append(
                                f"Item {req.item_id}: excesso de capacidade ao carregar no armazém "
                                f"({carga_atual:.1f} kg > {veiculo.capacity_kg:.1f} kg)."
                            )
                continue

            # -------------------------------------------------------------
            # DELIVERY: agrupar ações consecutivas na mesma localização.
            # -------------------------------------------------------------
            if acao == "delivery":
                if alvo not in self.pedidos:
                    erros.append(f"Item desconhecido na entrega: {alvo}.")
                    i += 1
                    continue

                destino = self.pedidos[alvo].delivery_loc
                grupo: List[Request] = []
                j = i
                while j < len(acoes) and acoes[j][0] == "delivery":
                    item_id = acoes[j][1]
                    if item_id not in self.pedidos:
                        break
                    req = self.pedidos[item_id]
                    if req.delivery_loc != destino:
                        break
                    grupo.append(req)
                    j += 1
                i = j

                candidatos: List[Request] = []
                ids_grupo: Set[int] = set()
                for req in grupo:
                    if req.item_id in ids_grupo:
                        erros.append(f"Item {req.item_id}: entrega repetida na mesma rota.")
                        continue
                    ids_grupo.add(req.item_id)
                    if req.item_id not in na_carrinha_para_entrega:
                        erros.append(
                            f"Item {req.item_id}: tentativa de entrega sem ter sido previamente "
                            f"recolhido e carregado no armazém."
                        )
                        continue
                    candidatos.append(req)

                if not candidatos:
                    continue

                deslocar(destino)
                inicio_servico = max(
                    [relogio] + [req.delivery_start for req in candidatos]
                )
                validos = [req for req in candidatos if inicio_servico <= req.delivery_end]
                for req in candidatos:
                    if inicio_servico > req.delivery_end:
                        erros.append(
                            f"Item {req.item_id}: entrega não cabe na janela; "
                            f"o serviço começaria às {inicio_servico:%d/%m %H:%M}, "
                            f"mas a janela fecha às {req.delivery_end:%d/%m %H:%M}."
                        )

                if validos:
                    relogio = inicio_servico + timedelta(minutes=self.tempo_servico_min)
                    for req in validos:
                        carga_atual -= req.weight_kg
                        na_carrinha_para_entrega.remove(req.item_id)
                        entregues.add(req.item_id)
                continue

            erros.append(f"Ação desconhecida: {acao}")
            i += 1

        duracao_total_min = (relogio - hora_partida).total_seconds() / 60.0

        # Uma rota completa tem de entregar todos os itens-alvo e terminar
        # no armazém, sem carga desses itens ainda a bordo ou armazenada.
        itens_pendentes = (
            set(no_armazem)
            | na_carrinha_recolhidos
            | na_carrinha_para_entrega
        ) & itens_objetivo
        completa = (
            itens_objetivo.issubset(entregues)
            and not itens_pendentes
            and paragem_atual == self.armazem
            and abs(carga_atual) <= 1e-6
        )

        if exigir_rota_completa and not completa:
            erros.append(
                "Rota incompleta: faltam itens por entregar ou o veículo não regressou ao armazém."
            )

        return {
            "viavel": len(erros) == 0,
            "completa": completa,
            "erros": erros,
            "distancia_km": round(distancia_total, 2),
            "duracao_total_min": round(duracao_total_min, 1),
            "hora_fim": relogio,
            "carga_final_kg": round(carga_atual, 2),
            "entregues": entregues,
            "no_armazem": no_armazem,
        }


"""State: Representa o estado atual na árvore de pesquisa (paragem atual, relógio, carga a bordo, 
itens recolhidos/no armazém/entregues e distância acumulada), incluindo o método paragens_pendentes() para alimentar as heurísticas do Greedy e do A*."""

@dataclass(frozen=True)
class State:
    """
    Representa um estado na árvore de pesquisa (UCS, Greedy Best-First e A*).
    """
    paragem_atual: int
    tempo_atual: datetime
    carga_atual_kg: float = 0.0
    recolhidos_a_bordo: FrozenSet[int] = field(default_factory=frozenset)
    no_armazem: FrozenSet[int] = field(default_factory=frozenset)
    para_entrega_a_bordo: FrozenSet[int] = field(default_factory=frozenset)
    entregues: FrozenSet[int] = field(default_factory=frozenset)
    distancia_acumulada_km: float = 0.0
    historico_paragens: Tuple[int, ...] = field(default_factory=tuple)
    # Pares (item_id, hora_chegada_ao_armazem), necessários para validar as 24 h.
    # Fica no fim para não alterar a ordem dos argumentos posicionais já existentes.
    chegadas_armazem: Tuple[Tuple[int, datetime], ...] = field(default_factory=tuple)

    def hora_chegada_armazem(self, item_id: int) -> Optional[datetime]:
        """Devolve a hora a que um item chegou ao armazém, se ainda estiver registado."""
        return dict(self.chegadas_armazem).get(item_id)

    def paragens_pendentes(self, problem: Problem, itens_objetivo: Set[int],
                           so_recolher: Set[int] = frozenset()) -> Set[int]:
        """
        Devolve o conjunto de location_id que ainda falta visitar para concluir os itens_objetivo
        (itens a entregar) e os itens so_recolher (itens que só têm de chegar ao armazém hoje,
        porque são entregues no dia seguinte).
        """
        paragens = set()
        for iid in so_recolher:
            if iid in self.no_armazem:
                continue
            if iid not in self.recolhidos_a_bordo:
                paragens.add(problem.pedidos[iid].pickup_loc)
            paragens.add(problem.armazem)
        for iid in itens_objetivo:
            if iid in self.entregues:
                continue
            req = problem.pedidos[iid]
            if iid not in self.recolhidos_a_bordo and iid not in self.no_armazem and iid not in self.para_entrega_a_bordo:
                paragens.add(req.pickup_loc)
                paragens.add(problem.armazem)
                paragens.add(req.delivery_loc)
            elif iid in self.recolhidos_a_bordo:
                paragens.add(problem.armazem)
                paragens.add(req.delivery_loc)
            elif iid in self.no_armazem:
                paragens.add(problem.armazem)
                paragens.add(req.delivery_loc)
            elif iid in self.para_entrega_a_bordo:
                paragens.add(req.delivery_loc)
        return paragens

    def chave(self) -> tuple:
        """
        Identifica o estado para a deteção de estados repetidos na pesquisa.

        Inclui apenas o que influencia o futuro: posição, hora, itens a bordo,
        itens no armazém e itens entregues. NÃO inclui o histórico nem a distância
        acumulada (dois caminhos diferentes que chegam à mesma situação são o
        mesmo estado). A hora é incluída porque, com janelas temporais, chegar
        à mesma situação mais tarde não é equivalente a chegar mais cedo.
        """
        return (
            self.paragem_atual,
            self.tempo_atual,
            self.recolhidos_a_bordo,
            self.no_armazem,
            self.para_entrega_a_bordo,
            self.entregues,
        )

    def __lt__(self, other: "State") -> bool:
        return self.distancia_acumulada_km < other.distancia_acumulada_km

def verificar_solucao(
    problem: Problem,
    rotas: List[Tuple[int, List[Tuple[str, int]], datetime]],
    itens_objetivo: Optional[Set[int]] = None,
) -> Dict[str, object]:
    """
    Verifica uma solução completa, formada por várias rotas (de um ou mais veículos,
    em um ou mais dias). Cada rota é um tuplo (vehicle_id, acoes, hora_partida).

    As rotas são simuladas por ordem de hora de partida e partilham o armazém:
    um item descarregado por uma rota pode ser carregado por uma rota posterior
    (de outro veículo ou do dia seguinte), respeitando as 24 h de permanência.

    Para além das regras de cada rota, verifica que cada item-objetivo é
    entregue exatamente uma vez no conjunto das rotas.
    """
    if itens_objetivo is None:
        itens_objetivo = set(problem.pedidos)
    erros: List[str] = []
    armazem: Dict[int, datetime] = {}
    contagem_entregas: Dict[int, int] = {}
    distancia_total = 0.0

    for n, (vehicle_id, acoes, hora_partida) in enumerate(sorted(rotas, key=lambda r: r[2]), start=1):
        res = problem.verificar_viabilidade(
            vehicle_id, acoes, hora_partida, chegada_armazem_previa=armazem
        )
        for e in res["erros"]:
            erros.append(f"Rota {n} (veículo {vehicle_id}): {e}")
        if res["hora_fim"] and acoes and acoes[-1][0] != "warehouse":
            erros.append(f"Rota {n} (veículo {vehicle_id}): não termina no armazém.")
        armazem = res["no_armazem"]
        distancia_total += res["distancia_km"]
        for item_id in res["entregues"]:
            contagem_entregas[item_id] = contagem_entregas.get(item_id, 0) + 1

    for item_id in sorted(itens_objetivo):
        n_entregas = contagem_entregas.get(item_id, 0)
        if n_entregas == 0:
            erros.append(f"Item {item_id}: não foi entregue.")
        elif n_entregas > 1:
            erros.append(f"Item {item_id}: foi entregue {n_entregas} vezes.")

    return {
        "viavel": len(erros) == 0,
        "erros": erros,
        "distancia_km": round(distancia_total, 2),
    }


# =====================================================================
# 3. TESTES MANUAIS - para testar a função verificar_viabilidade
# =====================================================================

def executar_testes_manuais(pasta: str = "docs/data_small_30_31oct2026/"):
    """Executa testes de custo e viabilidade com rotas criadas manualmente."""
    prob = Problem(pasta)
    print(f"=== Instância carregada de: {pasta} ===")
    print(f"Paragens: {len(prob.paragens)} | Veículos: {len(prob.veiculos)} | Pedidos: {len(prob.pedidos)}")
    print(f"Armazém (location_id): {prob.armazem}\n")

    # Teste 1: Rota manual VIÁVEL (Recolher os 2 itens da Encomenda 1, passar no armazém e entregar)
    # Item 1 (produtor paragem 3, disp 07:45-10:45) e Item 2 (produtor paragem 6, disp 08:15-10:15)
    # Entrega da Encomenda 1 na paragem 12 (janela 12:30-14:30)
    rota_viavel = [
        ("pickup", 1),
        ("pickup", 2),
        ("warehouse", prob.armazem),
        ("load", 1),
        ("load", 2),
        ("delivery", 1),
        ("delivery", 2),
        ("warehouse", prob.armazem), 
    ]
    partida = datetime(2026, 10, 30, 7, 15)
    res1 = prob.verificar_viabilidade(
        vehicle_id=1,
        acoes=rota_viavel,
        hora_partida=partida,
        itens_objetivo={1, 2},
        exigir_rota_completa=True,
    )
    print("--- Teste 1: Rota Manual Viável (Encomenda 1 completa) ---")
    print("Viável?       ", res1["viavel"])
    print("Completa?     ", res1["completa"])
    print("Distância:    ", res1["distancia_km"], "km")
    print("Duração total:", res1["duracao_total_min"], "min | Fim:", res1["hora_fim"])
    print("Erros:        ", res1["erros"], "\n")

    # Teste 2: Rota manual INVIÁVEL (Tentar entregar diretamente do produtor ao cliente sem ir ao armazém)
    rota_sem_armazem = [
        ("pickup", 1),
        ("delivery", 1),
    ]
    res2 = prob.verificar_viabilidade(vehicle_id=1, acoes=rota_sem_armazem, hora_partida=partida)
    print("--- Teste 2: Rota Manual Inviável (Sem passagem obrigatória pelo armazém) ---")
    print("Viável?       ", res2["viavel"])
    print("Erros:        ", res2["erros"], "\n")

    # Teste 3: Rota manual INVIÁVEL (Atraso na janela horária - partida às 15:00)
    partida_tardia = datetime(2026, 10, 30, 15, 0)
    res3 = prob.verificar_viabilidade(vehicle_id=1, acoes=rota_viavel, hora_partida=partida_tardia)
    print("--- Teste 3: Rota Manual Inviável (Fora das janelas temporais) ---")
    print("Viável?       ", res3["viavel"])
    print("Erros:        ", res3["erros"])


if __name__ == "__main__":
    import os
    if os.path.exists("docs/data_small_30_31oct2026/"):
        executar_testes_manuais("docs/data_small_30_31oct2026/")
    elif os.path.exists("docs/data_tiny/"):
        executar_testes_manuais("docs/data_tiny/")
    else:
        print("Módulo model.py carregado com sucesso.")