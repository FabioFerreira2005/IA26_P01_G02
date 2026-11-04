"""
pesquisa.py — Pesquisa informada (UCS, Greedy Best-First e A*) sobre o model.py.

IA 2026/27 · TP1 · Grupo 02 (IA26_P01_G02)

Decisões de modelação (explicadas no notebook 02_pesquisa_informada.ipynb):
  1. Cada encomenda é servida por um único veículo e os itens de uma encomenda
     são entregues juntos (decisão da EDA).
  2. O problema é dividido por veículo e por dia (Subproblema). Cada dia começa
     e acaba no armazém. Os itens recolhidos num dia e entregues no dia seguinte
     passam a noite no armazém (limite de 24 h verificado ao carregar).
  3. Uma ação é uma visita a uma paragem: recolher num produtor, ir ao armazém
     (descarregar e/ou carregar) ou entregar num cliente. O veículo pode esperar
     pela abertura de uma janela.
  4. O custo g(n) é a distância real percorrida (km); as heurísticas usam as
     distâncias mínimas (Floyd-Warshall) do model.py.
  5. Cada rota encontrada é validada no fim com Problem.verificar_viabilidade().
"""

import heapq
import itertools
import os
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Callable, Dict, FrozenSet, List, Optional, Tuple

# o model.py está na pasta-mãe (raiz do repositório)
_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from model import Problem, State  # noqa: E402

from heuristicas import h_zero  # noqa: E402

MIN = timedelta(minutes=1)


# =====================================================================
# 1. SUBPROBLEMA: um veículo num dia
# =====================================================================

@dataclass
class Subproblema:
    problem: Problem
    vehicle_id: int
    dia: date
    recolher: FrozenSet[int]                     # itens a recolher hoje
    entregar: FrozenSet[int]                     # itens a entregar hoje
    chegadas_previas: Dict[int, datetime]        # itens já no armazém (de ontem) -> hora de chegada
    hora_inicio: datetime = None

    def __post_init__(self):
        if self.hora_inicio is None:
            self.hora_inicio = datetime.combine(self.dia, datetime.min.time()) + timedelta(hours=6)
        pb = self.problem
        self.veiculo = pb.veiculos[self.vehicle_id]
        self.capacidade = self.veiculo.capacity_kg
        # itens de cada encomenda que têm de ser entregues hoje
        self.itens_encomenda: Dict[int, List[int]] = {}
        for iid in sorted(self.entregar):
            self.itens_encomenda.setdefault(pb.pedidos[iid].order_id, []).append(iid)

    def estado_inicial(self) -> State:
        return State(
            paragem_atual=self.problem.armazem,
            tempo_atual=self.hora_inicio,
            no_armazem=frozenset(self.chegadas_previas),
            historico_paragens=(self.problem.armazem,),
            chegadas_armazem=tuple(sorted(self.chegadas_previas.items())),
        )

    def objetivo(self, s: State) -> bool:
        """Tudo recolhido e descarregado, tudo o que é de hoje entregue, veículo vazio no armazém."""
        if s.paragem_atual != self.problem.armazem or s.recolhidos_a_bordo or s.para_entrega_a_bordo:
            return False
        if not self.entregar <= s.entregues:
            return False
        tratados = s.no_armazem | s.entregues
        return self.recolher <= tratados


# =====================================================================
# 2. SUCESSORES
# =====================================================================

def _por_recolher(sub: Subproblema, s: State):
    feitos = s.recolhidos_a_bordo | s.no_armazem | s.para_entrega_a_bordo | s.entregues
    return [i for i in sub.recolher if i not in feitos]


def _novo_estado(s: State, **mud) -> State:
    base = dict(
        paragem_atual=s.paragem_atual, tempo_atual=s.tempo_atual, carga_atual_kg=s.carga_atual_kg,
        recolhidos_a_bordo=s.recolhidos_a_bordo, no_armazem=s.no_armazem,
        para_entrega_a_bordo=s.para_entrega_a_bordo, entregues=s.entregues,
        distancia_acumulada_km=s.distancia_acumulada_km, historico_paragens=s.historico_paragens,
        chegadas_armazem=s.chegadas_armazem,
    )
    base.update(mud)
    return State(**base)


