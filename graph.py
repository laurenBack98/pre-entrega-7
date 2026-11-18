from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt
from state import MultiAgentState
from agents.supervisor import supervisor_node
from agents.research_agent import research_node
from agents.analyst_agent import analyst_node


def human_approval_node(state: MultiAgentState):
    """Nodo que pausa la ejecución esperando confirmación externa (HITL)."""
    # Si ya fue aprobado previamente tras reanudar, no volvemos a pausar
    if state.get("aprobado_por_humano") is not None:
        return {
            "requiere_aprobacion": False,
            "step_count": state.get("step_count", 0) + 1,
        }

    # Interrupción activa: pausa el grafo y expone la solicitud al caller
    decision_humana = interrupt({
        "mensaje": "Se requiere aprobación humana para autorizar el presupuesto calculado.",
        "datos_analisis": state.get("datos_analisis"),
    })

    return {
        "aprobado_por_humano": decision_humana.get("aprobado", False),
        "comentario_humano": decision_humana.get("comentario", ""),
        "requiere_aprobacion": False,
        "step_count": state.get("step_count", 0) + 1,
    }


def router(state: MultiAgentState):
    """Enrutamiento según la decisión del supervisor y estado de aprobación."""
    siguiente = state.get("next")
    
    # Si el analista ya calculó pero requiere aprobación humana antes de cerrar
    if state.get("datos_analisis") and state.get("aprobado_por_humano") is None:
        return "human_approval"
        
    if siguiente == "investigador":
        return "investigador"
    elif siguiente == "analista":
        return "analista"
    elif siguiente == "human_approval":
        return "human_approval"
    else:
        return END


def create_production_graph(checkpointer=None):
    """Compila el grafo multi-agente con soporte de checkpoints y HITL."""
    builder = StateGraph(MultiAgentState)

    builder.add_node("supervisor", supervisor_node)
    builder.add_node("investigador", research_node)
    builder.add_node("analista", analyst_node)
    builder.add_node("human_approval", human_approval_node)

    builder.add_edge(START, "supervisor")

    builder.add_conditional_edges(
        "supervisor",
        router,
        {
            "investigador": "investigador",
            "analista": "analista",
            "human_approval": "human_approval",
            END: END,
        },
    )

    builder.add_edge("investigador", "supervisor")
    builder.add_edge("analista", "supervisor")
    builder.add_edge("human_approval", "supervisor")

    # Usamos MemorySaver por defecto o el checkpointer persistente que inyectemos
    memory = checkpointer or MemorySaver()
    return builder.compile(checkpointer=memory)
