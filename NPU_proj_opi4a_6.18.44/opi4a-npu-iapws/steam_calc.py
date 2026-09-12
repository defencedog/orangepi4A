#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""steam_calc.py — Interactive / CLI Steam Property Calculator.

Uses the quantized neural surrogate model to evaluate steam properties
instantly with physical unit formatting and validation against exact IAPWS-97.

Usage:
  python3 steam_calc.py --pressure 1.0 --temperature 573.15
  python3 steam_calc.py -P 3.5 -T 623.15
  python3 steam_calc.py --interactive
"""

import os
import sys
import json
import argparse
import numpy as np

try:
    from iapws import IAPWS97
    HAS_IAPWS = True
except ImportError:
    HAS_IAPWS = False

try:
    from ai_edge_litert.interpreter import Interpreter
except ImportError:
    try:
        from tflite_runtime.interpreter import Interpreter
    except ImportError:
        print("[!] Error: 'ai_edge_litert' or 'tflite_runtime' required.")
        sys.exit(1)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(SCRIPT_DIR, "models")
MODEL_PATH = os.path.join(MODELS_DIR, "iapws_aligned16_int8.tflite")
NORM_PATH = os.path.join(MODELS_DIR, "norm_params.json")


class SteamCalculator:
    def __init__(self, model_path=MODEL_PATH, norm_path=NORM_PATH):
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Surrogate model not found at {model_path}")
        if not os.path.exists(norm_path):
            raise FileNotFoundError(f"Normalization metadata not found at {norm_path}")

        with open(norm_path, "r") as f:
            self.norm = json.load(f)

        self.in_min = np.array(self.norm["in_min"], dtype=np.float32)
        self.in_max = np.array(self.norm["in_max"], dtype=np.float32)
        self.tgt_min = np.array(self.norm["tgt_min"], dtype=np.float32)
        self.tgt_max = np.array(self.norm["tgt_max"], dtype=np.float32)

        self.interpreter = Interpreter(model_path=model_path)
        self.interpreter.allocate_tensors()
        self.in_det = self.interpreter.get_input_details()[0]
        self.out_det = self.interpreter.get_output_details()[0]

        self.in_scale, self.in_zp = self.in_det["quantization"]
        self.out_scale, self.out_zp = self.out_det["quantization"]

    def calculate(self, pressure_mpa, temperature_k):
        """Calculate thermodynamic properties given P (MPa) and T (K)."""
        # Range validation
        if not (self.in_min[0] <= pressure_mpa <= self.in_max[0]):
            print(f"[!] Warning: Pressure {pressure_mpa:.2f} MPa outside trained range [{self.in_min[0]}, {self.in_max[0]}].")
        if not (self.in_min[1] <= temperature_k <= self.in_max[1]):
            print(f"[!] Warning: Temperature {temperature_k:.2f} K outside trained range [{self.in_min[1]}, {self.in_max[1]}].")

        # Input normalization and 16-channel padding
        norm_p = (pressure_mpa - self.in_min[0]) / (self.in_max[0] - self.in_min[0])
        norm_t = (temperature_k - self.in_min[1]) / (self.in_max[1] - self.in_min[1])

        in_buf = np.zeros((1, 1, 1, 16), dtype=np.float32)
        in_buf[0, 0, 0, 0] = norm_p
        in_buf[0, 0, 0, 1] = norm_t

        quant_in = np.clip(np.round(in_buf / self.in_scale) + self.in_zp, -128, 127).astype(np.int8)
        self.interpreter.set_tensor(self.in_det["index"], quant_in)
        self.interpreter.invoke()

        raw_out = self.interpreter.get_tensor(self.out_det["index"])
        out_norm = (raw_out.astype(np.float32) - self.out_zp) * self.out_scale
        pred_phys = out_norm[0, 0, 0, :4] * (self.tgt_max - self.tgt_min) + self.tgt_min

        results = {
            "pressure_mpa": pressure_mpa,
            "pressure_bar": pressure_mpa * 10.0,
            "temperature_k": temperature_k,
            "temperature_c": temperature_k - 273.15,
            "density": float(pred_phys[0]),
            "enthalpy": float(pred_phys[1]),
            "entropy": float(pred_phys[2]),
            "cp": float(pred_phys[3]),
        }

        if HAS_IAPWS:
            try:
                st = IAPWS97(P=pressure_mpa, T=temperature_k)
                results["iapws_density"] = float(st.rho)
                results["iapws_enthalpy"] = float(st.h)
                results["iapws_entropy"] = float(st.s)
                results["iapws_cp"] = float(st.cp)
                results["iapws_phase"] = st.phase
            except Exception:
                pass

        return results

    def print_report(self, res):
        print("\n" + "=" * 68)
        print("          NPU STEAM TABLES — THERMODYNAMIC PROPERTY REPORT")
        print("=" * 68)
        print(f"State Point : P = {res['pressure_mpa']:.4f} MPa ({res['pressure_bar']:.2f} bar) | T = {res['temperature_k']:.2f} K ({res['temperature_c']:.2f} °C)")
        print("-" * 68)
        print(f"{'Property':<28} {'Surrogate':<14} {'IAPWS-97':<14} {'Unit':<10}")
        print("-" * 68)

        has_exact = "iapws_density" in res
        props = [
            ("Density (rho)", res["density"], res.get("iapws_density"), "kg/m³"),
            ("Specific Enthalpy (h)", res["enthalpy"], res.get("iapws_enthalpy"), "kJ/kg"),
            ("Specific Entropy (s)", res["entropy"], res.get("iapws_entropy"), "kJ/(kg·K)"),
            ("Isobaric Heat Cap (cp)", res["cp"], res.get("iapws_cp"), "kJ/(kg·K)"),
        ]

        for name, val, exact_val, unit in props:
            exact_str = f"{exact_val:.4f}" if exact_val is not None else "N/A"
            if exact_val is not None:
                err_pct = abs(val - exact_val) / max(abs(exact_val), 1e-6) * 100.0
                print(f"{name:<28} {val:<14.4f} {exact_str:<14} {unit:<10} (Err: {err_pct:.2f}%)")
            else:
                print(f"{name:<28} {val:<14.4f} {exact_str:<14} {unit:<10}")

        print("=" * 68 + "\n")


def interactive_mode(calc):
    print("\n=== NPU Steam Tables Interactive Calculator ===")
    print("Type 'q' or 'exit' to quit.\n")
    while True:
        try:
            p_str = input("Enter Pressure (MPa) [e.g. 1.0]: ").strip()
            if p_str.lower() in ['q', 'exit']:
                break
            t_str = input("Enter Temperature (K) [e.g. 573.15]: ").strip()
            if t_str.lower() in ['q', 'exit']:
                break

            p = float(p_str)
            t = float(t_str)
            res = calc.calculate(p, t)
            calc.print_report(res)
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"[!] Invalid input: {e}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NPU Steam Tables Property Evaluator")
    parser.add_argument("-P", "--pressure", type=float, default=None, help="Pressure in MPa (e.g. 1.0 for 10 bar)")
    parser.add_argument("-T", "--temperature", type=float, default=None, help="Temperature in Kelvin (e.g. 573.15 for 300 C)")
    parser.add_argument("-i", "--interactive", action="store_true", help="Launch interactive CLI prompt")
    args = parser.parse_args()

    calc = SteamCalculator()

    if args.interactive or (args.pressure is None and args.temperature is None):
        interactive_mode(calc)
    else:
        if args.pressure is None or args.temperature is None:
            print("[!] Please specify both --pressure and --temperature.")
            sys.exit(1)
        res = calc.calculate(args.pressure, args.temperature)
        calc.print_report(res)