def sem_saida(sub: Subproblema, s: State) -> bool:
    """Poda: devolve True se algum item já não pode ser servido a tempo (beco sem saída)."""
    pb = sub.problem
    t = s.tempo_atual
    for i in _por_recolher(sub, s):
        if pb.pedidos[i].availability_end < t:
            return True
    for i in sub.entregar:
        if i not in s.entregues and pb.pedidos[i].delivery_end < t:
            return True
    limite = timedelta(hours=pb.permanencia_max_h)
    for i, chegada in s.chegadas_armazem:
        if i in sub.entregar and t - chegada > limite:
            return True
    return False


def sucessores(sub: Subproblema, s: State):
    """
    Gera (descricao, acoes_model, novo_estado). As ações estão no formato do
    verificar_viabilidade(): ("pickup", item), ("warehouse", A), ("load", item), ("delivery", item).
    """
    pb = sub.problem
    A = pb.armazem
    cap = sub.capacidade
    atual, t = s.paragem_atual, s.tempo_atual
    resultado = []

    # ---------- (a) recolher num produtor ----------
    por_produtor: Dict[int, List[int]] = {}
    for i in _por_recolher(sub, s):
        por_produtor.setdefault(pb.pedidos[i].pickup_loc, []).append(i)

    for p, itens in por_produtor.items():
        if p == atual:
            continue  # duas visitas seguidas ao mesmo sítio seriam uma só visita
        chegada = t + pb.tempo[(atual, p)] * MIN
        cands = [i for i in itens if pb.pedidos[i].availability_end >= chegada]
        if not cands:
            continue
        vistos = set()
        # variantes: começar o serviço à chegada ou esperar pela abertura de cada janela
        for t_alvo in sorted({max(chegada, pb.pedidos[i].availability_start) for i in cands}):
            escolhidos = [i for i in cands
                          if pb.pedidos[i].availability_start <= t_alvo <= pb.pedidos[i].availability_end]
            escolhidos.sort(key=lambda i: (pb.pedidos[i].availability_end, i))
            carga, levar = s.carga_atual_kg, []
            for i in escolhidos:
                if carga + pb.pedidos[i].weight_kg <= cap + 1e-6:
                    levar.append(i)
                    carga += pb.pedidos[i].weight_kg
            chave = frozenset(levar)
            if not levar or chave in vistos:
                continue
            vistos.add(chave)
            inicio = max([chegada] + [pb.pedidos[i].availability_start for i in levar])
            novo = _novo_estado(
                s, paragem_atual=p, tempo_atual=inicio + pb.tempo_servico_min * MIN,
                carga_atual_kg=carga, recolhidos_a_bordo=s.recolhidos_a_bordo | chave,
                distancia_acumulada_km=s.distancia_acumulada_km + pb.distancia[(atual, p)],
                historico_paragens=s.historico_paragens + (p,),
            )
            acoes = [("pickup", i) for i in levar]
            resultado.append((f"recolher em {p} ({len(levar)} itens) às {inicio:%H:%M}", acoes, novo))

    # ---------- (b) ir ao armazém: descarregar e/ou carregar ----------
    chegada = t + pb.tempo[(atual, A)] * MIN
    relogio = chegada
    descarregar = s.recolhidos_a_bordo
    chegadas = dict(s.chegadas_armazem)
    carga = s.carga_atual_kg
    no_armazem = s.no_armazem
    if descarregar:
        relogio = chegada + pb.tempo_armazem_min * MIN
        for i in descarregar:
            chegadas[i] = chegada
            carga -= pb.pedidos[i].weight_kg
        no_armazem = no_armazem | descarregar
    inicio_carga = relogio

    # encomendas de hoje completas no armazém, ainda a tempo e dentro das 24 h
    limite = timedelta(hours=pb.permanencia_max_h)
    prontas = []
    for oid, itens in sub.itens_encomenda.items():
        if not all(i in no_armazem for i in itens):
            continue
        req = pb.pedidos[itens[0]]
        if inicio_carga + (pb.tempo_armazem_min + pb.tempo[(A, req.delivery_loc)]) * MIN > req.delivery_end:
            continue
        if any(inicio_carga - chegadas[i] > limite for i in itens):
            continue
        prontas.append((req.delivery_end, oid, itens))
    prontas.sort()
    carregar, c = [], carga
    for _, oid, itens in prontas:
        peso = sum(pb.pedidos[i].weight_kg for i in itens)
        if c + peso <= cap + 1e-6:
            carregar.extend(itens)
            c += peso

    variantes = []
    if carregar:
        variantes.append(carregar)               # descarregar e carregar tudo o que está pronto
    if descarregar and atual != A:
        variantes.append([])                     # só descarregar
    if not descarregar and not carregar and atual != A:
        # regresso final ao armazém (só faz sentido se não houver mais nada a fazer fora)
        if not _por_recolher(sub, s) and not s.para_entrega_a_bordo:
            variantes.append([])
    for carregar_v in variantes:
        if atual == A and not carregar_v:
            continue
        cv = frozenset(carregar_v)
        rel = inicio_carga + (pb.tempo_armazem_min * MIN if cv else timedelta(0))
        chegadas_v = {i: h for i, h in chegadas.items() if i not in cv}
        novo = _novo_estado(
            s, paragem_atual=A, tempo_atual=rel,
            carga_atual_kg=carga + sum(pb.pedidos[i].weight_kg for i in cv),
            recolhidos_a_bordo=frozenset(), no_armazem=no_armazem - cv,
            para_entrega_a_bordo=s.para_entrega_a_bordo | cv,
            distancia_acumulada_km=s.distancia_acumulada_km + pb.distancia[(atual, A)],
            historico_paragens=s.historico_paragens + ((A,) if atual != A else ()),
            chegadas_armazem=tuple(sorted(chegadas_v.items())),
        )
        acoes = [("warehouse", A)] + [("load", i) for i in sorted(cv)]
        desc = f"armazém: descarrega {len(descarregar)}, carrega {len(cv)}"
        resultado.append((desc, acoes, novo))

    # ---------- (c) entregar num cliente ----------
    por_cliente: Dict[int, Dict[int, List[int]]] = {}
    for i in s.para_entrega_a_bordo:
        req = pb.pedidos[i]
        por_cliente.setdefault(req.delivery_loc, {}).setdefault(req.order_id, []).append(i)

    for loc, encomendas in por_cliente.items():
        if loc == atual:
            continue
        chegada = t + pb.tempo[(atual, loc)] * MIN
        cands = {oid: itens for oid, itens in encomendas.items()
                 if pb.pedidos[itens[0]].delivery_end >= chegada}
        if not cands:
            continue
        vistos = set()
        for t_alvo in sorted({max(chegada, pb.pedidos[it[0]].delivery_start) for it in cands.values()}):
            escolhidas = [oid for oid, it in cands.items()
                          if pb.pedidos[it[0]].delivery_start <= t_alvo <= pb.pedidos[it[0]].delivery_end]
            chave = frozenset(escolhidas)
            if not escolhidas or chave in vistos:
                continue
            vistos.add(chave)
            itens = sorted(i for oid in escolhidas for i in cands[oid])
            inicio = max([chegada] + [pb.pedidos[i].delivery_start for i in itens])
            fi = frozenset(itens)
            novo = _novo_estado(
                s, paragem_atual=loc, tempo_atual=inicio + pb.tempo_servico_min * MIN,
                carga_atual_kg=s.carga_atual_kg - sum(pb.pedidos[i].weight_kg for i in itens),
                para_entrega_a_bordo=s.para_entrega_a_bordo - fi, entregues=s.entregues | fi,
                distancia_acumulada_km=s.distancia_acumulada_km + pb.distancia[(atual, loc)],
                historico_paragens=s.historico_paragens + (loc,),
            )
            acoes = [("delivery", i) for i in itens]
            resultado.append((f"entregar em {loc} ({len(escolhidas)} encomendas) às {inicio:%H:%M}", acoes, novo))

    return [r for r in resultado if not sem_saida(sub, r[2])]


