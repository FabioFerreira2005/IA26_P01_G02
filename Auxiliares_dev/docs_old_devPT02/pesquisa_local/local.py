"""
local.py — Pesquisa local (Hill-Climbing) sobre as rotas do Greedy.

IA 2026/27 · TP1 · Grupo 02 (IA26_P01_G02) · Parte: Alexandre Silva

Ideia geral
-----------
1. Uma solução é, para cada (veículo, dia), uma SEQUÊNCIA DE VISITAS:
     - recolha  num produtor (com os itens recolhidos lá),
     - armazém  (descarrega o que vem a bordo e carrega os itens indicados),
     - entrega  num cliente (com os itens entregues lá).
   A última visita é o regresso ao armazém e fica sempre no fim.
2. Vizinhos de uma solução (3 movimentos):
     - trocar(i, j):   troca a visita i com a visita j;
     - mover(i, j):    tira a visita i e põe-na na posição j;
     - inverter(i, j): inverte a ordem das visitas entre i e j (2-opt).
   Extra opcional: mover_bloco (or-opt) — mover 2 ou 3 visitas seguidas de uma vez.
3. Um vizinho só é aceite se o verificador do model.py (verificar_viabilidade)
   o aprovar: janelas, capacidade, fluxo produtor -> armazém -> cliente, 24 h no
   armazém, e a rota tem de ficar completa.
4. Hill-Climbing: parte da solução do Greedy e passa sempre para um vizinho
   viável MELHOR (menos km). Para quando nenhum vizinho melhora (ótimo local).

O módulo não depende de nenhum algoritmo de pesquisa em particular: recebe as
rotas no formato de ações do verificar_viabilidade (pickup / warehouse / load /
delivery), por isso serve para a solução do Greedy de qualquer pesquisa.py.
"""

import math
import os
import random
import sys
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Callable, Dict, Iterator, List, Optional, Set, Tuple

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from model import Problem  # noqa: E402


# =====================================================================
# 1. REPRESENTAÇÃO: sequência de visitas
# =====================================================================

@dataclass(frozen=True)
class Visita:
    tipo: str                       # "recolha", "armazem" ou "entrega"
    local: int                      # location_id
    itens: Tuple[int, ...] = ()     # recolha/entrega: itens servidos; armazém: itens carregados

    def __str__(self):
        if self.tipo == "armazem":
            return f"A({len(self.itens)})" if self.itens else "A"
        letra = "R" if self.tipo == "recolha" else "E"
        return f"{letra}{self.local}"


def acoes_para_visitas(pb: Problem, acoes: List[Tuple[str, int]]) -> List[Visita]:
    """
    Converte uma lista de ações do verificar_viabilidade numa sequência de visitas.
    Recolhas (ou entregas) seguidas no mesmo sítio formam uma visita; um
    ("warehouse", A) e os ("load", i) que se lhe seguem formam uma visita ao armazém.
    """
    visitas: List[Visita] = []
    i = 0
    while i < len(acoes):
        acao, alvo = acoes[i]
        if acao in ("pickup", "delivery"):
            tipo = "recolha" if acao == "pickup" else "entrega"
            loc_de = (lambda it: pb.pedidos[it].pickup_loc) if acao == "pickup" else (lambda it: pb.pedidos[it].delivery_loc)
            loc = loc_de(alvo)
            itens = []
            while i < len(acoes) and acoes[i][0] == acao and loc_de(acoes[i][1]) == loc:
                itens.append(acoes[i][1])
                i += 1
            visitas.append(Visita(tipo, loc, tuple(itens)))
        elif acao == "warehouse":
            i += 1
            carregar = []
            while i < len(acoes) and acoes[i][0] == "load":
                carregar.append(acoes[i][1])
                i += 1
            visitas.append(Visita("armazem", pb.armazem, tuple(carregar)))
        else:
            raise ValueError(f"Ação inesperada fora de uma visita ao armazém: {acoes[i]}")
    return visitas


def visitas_para_acoes(pb: Problem, visitas: List[Visita]) -> List[Tuple[str, int]]:
    """Operação inversa: a sequência de visitas volta ao formato do verificador."""
    acoes: List[Tuple[str, int]] = []
    for v in visitas:
        if v.tipo == "recolha":
            acoes += [("pickup", i) for i in v.itens]
        elif v.tipo == "entrega":
            acoes += [("delivery", i) for i in v.itens]
        else:
            acoes.append(("warehouse", pb.armazem))
            acoes += [("load", i) for i in v.itens]
    return acoes


