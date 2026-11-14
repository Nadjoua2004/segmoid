"""
Time Series Vital Forecasting Service for Spaceflight Clinical Decision Support.
Supports Multi-Scale Horizons:
1. DAILY (24-Hour Intra-Sol Horizon): Hourly modeling with circadian diurnal cycle harmonics.
2. WEEKLY (7-Day Tactical Horizon): Multi-day trend velocity with damped Holt-Winters smoothing.
3. MONTHLY (30-Day Strategic Transit Horizon): Long-duration adaptation with asymptotic biological plateau damping.
"""
import math
from typing import List, Dict, Any, Optional, Tuple, Union
import numpy as np
from scipy.optimize import minimize

class TimeSeriesForecaster:
    """
    Physiological Time-Series Engine supporting Daily (24h), Weekly (7d), and Monthly (30d) horizons.
    """

    def fit_and_forecast(
        self,
        series: Union[List[float], np.ndarray],
        horizon: int = 7,
        min_bound: Optional[float] = None,
        max_bound: Optional[float] = None,
        default_baseline: float = 72.0,
        time_scale: str = "WEEKLY"
    ) -> Dict[str, Any]:
        """
        Fit time series and project trajectory across the specified operational time scale.
        """
        time_scale = time_scale.upper()
        if time_scale == "DAILY" and horizon == 7:
            horizon = 24
        elif time_scale == "MONTHLY" and horizon == 7:
            horizon = 30

        y = np.array(series, dtype=float)
        y = y[~np.isnan(y)]
        n = len(y)

        if n == 0:
            forecasts = np.array([default_baseline] * horizon)
            return {
                "forecast": forecasts,
                "lower_bound": forecasts * 0.95,
                "upper_bound": forecasts * 1.05,
                "r2_fit": 0.0,
                "trend_velocity": 0.0,
                "time_scale": time_scale,
                "model": "Fallback Baseline"
            }
        if n == 1:
            forecasts = np.array([y[0]] * horizon)
            return {
                "forecast": forecasts,
                "lower_bound": forecasts * 0.95,
                "upper_bound": forecasts * 1.05,
                "r2_fit": 1.0,
                "trend_velocity": 0.0,
                "time_scale": time_scale,
                "model": "Single-Point Persistence"
            }

        # -------------------------------------------------------------
        # 1. Parameter Bounds Tuning per Time Scale
        # -------------------------------------------------------------
        # In Monthly forecasts, damping phi is tightened (0.78 - 0.88) to enforce biological plateau.
        # In Weekly forecasts, damping is moderate (0.85 - 0.96).
        # In Daily forecasts, alpha recency is higher for rapid hourly response.
        if time_scale == "MONTHLY":
            initial_params = [0.4, 0.1, 0.84]
            bounds = [(0.05, 0.85), (0.01, 0.40), (0.75, 0.88)]
        elif time_scale == "DAILY":
            initial_params = [0.7, 0.25, 0.92]
            bounds = [(0.20, 0.98), (0.05, 0.60), (0.80, 0.98)]
        else:  # WEEKLY
            initial_params = [0.5, 0.2, 0.92]
            bounds = [(0.05, 0.95), (0.01, 0.70), (0.75, 0.98)]

        def loss_func(params):
            alpha, beta, phi = params
            l = np.zeros(n)
            b = np.zeros(n)
            l[0] = y[0]
            b[0] = (y[1] - y[0]) if n > 1 else 0.0
            sse = 0.0

            for t in range(1, n):
                one_step_pred = l[t - 1] + phi * b[t - 1]
                sse += (y[t] - one_step_pred) ** 2
                l[t] = alpha * y[t] + (1.0 - alpha) * (l[t - 1] + phi * b[t - 1])
                b[t] = beta * (l[t] - l[t - 1]) + (1.0 - beta) * phi * b[t - 1]

            return sse / max(1, n - 1)

        try:
            opt = minimize(loss_func, initial_params, bounds=bounds, method="L-BFGS-B")
            alpha, beta, phi = opt.x if opt.success else initial_params
        except Exception:
            alpha, beta, phi = initial_params

        # -------------------------------------------------------------
        # 2. In-Sample Execution & Residual Estimation
        # -------------------------------------------------------------
        l = np.zeros(n)
        b = np.zeros(n)
        in_sample_preds = np.zeros(n)
        l[0] = y[0]
        b[0] = y[1] - y[0]
        in_sample_preds[0] = y[0]

        for t in range(1, n):
            in_sample_preds[t] = l[t - 1] + phi * b[t - 1]
            l[t] = alpha * y[t] + (1.0 - alpha) * (l[t - 1] + phi * b[t - 1])
            b[t] = beta * (l[t] - l[t - 1]) + (1.0 - beta) * phi * b[t - 1]

        residuals = y[1:] - in_sample_preds[1:]
        residual_std = float(np.std(residuals)) if len(residuals) > 1 else 1.0

        ss_res = np.sum((y - in_sample_preds) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r2 = max(0.0, float(1.0 - (ss_res / ss_tot))) if ss_tot > 1e-6 else 0.0

        # -------------------------------------------------------------
        # 3. Horizon Multi-Step Forecasting
        # -------------------------------------------------------------
        forecasts = []
        lower_bounds = []
        upper_bounds = []
        last_level = l[-1]
        last_trend = b[-1]

        for h in range(1, horizon + 1):
            damped_trend_multiplier = sum(phi ** i for i in range(1, h + 1))
            fh = last_level + damped_trend_multiplier * last_trend

            # Circadian Harmonic Wave Adjustment for DAILY scale
            # Human circadian body clock: Peak in late afternoon (~16:00), Nadir during REM sleep (~04:00)
            if time_scale == "DAILY":
                hour_mod = h % 24
                # Diurnal harmonic modulation amplitude: ~3.5 BPM / ~0.3 C
                circadian_amplitude = 3.5 if default_baseline > 50.0 else 0.25
                circadian_wave = circadian_amplitude * math.cos(2.0 * math.pi * (hour_mod - 16.0) / 24.0)
                fh += circadian_wave

            # Expanding uncertainty interval over forecast horizon
            # Square root growth in variance reflects forecast diffusion
            horizon_uncertainty = 1.96 * residual_std * math.sqrt(h)
            if time_scale == "MONTHLY":
                # For 30-day window, uncertainty saturates at biological limits
                horizon_uncertainty = min(horizon_uncertainty, 3.5 * residual_std)

            lower_b = fh - horizon_uncertainty
            upper_b = fh + horizon_uncertainty

            if min_bound is not None:
                fh = max(min_bound, fh)
                lower_b = max(min_bound, lower_b)
            if max_bound is not None:
                fh = min(max_bound, fh)
                upper_b = min(max_bound, upper_b)

            forecasts.append(round(float(fh), 2))
            lower_bounds.append(round(float(lower_b), 2))
            upper_bounds.append(round(float(upper_b), 2))

        return {
            "forecast": np.array(forecasts),
            "lower_bound": np.array(lower_bounds),
            "upper_bound": np.array(upper_bounds),
            "r2_fit": round(r2, 3),
            "trend_velocity": round(float(last_trend), 3),
            "alpha": round(float(alpha), 3),
            "beta": round(float(beta), 3),
            "phi": round(float(phi), 3),
            "time_scale": time_scale,
            "horizon_steps": horizon,
            "model": f"Holt-Winters Damped Time-Series [{time_scale}]"
        }

time_series_forecaster = TimeSeriesForecaster()
