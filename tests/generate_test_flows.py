"""Script para generar datos de prueba de flows CBOE."""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from gex import store, metrics
from gex.config import SETTINGS

ET = ZoneInfo("America/New_York")

def generate_test_flows(symbol: str = "SPX", day: str = None):
    """Genera datos de prueba de flows CBOE."""
    day = day or datetime.now(ET).strftime("%Y-%m-%d")
    
    # Generar datos simulados para un día de trading
    base_time = datetime.strptime(day, "%Y-%m-%d").replace(hour=9, minute=30)
    
    flows = []
    for i in range(78):  # ~6.5 horas de trading en minutos
        ts = base_time + timedelta(minutes=i)
        
        # Simular variaciones aleatorias realistas
        flow_total = np.random.normal(0, 10)  # +/- $10M por minuto
        flow_calls = max(0, flow_total * 0.6) if flow_total > 0 else min(0, flow_total * 0.4)
        flow_puts = flow_total - flow_calls
        
        # Gamma flows
        gflow_total = np.random.normal(0, 0.5)  # +/- $0.5Bn por minuto
        gflow_calls = max(0, gflow_total * 0.7) if gflow_total > 0 else min(0, gflow_total * 0.3)
        gflow_puts = gflow_total - gflow_calls
        
        flow = {
            "timestamp": ts.replace(tzinfo=None),  # Timestamp naive como espera el sistema
            "flow_total": flow_total * 1e6,  # Convertir a dólares
            "flow_calls": flow_calls * 1e6,
            "flow_puts": flow_puts * 1e6,
            "flow_0dte": flow_total * 0.3 * 1e6,
            "gflow_total": gflow_total * 1e9,  # Convertir a miles de millones
            "gflow_calls": gflow_calls * 1e9,
            "gflow_puts": gflow_puts * 1e9,
            "gflow_0dte": gflow_total * 0.2 * 1e9,
            "contracts_traded": np.random.randint(100, 1000),
            "source": "cboe"
        }
        flows.append(flow)
    
    df = pd.DataFrame(flows)
    
    # Guardar usando el store
    for _, row in df.iterrows():
        store.append_daily("flows", symbol, row.to_dict(), row["timestamp"])
    
    print(f"Generados {len(flows)} registros de flows para {symbol} el {day}")
    return df

if __name__ == "__main__":
    # Generar datos para múltiples símbolos
    symbols = ["SPX", "NDX", "SPY", "QQQ"]
    
    for symbol in symbols:
        generate_test_flows(symbol)
    
    # Verificar que se guardaron correctamente
    today = datetime.now(ET).strftime("%Y-%m-%d")
    for symbol in symbols:
        loaded = store.load_flows(symbol, today)
        print(f"{symbol}: {len(loaded)} registros cargados")
        if not loaded.empty:
            print(f"  Columnas: {list(loaded.columns)}")
        else:
            print(f"  No se encontraron datos")