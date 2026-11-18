from langchain_core.tools import tool
from dotenv import load_dotenv
from ingesta import build_vectorstore
import retriver

load_dotenv()

# Inicializamos el retriever híbrido
print("Cargando retriever de Rapanui para el especialista de investigación...")
_, chunks = build_vectorstore()
_hybrid_retriever = retriver.get_hybrid_retriever(chunks, k=3)


@tool
def buscar_datos_rapanui(consulta: str) -> str:
    """Busca políticas, beneficios, requisitos y normas de calidad de Rapanui en la base vectorial."""
    docs = _hybrid_retriever.invoke(consulta)
    if not docs:
        return "No se encontró información relevante en los documentos."
    return "\n\n".join([f"Fuente [{d.metadata.get('source', 'doc')}]: {d.page_content}" for d in docs])


@tool
def calcular_costos_beneficios(
    cantidad_empleados: int,
    costo_gimnasio_base: float = 40000.0,
    costo_obra_social_base: float = 65000.0,
    porcentaje_descuento_gym: float = 0.50
) -> str:
    """
    Calcula el costo total y el ahorro corporativo mensual de los beneficios laborales de Rapanui.
    Aplica el 50% de descuento corporativo en Sport Club y suma la cobertura de obra social.
    """
    gasto_gym_por_empleado = costo_gimnasio_base * porcentaje_descuento_gym
    ahorro_gym_por_empleado = costo_gimnasio_base * (1 - porcentaje_descuento_gym)

    costo_total_empleado = gasto_gym_por_empleado + costo_obra_social_base
    costo_total_empresa = costo_total_empleado * cantidad_empleados
    ahorro_total_empleados = ahorro_gym_por_empleado * cantidad_empleados

    return (
        f"--- Análisis Financiero de Beneficios ({cantidad_empleados} empleados) ---\n"
        f"• Aporte Gym por empleado (con 50% bonificado): ${gasto_gym_por_empleado:,.2f}\n"
        f"• Obra social corporativa por empleado: ${costo_obra_social_base:,.2f}\n"
        f"• Costo unitario total por empleado: ${costo_total_empleado:,.2f}/mes\n"
        f"• Inversión total mensual de Rapanui: ${costo_total_empresa:,.2f}/mes\n"
        f"• Ahorro total acumulado por empleados: ${ahorro_total_empleados:,.2f}/mes"
    )
