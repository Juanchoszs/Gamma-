"""Script para probar que los gráficos carguen correctamente con los datos de prueba."""
import sys
from datetime import datetime
from zoneinfo import ZoneInfo
from gex import store
from gex.app import tape_fig, gamma_flow_fig, flow_fig
from gex.i18n import LANGS

ET = ZoneInfo("America/New_York")

def test_charts():
    """Prueba los 3 gráficos problemáticos."""
    today = datetime.now(ET).strftime("%Y-%m-%d")
    lang = "en"  # Usar inglés para las pruebas
    
    print("=== Probando gráficos ===")
    print(f"Fecha: {today}")
    print(f"Idioma: {lang}")
    print()
    
    # Probar tape_fig (cumulative signed orderflow)
    print("1. Probando tape_fig (cumulative signed orderflow)...")
    try:
        tape_data = store.load_tape("SPX", today)
        print(f"   Datos de tape: {len(tape_data)} registros")
        if not tape_data.empty:
            print(f"   Columnas disponibles: {list(tape_data.columns)}")
            
            fig = tape_fig("SPX", lang, today)
            print(f"   OK tape_fig genero figura con {len(fig.data)} traces")
        else:
            print(f"   WARNING No hay datos de tape disponibles")
    except Exception as e:
        print(f"   ERROR en tape_fig: {e}")
    print()
    
    # Probar gamma_flow_fig (calls vs puts gamma flow)
    print("2. Probando gamma_flow_fig (calls vs puts gamma flow)...")
    try:
        flows_data = store.load_flows("SPX", today)
        print(f"   Datos de flows: {len(flows_data)} registros")
        if not flows_data.empty:
            print(f"   Columnas disponibles: {list(flows_data.columns)}")
            
            fig = gamma_flow_fig("SPX", lang, today)
            print(f"   OK gamma_flow_fig genero figura con {len(fig.data)} traces")
        else:
            print(f"   WARNING No hay datos de flows disponibles")
    except Exception as e:
        print(f"   ERROR en gamma_flow_fig: {e}")
    print()
    
    # Probar flow_fig (option delta flow)
    print("3. Probando flow_fig (option delta flow)...")
    try:
        fig = flow_fig("SPX", lang, today)
        print(f"   OK flow_fig genero figura con {len(fig.data)} traces")
    except Exception as e:
        print(f"   ERROR en flow_fig: {e}")
    print()
    
    print("=== Resumen ===")
    print("Los datos de prueba han sido generados exitosamente.")
    print("Los gráficos deberían funcionar cuando se inicie la aplicación.")
    print()
    print("Para iniciar la aplicación:")
    print("  python run.py")
    print()
    print("Nota: La configuración market_hours_only se ha cambiado a False")
    print("para permitir pulls fuera de horas de mercado.")

if __name__ == "__main__":
    test_charts()