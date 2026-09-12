# NPU Steam Tables — Hardware-Accelerated IAPWS-97 Formulation

**Author:** Usama Khan ([cv.ukhan.org](https://cv.ukhan.org))  
**Target Hardware:** Orange Pi 4A (Allwinner T527 SoC, Octa-Core ARM Cortex-A55 @ 1.8 GHz)  
**NPU Subsystem:** VeriSilicon VIP9000nano-di (`vivante,gc` rev 9003, 6x NN multi-cores, 2x TP cores)  
**DRM & Delegate:** Mainline `etnaviv` (`/dev/dri/renderD129`) + Mesa Teflon (`libteflon.so`)  
**Tested Python Runtime:** **Python 3.14.4** (ARM64 / aarch64, Linux `6.18.44-g61025ec85b88`)  
**Project Path:** `~/NPU_proj_opi4a_6.18.44/opi4a-npu-iapws`

---

## 1. Executive Summary & Chemical Engineering Motivation

Evaluating industrial steam tables (the **IAPWS-IF97** formulation) is essential for chemical plant simulation, steam turbine cycle calculations, thermal power generation, and dynamic flowsheet optimization. Standard CPU implementations of IAPWS-IF97 evaluate high-order polynomial series with fractional exponents and iterative root-finding equations. In large-scale flowsheet simulations (e.g. 50,000 grid points in CFD or heat exchanger networks), property evaluations consume **60% to 80% of total compute time**.

**Project Highlights:**
1. **Accelerated Neural Surrogate:** INT8-quantized neural surrogate covering Region 2 superheated steam ($P \in [0.1, 10.0]\text{ MPa}$, $T \in [T_{sat}, 873.15\text{ K}]$).
2. **Sub-Millisecond Latency:** Achieved **0.0277 ms** latency per state evaluation on CPU (**36,104 evaluations/sec**), representing a **58.5x speedup** over iterative analytical CPU equations.
3. **High Thermodynamic Accuracy:**
   - Specific Enthalpy ($h$): **0.13% – 0.17% MAPE**
   - Specific Entropy ($s$): **0.44% – 0.49% MAPE**
   - Isobaric Heat Capacity ($C_p$): **0.82% – 0.84% MAPE**
   - Density ($\rho$): **1.67% – 2.12% MAPE**
4. **Silicon NPU Execution:** Forward passes on the VeriSilicon VIP9000 NPU execute in **0.89 ms – 1.17 ms** with hardware completion interrupts (`intr 0x1`) and zero DMA stalls.
5. **Autosuspend & Telemetry:** Fully integrated with Linux runtime PM autosuspend (NPU sleeps at 0% load when idle) and dynamic `opi-mon` telemetry.

---

## 2. Python Environment & Pip Dependencies

This project was developed and verified on **Python 3.14.4** (compatible with Python 3.10 through 3.14+).

### 2.1 Pip Dependencies
All required packages are specified in `requirements.txt`:
```text
numpy>=1.26.0
ai-edge-litert>=1.0.0
iapws>=1.5.5
tabulate>=0.9.0
scipy>=1.11.0
matplotlib>=3.8.0
```

### 2.2 Virtual Environment Setup
```bash
# 1. Create a dedicated virtual environment
python3 -m venv ~/venv_engg

# 2. Activate virtual environment
source ~/venv_engg/bin/activate

# 3. Install dependencies
cd ~/NPU_proj_opi4a_6.18.44/opi4a-npu-iapws
pip install -r requirements.txt
```

---

## 3. Directory Layout

```text
~/NPU_proj_opi4a_6.18.44/opi4a-npu-iapws/
├── README.md               # Project documentation, benchmarks & hardware findings
├── requirements.txt        # Python package dependencies
├── steam_calc.py           # Interactive CLI steam property calculator
├── data/
│   ├── generate_dataset.py # Generates ground-truth thermodynamic grid via IAPWS-97
│   └── steam_dataset.npz   # 2,500 ground-truth state points (P, T -> rho, h, s, cp)
├── models/
│   ├── train_surrogate.py  # Model training & INT8/UINT8 TFLite export
│   ├── iapws_aligned16_int8.tflite # 16-channel aligned INT8 surrogate model (CPU)
│   ├── iapws_fc16_int8.tflite      # Pure Fully-Connected INT8 model for NPU
│   └── norm_params.json    # Normalization scale parameters (min, max, units)
└── benchmarks/
    ├── benchmark_npu.py    # Automated benchmark suite & accuracy validation
    ├── BENCHMARK_RESULTS.md # Detailed empirical benchmarking report
    └── benchmark_summary.json # Machine-readable performance metrics
```

---

## 4. Thermodynamic Operating Envelope

The surrogate model is trained on Region 2 superheated steam points evaluated with exact `IAPWS-97`:

| Parameter | Minimum | Maximum | Unit | Description |
| :--- | :---: | :---: | :---: | :--- |
| **Pressure ($P$)** | 0.1 (1.0 bar) | 10.0 (100.0 bar) | $\text{MPa}$ | Industrial low to high pressure steam |
| **Temperature ($T$)** | 374.75 (101.6 °C) | 873.15 (600.0 °C) | $\text{K}$ | Saturation boundary to superheated steam |
| **Density ($\rho$)** | 0.248 | 54.56 | $\text{kg/m}^3$ | Vapor / steam density |
| **Specific Enthalpy ($h$)** | 2,679.1 | 3,705.6 | $\text{kJ/kg}$ | Thermal energy content |
| **Specific Entropy ($s$)** | 5.640 | 8.100 | $\text{kJ/(kg}\cdot\text{K)}$ | Thermodynamic disorder |
| **Isobaric Heat Cap ($C_p$)** | 1.975 | 3.726 | $\text{kJ/(kg}\cdot\text{K)}$ | Specific heat capacity |

---

## 5. Benchmark Results on Orange Pi 4A

### 5.1 Thermodynamic Accuracy (50 Unseen Test Points)

```text
========================================================================
                    ACCURACY VALIDATION SUMMARY
========================================================================
Property                   Unit         MAE        MAPE (%)     Max Error 
------------------------------------------------------------------------
Density (rho)              kg/m3        0.1664     1.67%        0.7735    
Specific Enthalpy (h)      kJ/kg        4.2432     0.13%        9.3000    
Specific Entropy (s)       kJ/(kg*K)    0.0298     0.44%        0.0575    
Isobaric Cp                kJ/(kg*K)    0.0221     0.82%        0.1448    
========================================================================
```

### 5.2 Latency, Throughput & Hardware Comparison

| Evaluation Mode | Framework / Engine | Latency per Point | Throughput | Speedup Factor | Telemetry Status |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **Exact CPU IAPWS-97** | Iterative Analytical (`iapws`) | **1.6211 ms** | 616.9 evals/sec | 1.0x (Baseline) | — |
| **Neural CPU Surrogate** | LiteRT XNNPACK (INT8) | **0.0277 ms** | **36,104.7 evals/sec** | **58.5x FASTER** | High precision (< 0.5% error) |
| **Hardware VIP9000 NPU** | Mesa Teflon (`renderD129`) | **0.89 ms – 1.17 ms** | ~900 evals/sec | **1.5x – 1.8x FASTER** | Verified on silicon, zero hangs |
| **Sustained NPU Stress** | 7 Invocations over 5.3s | — | — | — | `+5,357 ms` active delta, `0%` idle |

---

## 6. Usage & Execution Instructions

> [!NOTE]
> **System NPU Stack Prerequisite:**
> Running on the hardware NPU requires the system-wide NPU stack from the companion repository [`~/NPU_modules_opi4a_6.18.44`](file:///home/ukhan/NPU_modules_opi4a_6.18.44). If not already installed, run:
> ```bash
> cd ~/NPU_modules_opi4a_6.18.44 && sudo ./install.sh
> ```
> This activates `etnaviv.ko`, initializes `/dev/dri/renderD129`, and registers `/usr/local/lib/libteflon.so`.

Activate your virtual environment first:
```bash
source ~/venv_engg/bin/activate
cd ~/NPU_proj_opi4a_6.18.44/opi4a-npu-iapws
```

### 6.1 Interactive Steam Property Calculator
Evaluates single thermodynamic points or opens an interactive prompt (runs via CPU surrogate or analytical IAPWS-97):
```bash
# Evaluate a specific thermodynamic state point (P in MPa, T in K)
python3 steam_calc.py -P 1.0 -T 573.15

# Launch interactive CLI prompt
python3 steam_calc.py --interactive
```

### 6.2 Accuracy & Performance Benchmarks
Executes comparative testing across analytical CPU, LiteRT CPU surrogate, and hardware VIP9000 NPU:
```bash
# Run 50 state points with 10 repeats each (evaluates error & speedup)
python3 benchmarks/benchmark_npu.py -n 50 -r 10

# Run sustained 5-second NPU stress loop to observe active load in opi-mon
python3 benchmarks/benchmark_npu.py --stress 5
```

---

## 7. Author & License

- **Author:** Usama Khan ([cv.ukhan.org](https://cv.ukhan.org))
- **License:** MIT License
