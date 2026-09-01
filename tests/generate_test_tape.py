"""Script para generar datos de prueba de tape (order flow firmado)."""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from gex import store
from gex.config import SETTINGS

ET = ZoneInfo("America/New_York")

def generate_test_tape(symbol: str = "SPX", day: str = None):
    """Genera datos de prueba de tape (order flow firmado)."""
    day = day or datetime.now(ET).strftime("%Y-%m-%d")
    
    # Generar datos simulados para un día de trading
    base_time = datetime.strptime(day, "%Y-%m-%d").replace(hour=9, minute=30)
    
    tape_bars = []
    for i in range(78):  # ~6.5 horas de trading en minutos
        ts = base_time + timedelta(minutes=i)
        
        # Simular order flow firmado
        net_contracts = np.random.normal(0, 50)  # +/- 50 contratos netos por minuto
        net_calls = max(0, net_contracts * 0.6) if net_contracts > 0 else min(0, net_contracts * 0.4)
        net_puts = net_contracts - net_calls
        
        # Delta flow (en millones de dólares)
        net_delta = net_contracts * 100 * 5000  # Asumiendo contrato $100 y spot ~$5000
        
        # Gamma flow
        net_gamma = np.random.normal(0, 0.1)  # Gamma en escala apropiada
        net_gamma_calls = max(0, net_gamma * 0.7) if net_gamma > 0 else min(0, net_gamma * 0.3)
        net_gamma_puts = net_gamma - net_gamma_calls
        
        bar = {
            "timestamp": ts.replace(tzinfo=None),  # Timestamp naive como espera el sistema
            "symbol": symbol,
            "net_contracts": net_contracts,
            "net_premium": net_contracts * 100 * 5000 * 0.1,  # Premium estimado
            "net_calls": net_calls,
            "net_puts": net_puts,
            "net_delta": net_delta,
            "delta_prints": np.random.randint(10, 100),
            "no_delta_prints": np.random.randint(0, 10),
            "net_gamma": net_gamma,
            "net_gamma_calls": net_gamma_calls,
            "net_gamma_puts": net_gamma_puts,
            "buy_contracts": abs(net_contracts) if net_contracts > 0 else 0,
            "sell_contracts": abs(net_contracts) if net_contracts < 0 else 0,
            "prints": np.random.randint(50, 200),
            "spread_contracts": np.random.randint(0, 10),
            "spread_prints": np.random.randint(0, 5),
            "undefined_prints": np.random.randint(0, 3),
        }
        tape_bars.append(bar)
    
    df = pd.DataFrame(tape_bars)
    
    # Guardar usando el store
    for _, row in df.iterrows():
        store.append_tape(symbol, [row.to_dict()], row["timestamp"])
    
    print(f"Generados {len(tape_bars)} registros de tape para {symbol} el {day}")
    return df

if __name__ == "__main__":
    # Generar datos para múltiples símbolos
    symbols = ["SPX", "NDX", "SPY", "QQQ"]
    
    for symbol in symbols:
        generate_test_tape(symbol)
    
    # Verificar que se guardaron correctamente
    today = datetime.now(ET).strftime("%Y-%m-%d")
    for symbol in symbols:
        loaded = store.load_tape(symbol, today)
        print(f"{symbol}: {len(loaded)} registros de tape cargados")
        if not loaded.empty:
            print(f"  Columnas: {list(loaded.columns)}")
        else:
            print(f"  No se encontraron datos de tape")