# =====================================================================
# 3. ALGORITMOS: UCS, Greedy Best-First, A*
# =====================================================================

@dataclass
class No:
    estado: State
    pai: Optional["No"]
    acoes: List[Tuple[str, int]]
    descricao: str


def _chave(s: State):
    """Estados com a mesma chave só diferem na distância e na hora (comparados por dominância)."""
    return (s.paragem_atual, s.recolhidos_a_bordo, s.no_armazem,
            s.para_entrega_a_bordo, s.entregues, s.chegadas_armazem)


def pesquisar(sub: Subproblema, estrategia: str, heuristica: Callable = h_zero,
              max_expansoes: int = 300_000, limite_s: float = 120.0,
              estado_inicial: Optional[State] = None) -> Dict:
    """
    estrategia: "ucs" (f = g), "greedy" (f = h) ou "astar" (f = g + h).

    Pesquisa em grafo com poda por dominância: um estado é descartado se já
    existir outro com a mesma chave, distância <= e hora <= (chegar mais cedo
    com menos km nunca é pior, porque o veículo pode esperar).
    Devolve a solução, os km, os nós expandidos/gerados e o tempo de execução.
    """
    h = heuristica if estrategia != "ucs" else h_zero
    inicio_rel = time.perf_counter()
    s0 = estado_inicial if estado_inicial is not None else sub.estado_inicial()
    contador = itertools.count()
    fronteira = []
    rotulos: Dict = {}  # chave -> lista de (g, hora) não dominados

    def dominado(s: State) -> bool:
        g, t = s.distancia_acumulada_km, s.tempo_atual
        for g0, t0 in rotulos.get(_chave(s), []):
            if g0 <= g + 1e-9 and t0 <= t:
                return True
        return False

    def registar(s: State):
        g, t = s.distancia_acumulada_km, s.tempo_atual
        k = _chave(s)
        lst = [(g0, t0) for g0, t0 in rotulos.get(k, []) if not (g <= g0 + 1e-9 and t <= t0)]
        lst.append((g, t))
        rotulos[k] = lst

    def prioridade(s: State):
        g = s.distancia_acumulada_km
        hv = h(s, sub)
        if estrategia == "greedy":
            return (hv, g)
        if estrategia == "astar":
            return (g + hv, hv)
        return (g, 0.0)

    registar(s0)
    heapq.heappush(fronteira, (prioridade(s0), next(contador), No(s0, None, [], "início no armazém")))
    expandidos = gerados = 0
    terminou = True

    while fronteira:
        if expandidos >= max_expansoes or time.perf_counter() - inicio_rel > limite_s:
            terminou = False
            break
        _, _, no = heapq.heappop(fronteira)
        s = no.estado
        # ignora entradas obsoletas (entretanto apareceu um estado melhor com a mesma chave)
        if (s.distancia_acumulada_km, s.tempo_atual) not in rotulos.get(_chave(s), []):
            continue
        if sub.objetivo(s):
            return _resultado(sub, estrategia, no, expandidos, gerados, inicio_rel, True)
        expandidos += 1
        for desc, acoes, novo in sucessores(sub, s):
            gerados += 1
            if dominado(novo):
                continue
            registar(novo)
            heapq.heappush(fronteira, (prioridade(novo), next(contador), No(novo, no, acoes, desc)))

    return _resultado(sub, estrategia, None, expandidos, gerados, inicio_rel, terminou)


