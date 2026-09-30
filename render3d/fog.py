# -*- coding: utf-8 -*-
"""Fog (atmospheric extinction) -- the SAR pipeline and three.js must use the same equation.

    SAR (sar/camera.py:94,143)   T = exp(-beta * r)                 r = ray range (radial)
    three.js FogExp2 (r170)      T = exp(-(rho * d)^2)              d = view depth (-mvPosition.z)
    Koschmieder (sar/sensors.py) V = 3.912 / beta                   (visibility at 2% contrast)

Using three.js as-is gives two differences: (1) the exponent is squared, (2) the distance is depth, not range
(the edges of a wide FOV get less fog). The GLSL below overrides both to Beer-Lambert + radial distance.
Apply it before any material is compiled (html.py does this).
"""
from __future__ import annotations

import math

KOSCHMIEDER = 3.912          # -ln(0.02). Same constant as sar/sensors.py C_MIN=0.02

# three.js r170 ShaderChunk override. vFogDepth becomes the radial distance and the factor becomes Beer-Lambert.
GLSL_FOG_VERTEX = "#ifdef USE_FOG\n\tvFogDepth = length( mvPosition.xyz );\n#endif\n"
GLSL_FOG_FRAGMENT = ("#ifdef USE_FOG\n\tfloat fogFactor = 1.0 - exp( - fogDensity * vFogDepth );\n"
                     "\tgl_FragColor.rgb = mix( gl_FragColor.rgb, fogColor, fogFactor );\n#endif\n")


def beta_from_visibility(V_m: float) -> float:
    return KOSCHMIEDER / max(1.0, V_m)


def T_beer_lambert(beta: float, r: float) -> float:
    return math.exp(-beta * r)


def T_three_default(rho: float, d: float) -> float:
    return math.exp(-(rho * d) ** 2)


def rho_matching_visibility(V_m: float) -> float:
    """three.js default FogExp2 density that gives 2% contrast at the same V: (rho V)^2 = 3.912."""
    return math.sqrt(KOSCHMIEDER) / max(1.0, V_m)


def compare_models(V_m: float, half_fov_deg: float, n: int = 400) -> dict:
    """At the same visibility V, the difference between the two models (0..2V). No browser needed; this is the analytic difference."""
    beta = beta_from_visibility(V_m); rho = rho_matching_visibility(V_m)
    worst, at = 0.0, 0.0
    for k in range(1, n + 1):
        r = 2 * V_m * k / n
        d = abs(T_beer_lambert(beta, r) - T_three_default(rho, r))
        if d > worst:
            worst, at = d, r
    # Radial vs depth: at the FOV edge d = r cos(theta), so FogExp2 is lighter there.
    th = math.radians(half_fov_deg)
    r = V_m / 2
    edge = T_three_default(rho, r * math.cos(th)) - T_three_default(rho, r)
    return {"beta": beta, "rho": rho, "max_abs_dT": worst, "at_r": at, "edge_depth_bias_dT": edge}