def texto_rota(visitas: List[Visita]) -> str:
    """Representação curta, por exemplo: A(5) R3 R2 R1 E9 A(12) E7 E5 A"""
    return " ".join(str(v) for v in visitas)


# =====================================================================
# 2. AVALIAÇÃO com o verificador do model.py
# =====================================================================

@dataclass
class Contexto:
    """O que é preciso para avaliar uma rota de um veículo num dia."""
    problem: Problem
    vehicle_id: int
    dia: date
    hora_partida: datetime
    recolher: Set[int]                         # itens que têm de ser recolhidos hoje
    entregar: Set[int]                         # itens que têm de ser entregues hoje
    chegadas_previas: Dict[int, datetime] = field(default_factory=dict)  # itens já no armazém
    avaliacoes: int = 0                        # contador de chamadas ao verificador


def avaliar(ctx: Contexto, visitas: List[Visita]) -> Tuple[bool, float, Dict]:
    """
    Corre o verificar_viabilidade e devolve (aceitável, km, resultado).
    Aceitável = sem erros E rota completa: tudo o que é de hoje entregue, tudo o
    que foi recolhido descarregado no armazém e o veículo vazio no armazém.
    """
    pb = ctx.problem
    ctx.avaliacoes += 1
    res = pb.verificar_viabilidade(
        vehicle_id=ctx.vehicle_id, acoes=visitas_para_acoes(pb, visitas),
        hora_partida=ctx.hora_partida, chegada_armazem_previa=ctx.chegadas_previas,
        itens_objetivo=set(ctx.entregar),
    )
    completa = (
        bool(visitas) and visitas[-1].tipo == "armazem"
        and set(ctx.entregar) <= res["entregues"]
        and set(ctx.recolher) <= (res["entregues"] | set(res["no_armazem"]))
        and abs(res["carga_final_kg"]) < 1e-6
    )
    return (res["viavel"] and completa), res["distancia_km"], res


# =====================================================================
# 3. VIZINHANÇA: trocar, mover, inverter
# =====================================================================

MOVIMENTOS = ("trocar", "mover", "inverter")
# Extra (opcional): mover um BLOCO de 2 ou 3 visitas seguidas para outra posição,
# na mesma ordem ou invertido (or-opt). Não faz parte do plano base.
MOVIMENTOS_COM_BLOCO = MOVIMENTOS + ("mover_bloco",)


def _n_moveis(visitas: List[Visita]) -> int:
    """O regresso final ao armazém (última visita, sem carregamentos) fica fixo."""
    if visitas and visitas[-1].tipo == "armazem" and not visitas[-1].itens:
        return len(visitas) - 1
    return len(visitas)


def aplicar(visitas: List[Visita], movimento: str, i: int, j: int) -> List[Visita]:
    """Aplica um movimento e devolve uma nova lista (a original não é alterada)."""
    nova = list(visitas)
    if movimento.startswith("mover_bloco"):
        # formato: "mover_bloco<L>" ou "mover_bloco<L>_inv"; i = início do bloco, j = nova posição
        L = int(movimento[len("mover_bloco")])
        bloco = nova[i:i + L]
        if movimento.endswith("_inv"):
            bloco = bloco[::-1]
        del nova[i:i + L]
        nova[j:j] = bloco
        return nova
    if movimento == "trocar":
        nova[i], nova[j] = nova[j], nova[i]
    elif movimento == "mover":
        v = nova.pop(i)
        nova.insert(j, v)
    elif movimento == "inverter":
        nova[i:j + 1] = reversed(nova[i:j + 1])
    else:
        raise ValueError(movimento)
    return nova


def vizinhos(visitas: List[Visita], movimentos=MOVIMENTOS) -> Iterator[Tuple[str, int, int, List[Visita]]]:
    """
    Gera todos os vizinhos (movimento, i, j, nova_rota), sem repetidos óbvios:
      - trocar(i, j) com i < j;
      - mover(i, j) com j != i e j != i + 1 (mover para a posição seguinte = trocar vizinhos);
      - inverter(i, j) com j >= i + 2 (inverter 2 visitas = trocar vizinhos).
    """
    n = _n_moveis(visitas)
    if "trocar" in movimentos:
        for i in range(n):
            for j in range(i + 1, n):
                yield "trocar", i, j, aplicar(visitas, "trocar", i, j)
    if "mover" in movimentos:
        for i in range(n):
            for j in range(n):
                if j != i and j != i + 1:
                    yield "mover", i, j, aplicar(visitas, "mover", i, j)
    if "inverter" in movimentos:
        for i in range(n):
            for j in range(i + 2, n):
                yield "inverter", i, j, aplicar(visitas, "inverter", i, j)
    if "mover_bloco" in movimentos:
        for L in (2, 3):
            for i in range(n - L + 1):
                for j in range(n - L + 1):      # posição na lista já sem o bloco
                    if j == i:
                        continue
                    for nome in (f"mover_bloco{L}", f"mover_bloco{L}_inv"):
                        yield nome, i, j, aplicar(visitas, nome, i, j)


