from __future__ import annotations

import numpy as np
import pandas as pd

from gex.domain.gex import metrics


def test_absolute_gamma_profile_preserves_gross_exposure_when_sides_offset(monkeypatch):
    monkeypatch.setattr(metrics.rates, "current_rate", lambda: 0.04)
    chain = pd.DataFrame({
        "type": ["C", "P"],
        "strike": [100.0, 100.0],
        "iv": [0.2, 0.2],
        "t_years": [0.1, 0.1],
        "open_interest": [100.0, 100.0],
    })

    _, net = metrics.gamma_profile(chain, 100.0, range_pct=0.01, steps=5)
    _, absolute = metrics.gamma_profile(chain, 100.0, range_pct=0.01, steps=5, absolute=True)

    assert np.allclose(net, 0.0)
    assert np.all(absolute > 0.0)
