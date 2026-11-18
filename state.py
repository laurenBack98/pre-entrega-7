from typing import Literal, Optional
from langgraph.graph import MessagesState


class MultiAgentState(MessagesState):
    """Estado compartido del sistema multi-agente con soporte HITL."""
    next: Literal["investigador", "analista", "human_approval", "FINISH"]
    datos_investigacion: Optional[str] = None
    datos_analisis: Optional[str] = None
    step_count: int = 0
    # Campos para Human-in-the-Loop
    requiere_aprobacion: bool = False
    aprobado_por_humano: Optional[bool] = None
    comentario_humano: Optional[str] = None