def verificar_admissibilidade(sub: Subproblema, heuristicas: Dict[str, Callable],
                              max_estados: int = 150) -> Dict[str, Dict]:
    """
    Teste empírico da admissibilidade: para estados alcançáveis, calcula o custo
    ótimo real que falta, h*(n), com o UCS a partir desse estado, e confirma que
    h(n) <= h*(n) para todas as heurísticas. Devolve, por heurística, o número de
    estados testados, de violações e a razão média h/h* (mais perto de 1 = mais informada).
    """
    # recolhe estados alcançáveis (pesquisa em largura limitada)
    vistos, fila, estados = set(), [sub.estado_inicial()], []
    while fila and len(estados) < max_estados:
        s = fila.pop(0)
        k = (_chave(s), s.tempo_atual)
        if k in vistos:
            continue
        vistos.add(k)
        estados.append(s)
        fila.extend(novo for _, _, novo in sucessores(sub, s))
    stats = {n: {"estados": 0, "violacoes": 0, "soma_razao": 0.0} for n in heuristicas}
    for s in estados:
        res = pesquisar(sub, "ucs", estado_inicial=s, max_expansoes=100_000, limite_s=30)
        if not res["encontrou"]:
            continue  # beco sem saída: h* infinito, qualquer h é admissível
        h_estrela = res["distancia_km"] - s.distancia_acumulada_km
        for n, h in heuristicas.items():
            hv = h(s, sub)
            st = stats[n]
            st["estados"] += 1
            if hv > h_estrela + 1e-6:
                st["violacoes"] += 1
            if h_estrela > 1e-9:
                st["soma_razao"] += hv / h_estrela
    for st in stats.values():
        st["razao_media_h_hestrela"] = round(st.pop("soma_razao") / max(st["estados"], 1), 3)
    return stats


