"""Modelo do problema de distribuição local (IA26_P01_G02).

Este módulo contém os dados, as classes do problema/estado, a função de custo,
o verificador de viabilidade de rotas e a validação conjunta da frota. As
heurísticas e os algoritmos de pesquisa estão em pesquisa.py.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

import math
import pandas as pd

COLUNAS_DATA = [
    "availability_start",
    "availability_end",
    "delivery_start",
    "delivery_end",
]

FICHEIROS_CSV = (
    "localities.csv",
    "producers.csv",
    "products.csv",
    "collection_centers.csv",
    "vehicles.csv",
    "customers.csv",
    "delivery_locations.csv",
    "orders.csv",
    "order_items.csv",
    "locations.csv",
    "distance_matrix.csv",
    "rules.csv",
)


def carregar_dados(pasta: str) -> Dict[str, pd.DataFrame]:
    """Lê os 12 CSV da pasta e converte as colunas temporais para datetime."""
    raiz = Path(pasta)
    em_falta = [nome for nome in FICHEIROS_CSV if not (raiz / nome).is_file()]
    if em_falta:
        raise FileNotFoundError(
            f"Não foram encontrados todos os CSV em '{raiz}': {', '.join(em_falta)}"
        )

    dados: Dict[str, pd.DataFrame] = {}
    nomes = [Path(nome).stem for nome in FICHEIROS_CSV]
    for nome, ficheiro in zip(nomes, FICHEIROS_CSV):
        caminho = raiz / ficheiro
        if nome == "orders":
            dados[nome] = pd.read_csv(caminho, parse_dates=["order_datetime"])
        elif nome == "order_items":
            dados[nome] = pd.read_csv(caminho, parse_dates=COLUNAS_DATA)
        else:
            dados[nome] = pd.read_csv(caminho)
    return dados


def paragem_armazem(dados: Dict[str, pd.DataFrame]) -> int:
    """Devolve o location_id do único centro de recolha."""
    locations = dados["locations"]
    armazens = locations.loc[
        locations["location_type"] == "collection_center", "location_id"
    ]
    if len(armazens) != 1:
        raise ValueError(
            f"Esperava exatamente um armazém, mas encontrei {len(armazens)}."
        )
    return int(armazens.iloc[0])


def construir_pedidos(dados: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Consolida cada OrderItem com produto, produtor e local de entrega."""
    items = dados["order_items"].copy()
    products = dados["products"]
    orders = dados["orders"]
    locations = dados["locations"]

    colunas_produto = ["product_id", "producer_id", "name", "unit_weight_kg"]
    pedidos = items.merge(
        products[colunas_produto], on="product_id", how="left", validate="many_to_one"
    )

    if "weight_kg" not in pedidos.columns:
        pedidos["weight_kg"] = pedidos["quantity"] * pedidos["unit_weight_kg"]
    else:
        pedidos["weight_kg"] = pedidos["weight_kg"].fillna(
            pedidos["quantity"] * pedidos["unit_weight_kg"]
        )

    pedidos = pedidos.merge(
        orders[["order_id", "delivery_location_id"]],
        on="order_id",
        how="left",
        validate="many_to_one",
    )

    paragens_produtores = locations.loc[
        locations["location_type"] == "producer", ["ref_id", "location_id"]
    ].rename(columns={"ref_id": "producer_id", "location_id": "paragem_recolha"})
    pedidos = pedidos.merge(
        paragens_produtores, on="producer_id", how="left", validate="many_to_one"
    )

    paragens_entrega = locations.loc[
        locations["location_type"] == "delivery_location", ["ref_id", "location_id"]
    ].rename(
        columns={"ref_id": "delivery_location_id", "location_id": "paragem_entrega"}
    )
    pedidos = pedidos.merge(
        paragens_entrega,
        on="delivery_location_id",
        how="left",
        validate="many_to_one",
    )

    obrigatorias = [
        "order_item_id", "order_id", "name", "weight_kg", "paragem_recolha",
        "paragem_entrega", *COLUNAS_DATA,
    ]
    nulos = pedidos[obrigatorias].isna().sum()
    nulos = nulos[nulos > 0]
    if not nulos.empty:
        raise ValueError(f"Há dados em falta na tabela consolidada: {nulos.to_dict()}")

    pedidos["dia_recolha"] = pedidos["availability_start"].dt.date
    pedidos["dia_entrega"] = pedidos["delivery_start"].dt.date
    return pedidos.sort_values("order_item_id").reset_index(drop=True)


