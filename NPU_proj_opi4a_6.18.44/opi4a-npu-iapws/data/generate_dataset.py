#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""generate_dataset.py — Generate high-precision IAPWS-IF97 steam table dataset.

Generates ground truth thermodynamic properties across the industrial superheated
steam region (Region 2 of IAPWS-IF97):
  - Pressure: 0.1 MPa (1 bar) to 10.0 MPa (100 bar)
  - Temperature: Tsat(P) + 2 K to 873.15 K (600 °C)

Targets:
  1. Density (rho) [kg/m^3]
  2. Specific Enthalpy (h) [kJ/kg]
  3. Specific Entropy (s) [kJ/(kg*K)]
  4. Isobaric Heat Capacity (cp) [kJ/(kg*K)]
"""

import os
import sys
import time
import numpy as np
from iapws import IAPWS97

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_FILE = os.path.join(SCRIPT_DIR, "steam_dataset.npz")

def generate_steam_data(num_p=50, num_t=50):
    print("=" * 65)
    print("Generating IAPWS-IF97 Thermodynamic Training Grid (Region 2)")
    print("=" * 65)
    
    # 50 log-spaced pressures between 0.1 MPa (1 bar) and 10.0 MPa (100 bar)
    pressures = np.geomspace(0.1, 10.0, num=num_p)
    
    inputs_list = []
    targets_list = []
    
    t0 = time.perf_counter()
    count = 0
    
    for P in pressures:
        # Calculate saturation temperature at pressure P
        try:
            sat_state = IAPWS97(P=P, x=1.0)
            t_sat = sat_state.T
        except Exception:
            # Fallback approximation for Tsat if boundary issue
            t_sat = 373.15
        
        # Sample temperatures from Tsat + 2K up to 873.15 K (600 °C)
        t_min = max(t_sat + 2.0, 373.15)
        t_max = 873.15
        if t_min >= t_max:
            continue
        
        temps = np.linspace(t_min, t_max, num=num_t)
        for T in temps:
            try:
                state = IAPWS97(P=P, T=T)
                # Ensure we are in Region 2 (superheated vapor)
                if state.region == 2:
                    inputs_list.append([float(P), float(T)])
                    targets_list.append([
                        float(state.rho),
                        float(state.h),
                        float(state.s),
                        float(state.cp)
                    ])
                    count += 1
            except Exception:
                continue

    elapsed = time.perf_counter() - t0
    inputs = np.array(inputs_list, dtype=np.float32)
    targets = np.array(targets_list, dtype=np.float32)
    
    print(f"[OK] Generated {len(inputs)} thermodynamic state points in {elapsed:.2f} s")
    print(f"     Average CPU computation: {elapsed / len(inputs) * 1000:.2f} ms/point")
    print("-" * 65)
    print(f"Input Ranges:")
    print(f"  P (MPa): min={inputs[:, 0].min():.4f}, max={inputs[:, 0].max():.4f}")
    print(f"  T (K)  : min={inputs[:, 1].min():.2f}, max={inputs[:, 1].max():.2f}")
    print(f"Target Ranges:")
    print(f"  rho (kg/m3) : min={targets[:, 0].min():.4f}, max={targets[:, 0].max():.4f}")
    print(f"  h (kJ/kg)   : min={targets[:, 1].min():.2f}, max={targets[:, 1].max():.2f}")
    print(f"  s (kJ/kg-K) : min={targets[:, 2].min():.4f}, max={targets[:, 2].max():.4f}")
    print(f"  cp (kJ/kg-K): min={targets[:, 3].min():.4f}, max={targets[:, 3].max():.4f}")
    
    # Compute normalization statistics
    in_min = inputs.min(axis=0)
    in_max = inputs.max(axis=0)
    tgt_min = targets.min(axis=0)
    tgt_max = targets.max(axis=0)
    
    np.savez_compressed(
        OUT_FILE,
        inputs=inputs,
        targets=targets,
        in_min=in_min,
        in_max=in_max,
        tgt_min=tgt_min,
        tgt_max=tgt_max
    )
    print(f"[OK] Dataset saved to: {OUT_FILE} ({os.path.getsize(OUT_FILE) / 1024:.1f} KB)")
    print("=" * 65)

if __name__ == "__main__":
    generate_steam_data()