def _resultado(sub, estrategia, no, expandidos, gerados, inicio_rel, terminou) -> Dict:
    passos = []
    while no is not None:
        passos.append(no)
        no = no.pai
    passos.reverse()
    acoes = [a for n in passos for a in n.acoes]
    final = passos[-1].estado if passos else None
    return {
        "estrategia": estrategia,
        "encontrou": bool(passos),
        "terminou": terminou,
        "distancia_km": round(final.distancia_acumulada_km, 2) if final else None,
        "hora_fim": final.tempo_atual if final else None,
        "nos_expandidos": expandidos,
        "nos_gerados": gerados,
        "tempo_s": round(time.perf_counter() - inicio_rel, 4),
        "acoes": acoes,
        "passos": [(n.estado.tempo_atual, n.descricao, n.estado.paragem_atual) for n in passos],
        "estado_final": final,
    }


def validar(sub: Subproblema, res: Dict) -> Dict:
    """Confirma a rota com o verificador do model.py (custos e restrições)."""
    v = sub.problem.verificar_viabilidade(
        vehicle_id=sub.vehicle_id, acoes=res["acoes"], hora_partida=sub.hora_inicio,
        chegada_armazem_previa=sub.chegadas_previas, itens_objetivo=set(sub.entregar),
    )
    ok_km = abs(v["distancia_km"] - res["distancia_km"]) < 0.05
    return {"viavel": v["viavel"], "erros": v["erros"], "km_confere": ok_km,
            "distancia_verificador": v["distancia_km"]}


# =====================================================================
# 4. PLANO COMPLETO: atribuição das encomendas e encadeamento dos dias
# =====================================================================

def dias_do_problema(pb: Problem) -> List[date]:
    dias = set()
    for r in pb.pedidos.values():
        dias.add(r.dia_recolha)
        dias.add(r.dia_entrega)
    return sorted(dias)


def _normalizar(atribuicao: Dict[int, object]) -> Dict[int, Tuple[int, int]]:
    """Aceita {encomenda: veículo} ou {encomenda: (veículo_recolha, veículo_entrega)}."""
    return {o: (v if isinstance(v, tuple) else (v, v)) for o, v in atribuicao.items()}


def planear(pb: Problem, atribuicao: Dict[int, object], estrategia: str, heuristica: Callable = h_zero,
            max_expansoes: int = 300_000, limite_s: float = 120.0, validar_rotas: bool = True) -> Dict:
    """
    Plano completo, dia a dia e veículo a veículo.

    O armazém é partilhado: os itens que lá ficam ao fim de um dia (com a hora de
    chegada) podem ser carregados no dia seguinte por qualquer veículo. Dentro do
    mesmo dia, cada encomenda é recolhida e entregue pelo mesmo veículo, por isso
    os veículos de um dia são independentes entre si.
    """
    atr = _normalizar(atribuicao)
    chegadas_globais: Dict[int, datetime] = {}
    resultados = []
    falhou = False
    for d in dias_do_problema(pb):
        for v in sorted(pb.veiculos):
            recolher = frozenset(i for i, r in pb.pedidos.items()
                                 if r.order_id in atr and atr[r.order_id][0] == v and r.dia_recolha == d)
            entregar = frozenset(i for i, r in pb.pedidos.items()
                                 if r.order_id in atr and atr[r.order_id][1] == v and r.dia_entrega == d)
            if not recolher and not entregar:
                continue
            previas = {i: chegadas_globais[i] for i in entregar if i in chegadas_globais}
            sub = Subproblema(pb, v, d, recolher, entregar, previas)
            res = pesquisar(sub, estrategia, heuristica, max_expansoes, limite_s)
            res["vehicle_id"], res["dia"], res["subproblema"] = v, d, sub
            resultados.append(res)
            if not res["encontrou"]:
                falhou = True
                break
            if validar_rotas:
                res["validacao"] = validar(sub, res)
            chegadas_globais.update(dict(res["estado_final"].chegadas_armazem))
        if falhou:
            break
    viavel = not falhou
    if validar_rotas and viavel:
        viavel = all(r["validacao"]["viavel"] and r["validacao"]["km_confere"] for r in resultados)
    return {
        "estrategia": estrategia,
        "viavel": viavel,
        "terminou": all(r["terminou"] for r in resultados),
        "distancia_km": round(sum(r["distancia_km"] for r in resultados), 2) if viavel else None,
        "nos_expandidos": sum(r["nos_expandidos"] for r in resultados),
        "nos_gerados": sum(r["nos_gerados"] for r in resultados),
        "tempo_s": round(sum(r["tempo_s"] for r in resultados), 3),
        "rotas": resultados,
    }