def vizinho_aleatorio(visitas: List[Visita], rnd: random.Random, movimentos=MOVIMENTOS):
    """Um vizinho ao acaso (usado no Simulated Annealing)."""
    n = _n_moveis(visitas)
    if n < 2:
        return None
    m = rnd.choice(movimentos)
    if m == "mover_bloco":
        L = rnd.choice((2, 3)) if n >= 4 else 2
        if n < L + 1:
            return None
        i = rnd.randrange(n - L + 1)
        j = rnd.choice([k for k in range(n - L + 1) if k != i])
        nome = f"mover_bloco{L}" + ("_inv" if rnd.random() < 0.5 else "")
        return nome, i, j, aplicar(visitas, nome, i, j)
    if m == "inverter" and n < 3:
        m = "trocar"
    if m == "trocar":
        i, j = sorted(rnd.sample(range(n), 2))
    elif m == "mover":
        i = rnd.randrange(n)
        j = rnd.choice([k for k in range(n) if k != i and k != i + 1] or [i])
    else:
        i = rnd.randrange(n - 2)
        j = rnd.randrange(i + 2, n)
    return m, i, j, aplicar(visitas, m, i, j)


# =====================================================================
# 4. HILL-CLIMBING (e Simulated Annealing como extra)
# =====================================================================

def hill_climbing(ctx: Contexto, inicial: List[Visita], estrategia: str = "melhor",
                  movimentos=MOVIMENTOS, max_iter: int = 1000, semente: int = 0,
                  restricao_extra: Optional[Callable[[List[Visita]], bool]] = None) -> Dict:
    """
    Hill-Climbing sobre a sequência de visitas.

    estrategia="melhor"   (steepest ascent): avalia TODOS os vizinhos e passa para o melhor.
    estrategia="primeiro" (first improvement): percorre os vizinhos por ordem aleatória
                           (semente fixa) e passa para o primeiro que melhora.

    Só são aceites vizinhos aprovados pelo verificador (e pela restricao_extra, que o
    plano usa para garantir que o dia seguinte continua viável). Para quando nenhum
    vizinho melhora: ótimo local.

    Devolve a rota final e o histórico (custo por iteração) para os gráficos.
    """
    ok, custo, _ = avaliar(ctx, inicial)
    if not ok:
        raise ValueError("A solução inicial não é viável segundo o verificador.")
    rnd = random.Random(semente)
    atual = list(inicial)
    t0 = time.perf_counter()
    historico = [{"iteracao": 0, "custo_km": custo, "movimento": "inicial", "vizinhos_avaliados": 0,
                  "vizinhos_viaveis": 0, "tempo_s": 0.0, "rota": texto_rota(atual)}]

    for it in range(1, max_iter + 1):
        cand = list(vizinhos(atual, movimentos))
        if estrategia == "primeiro":
            rnd.shuffle(cand)
        melhor = None
        avaliados = viaveis = 0
        for m, i, j, nova in cand:
            avaliados += 1
            ok, c, _ = avaliar(ctx, nova)
            if not ok:
                continue
            viaveis += 1
            if c < (melhor[0] if melhor else custo) - 1e-9:
                if restricao_extra is not None and not restricao_extra(nova):
                    continue
                melhor = (c, m, i, j, nova)
                if estrategia == "primeiro":
                    break
        if melhor is None:
            historico[-1]["parou"] = "ótimo local"
            break
        custo, m, i, j, atual = melhor
        historico.append({"iteracao": it, "custo_km": round(custo, 2), "movimento": f"{m}({i}, {j})",
                          "vizinhos_avaliados": avaliados, "vizinhos_viaveis": viaveis,
                          "tempo_s": round(time.perf_counter() - t0, 3), "rota": texto_rota(atual)})
    return {"rota": atual, "custo_km": round(custo, 2), "historico": historico,
            "iteracoes": len(historico) - 1, "tempo_s": round(time.perf_counter() - t0, 3)}