@dataclass(frozen=True)
class Request:
    """Um item de encomenda, com peso, origem, destino e janelas temporais."""
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
    """Veículo sediado no centro de recolha."""
    vehicle_id: int
    plate: str
    capacity_kg: float
    refrigerated: bool
    avg_speed_kmh: float
    center_loc: int


class Problem:
    """Dados de uma instância e operações comuns aos algoritmos de pesquisa."""

    def __init__(self, pasta: str):
        dados = carregar_dados(pasta)
        self.armazem = paragem_armazem(dados)

        self.paragens: Dict[int, dict] = {}
        for _, p in dados["locations"].iterrows():
            loc_id = int(p["location_id"])
            self.paragens[loc_id] = {
                "tipo": str(p["location_type"]),
                "nome": str(p["name"]),
                "latitude": float(p["latitude"]),
                "longitude": float(p["longitude"]),
            }

        self.regras: Dict[str, object] = {}
        for _, regra in dados["rules"].iterrows():
            valor = regra["value"]
            try:
                valor = float(valor)
            except (TypeError, ValueError):
                valor = str(valor)
            self.regras[str(regra["rule"])] = valor

        self.tempo_servico_min = float(self.regras.get("stop_service_min", 10.0))
        self.tempo_armazem_min = float(self.regras.get("warehouse_handling_min", 15.0))
        self.permanencia_max_h = float(self.regras.get("max_warehouse_dwell_h", 24.0))

        self.veiculos: Dict[int, Vehicle] = {}
        for _, v in dados["vehicles"].iterrows():
            vid = int(v["vehicle_id"])
            refrigerado = v["refrigerated"]
            if isinstance(refrigerado, str):
                refrigerado = refrigerado.strip().lower() in {"1", "true", "yes", "sim"}
            else:
                refrigerado = bool(refrigerado)
            self.veiculos[vid] = Vehicle(
                vehicle_id=vid,
                plate=str(v["plate"]),
                capacity_kg=float(v["capacity_kg"]),
                refrigerated=refrigerado,
                avg_speed_kmh=float(v["avg_speed_kmh"]),
                center_loc=self.armazem,
            )

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
                availability_start=pd.Timestamp(item["availability_start"]).to_pydatetime(),
                availability_end=pd.Timestamp(item["availability_end"]).to_pydatetime(),
                delivery_start=pd.Timestamp(item["delivery_start"]).to_pydatetime(),
                delivery_end=pd.Timestamp(item["delivery_end"]).to_pydatetime(),
            )

        self.distancia: Dict[Tuple[int, int], float] = {}
        self.tempo: Dict[Tuple[int, int], float] = {}
        for _, linha in dados["distance_matrix"].iterrows():
            chave = (
                int(linha["origin_location_id"]),
                int(linha["destination_location_id"]),
            )
            self.distancia[chave] = float(linha["distance_km"])
            self.tempo[chave] = float(linha["duration_min"])

        locais = list(self.paragens)
        for loc_id in locais:
            self.distancia[(loc_id, loc_id)] = 0.0
            self.tempo[(loc_id, loc_id)] = 0.0

        # Verifica que a matriz permite deslocações entre todas as paragens.
        faltas = [
            (a, b) for a in locais for b in locais
            if (a, b) not in self.distancia or (a, b) not in self.tempo
        ]
        if faltas:
            raise ValueError(
                f"A matriz distância/tempo está incompleta. Exemplos de pares em falta: {faltas[:5]}"
            )

        # Floyd-Warshall: matriz auxiliar de limites inferiores para as heurísticas.
        # O custo real das rotas continua a utilizar self.distancia.
        infinito = float("inf")
        self.distancia_minima: Dict[Tuple[int, int], float] = {
            (a, b): (0.0 if a == b else self.distancia[(a, b)])
            for a in locais for b in locais
        }
        for k in locais:
            for i in locais:
                dik = self.distancia_minima[(i, k)]
                if math.isinf(dik):
                    continue
                for j in locais:
                    alternativa = dik + self.distancia_minima[(k, j)]
                    if alternativa < self.distancia_minima[(i, j)]:
                        self.distancia_minima[(i, j)] = alternativa

    def distancia_entre(self, origem: int, destino: int) -> float:
        return self.distancia[(origem, destino)]

    def tempo_entre(self, origem: int, destino: int) -> float:
        return self.tempo[(origem, destino)]

    def distancia_inferior_entre(self, origem: int, destino: int) -> float:
        """Distância mínima entre locais, usada apenas como limite inferior."""
        return self.distancia_minima[(origem, destino)]

    def custo_rota(self, paragens_rota: List[int]) -> Dict[str, float]:
        """Calcula a distância e o tempo de condução entre paragens consecutivas."""
        distancia = 0.0
        tempo = 0.0
        for origem, destino in zip(paragens_rota[:-1], paragens_rota[1:]):
            distancia += self.distancia_entre(origem, destino)
            tempo += self.tempo_entre(origem, destino)
        return {
            "distancia_km": round(distancia, 2),
            "tempo_viagem_min": round(tempo, 2),
        }

    def verificar_viabilidade(
        self,
        vehicle_id: int,
        acoes: List[Tuple[str, int]],
        hora_partida: datetime,
        chegada_armazem_previa: Optional[Dict[int, datetime]] = None,
        itens_objetivo: Optional[Set[int]] = None,
        exigir_rota_completa: bool = False,
    ) -> Dict[str, object]:
        """Simula ações e verifica capacidade, fluxo, janelas e permanência no armazém.

        Ações consecutivas de pickup/delivery no mesmo local contam como uma visita
        (10 min). Ações consecutivas de load contam como um lote (15 min). A nível
        do plano de pesquisa, todos os itens de uma encomenda são carregados e
        entregues em conjunto; o verificador também controla essa decisão.
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
        no_armazem: Dict[int, datetime] = dict(chegada_armazem_previa or {})
        entregues: Set[int] = set()

        if itens_objetivo is None:
            itens_objetivo = {
                alvo for acao, alvo in acoes if acao in {"pickup", "load", "delivery"}
            }
        else:
            itens_objetivo = set(itens_objetivo)

        desconhecidos = itens_objetivo.difference(self.pedidos)
        if desconhecidos:
            raise KeyError(f"Itens objetivo desconhecidos: {sorted(desconhecidos)}")

        itens_por_encomenda: Dict[int, Set[int]] = {}
        for iid in itens_objetivo:
            itens_por_encomenda.setdefault(self.pedidos[iid].order_id, set()).add(iid)

        def deslocar(destino: int) -> None:
            nonlocal paragem_atual, relogio, distancia_total
            if paragem_atual != destino:
                relogio += timedelta(minutes=self.tempo_entre(paragem_atual, destino))
                distancia_total += self.distancia_entre(paragem_atual, destino)
                paragem_atual = destino

        def ordem_completa_no_lote(ids_lote: Set[int], order_id: int) -> bool:
            return itens_por_encomenda.get(order_id, set()).issubset(ids_lote)

        i = 0
        while i < len(acoes):
            acao, alvo = acoes[i]

            # 1. Recolha: agrupa ações pickup consecutivas no mesmo produtor.
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
                    if item_id not in self.pedidos or self.pedidos[item_id].pickup_loc != destino:
                        break
                    grupo.append(self.pedidos[item_id])
                    j += 1
                i = j

                candidatos: List[Request] = []
                vistos: Set[int] = set()
                for req in grupo:
                    if req.item_id in vistos:
                        erros.append(f"Item {req.item_id}: recolha repetida na mesma rota.")
                        continue
                    vistos.add(req.item_id)
                    if (
                        req.item_id in na_carrinha_recolhidos
                        or req.item_id in no_armazem
                        or req.item_id in na_carrinha_para_entrega
                        or req.item_id in entregues
                    ):
                        erros.append(f"Item {req.item_id}: já foi recolhido ou entregue.")
                        continue
                    candidatos.append(req)

                if not candidatos:
                    continue

                deslocar(destino)
                inicio_servico = max(
                    [relogio] + [req.availability_start for req in candidatos]
                )
                validos = [req for req in candidatos if inicio_servico <= req.availability_end]
                for req in candidatos:
                    if inicio_servico > req.availability_end:
                        erros.append(
                            f"Item {req.item_id}: recolha fora da janela; início previsto "
                            f"{inicio_servico:%d/%m %H:%M}, fecho "
                            f"{req.availability_end:%d/%m %H:%M}."
                        )

                if validos:
                    relogio = inicio_servico + timedelta(minutes=self.tempo_servico_min)
                    for req in validos:
                        carga_atual += req.weight_kg
                        na_carrinha_recolhidos.add(req.item_id)
                    if carga_atual > veiculo.capacity_kg + 1e-6:
                        erros.append(
                            f"Excesso de capacidade no veículo {vehicle_id}: "
                            f"{carga_atual:.2f} kg > {veiculo.capacity_kg:.2f} kg."
                        )
                continue

            # 2. Armazém: regressar e descarregar os produtos recolhidos.
            if acao == "warehouse":
                if alvo != self.armazem:
                    erros.append(
                        f"Ação warehouse inválida: {alvo}; o armazém é {self.armazem}."
                    )
                    i += 1
                    continue
                deslocar(self.armazem)
                if na_carrinha_recolhidos:
                    hora_chegada = relogio
                    relogio += timedelta(minutes=self.tempo_armazem_min)
                    for item_id in list(na_carrinha_recolhidos):
                        no_armazem[item_id] = hora_chegada
                        carga_atual -= self.pedidos[item_id].weight_kg
                    na_carrinha_recolhidos.clear()
                i += 1
                continue

            # 3. Carregamento: todas as ações load consecutivas são um lote.
            if acao == "load":
                ids_lote: List[int] = []
                j = i
                while j < len(acoes) and acoes[j][0] == "load":
                    ids_lote.append(acoes[j][1])
                    j += 1
                i = j

                if paragem_atual != self.armazem:
                    erros.append("Tentativa de carregar produtos fora do armazém.")
                    continue

                ids_set = set(ids_lote)
                inicio_carregamento = relogio
                candidatos: List[Request] = []
                vistos: Set[int] = set()
                for item_id in ids_lote:
                    if item_id not in self.pedidos:
                        erros.append(f"Item desconhecido no carregamento: {item_id}.")
                        continue
                    req = self.pedidos[item_id]
                    if item_id in vistos:
                        erros.append(f"Item {item_id}: carregamento repetido.")
                        continue
                    vistos.add(item_id)
                    if item_id not in no_armazem:
                        erros.append(f"Item {item_id}: não está no armazém para ser carregado.")
                        continue
                    if not ordem_completa_no_lote(ids_set, req.order_id):
                        erros.append(
                            f"Encomenda {req.order_id}: os seus itens objetivo têm de ser carregados em conjunto."
                        )
                        continue

                    chegada = no_armazem[item_id]
                    permanencia_h = (inicio_carregamento - chegada).total_seconds() / 3600.0
                    if permanencia_h < -1e-6:
                        erros.append(f"Item {item_id}: carregamento anterior à chegada ao armazém.")
                        continue
                    if permanencia_h > self.permanencia_max_h + 1e-6:
                        erros.append(
                            f"Item {item_id}: permanência de {permanencia_h:.2f} h excede "
                            f"o máximo de {self.permanencia_max_h:.1f} h."
                        )
                        continue
                    candidatos.append(req)

                # Evita carregar apenas parte de uma encomenda se algum dos seus itens falhou.
                ids_candidatos = {r.item_id for r in candidatos}
                ids_validos: Set[int] = set()
                for req in candidatos:
                    grupo_ordem = itens_por_encomenda.get(req.order_id, set())
                    if grupo_ordem.issubset(ids_candidatos):
                        ids_validos.add(req.item_id)
                candidatos = [r for r in candidatos if r.item_id in ids_validos]

                if candidatos:
                    relogio += timedelta(minutes=self.tempo_armazem_min)
                    for req in candidatos:
                        del no_armazem[req.item_id]
                        carga_atual += req.weight_kg
                        na_carrinha_para_entrega.add(req.item_id)
                    if carga_atual > veiculo.capacity_kg + 1e-6:
                        erros.append(
                            f"Excesso de capacidade ao carregar: {carga_atual:.2f} kg > "
                            f"{veiculo.capacity_kg:.2f} kg."
                        )
                continue

            # 4. Entrega: agrupa ações delivery consecutivas no mesmo destino.
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
                    if item_id not in self.pedidos or self.pedidos[item_id].delivery_loc != destino:
                        break
                    grupo.append(self.pedidos[item_id])
                    j += 1
                i = j

                ids_grupo = {r.item_id for r in grupo}
                candidatos: List[Request] = []
                vistos: Set[int] = set()
                for req in grupo:
                    if req.item_id in vistos:
                        erros.append(f"Item {req.item_id}: entrega repetida.")
                        continue
                    vistos.add(req.item_id)
                    if req.item_id not in na_carrinha_para_entrega:
                        erros.append(
                            f"Item {req.item_id}: tentativa de entrega sem carregamento prévio no armazém."
                        )
                        continue
                    if not ordem_completa_no_lote(ids_grupo, req.order_id):
                        erros.append(
                            f"Encomenda {req.order_id}: os seus itens objetivo têm de ser entregues em conjunto."
                        )
                        continue
                    candidatos.append(req)

                ids_candidatos = {r.item_id for r in candidatos}
                candidatos = [
                    r for r in candidatos
                    if itens_por_encomenda.get(r.order_id, set()).issubset(ids_candidatos)
                ]
                if not candidatos:
                    continue

                deslocar(destino)
                inicio_servico = max([relogio] + [r.delivery_start for r in candidatos])
                validos = [r for r in candidatos if inicio_servico <= r.delivery_end]
                for req in candidatos:
                    if inicio_servico > req.delivery_end:
                        erros.append(
                            f"Item {req.item_id}: entrega fora da janela; início previsto "
                            f"{inicio_servico:%d/%m %H:%M}, fecho "
                            f"{req.delivery_end:%d/%m %H:%M}."
                        )
                # Só entregar uma encomenda se todos os seus itens forem válidos.
                ids_validos = {r.item_id for r in validos}
                ids_entregar: Set[int] = set()
                for req in validos:
                    grupo_ordem = itens_por_encomenda.get(req.order_id, set())
                    if grupo_ordem.issubset(ids_validos):
                        ids_entregar.update(grupo_ordem)
                if ids_entregar:
                    relogio = inicio_servico + timedelta(minutes=self.tempo_servico_min)
                    for item_id in ids_entregar:
                        carga_atual -= self.pedidos[item_id].weight_kg
                        na_carrinha_para_entrega.remove(item_id)
                        entregues.add(item_id)
                continue

            erros.append(f"Ação desconhecida: {acao}.")
            i += 1

        duracao_total_min = (relogio - hora_partida).total_seconds() / 60.0
        itens_pendentes = (
            set(no_armazem) | na_carrinha_recolhidos | na_carrinha_para_entrega
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


    def validar_atribuicao_frota(
        self,
        atribuicao: Dict[int, Set[int]],
        itens_objetivo: Set[int],
    ) -> Dict[str, object]:
        """Valida a distribuição de encomendas pelos veículos.

        Cada encomenda tem de ficar inteira num único veículo. A capacidade é
        verificada por encomenda (não pela soma de todas as encomendas), porque
        um veículo pode regressar várias vezes ao armazém e fazer várias viagens.
        """
        objetivo = set(itens_objetivo)
        erros: List[str] = []

        veiculos_atribuicao = set(atribuicao)
        veiculos_desconhecidos = veiculos_atribuicao.difference(self.veiculos)
        if veiculos_desconhecidos:
            erros.append(
                f"Veículos desconhecidos na atribuição: {sorted(veiculos_desconhecidos)}."
            )

        itens_desconhecidos = objetivo.difference(self.pedidos)
        if itens_desconhecidos:
            erros.append(f"Itens objetivo desconhecidos: {sorted(itens_desconhecidos)}.")

        atribuicoes_por_item: Dict[int, List[int]] = {}
        for vehicle_id, itens in atribuicao.items():
            for item_id in set(itens):
                atribuicoes_por_item.setdefault(item_id, []).append(vehicle_id)

        repetidos = sorted(iid for iid, donos in atribuicoes_por_item.items() if len(donos) > 1)
        nao_atribuidos = sorted(objetivo.difference(atribuicoes_por_item))
        fora_objetivo = sorted(set(atribuicoes_por_item).difference(objetivo))
        if repetidos:
            erros.append(f"Itens atribuídos a mais do que um veículo: {repetidos}.")
        if nao_atribuidos:
            erros.append(f"Itens sem veículo atribuído: {nao_atribuidos}.")
        if fora_objetivo:
            erros.append(f"Atribuição contém itens fora do objetivo: {fora_objetivo}.")

        itens_por_encomenda_completos: Dict[int, Set[int]] = {}
        for req in self.pedidos.values():
            itens_por_encomenda_completos.setdefault(req.order_id, set()).add(req.item_id)
        itens_por_encomenda_objetivo: Dict[int, Set[int]] = {}
        for item_id in objetivo.intersection(self.pedidos):
            order_id = self.pedidos[item_id].order_id
            itens_por_encomenda_objetivo.setdefault(order_id, set()).add(item_id)

        for order_id, itens_ordem_objetivo in itens_por_encomenda_objetivo.items():
            itens_ordem_completos = itens_por_encomenda_completos[order_id]
            if itens_ordem_objetivo != itens_ordem_completos:
                em_falta = sorted(itens_ordem_completos.difference(itens_ordem_objetivo))
                erros.append(
                    f"A encomenda {order_id} está incompleta no objetivo; faltam os itens {em_falta}."
                )
                continue

            donos = {
                vehicle_id
                for item_id in itens_ordem_objetivo
                for vehicle_id in atribuicoes_por_item.get(item_id, [])
            }
            if len(donos) > 1:
                erros.append(
                    f"A encomenda {order_id} foi dividida por vários veículos: {sorted(donos)}."
                )
                continue
            if len(donos) == 1:
                vehicle_id = next(iter(donos))
                if vehicle_id in self.veiculos:
                    peso_ordem = sum(self.pedidos[iid].weight_kg for iid in itens_ordem_completos)
                    capacidade = self.veiculos[vehicle_id].capacity_kg
                    if peso_ordem > capacidade + 1e-6:
                        erros.append(
                            f"A encomenda {order_id} pesa {peso_ordem:.2f} kg e não cabe "
                            f"no veículo {vehicle_id} ({capacidade:.2f} kg)."
                        )

        pesos_por_veiculo = {
            vehicle_id: round(
                sum(self.pedidos[iid].weight_kg for iid in set(itens).intersection(self.pedidos)),
                2,
            )
            for vehicle_id, itens in atribuicao.items()
            if vehicle_id in self.veiculos
        }
        return {
            "valida": not erros,
            "erros": erros,
            "pesos_atribuidos_kg": pesos_por_veiculo,
            "encomendas_por_veiculo": {
                vehicle_id: sorted({self.pedidos[iid].order_id for iid in set(itens) if iid in self.pedidos})
                for vehicle_id, itens in atribuicao.items()
            },
        }

    def verificar_plano_frota(
        self,
        atribuicao: Dict[int, Set[int]],
        resultados: Dict[int, Dict[str, object]],
        hora_partida: datetime,
        itens_objetivo: Set[int],
        itens_ja_no_armazem_por_veiculo: Optional[Dict[int, Dict[int, datetime]]] = None,
    ) -> Dict[str, object]:
        """Verifica em conjunto a cobertura e as rotas de todos os veículos."""
        validacao_atribuicao = self.validar_atribuicao_frota(atribuicao, itens_objetivo)
        erros = list(validacao_atribuicao["erros"])
        chegadas_iniciais = itens_ja_no_armazem_por_veiculo or {}
        validacoes: Dict[int, Dict[str, object]] = {}
        distancia_total = 0.0
        entregues_globalmente: Set[int] = set()

        for vehicle_id, itens_veiculo in atribuicao.items():
            resultado = resultados.get(vehicle_id)
            if not resultado or not resultado.get("sucesso"):
                erros.append(f"O veículo {vehicle_id} não tem uma rota completa com sucesso.")
                continue

            validacao = self.verificar_viabilidade(
                vehicle_id=vehicle_id,
                acoes=list(resultado.get("acoes", [])),
                hora_partida=hora_partida,
                chegada_armazem_previa=dict(chegadas_iniciais.get(vehicle_id, {})),
                itens_objetivo=set(itens_veiculo),
                exigir_rota_completa=True,
            )
            validacoes[vehicle_id] = validacao
            if not validacao.get("viavel") or not validacao.get("completa"):
                erros.extend(
                    f"Veículo {vehicle_id}: {erro}" for erro in validacao.get("erros", [])
                )
            entregues = set(validacao.get("entregues", set()))
            esperados = set(itens_veiculo)
            if entregues != esperados:
                erros.append(
                    f"Veículo {vehicle_id}: entregou {sorted(entregues)}, "
                    f"mas estavam atribuídos {sorted(esperados)}."
                )
            repetidos = entregues_globalmente.intersection(entregues)
            if repetidos:
                erros.append(f"Itens entregues por mais do que um veículo: {sorted(repetidos)}.")
            entregues_globalmente.update(entregues)
            distancia_total += float(validacao.get("distancia_km", 0.0))

        objetivo = set(itens_objetivo)
        em_falta = objetivo.difference(entregues_globalmente)
        a_mais = entregues_globalmente.difference(objetivo)
        if em_falta:
            erros.append(f"Itens do objetivo por entregar: {sorted(em_falta)}.")
        if a_mais:
            erros.append(f"Itens entregues fora do objetivo: {sorted(a_mais)}.")

        return {
            "viavel": not erros,
            "completa": not em_falta and not a_mais and entregues_globalmente == objetivo,
            "erros": erros,
            "distancia_total_km": round(distancia_total, 2),
            "entregues": entregues_globalmente,
            "validacao_atribuicao": validacao_atribuicao,
            "validacoes_por_veiculo": validacoes,
        }


@dataclass(frozen=True)
class State:
    """Estado de pesquisa: posição, tempo, carga e fase de cada item."""
    paragem_atual: int
    tempo_atual: datetime
    carga_atual_kg: float = 0.0
    recolhidos_a_bordo: FrozenSet[int] = field(default_factory=frozenset)
    no_armazem: FrozenSet[int] = field(default_factory=frozenset)
    para_entrega_a_bordo: FrozenSet[int] = field(default_factory=frozenset)
    entregues: FrozenSet[int] = field(default_factory=frozenset)
    distancia_acumulada_km: float = 0.0
    historico_paragens: Tuple[int, ...] = field(default_factory=tuple)
    chegadas_armazem: Tuple[Tuple[int, datetime], ...] = field(default_factory=tuple)
    # Última classe de ação executada; evita contar duas visitas consecutivas
    # ao mesmo local como uma única visita no verificador.
    ultima_acao: Optional[str] = None

    def hora_chegada_armazem(self, item_id: int) -> Optional[datetime]:
        return dict(self.chegadas_armazem).get(item_id)

    def paragens_pendentes(self, problem: "Problem", itens_objetivo: Set[int]) -> Set[int]:
        """Localizações ainda necessárias para concluir os itens objetivo."""
        pendentes: Set[int] = set()
        for iid in itens_objetivo:
            if iid in self.entregues:
                continue
            req = problem.pedidos[iid]
            if iid in self.para_entrega_a_bordo:
                pendentes.add(req.delivery_loc)
            elif iid in self.recolhidos_a_bordo or iid in self.no_armazem:
                pendentes.add(problem.armazem)
                pendentes.add(req.delivery_loc)
            else:
                pendentes.add(req.pickup_loc)
                pendentes.add(problem.armazem)
                pendentes.add(req.delivery_loc)
        return pendentes


def executar_testes_manuais(pasta: str = "docs/data_small_30_31oct2026/") -> None:
    """Executa testes de rota viável e de violações básicas do fluxo/janelas."""
    prob = Problem(pasta)
    print(
        f"=== Instância: {pasta} ===\n"
        f"Paragens: {len(prob.paragens)} | Veículos: {len(prob.veiculos)} | "
        f"Pedidos (itens): {len(prob.pedidos)} | Armazém: {prob.armazem}\n"
    )

    partida = datetime(2026, 10, 30, 7, 15)
    rota_viavel = [
        ("pickup", 1), ("pickup", 2),
        ("warehouse", prob.armazem),
        ("load", 1), ("load", 2),
        ("delivery", 1), ("delivery", 2),
        ("warehouse", prob.armazem),
    ]
    res = prob.verificar_viabilidade(
        1, rota_viavel, partida, itens_objetivo={1, 2}, exigir_rota_completa=True
    )
    print("Teste 1 — rota completa:", res["viavel"], "| completa:", res["completa"])
    print("Distância:", res["distancia_km"], "km | duração:", res["duracao_total_min"], "min")
    print("Erros:", res["erros"])

    rota_sem_armazem = [("pickup", 1), ("delivery", 1)]
    res2 = prob.verificar_viabilidade(1, rota_sem_armazem, partida, itens_objetivo={1})
    print("Teste 2 — entrega sem carregamento no armazém:", res2["viavel"])
    print("Erros:", res2["erros"])


if __name__ == "__main__":
    import os

    if os.path.isdir("docs/data_tiny"):
        executar_testes_manuais("docs/data_tiny")
    elif os.path.isdir("docs/data_small_30_31oct2026"):
        executar_testes_manuais("docs/data_small_30_31oct2026")
    else:
        print("model.py carregado. Para executar os testes, disponibiliza a pasta dos CSV.")
