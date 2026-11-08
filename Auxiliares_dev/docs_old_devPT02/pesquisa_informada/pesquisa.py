"""Pesquisa informada para o projeto IA26_P01_G02.

Inclui:
- Sucessores para recolha, passagem pelo armazém/carregamento e entrega;
- UCS, Greedy Best-First e A*;
- H1: pedido mais caro (maior custo mínimo obrigatório por item);
- H2: árvore geradora mínima (MST), calculada com Prim;
- Comparação de algoritmos e seleção de encomendas para testes de um veículo/dia;
- Otimização conjunta da atribuição e das rotas de dois veículos;
- Comparação dos cinco métodos de pesquisa ao nível da frota.

As duas heurísticas usadas neste módulo são h1_pedido_mais_caro e h2_mst.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from itertools import combinations
from typing import Callable, Dict, Iterable, Iterator, List, Optional, Set, Tuple
import heapq
import math
import time

import pandas as pd

from model import Problem, Request, State

Heuristica = Callable[[State, Problem, Set[int]], float]
Acoes = Tuple[Tuple[str, int], ...]


# =====================================================================
# 1. FUNÇÕES AUXILIARES
# =====================================================================

def _subconjuntos_nao_vazios(elementos: Iterable[int]) -> Iterator[Tuple[int, ...]]:
    """Gera todos os subconjuntos não vazios, por ordem crescente de tamanho."""
    lista = tuple(sorted(elementos))
    for tamanho in range(1, len(lista) + 1):
        yield from combinations(lista, tamanho)


def _itens_por_encomenda(
    problem: Problem,
    itens_objetivo: Set[int],
) -> Dict[int, Tuple[int, ...]]:
    """Agrupa os itens objetivo por encomenda, com ordem determinística."""
    grupos: Dict[int, List[int]] = {}
    for item_id in sorted(itens_objetivo):
        if item_id not in problem.pedidos:
            raise KeyError(f"Item objetivo desconhecido: {item_id}")
        order_id = problem.pedidos[item_id].order_id
        grupos.setdefault(order_id, []).append(item_id)
    return {order_id: tuple(ids) for order_id, ids in grupos.items()}


def _peso_itens(problem: Problem, itens: Iterable[int]) -> float:
    return sum(problem.pedidos[iid].weight_kg for iid in itens)


def _assinatura_estado(state: State) -> tuple:
    """Parte do estado que determina as ações futuras possíveis.

    O histórico de paragens e o custo acumulado não entram na assinatura:
    são usados para comparar caminhos que chegaram à mesma situação logística.
    As horas de chegada ao armazém entram, porque afetam o limite das 24 horas.
    """
    return (
        state.paragem_atual,
        state.recolhidos_a_bordo,
        state.no_armazem,
        state.para_entrega_a_bordo,
        state.entregues,
        state.chegadas_armazem,
        state.ultima_acao,
    )


def _adicionar_paragem(historico: Tuple[int, ...], paragem: int) -> Tuple[int, ...]:
    if historico and historico[-1] == paragem:
        return historico
    return historico + (paragem,)


# =====================================================================
# 2. HEURÍSTICA H1 — PEDIDO MAIS CARO
# =====================================================================

def h1_pedido_mais_caro(
    state: State,
    problem: Problem,
    itens_objetivo: Set[int],
) -> float:
    """Devolve o maior custo mínimo obrigatório entre os itens ainda pendentes.

    Para cada item calcula-se apenas o percurso obrigatório que ainda falta:
    - por recolher: posição atual -> produtor -> armazém -> entrega -> armazém;
    - recolhido ou armazenado: posição atual -> armazém -> entrega -> armazém;
    - carregado para entrega: posição atual -> entrega -> armazém.

    Usa-se o máximo, e não a soma, porque vários itens podem partilhar as mesmas
    deslocações e ser transportados na mesma viagem.
    """
    d = problem.distancia_inferior_entre
    armazem = problem.armazem
    atual = state.paragem_atual
    maior_custo = 0.0
    existe_pendente = False

    for item_id in itens_objetivo:
        if item_id in state.entregues:
            continue
        existe_pendente = True
        req = problem.pedidos[item_id]

        if item_id in state.para_entrega_a_bordo:
            custo_item = d(atual, req.delivery_loc) + d(req.delivery_loc, armazem)
        elif item_id in state.recolhidos_a_bordo or item_id in state.no_armazem:
            custo_item = (
                d(atual, armazem)
                + d(armazem, req.delivery_loc)
                + d(req.delivery_loc, armazem)
            )
        else:
            custo_item = (
                d(atual, req.pickup_loc)
                + d(req.pickup_loc, armazem)
                + d(armazem, req.delivery_loc)
                + d(req.delivery_loc, armazem)
            )
        maior_custo = max(maior_custo, custo_item)

    if not existe_pendente:
        return d(atual, armazem)
    return maior_custo


# =====================================================================
# 3. HEURÍSTICA H2 — ÁRVORE GERADORA MÍNIMA (MST)
# =====================================================================

def _calcular_mst_prim(paragens: Set[int], problem: Problem) -> float:
    """Calcula o peso da MST do conjunto de paragens através do algoritmo Prim."""
    if len(paragens) <= 1:
        return 0.0

    d = problem.distancia_inferior_entre
    por_ligar = set(paragens)
    inicial = min(por_ligar)
    por_ligar.remove(inicial)

    menor_ligacao = {p: d(inicial, p) for p in por_ligar}
    peso_total = 0.0

    while por_ligar:
        seguinte = min(por_ligar, key=lambda p: (menor_ligacao[p], p))
        peso_total += menor_ligacao[seguinte]
        por_ligar.remove(seguinte)

        for p in por_ligar:
            alternativa = d(seguinte, p)
            if alternativa < menor_ligacao[p]:
                menor_ligacao[p] = alternativa

    return peso_total


def h2_mst(
    state: State,
    problem: Problem,
    itens_objetivo: Set[int],
) -> float:
    """Limite inferior baseado em entrada + MST das paragens pendentes + saída.

    h2(n) = min d(atual, p) + MST(P) + min d(p, armazém), para p em P.

    P contém as localizações ainda necessárias para completar os itens objetivo.
    As distâncias vêm da matriz auxiliar de caminhos mínimos do Problem.
    """
    pendentes = state.paragens_pendentes(problem, itens_objetivo)
    d = problem.distancia_inferior_entre
    armazem = problem.armazem

    if not pendentes:
        return d(state.paragem_atual, armazem)

    entrada = min(d(state.paragem_atual, p) for p in pendentes)
    saida = min(d(p, armazem) for p in pendentes)
    arvore = _calcular_mst_prim(pendentes, problem)
    return entrada + arvore + saida


# =====================================================================
# 4. GERAÇÃO DE SUCESSORES
# =====================================================================

def sucessores_com_acoes(
    state: State,
    problem: Problem,
    vehicle_id: int,
    itens_objetivo: Set[int],
) -> List[Tuple[State, Acoes]]:
    """Gera sucessores viáveis e as ações que conduzem a cada sucessor.

    A geração é exaustiva dentro de cada paragem: são consideradas as combinações
    de itens que respeitam capacidade e janelas, em vez de escolher apenas um lote
    através de uma regra gulosa. Os itens de cada encomenda são carregados e
    entregues em conjunto, de acordo com a decisão de modelação descrita na EDA.

    As ações mantêm o formato do model.py:
      ('pickup', item_id), ('warehouse', armazem_id),
      ('load', item_id), ('delivery', item_id).
    """
    itens_objetivo = set(itens_objetivo)
    grupos_ordem = _itens_por_encomenda(problem, itens_objetivo)
    veiculo = problem.veiculos[vehicle_id]
    capacidade = veiculo.capacity_kg
    armazem = problem.armazem
    atual = state.paragem_atual
    relogio = state.tempo_atual
    sucessores: List[Tuple[State, Acoes]] = []

    # Se tudo foi entregue, só falta regressar ao armazém.
    if itens_objetivo.issubset(state.entregues):
        if atual != armazem:
            distancia = problem.distancia_entre(atual, armazem)
            minutos = problem.tempo_entre(atual, armazem)
            sucessor = State(
                paragem_atual=armazem,
                tempo_atual=relogio + timedelta(minutes=minutos),
                carga_atual_kg=state.carga_atual_kg,
                recolhidos_a_bordo=state.recolhidos_a_bordo,
                no_armazem=state.no_armazem,
                para_entrega_a_bordo=state.para_entrega_a_bordo,
                entregues=state.entregues,
                distancia_acumulada_km=state.distancia_acumulada_km + distancia,
                historico_paragens=_adicionar_paragem(state.historico_paragens, armazem),
                chegadas_armazem=state.chegadas_armazem,
                ultima_acao="warehouse",
            )
            sucessores.append((sucessor, (("warehouse", armazem),)))
        return sucessores

    # --------------------------------------------------------------
    # AÇÃO 1 — PICKUP: visitar um produtor e recolher uma combinação viável.
    # --------------------------------------------------------------
    itens_por_recolher = [
        iid for iid in sorted(itens_objetivo)
        if iid not in state.recolhidos_a_bordo
        and iid not in state.no_armazem
        and iid not in state.para_entrega_a_bordo
        and iid not in state.entregues
    ]
    produtores: Dict[int, List[int]] = {}
    for iid in itens_por_recolher:
        loc = problem.pedidos[iid].pickup_loc
        produtores.setdefault(loc, []).append(iid)

    for local_produtor in sorted(produtores):
        # O model.py agrupa ações pickup consecutivas no mesmo local numa visita.
        # Para manter os relógios sincronizados, não criamos uma segunda visita
        # consecutiva ao mesmo produtor sem antes sair desse local.
        if atual == local_produtor and state.ultima_acao == "pickup":
            continue
        distancia = problem.distancia_entre(atual, local_produtor)
        minutos = problem.tempo_entre(atual, local_produtor)
        chegada = relogio + timedelta(minutes=minutos)

        for lote in _subconjuntos_nao_vazios(produtores[local_produtor]):
            peso_lote = _peso_itens(problem, lote)
            if state.carga_atual_kg + peso_lote > capacidade + 1e-6:
                continue

            pedidos_lote = [problem.pedidos[iid] for iid in lote]
            inicio_servico = max(
                [chegada] + [req.availability_start for req in pedidos_lote]
            )
            if any(inicio_servico > req.availability_end for req in pedidos_lote):
                continue

            novo_tempo = inicio_servico + timedelta(minutes=problem.tempo_servico_min)
            ids = frozenset(lote)
            novo_estado = State(
                paragem_atual=local_produtor,
                tempo_atual=novo_tempo,
                carga_atual_kg=state.carga_atual_kg + peso_lote,
                recolhidos_a_bordo=state.recolhidos_a_bordo | ids,
                no_armazem=state.no_armazem,
                para_entrega_a_bordo=state.para_entrega_a_bordo,
                entregues=state.entregues,
                distancia_acumulada_km=state.distancia_acumulada_km + distancia,
                historico_paragens=_adicionar_paragem(
                    state.historico_paragens, local_produtor
                ),
                chegadas_armazem=state.chegadas_armazem,
                ultima_acao="pickup",
            )
            acoes = tuple(("pickup", iid) for iid in lote)
            sucessores.append((novo_estado, acoes))

    # --------------------------------------------------------------
    # AÇÃO 2 — WAREHOUSE: descarregar recolhas e/ou carregar encomendas completas.
    # --------------------------------------------------------------
    tem_recolhidos = bool(state.recolhidos_a_bordo)
    tem_armazenados = bool(state.no_armazem)

    if tem_recolhidos or tem_armazenados:
        distancia = problem.distancia_entre(atual, armazem)
        minutos = problem.tempo_entre(atual, armazem)
        chegada_armazem = relogio + timedelta(minutes=minutos)

        carga_depois_descarga = state.carga_atual_kg
        armazenados = set(state.no_armazem)
        chegadas = dict(state.chegadas_armazem)
        acoes_prefixo: List[Tuple[str, int]] = []
        hora_disponivel = chegada_armazem

        if atual != armazem or tem_recolhidos:
            acoes_prefixo.append(("warehouse", armazem))

        if tem_recolhidos:
            # Os itens entram em stock no instante da chegada, antes dos 15 min de descarga.
            for iid in state.recolhidos_a_bordo:
                armazenados.add(iid)
                chegadas[iid] = chegada_armazem
                carga_depois_descarga -= problem.pedidos[iid].weight_kg
            hora_disponivel += timedelta(minutes=problem.tempo_armazem_min)

            # Sucessor que apenas descarrega, permitindo recolher mais produtos depois.
            so_descarga = State(
                paragem_atual=armazem,
                tempo_atual=hora_disponivel,
                carga_atual_kg=max(0.0, carga_depois_descarga),
                recolhidos_a_bordo=frozenset(),
                no_armazem=frozenset(armazenados),
                para_entrega_a_bordo=state.para_entrega_a_bordo,
                entregues=state.entregues,
                distancia_acumulada_km=state.distancia_acumulada_km + distancia,
                historico_paragens=_adicionar_paragem(state.historico_paragens, armazem),
                chegadas_armazem=tuple(sorted(chegadas.items())),
                ultima_acao="warehouse",
            )
            sucessores.append((so_descarga, tuple(acoes_prefixo)))

        # Só se pode carregar uma encomenda quando todos os seus itens objetivo
        # já estão no armazém e nenhum deles ultrapassou as 24 horas.
        encomendas_carregaveis: Dict[int, Tuple[int, ...]] = {}
        for order_id, ids_ordem in grupos_ordem.items():
            if not set(ids_ordem).issubset(armazenados):
                continue
            dentro_das_24h = True
            for iid in ids_ordem:
                hora_chegada = chegadas.get(iid)
                if hora_chegada is None:
                    dentro_das_24h = False
                    break
                permanencia_h = (hora_disponivel - hora_chegada).total_seconds() / 3600.0
                if permanencia_h > problem.permanencia_max_h + 1e-6:
                    dentro_das_24h = False
                    break
            peso_ordem = _peso_itens(problem, ids_ordem)
            if dentro_das_24h and peso_ordem <= capacidade + 1e-6:
                encomendas_carregaveis[order_id] = ids_ordem

        combinacoes_carregamento = (
            _subconjuntos_nao_vazios(encomendas_carregaveis)
            if state.ultima_acao != "load" else ()
        )
        for ordens_escolhidas in combinacoes_carregamento:
            itens_carregar = tuple(
                iid
                for order_id in ordens_escolhidas
                for iid in encomendas_carregaveis[order_id]
            )
            peso_carregar = _peso_itens(problem, itens_carregar)
            if carga_depois_descarga + peso_carregar > capacidade + 1e-6:
                continue

            novo_armazenamento = armazenados.difference(itens_carregar)
            novas_chegadas = {
                iid: hora for iid, hora in chegadas.items() if iid not in itens_carregar
            }
            tempo_fim_load = hora_disponivel + timedelta(minutes=problem.tempo_armazem_min)
            novo_estado = State(
                paragem_atual=armazem,
                tempo_atual=tempo_fim_load,
                carga_atual_kg=carga_depois_descarga + peso_carregar,
                recolhidos_a_bordo=frozenset(),
                no_armazem=frozenset(novo_armazenamento),
                para_entrega_a_bordo=state.para_entrega_a_bordo | frozenset(itens_carregar),
                entregues=state.entregues,
                distancia_acumulada_km=state.distancia_acumulada_km + distancia,
                historico_paragens=_adicionar_paragem(state.historico_paragens, armazem),
                chegadas_armazem=tuple(sorted(novas_chegadas.items())),
                ultima_acao="load",
            )
            acoes_load = tuple(("load", iid) for iid in itens_carregar)
            sucessores.append((novo_estado, tuple(acoes_prefixo) + acoes_load))

    # --------------------------------------------------------------
    # AÇÃO 3 — DELIVERY: entregar uma ou mais encomendas completas num destino.
    # --------------------------------------------------------------
    encomendas_a_entregar: Dict[int, Tuple[int, ...]] = {}
    for order_id, ids_ordem in grupos_ordem.items():
        if set(ids_ordem).issubset(state.para_entrega_a_bordo):
            encomendas_a_entregar[order_id] = ids_ordem

    por_destino: Dict[int, List[int]] = {}
    for order_id, ids_ordem in encomendas_a_entregar.items():
        destino = problem.pedidos[ids_ordem[0]].delivery_loc
        por_destino.setdefault(destino, []).append(order_id)

    for destino in sorted(por_destino):
        # Evita criar dois lotes delivery consecutivos no mesmo destino: o
        # verificador interpreta ações consecutivas nesse local como uma visita.
        if atual == destino and state.ultima_acao == "delivery":
            continue
        ordens_no_destino = sorted(por_destino[destino])
        for ordens_escolhidas in _subconjuntos_nao_vazios(ordens_no_destino):
            itens_lote = tuple(
                iid
                for order_id in ordens_escolhidas
                for iid in encomendas_a_entregar[order_id]
            )
            pedidos_lote = [problem.pedidos[iid] for iid in itens_lote]
            distancia = problem.distancia_entre(atual, destino)
            minutos = problem.tempo_entre(atual, destino)
            chegada = relogio + timedelta(minutes=minutos)
            inicio_servico = max(
                [chegada] + [req.delivery_start for req in pedidos_lote]
            )
            if any(inicio_servico > req.delivery_end for req in pedidos_lote):
                continue

            peso_entregue = _peso_itens(problem, itens_lote)
            novo_estado = State(
                paragem_atual=destino,
                tempo_atual=inicio_servico + timedelta(minutes=problem.tempo_servico_min),
                carga_atual_kg=max(0.0, state.carga_atual_kg - peso_entregue),
                recolhidos_a_bordo=state.recolhidos_a_bordo,
                no_armazem=state.no_armazem,
                para_entrega_a_bordo=state.para_entrega_a_bordo.difference(itens_lote),
                entregues=state.entregues | frozenset(itens_lote),
                distancia_acumulada_km=state.distancia_acumulada_km + distancia,
                historico_paragens=_adicionar_paragem(state.historico_paragens, destino),
                chegadas_armazem=state.chegadas_armazem,
                ultima_acao="delivery",
            )
            acoes_delivery = tuple(("delivery", iid) for iid in itens_lote)
            sucessores.append((novo_estado, acoes_delivery))

    return sucessores


def sucessores(
    state: State,
    problem: Problem,
    vehicle_id: int,
    itens_objetivo: Set[int],
) -> List[State]:
    """Devolve apenas os estados sucessores, sem as ações usadas para os gerar."""
    return [estado for estado, _ in sucessores_com_acoes(
        state, problem, vehicle_id, itens_objetivo
    )]


# =====================================================================
# 5. UCS, GREEDY BEST-FIRST E A*
# =====================================================================

def executar_pesquisa(
    problem: Problem,
    vehicle_id: int,
    itens_objetivo: Set[int],
    hora_partida: datetime,
    algoritmo: str = "a_star",
    heuristica: Optional[Heuristica] = None,
    itens_ja_no_armazem: Optional[Dict[int, datetime]] = None,
    max_nos_expandidos: Optional[int] = None,
) -> Dict[str, object]:
    """Executa UCS, Greedy ou A* para um veículo e um conjunto de itens.

    `itens_objetivo` deve representar encomendas completas dentro do âmbito
    temporal escolhido. O veículo pode fazer várias viagens ao armazém dentro
    da rota de planeamento. Cada chamada planeia apenas um veículo.
    """
    algoritmo = algoritmo.lower().strip()
    if algoritmo not in {"ucs", "greedy", "a_star"}:
        raise ValueError("algoritmo deve ser 'ucs', 'greedy' ou 'a_star'.")
    if algoritmo in {"greedy", "a_star"} and heuristica is None:
        raise ValueError(f"O algoritmo {algoritmo} necessita de uma heurística.")
    if vehicle_id not in problem.veiculos:
        raise KeyError(f"Veículo desconhecido: {vehicle_id}")

    itens_objetivo = set(itens_objetivo)
    desconhecidos = itens_objetivo.difference(problem.pedidos)
    if desconhecidos:
        raise KeyError(f"Itens objetivo desconhecidos: {sorted(desconhecidos)}")

    itens_ja_no_armazem = dict(itens_ja_no_armazem or {})
    if not set(itens_ja_no_armazem).issubset(itens_objetivo):
        raise ValueError("itens_ja_no_armazem contém IDs que não pertencem a itens_objetivo.")

    inicio = time.perf_counter()
    estado_inicial = State(
        paragem_atual=problem.armazem,
        tempo_atual=hora_partida,
        carga_atual_kg=0.0,
        recolhidos_a_bordo=frozenset(),
        no_armazem=frozenset(itens_ja_no_armazem),
        para_entrega_a_bordo=frozenset(),
        entregues=frozenset(),
        distancia_acumulada_km=0.0,
        historico_paragens=(problem.armazem,),
        chegadas_armazem=tuple(sorted(itens_ja_no_armazem.items())),
    )

    def prioridade(estado: State) -> float:
        g = estado.distancia_acumulada_km
        if algoritmo == "ucs":
            return g
        h = float(heuristica(estado, problem, itens_objetivo))  # type: ignore[misc]
        if not math.isfinite(h) or h < -1e-9:
            raise ValueError(f"A heurística devolveu um valor inválido: {h}")
        return h if algoritmo == "greedy" else g + h

    # (prioridade, contador de desempate, estado, ações acumuladas)
    fronteira: List[Tuple[float, int, State, Acoes]] = []
    contador = 0
    heapq.heappush(fronteira, (prioridade(estado_inicial), contador, estado_inicial, tuple()))

    # Para cada situação logística, mantém pares (km, hora) não dominados.
    visitados: Dict[tuple, List[Tuple[float, datetime]]] = {}
    nos_expandidos = 0
    nos_gerados = 1
    ultima_validacao = None
    limite_atingido = False

    while fronteira:
        _, _, estado_atual, acoes_atuais = heapq.heappop(fronteira)

        # Objetivo: todos os itens entregues, veículo no armazém e sem carga.
        objetivo = (
            itens_objetivo.issubset(estado_atual.entregues)
            and estado_atual.paragem_atual == problem.armazem
            and not (estado_atual.recolhidos_a_bordo & itens_objetivo)
            and not (estado_atual.no_armazem & itens_objetivo)
            and not (estado_atual.para_entrega_a_bordo & itens_objetivo)
            and abs(estado_atual.carga_atual_kg) <= 1e-6
        )
        if objetivo:
            validacao = problem.verificar_viabilidade(
                vehicle_id=vehicle_id,
                acoes=list(acoes_atuais),
                hora_partida=hora_partida,
                chegada_armazem_previa=itens_ja_no_armazem,
                itens_objetivo=itens_objetivo,
                exigir_rota_completa=True,
            )
            ultima_validacao = validacao
            if validacao["viavel"] and validacao["completa"]:
                return {
                    "sucesso": True,
                    "algoritmo": algoritmo,
                    "heuristica": getattr(heuristica, "__name__", None),
                    "distancia_km": round(estado_atual.distancia_acumulada_km, 2),
                    "nos_expandidos": nos_expandidos,
                    "nos_gerados": nos_gerados,
                    "tempo_execucao_s": round(time.perf_counter() - inicio, 6),
                    "rota_paragens": list(estado_atual.historico_paragens),
                    "acoes": list(acoes_atuais),
                    "validacao": validacao,
                    "estado_final": estado_atual,
                    "limite_atingido": False,
                }
            # Uma divergência entre pesquisa e verificador não é aceite como sucesso.
            # Continua a pesquisa para permitir encontrar outro caminho, se existir.

        assinatura = _assinatura_estado(estado_atual)
        g_atual = estado_atual.distancia_acumulada_km
        t_atual = estado_atual.tempo_atual
        fronteira_pareto = visitados.setdefault(assinatura, [])

        # Um estado anterior com menor/igual distância e hora domina este estado.
        if any(g_ant <= g_atual + 1e-9 and t_ant <= t_atual for g_ant, t_ant in fronteira_pareto):
            continue

        # Remove estados que este estado domina.
        visitados[assinatura] = [
            (g_ant, t_ant)
            for g_ant, t_ant in fronteira_pareto
            if not (g_atual <= g_ant + 1e-9 and t_atual <= t_ant)
        ]
        visitados[assinatura].append((g_atual, t_atual))

        if max_nos_expandidos is not None and nos_expandidos >= max_nos_expandidos:
            limite_atingido = True
            break

        nos_expandidos += 1
        for proximo, acoes_passo in sucessores_com_acoes(
            estado_atual, problem, vehicle_id, itens_objetivo
        ):
            contador += 1
            nos_gerados += 1
            heapq.heappush(
                fronteira,
                (prioridade(proximo), contador, proximo, acoes_atuais + acoes_passo),
            )

    return {
        "sucesso": False,
        "algoritmo": algoritmo,
        "heuristica": getattr(heuristica, "__name__", None),
        "distancia_km": float("inf"),
        "nos_expandidos": nos_expandidos,
        "nos_gerados": nos_gerados,
        "tempo_execucao_s": round(time.perf_counter() - inicio, 6),
        "rota_paragens": [],
        "acoes": [],
        "validacao": ultima_validacao,
        "estado_final": None,
        "limite_atingido": limite_atingido,
    }


def ucs(
    problem: Problem,
    vehicle_id: int,
    itens_objetivo: Set[int],
    hora_partida: datetime,
    itens_ja_no_armazem: Optional[Dict[int, datetime]] = None,
    max_nos_expandidos: Optional[int] = None,
) -> Dict[str, object]:
    """Atalho para executar Pesquisa de Custo Uniforme."""
    return executar_pesquisa(
        problem, vehicle_id, itens_objetivo, hora_partida,
        algoritmo="ucs", itens_ja_no_armazem=itens_ja_no_armazem,
        max_nos_expandidos=max_nos_expandidos,
    )


def greedy_search(
    problem: Problem,
    vehicle_id: int,
    itens_objetivo: Set[int],
    hora_partida: datetime,
    heuristica: Heuristica = h1_pedido_mais_caro,
    itens_ja_no_armazem: Optional[Dict[int, datetime]] = None,
    max_nos_expandidos: Optional[int] = None,
) -> Dict[str, object]:
    """Atalho para executar Greedy Best-First com H1 ou H2."""
    return executar_pesquisa(
        problem, vehicle_id, itens_objetivo, hora_partida,
        algoritmo="greedy", heuristica=heuristica,
        itens_ja_no_armazem=itens_ja_no_armazem,
        max_nos_expandidos=max_nos_expandidos,
    )


def a_star_search(
    problem: Problem,
    vehicle_id: int,
    itens_objetivo: Set[int],
    hora_partida: datetime,
    heuristica: Heuristica = h1_pedido_mais_caro,
    itens_ja_no_armazem: Optional[Dict[int, datetime]] = None,
    max_nos_expandidos: Optional[int] = None,
) -> Dict[str, object]:
    """Atalho para executar A* com H1 ou H2."""
    return executar_pesquisa(
        problem, vehicle_id, itens_objetivo, hora_partida,
        algoritmo="a_star", heuristica=heuristica,
        itens_ja_no_armazem=itens_ja_no_armazem,
        max_nos_expandidos=max_nos_expandidos,
    )


# =====================================================================
# 6. SELEÇÃO DE ENCOMENDAS E COMPARAÇÃO
# =====================================================================

def selecionar_itens_veiculo_dia(
    problem: Problem,
    vehicle_id: int,
    dia: date,
    max_encomendas: Optional[int] = None,
) -> Set[int]:
    """Seleciona encomendas completas com recolha e entrega no mesmo dia.

    A capacidade é verificada por encomenda (uma encomenda completa tem de caber
    num veículo), mas não se limita a soma de todas as encomendas à capacidade:
    o veículo pode fazer várias viagens ao armazém no mesmo dia.

    Esta função é um auxiliar de testes; não substitui a atribuição de tarefas
    aos dois veículos que será feita na integração/CSP.
    """
    if vehicle_id not in problem.veiculos:
        raise KeyError(f"Veículo desconhecido: {vehicle_id}")
    capacidade = problem.veiculos[vehicle_id].capacity_kg

    por_encomenda: Dict[int, List[Request]] = {}
    for req in problem.pedidos.values():
        por_encomenda.setdefault(req.order_id, []).append(req)

    candidatas = []
    for order_id, pedidos_ordem in por_encomenda.items():
        # Só seleciona a encomenda se todas as suas linhas pertencem ao dia pedido.
        if not all(r.dia_recolha == dia and r.dia_entrega == dia for r in pedidos_ordem):
            continue
        peso = sum(r.weight_kg for r in pedidos_ordem)
        if peso > capacidade + 1e-6:
            continue
        fecho_mais_cedo = min(r.delivery_end for r in pedidos_ordem)
        candidatas.append((fecho_mais_cedo, order_id, pedidos_ordem))

    candidatas.sort(key=lambda x: (x[0], x[1]))
    selecionados: Set[int] = set()
    numero = 0
    for _, _, pedidos_ordem in candidatas:
        selecionados.update(r.item_id for r in pedidos_ordem)
        numero += 1
        if max_encomendas is not None and numero >= max_encomendas:
            break
    return selecionados


def comparar_algoritmos(
    problem: Problem,
    vehicle_id: int,
    itens_objetivo: Set[int],
    hora_partida: datetime,
    itens_ja_no_armazem: Optional[Dict[int, datetime]] = None,
    max_nos_expandidos: Optional[int] = None,
) -> Tuple[pd.DataFrame, Dict[str, Dict[str, object]]]:
    """Compara UCS, Greedy(H1/H2) e A*(H1/H2) no mesmo conjunto de itens."""
    configuracoes = [
        ("UCS", "ucs", None),
        ("Greedy — H1 pedido mais caro", "greedy", h1_pedido_mais_caro),
        ("Greedy — H2 MST", "greedy", h2_mst),
        ("A* — H1 pedido mais caro", "a_star", h1_pedido_mais_caro),
        ("A* — H2 MST", "a_star", h2_mst),
    ]

    linhas = []
    detalhes: Dict[str, Dict[str, object]] = {}
    for nome, algoritmo, heuristica in configuracoes:
        resultado = executar_pesquisa(
            problem=problem,
            vehicle_id=vehicle_id,
            itens_objetivo=set(itens_objetivo),
            hora_partida=hora_partida,
            algoritmo=algoritmo,
            heuristica=heuristica,
            itens_ja_no_armazem=itens_ja_no_armazem,
            max_nos_expandidos=max_nos_expandidos,
        )
        detalhes[nome] = resultado
        validacao = resultado["validacao"]
        viavel = bool(validacao and validacao.get("viavel", False))
        linhas.append({
            "Algoritmo": nome,
            "Sucesso": resultado["sucesso"],
            "Viável (verificador)": viavel,
            "Distância (km)": resultado["distancia_km"],
            "Nós expandidos": resultado["nos_expandidos"],
            "Nós gerados": resultado["nos_gerados"],
            "Tempo (s)": resultado["tempo_execucao_s"],
            "Limite atingido": resultado["limite_atingido"],
            "Rota": " -> ".join(map(str, resultado["rota_paragens"])),
        })

    return pd.DataFrame(linhas), detalhes


# =====================================================================
# 7. OTIMIZAÇÃO CONJUNTA DOS DOIS VEÍCULOS
# =====================================================================

def _gerar_atribuicoes_frota(
    problem: Problem,
    grupos_ordem: Dict[int, Tuple[int, ...]],
    vehicle_ids: Tuple[int, int],
    exigir_ambos_veiculos: bool = True,
    ordem_fixa_por_encomenda: Optional[Dict[int, int]] = None,
) -> Iterator[Dict[int, Set[int]]]:
    """Gera distribuições completas de encomendas pelos dois veículos.

    Cada encomenda é atribuída integralmente a um veículo. A ordem de exploração
    dá prioridade às encomendas mais pesadas/mais restritas e tenta equilibrar a
    carga atribuída para encontrar boas soluções cedo quando existe um limite.
    """
    capacidade = {
        vid: float(problem.veiculos[vid].capacity_kg) for vid in vehicle_ids
    }
    peso_ordem = {
        order_id: _peso_itens(problem, item_ids)
        for order_id, item_ids in grupos_ordem.items()
    }
    veiculos_elegiveis: Dict[int, Tuple[int, ...]] = {}
    ordem_fixa_por_encomenda = ordem_fixa_por_encomenda or {}
    for order_id in grupos_ordem:
        elegiveis = tuple(
            vid for vid in vehicle_ids
            if peso_ordem[order_id] <= capacidade[vid] + 1e-6
            and (order_id not in ordem_fixa_por_encomenda or ordem_fixa_por_encomenda[order_id] == vid)
        )
        if not elegiveis:
            raise ValueError(
                f"A encomenda {order_id} ({peso_ordem[order_id]:.2f} kg) "
                "não cabe em nenhum dos veículos selecionados."
            )
        veiculos_elegiveis[order_id] = elegiveis

    # Primeiro as encomendas com menos veículos possíveis; depois as mais pesadas.
    ordem_decisao = sorted(
        grupos_ordem,
        key=lambda oid: (
            len(veiculos_elegiveis[oid]),
            -peso_ordem[oid],
            min(problem.pedidos[i].delivery_end for i in grupos_ordem[oid]),
            oid,
        ),
    )

    atribuicao = {vid: set() for vid in vehicle_ids}
    peso_atribuido = {vid: 0.0 for vid in vehicle_ids}

    def recursao(indice: int) -> Iterator[Dict[int, Set[int]]]:
        if indice == len(ordem_decisao):
            if exigir_ambos_veiculos and any(not atribuicao[vid] for vid in vehicle_ids):
                return
            yield {vid: set(itens) for vid, itens in atribuicao.items()}
            return

        order_id = ordem_decisao[indice]
        elegiveis = veiculos_elegiveis[order_id]
        # Explora primeiro o veículo com menor ocupação relativa.
        candidatos = sorted(
            elegiveis,
            key=lambda vid: (peso_atribuido[vid] / capacidade[vid], vid),
        )
        for vehicle_id in candidatos:
            atribuicao[vehicle_id].update(grupos_ordem[order_id])
            peso_atribuido[vehicle_id] += peso_ordem[order_id]
            yield from recursao(indice + 1)
            peso_atribuido[vehicle_id] -= peso_ordem[order_id]
            atribuicao[vehicle_id].difference_update(grupos_ordem[order_id])

    yield from recursao(0)


def _contar_atribuicoes_possiveis(
    problem: Problem,
    grupos_ordem: Dict[int, Tuple[int, ...]],
    vehicle_ids: Tuple[int, int],
    exigir_ambos_veiculos: bool,
    ordem_fixa_por_encomenda: Optional[Dict[int, int]] = None,
) -> int:
    """Conta distribuições possíveis após excluir encomendas que não cabem."""
    total = 1
    ordem_fixa_por_encomenda = ordem_fixa_por_encomenda or {}
    elegiveis_por_ordem: Dict[int, Set[int]] = {}
    for order_id, item_ids in grupos_ordem.items():
        peso = _peso_itens(problem, item_ids)
        elegiveis = {
            vid for vid in vehicle_ids
            if peso <= problem.veiculos[vid].capacity_kg + 1e-6
            and (order_id not in ordem_fixa_por_encomenda or ordem_fixa_por_encomenda[order_id] == vid)
        }
        if not elegiveis:
            return 0
        elegiveis_por_ordem[order_id] = elegiveis
        total *= len(elegiveis)

    if exigir_ambos_veiculos:
        # Uma atribuição sem um dos veículos só é possível quando o outro pode
        # receber todas as encomendas; essas duas atribuições são excluídas.
        for vehicle_vazio in vehicle_ids:
            outro = next(vid for vid in vehicle_ids if vid != vehicle_vazio)
            if all(outro in elegiveis for elegiveis in elegiveis_por_ordem.values()):
                total -= 1
    return total


def otimizar_frota(
    problem: Problem,
    itens_objetivo: Set[int],
    hora_partida: datetime,
    vehicle_ids: Optional[Iterable[int]] = None,
    algoritmo: str = "a_star",
    heuristica: Optional[Heuristica] = h1_pedido_mais_caro,
    max_particoes: Optional[int] = 128,
    max_nos_expandidos_por_veiculo: Optional[int] = 100_000,
    exigir_ambos_veiculos: bool = True,
    itens_ja_no_armazem_por_veiculo: Optional[Dict[int, Dict[int, datetime]]] = None,
) -> Dict[str, object]:
    """Procura uma boa atribuição de encomendas e rotas para dois veículos.

    Para cada distribuição candidata:
      1. atribui cada encomenda inteira a um dos veículos;
      2. executa a pesquisa individual para cada veículo;
      3. valida as duas rotas em conjunto;
      4. compara a soma das distâncias percorridas.

    ``max_particoes=None`` explora todas as distribuições viáveis. Para conjuntos
    maiores, o limite por omissão evita iniciar milhões de pesquisas. Se o limite
    for atingido, o resultado é a melhor solução encontrada, não uma prova de
    ótimo global. O limite de nós é aplicado separadamente a cada rota.

    Para uma garantia mais forte de ótimo por atribuição, usar ``algoritmo='ucs'``
    e ``max_nos_expandidos_por_veiculo=None``. Com A*, a qualidade ótima depende
    da admissibilidade da heurística escolhida.
    """
    inicio = time.perf_counter()
    algoritmo = algoritmo.strip().lower()
    if algoritmo not in {"ucs", "greedy", "a_star"}:
        raise ValueError("algoritmo deve ser 'ucs', 'greedy' ou 'a_star'.")
    if algoritmo in {"greedy", "a_star"} and heuristica is None:
        heuristica = h1_pedido_mais_caro
    if max_particoes is not None and max_particoes < 1:
        raise ValueError("max_particoes tem de ser >= 1 ou None.")
    if max_nos_expandidos_por_veiculo is not None and max_nos_expandidos_por_veiculo < 1:
        raise ValueError("max_nos_expandidos_por_veiculo tem de ser >= 1 ou None.")

    ids_veiculos = tuple(sorted(vehicle_ids if vehicle_ids is not None else problem.veiculos))
    if len(ids_veiculos) != 2 or len(set(ids_veiculos)) != 2:
        raise ValueError(
            f"Esta função foi concebida para exatamente dois veículos; recebidos: {ids_veiculos}."
        )
    desconhecidos = set(ids_veiculos).difference(problem.veiculos)
    if desconhecidos:
        raise KeyError(f"Veículos desconhecidos: {sorted(desconhecidos)}")

    objetivo = set(itens_objetivo)
    if not objetivo:
        raise ValueError("itens_objetivo não pode estar vazio.")
    grupos_ordem = _itens_por_encomenda(problem, objetivo)

    # A otimização trabalha com encomendas completas, não com linhas isoladas.
    grupos_completos: Dict[int, Set[int]] = {}
    for req in problem.pedidos.values():
        grupos_completos.setdefault(req.order_id, set()).add(req.item_id)
    for order_id, item_ids in grupos_ordem.items():
        completos = grupos_completos[order_id]
        if set(item_ids) != completos:
            falta = sorted(completos.difference(item_ids))
            raise ValueError(
                f"A encomenda {order_id} não está completa em itens_objetivo; faltam {falta}."
            )

    # Validar de forma explícita que todos os itens estão nas encomendas completas.
    if len(grupos_ordem) == 0:
        raise ValueError("Não existem encomendas para distribuir.")

    # Itens já armazenados antes do início da pesquisa fixam a encomenda ao
    # veículo que os recolheu; as restantes linhas dessa encomenda seguem o mesmo veículo.
    chegadas_iniciais = itens_ja_no_armazem_por_veiculo or {}
    ordem_fixa_por_encomenda: Dict[int, int] = {}
    for vehicle_id, itens_stock in chegadas_iniciais.items():
        if vehicle_id not in ids_veiculos:
            raise ValueError(f"O stock inicial refere o veículo {vehicle_id}, fora da frota selecionada.")
        itens_stock = set(itens_stock)
        fora_objetivo = itens_stock.difference(objetivo)
        if fora_objetivo:
            raise ValueError(
                f"O stock inicial do veículo {vehicle_id} contém itens fora do objetivo: {sorted(fora_objetivo)}."
            )
        for item_id in itens_stock:
            order_id = problem.pedidos[item_id].order_id
            anterior = ordem_fixa_por_encomenda.get(order_id)
            if anterior is not None and anterior != vehicle_id:
                raise ValueError(
                    f"A encomenda {order_id} tem itens em stock em dois veículos diferentes."
                )
            ordem_fixa_por_encomenda[order_id] = vehicle_id

    total_particoes = _contar_atribuicoes_possiveis(
        problem, grupos_ordem, ids_veiculos, exigir_ambos_veiculos,
        ordem_fixa_por_encomenda=ordem_fixa_por_encomenda,
    )
    if total_particoes == 0:
        return {
            "sucesso": False,
            "algoritmo": algoritmo,
            "heuristica": getattr(heuristica, "__name__", None),
            "mensagem": "Não existem distribuições que respeitem a capacidade por encomenda.",
            "particoes_possiveis": 0,
            "particoes_avaliadas": 0,
            "limite_particoes_atingido": False,
            "otimo_global_comprovado": False,
            "melhor_solucao": None,
            "tempo_execucao_s": round(time.perf_counter() - inicio, 6),
        }

    melhor_solucao: Optional[Dict[str, object]] = None
    particoes_avaliadas = 0
    particoes_viaveis = 0
    particoes_sem_rota = 0
    pesquisas_limitadas = 0
    nos_expandidos_total = 0
    nos_gerados_total = 0
    limite_particoes_atingido = False

    for atribuicao in _gerar_atribuicoes_frota(
        problem, grupos_ordem, ids_veiculos, exigir_ambos_veiculos,
        ordem_fixa_por_encomenda=ordem_fixa_por_encomenda,
    ):
        if max_particoes is not None and particoes_avaliadas >= max_particoes:
            limite_particoes_atingido = True
            break
        particoes_avaliadas += 1

        resultados: Dict[int, Dict[str, object]] = {}
        atribuicao_completa = True
        for vehicle_id in ids_veiculos:
            itens_veiculo = set(atribuicao[vehicle_id])
            resultado = executar_pesquisa(
                problem=problem,
                vehicle_id=vehicle_id,
                itens_objetivo=itens_veiculo,
                hora_partida=hora_partida,
                algoritmo=algoritmo,
                heuristica=heuristica,
                itens_ja_no_armazem=(itens_ja_no_armazem_por_veiculo or {}).get(vehicle_id),
                max_nos_expandidos=max_nos_expandidos_por_veiculo,
            )
            resultados[vehicle_id] = resultado
            nos_expandidos_total += int(resultado.get("nos_expandidos", 0))
            nos_gerados_total += int(resultado.get("nos_gerados", 0))
            if resultado.get("limite_atingido"):
                pesquisas_limitadas += 1
            if not resultado.get("sucesso"):
                atribuicao_completa = False
                break

        if not atribuicao_completa:
            particoes_sem_rota += 1
            continue

        validacao_global = problem.verificar_plano_frota(
            atribuicao=atribuicao,
            resultados=resultados,
            hora_partida=hora_partida,
            itens_objetivo=objetivo,
            itens_ja_no_armazem_por_veiculo=itens_ja_no_armazem_por_veiculo,
        )
        if not validacao_global.get("viavel") or not validacao_global.get("completa"):
            particoes_sem_rota += 1
            continue

        particoes_viaveis += 1
        distancia_total = float(validacao_global["distancia_total_km"])
        duracao_total = sum(
            float(resultados[vid].get("validacao", {}).get("duracao_total_min", 0.0))
            for vid in ids_veiculos
        )
        candidato = {
            "atribuicao_itens": {vid: set(atribuicao[vid]) for vid in ids_veiculos},
            "atribuicao_encomendas": {
                vid: sorted({problem.pedidos[iid].order_id for iid in atribuicao[vid]})
                for vid in ids_veiculos
            },
            "resultados_por_veiculo": resultados,
            "validacao_global": validacao_global,
            "distancia_total_km": round(distancia_total, 2),
            "duracao_total_veiculos_min": round(duracao_total, 1),
        }
        if (
            melhor_solucao is None
            or distancia_total < float(melhor_solucao["distancia_total_km"]) - 1e-9
            or (
                abs(distancia_total - float(melhor_solucao["distancia_total_km"])) <= 1e-9
                and duracao_total < float(melhor_solucao["duracao_total_veiculos_min"])
            )
        ):
            melhor_solucao = candidato

    # Se ainda existirem distribuições por gerar, o limite foi atingido.
    if not limite_particoes_atingido and max_particoes is not None:
        # A enumeração pode ter terminado exatamente no limite. Confirmamos com
        # um iterador novo, sem executar qualquer pesquisa adicional.
        geradas = 0
        for _ in _gerar_atribuicoes_frota(
            problem, grupos_ordem, ids_veiculos, exigir_ambos_veiculos,
            ordem_fixa_por_encomenda=ordem_fixa_por_encomenda,
        ):
            geradas += 1
            if geradas > particoes_avaliadas:
                limite_particoes_atingido = True
                break

    todas_avaliadas = (
        not limite_particoes_atingido and particoes_avaliadas == total_particoes
    )
    sem_limites_internos = pesquisas_limitadas == 0
    # A prova de ótimo global é conservadora: UCS tem custo uniforme e só é
    # considerada prova quando todas as atribuições e pesquisas terminaram.
    otimo_global = (
        melhor_solucao is not None
        and todas_avaliadas
        and sem_limites_internos
        and algoritmo == "ucs"
    )

    return {
        "sucesso": melhor_solucao is not None,
        "algoritmo": algoritmo,
        "heuristica": getattr(heuristica, "__name__", None),
        "vehicle_ids": ids_veiculos,
        "numero_encomendas": len(grupos_ordem),
        "numero_itens": len(objetivo),
        "particoes_possiveis": total_particoes,
        "particoes_avaliadas": particoes_avaliadas,
        "particoes_viaveis": particoes_viaveis,
        "particoes_sem_rota": particoes_sem_rota,
        "pesquisas_limitadas": pesquisas_limitadas,
        "nos_expandidos_total": nos_expandidos_total,
        "nos_gerados_total": nos_gerados_total,
        "limite_particoes_atingido": limite_particoes_atingido,
        "todas_as_particoes_avaliadas": todas_avaliadas,
        "otimo_global_comprovado": otimo_global,
        "melhor_solucao": melhor_solucao,
        "tempo_execucao_s": round(time.perf_counter() - inicio, 6),
        "nota": (
            "Ótimo global comprovado para o modelo e objetivo de distância."
            if otimo_global else
            "Melhor solução encontrada entre as distribuições avaliadas; "
            "não é uma prova de ótimo global."
        ),
    }


def comparar_algoritmos_frota(
    problem: Problem,
    itens_objetivo: Set[int],
    hora_partida: datetime,
    vehicle_ids: Optional[Iterable[int]] = None,
    max_particoes: Optional[int] = 128,
    max_nos_expandidos_por_veiculo: Optional[int] = 100_000,
    exigir_ambos_veiculos: bool = True,
    itens_ja_no_armazem_por_veiculo: Optional[Dict[int, Dict[int, datetime]]] = None,
) -> Tuple[pd.DataFrame, Dict[str, Dict[str, object]]]:
    """Compara UCS, Greedy(H1/H2) e A*(H1/H2) para a frota completa.

    Cada configuração pode encontrar uma distribuição diferente das encomendas,
    pois a função otimiza a atribuição e as duas rotas em conjunto.
    """
    configuracoes = [
        ("UCS", "ucs", None),
        ("Greedy — H1 pedido mais caro", "greedy", h1_pedido_mais_caro),
        ("Greedy — H2 MST", "greedy", h2_mst),
        ("A* — H1 pedido mais caro", "a_star", h1_pedido_mais_caro),
        ("A* — H2 MST", "a_star", h2_mst),
    ]
    linhas: List[Dict[str, object]] = []
    detalhes: Dict[str, Dict[str, object]] = {}

    for nome, algoritmo, heuristica in configuracoes:
        resultado = otimizar_frota(
            problem=problem,
            itens_objetivo=set(itens_objetivo),
            hora_partida=hora_partida,
            vehicle_ids=vehicle_ids,
            algoritmo=algoritmo,
            heuristica=heuristica,
            max_particoes=max_particoes,
            max_nos_expandidos_por_veiculo=max_nos_expandidos_por_veiculo,
            exigir_ambos_veiculos=exigir_ambos_veiculos,
            itens_ja_no_armazem_por_veiculo=itens_ja_no_armazem_por_veiculo,
        )
        detalhes[nome] = resultado
        melhor = resultado.get("melhor_solucao")
        linhas.append({
            "Método": nome,
            "Sucesso": bool(resultado.get("sucesso")),
            "Distância total (km)": (
                melhor.get("distancia_total_km") if melhor else float("inf")
            ),
            "Partições avaliadas": resultado.get("particoes_avaliadas", 0),
            "Partições viáveis": resultado.get("particoes_viaveis", 0),
            "Nós expandidos (total)": resultado.get("nos_expandidos_total", 0),
            "Tempo total (s)": resultado.get("tempo_execucao_s", 0.0),
            "Ótimo global provado": bool(resultado.get("otimo_global_comprovado", False)),
            "Limite atingido": bool(resultado.get("limite_particoes_atingido", False))
                or int(resultado.get("pesquisas_limitadas", 0)) > 0,
        })

    return pd.DataFrame(linhas), detalhes


def tabela_resultado_frota(resultado_frota: Dict[str, object]) -> pd.DataFrame:
    """Cria uma tabela compacta com uma linha por veículo da melhor solução."""
    melhor = resultado_frota.get("melhor_solucao")
    if not melhor:
        return pd.DataFrame(columns=[
            "Veículo", "Encomendas", "Itens", "Distância (km)",
            "Nós expandidos", "Tempo (s)", "Sucesso",
        ])

    linhas = []
    resultados = melhor["resultados_por_veiculo"]
    for vehicle_id, resultado in sorted(resultados.items()):
        linhas.append({
            "Veículo": vehicle_id,
            "Encomendas": ", ".join(map(str, melhor["atribuicao_encomendas"][vehicle_id])),
            "Itens": len(melhor["atribuicao_itens"][vehicle_id]),
            "Distância (km)": resultado["distancia_km"],
            "Nós expandidos": resultado["nos_expandidos"],
            "Tempo (s)": resultado["tempo_execucao_s"],
            "Sucesso": resultado["sucesso"],
        })
    return pd.DataFrame(linhas)


# =====================================================================
# 7. EXECUÇÃO DE DEMONSTRAÇÃO
# =====================================================================

if __name__ == "__main__":
    import os

    pasta_teste = (
        "docs/data_tiny/" if os.path.isdir("docs/data_tiny/")
        else "docs/data_small_30_31oct2026/"
    )
    if os.path.isdir(pasta_teste):
        problem = Problem(pasta_teste)
        data_inicio = date.fromisoformat(str(problem.regras["start_date"]))
        hora_inicio = datetime.combine(data_inicio, datetime.min.time()) + timedelta(hours=7)
        itens = selecionar_itens_veiculo_dia(
            problem, vehicle_id=1, dia=data_inicio, max_encomendas=3
        )
        print(f"Instância: {pasta_teste}")
        print(f"Veículo: 1 | Dia: {data_inicio} | Itens objetivo: {sorted(itens)}")
        tabela, _ = comparar_algoritmos(
            problem, vehicle_id=1, itens_objetivo=itens, hora_partida=hora_inicio,
            max_nos_expandidos=100_000,
        )
        print(tabela.to_string(index=False))
    else:
        print("pesquisa.py carregado. Coloca a pasta docs/data_tiny/ para executar a demonstração.")