def simulated_annealing(ctx: Contexto, inicial: List[Visita], temperatura_inicial: float = 20.0,
                        arrefecimento: float = 0.995, max_iter: int = 3000, semente: int = 0,
                        movimentos=MOVIMENTOS,
                        restricao_extra: Optional[Callable[[List[Visita]], bool]] = None) -> Dict:
    """
    Extra: Simulated Annealing. Escolhe um vizinho ao acaso; se for viável, aceita-o
    sempre que melhora e, às vezes, quando piora (probabilidade exp(-Δ/T)). A
    temperatura T desce em cada iteração. Permite sair de ótimos locais do Hill-Climbing.
    """
    ok, custo, _ = avaliar(ctx, inicial)
    if not ok:
        raise ValueError("A solução inicial não é viável segundo o verificador.")
    rnd = random.Random(semente)
    atual, melhor_rota, melhor_custo = list(inicial), list(inicial), custo
    T = temperatura_inicial
    t0 = time.perf_counter()
    historico = [{"iteracao": 0, "custo_km": custo, "melhor_km": custo, "temperatura": T}]
    for it in range(1, max_iter + 1):
        viz = vizinho_aleatorio(atual, rnd, movimentos)
        if viz is not None:
            _, _, _, nova = viz
            ok, c, _ = avaliar(ctx, nova)
            if ok and (restricao_extra is None or restricao_extra(nova)):
                delta = c - custo
                if delta < 0 or rnd.random() < math.exp(-delta / max(T, 1e-9)):
                    atual, custo = nova, c
                    if c < melhor_custo - 1e-9:
                        melhor_rota, melhor_custo = list(nova), c
        T *= arrefecimento
        historico.append({"iteracao": it, "custo_km": round(custo, 2),
                          "melhor_km": round(melhor_custo, 2), "temperatura": round(T, 4)})
    return {"rota": melhor_rota, "custo_km": round(melhor_custo, 2), "historico": historico,
            "iteracoes": max_iter, "tempo_s": round(time.perf_counter() - t0, 3)}


# =====================================================================
# 5. PLANO COMPLETO: vários veículos e dias encadeados
# =====================================================================

@dataclass
class RotaPlano:
    vehicle_id: int
    dia: date
    hora_partida: datetime
    recolher: Set[int]
    entregar: Set[int]
    visitas: List[Visita]