def _opcoes(pb: Problem, oid: int) -> List[Tuple[int, int]]:
    """Encomendas do próprio dia: um só veículo. Encomendas que passam a noite no armazém: recolha e entrega podem ser de veículos diferentes."""
    r = next(r for r in pb.pedidos.values() if r.order_id == oid)
    V = sorted(pb.veiculos)
    if r.dia_recolha == r.dia_entrega:
        return [(v, v) for v in V]
    return [(a, b) for a in V for b in V]


def atribuir_por_insercao(pb: Problem, heuristica: Callable, max_expansoes: int = 20_000,
                          ordem: Optional[List[int]] = None) -> Tuple[Optional[Dict[int, Tuple[int, int]]], List[int]]:
    """
    Atribuição construtiva (inserção mais barata): as encomendas entram uma a uma,
    pela ordem dada, e cada uma fica com a opção de veículos que mantém o plano
    viável com o menor aumento de distância (avaliado com o Greedy, que é rápido).
    Devolve a atribuição (só com as encomendas que couberam) e as que ficaram de fora.
    """
    encomendas = ordem or sorted({r.order_id for r in pb.pedidos.values()},
                                 key=lambda o: min(r.availability_end for r in pb.pedidos.values() if r.order_id == o))
    atr: Dict[int, Tuple[int, int]] = {}
    custo_atual = 0.0
    falhadas = []
    for oid in encomendas:
        melhor = None
        for opc in _opcoes(pb, oid):
            tent = dict(atr)
            tent[oid] = opc
            plano = planear(pb, tent, "greedy", heuristica, max_expansoes, 10, validar_rotas=False)
            if plano["viavel"] and (melhor is None or plano["distancia_km"] < melhor[0]):
                melhor = (plano["distancia_km"], opc)
        if melhor is None:
            falhadas.append(oid)
            continue
        custo_atual, atr[oid] = melhor
    return atr, falhadas


def ordens_de_insercao(pb: Problem, n_aleatorias: int = 4, semente: int = 1) -> Dict[str, List[int]]:
    """Várias ordens de inserção: critérios de urgência e algumas ordens aleatórias (semente fixa, reprodutível)."""
    import random
    enc = sorted({r.order_id for r in pb.pedidos.values()})
    itens = {o: [r for r in pb.pedidos.values() if r.order_id == o] for o in enc}
    ordens = {
        "fim da janela de recolha": sorted(enc, key=lambda o: min(r.availability_end for r in itens[o])),
        "fim da janela de entrega": sorted(enc, key=lambda o: min(r.delivery_end for r in itens[o])),
        "mais produtores primeiro": sorted(enc, key=lambda o: -len({r.pickup_loc for r in itens[o]})),
        "mais pesada primeiro": sorted(enc, key=lambda o: -sum(r.weight_kg for r in itens[o])),
    }
    rnd = random.Random(semente)
    for k in range(n_aleatorias):
        o = enc[:]
        rnd.shuffle(o)
        ordens[f"aleatória {k + 1}"] = o
    return ordens


def melhor_atribuicao(pb: Problem, heuristica: Callable, n_aleatorias: int = 4,
                      max_expansoes: int = 20_000) -> Tuple[Dict[int, Tuple[int, int]], List[int], List[Tuple]]:
    """
    Corre a inserção com cada ordem e fica com a melhor atribuição: primeiro a que
    deixa menos encomendas de fora, depois a de menor distância (Greedy).
    Devolve (atribuição, encomendas de fora, tabela com o resultado de cada ordem).
    """
    tabela, melhor = [], None
    for nome, ordem in ordens_de_insercao(pb, n_aleatorias).items():
        t0 = time.perf_counter()
        atr, falhadas = atribuir_por_insercao(pb, heuristica, max_expansoes, ordem)
        km = planear(pb, atr, "greedy", heuristica, max_expansoes, 10, validar_rotas=False)["distancia_km"]
        criterio = (len(falhadas), km)
        if melhor is None or criterio < melhor[0]:
            melhor = (criterio, atr, falhadas)
        tabela.append((nome, len(falhadas), falhadas, km, round(time.perf_counter() - t0, 1)))
    return melhor[1], melhor[2], tabela