class PlanoLocal:
    """
    Guarda as rotas de todos os (veículo, dia) e otimiza-as uma a uma por ordem
    cronológica. Uma rota do dia d muda as horas de chegada ao armazém dos itens
    que passam a noite lá; por isso, ao otimizar o dia d, só se aceitam mudanças
    que mantêm viáveis as rotas do dia d+1 (limite de 24 h).
    """

    def __init__(self, pb: Problem, rotas: List[RotaPlano]):
        self.pb = pb
        self.rotas = {(r.vehicle_id, r.dia): r for r in rotas}
        self.dias = sorted({r.dia for r in rotas})

    @classmethod
    def de_acoes(cls, pb: Problem, entradas: List[Dict]) -> "PlanoLocal":
        """
        entradas: lista de dicionários com vehicle_id, dia, hora_partida, recolher,
        entregar e acoes (formato do verificar_viabilidade). É o que o Greedy produz.
        """
        rotas = [RotaPlano(e["vehicle_id"], e["dia"], e["hora_partida"], set(e["recolher"]),
                           set(e["entregar"]), acoes_para_visitas(pb, e["acoes"])) for e in entradas]
        return cls(pb, rotas)

    # --- chegadas ao armazém que passam de um dia para o seguinte ---
    def _contexto(self, r: RotaPlano, chegadas: Dict[int, datetime]) -> Contexto:
        previas = {i: h for i, h in chegadas.items() if i in r.entregar}
        return Contexto(self.pb, r.vehicle_id, r.dia, r.hora_partida, r.recolher, r.entregar, previas)

    def _chegadas_ate(self, dia: date, substituir: Optional[Tuple[Tuple[int, date], List[Visita]]] = None) -> Dict[int, datetime]:
        """Horas de chegada ao armazém dos itens descarregados nos dias ANTERIORES a `dia`."""
        chegadas: Dict[int, datetime] = {}
        for d in self.dias:
            if d >= dia:
                break
            anteriores = dict(chegadas)
            for (v, dd), r in sorted(self.rotas.items()):
                if dd != d:
                    continue
                visitas = substituir[1] if substituir and substituir[0] == (v, dd) else r.visitas
                _, _, res = avaliar(self._contexto(r, anteriores), visitas)
                chegadas.update(res["no_armazem"])
        return chegadas

    def custo_total(self) -> float:
        return round(sum(self.avaliar_rota(k)[1] for k in self.rotas), 2)

    def avaliar_rota(self, chave, visitas=None):
        r = self.rotas[chave]
        ctx = self._contexto(r, self._chegadas_ate(r.dia))
        return avaliar(ctx, visitas if visitas is not None else r.visitas)

    def valido(self) -> bool:
        """Todas as rotas aceites pelo verificador, com as chegadas encadeadas entre dias."""
        return all(self.avaliar_rota(k)[0] for k in self.rotas)

    def _dia_seguinte_ok(self, chave, visitas: List[Visita]) -> bool:
        _, dia = chave
        seguintes = [d for d in self.dias if d > dia]
        if not seguintes:
            return True
        prox = seguintes[0]
        chegadas = self._chegadas_ate(prox, substituir=(chave, visitas))
        for (v, d), r in self.rotas.items():
            if d == prox and not avaliar(self._contexto(r, chegadas), r.visitas)[0]:
                return False
        return True

    def perturbar(self, passos: int = 30, semente: int = 0) -> None:
        """Baralha todas as rotas com movimentos aleatórios viáveis (ver perturbar())."""
        for d in self.dias:
            for (v, dd), r in sorted(self.rotas.items()):
                if dd != d:
                    continue
                chave = (v, dd)
                ctx = self._contexto(r, self._chegadas_ate(d))
                extra = lambda vis, chave=chave: self._dia_seguinte_ok(chave, vis)
                r.visitas = perturbar(ctx, r.visitas, passos, semente + 1000 * v + d.day, restricao_extra=extra)

    def copia(self) -> "PlanoLocal":
        return PlanoLocal(self.pb, [RotaPlano(r.vehicle_id, r.dia, r.hora_partida, set(r.recolher),
                                              set(r.entregar), list(r.visitas)) for r in self.rotas.values()])

    def otimizar(self, metodo: str = "hc", **parametros) -> Dict:
        """
        metodo="hc" (Hill-Climbing; parâmetros: estrategia, movimentos, max_iter, semente)
        metodo="sa" (Simulated Annealing; parâmetros: temperatura_inicial, arrefecimento, max_iter, semente)
        Altera as rotas no próprio plano e devolve o histórico de cada rota.
        """
        resultados = {}
        t0 = time.perf_counter()
        for d in self.dias:
            for (v, dd), r in sorted(self.rotas.items()):
                if dd != d:
                    continue
                chave = (v, dd)
                ctx = self._contexto(r, self._chegadas_ate(d))
                extra = lambda vis, chave=chave: self._dia_seguinte_ok(chave, vis)
                if metodo == "hc":
                    res = hill_climbing(ctx, r.visitas, restricao_extra=extra, **parametros)
                elif metodo == "sa":
                    res = simulated_annealing(ctx, r.visitas, restricao_extra=extra, **parametros)
                else:
                    raise ValueError(metodo)
                res["avaliacoes_verificador"] = ctx.avaliacoes
                res["custo_inicial_km"] = res["historico"][0]["custo_km"]
                r.visitas = res["rota"]
                resultados[chave] = res
        return {"rotas": resultados, "custo_total_km": self.custo_total(),
                "tempo_s": round(time.perf_counter() - t0, 3), "valido": self.valido()}


def perturbar(ctx: Contexto, inicial: List[Visita], passos: int = 30, semente: int = 0,
              movimentos=MOVIMENTOS,
              restricao_extra: Optional[Callable[[List[Visita]], bool]] = None) -> List[Visita]:
    """
    Passeio aleatório: aplica `passos` movimentos ao acaso, aceitando qualquer
    vizinho VIÁVEL (pior ou melhor). Serve para criar soluções iniciais diferentes
    (e piores) a partir da do Greedy, para testar o Hill-Climbing com várias sementes.
    """
    rnd = random.Random(semente)
    atual = list(inicial)
    aceites = tentativas = 0
    while aceites < passos and tentativas < passos * 50:
        tentativas += 1
        viz = vizinho_aleatorio(atual, rnd, movimentos)
        if viz is None:
            break
        nova = viz[3]
        if avaliar(ctx, nova)[0] and (restricao_extra is None or restricao_extra(nova)):
            atual = nova
            aceites += 1
    return atual


def curva_total(resultado_otimizar: Dict, custo_inicial_total: float) -> List[float]:
    """
    Junta as curvas das várias rotas numa curva do custo TOTAL do plano: as rotas
    são otimizadas uma a seguir à outra, e cada melhoria de uma rota baixa o total.
    """
    curva = [custo_inicial_total]
    total = custo_inicial_total
    for _, res in sorted(resultado_otimizar["rotas"].items()):
        hist = res["historico"]
        chave = "melhor_km" if "melhor_km" in hist[0] else "custo_km"
        for a, b in zip(hist[:-1], hist[1:]):
            total += b[chave] - a[chave]
            curva.append(round(total, 2))
    return curva
