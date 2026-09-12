#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""train_surrogate.py — Train neural surrogate & export quantized INT8/UINT8 TFLite model.

Architecture:
  - Input:  [P_norm, T_norm] (shape: 1x2)
  - Hidden: Dense(64, relu) -> Dense(64, relu) -> Dense(32, relu)
  - Output: [rho_norm, h_norm, s_norm, cp_norm] (shape: 1x4)

Quantization:
  - Full Integer Quantization with representative dataset calibration.
  - Generates both UINT8 and INT8 variants for VeriSilicon VIP9000 NPU execution.
"""

import os
import json
import numpy as np
import tensorflow as tf

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(SCRIPT_DIR, "..", "data", "steam_dataset.npz")
if not os.path.exists(DATA_FILE):
    DATA_FILE = "steam_dataset.npz"

MODEL_DIR = SCRIPT_DIR
UINT8_MODEL_PATH = os.path.join(MODEL_DIR, "iapws_surrogate_uint8.tflite")
INT8_MODEL_PATH = os.path.join(MODEL_DIR, "iapws_surrogate_int8.tflite")
NORM_PARAMS_PATH = os.path.join(MODEL_DIR, "norm_params.json")

def train_and_export():
    print("=" * 65)
    print("Training IAPWS-IF97 Neural Surrogate Model")
    print("=" * 65)

    if not os.path.exists(DATA_FILE):
        raise FileNotFoundError(f"Dataset not found at {DATA_FILE}")

    # 1. Load dataset
    data = np.load(DATA_FILE)
    inputs = data['inputs']      # shape: (N, 2) -> [P, T]
    targets = data['targets']    # shape: (N, 4) -> [rho, h, s, cp]
    in_min = data['in_min']
    in_max = data['in_max']
    tgt_min = data['tgt_min']
    tgt_max = data['tgt_max']

    print(f"[OK] Loaded {len(inputs)} state points from {DATA_FILE}")

    # 2. Normalize to [0, 1]
    X = (inputs - in_min) / (in_max - in_min)
    y = (targets - tgt_min) / (tgt_max - tgt_min)

    # 3. Train/test split (85% train, 15% test)
    indices = np.random.RandomState(42).permutation(len(X))
    split = int(0.85 * len(X))
    train_idx, test_idx = indices[:split], indices[split:]

    X_train, y_train = X[train_idx], y[train_idx]
    X_test, y_test = X[test_idx], y[test_idx]
    print(f"[OK] Dataset split: {len(X_train)} train, {len(X_test)} test")

    # 4. Build Model
    model = tf.keras.Sequential([
        tf.keras.layers.Input(shape=(2,), batch_size=1, name="steam_input"),
        tf.keras.layers.Dense(64, activation='relu', name="dense_1"),
        tf.keras.layers.Dense(64, activation='relu', name="dense_2"),
        tf.keras.layers.Dense(32, activation='relu', name="dense_3"),
        tf.keras.layers.Dense(4, activation='linear', name="steam_output")
    ])
    model.summary()

    # 5. Compile and train
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=0.003),
        loss='mse',
        metrics=['mae']
    )

    print("\nTraining MLP surrogate...")
    history = model.fit(
        X_train, y_train,
        epochs=220,
        batch_size=32,
        validation_data=(X_test, y_test),
        verbose=0
    )

    val_loss = history.history['val_loss'][-1]
    print(f"[OK] Training complete. Final validation loss (MSE): {val_loss:.6f}")

    # 6. Evaluate accuracy in physical units
    y_pred_norm = model.predict(X_test, batch_size=1)
    y_pred = y_pred_norm * (tgt_max - tgt_min) + tgt_min
    y_true = targets[test_idx]

    prop_names = ["Density (rho)", "Enthalpy (h)", "Entropy (s)", "Heat Capacity (cp)"]
    units = ["kg/m3", "kJ/kg", "kJ/(kg*K)", "kJ/(kg*K)"]

    print("\nSurrogate Model Accuracy on Unseen Test Points:")
    print("-" * 65)
    for i in range(4):
        mape = np.mean(np.abs((y_true[:, i] - y_pred[:, i]) / y_true[:, i])) * 100.0
        max_err = np.max(np.abs((y_true[:, i] - y_pred[:, i]) / y_true[:, i])) * 100.0
        print(f"  {prop_names[i]:<22} MAPE: {mape:6.3f}%  |  Max Error: {max_err:6.3f}%")
    print("-" * 65)

    # 7. Save normalization metadata
    norm_meta = {
        "in_min": in_min.tolist(),
        "in_max": in_max.tolist(),
        "tgt_min": tgt_min.tolist(),
        "tgt_max": tgt_max.tolist(),
        "input_features": ["Pressure_MPa", "Temperature_K"],
        "target_properties": [
            {"name": "density", "unit": "kg/m3"},
            {"name": "enthalpy", "unit": "kJ/kg"},
            {"name": "entropy", "unit": "kJ/kg-K"},
            {"name": "cp", "unit": "kJ/kg-K"}
        ]
    }
    with open(NORM_PARAMS_PATH, "w") as f:
        json.dump(norm_meta, f, indent=2)
    print(f"[OK] Normalization metadata saved to: {NORM_PARAMS_PATH}")

    # 8. Representative dataset generator for post-training quantization
    def representative_dataset_gen():
        for i in range(min(500, len(X_train))):
            sample = np.expand_dims(X_train[i], axis=0).astype(np.float32)
            yield [sample]

    # 9. Quantize to UINT8 TFLite model
    print("\nQuantizing model to UINT8 per-tensor for VeriSilicon VIP9000 NPU...")
    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    converter.optimizations = [tf.lite.Optimize.DEFAULT]
    converter.representative_dataset = representative_dataset_gen
    converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    converter.inference_input_type = tf.uint8
    converter.inference_output_type = tf.uint8

    uint8_tflite_model = converter.convert()
    with open(UINT8_MODEL_PATH, "wb") as f:
        f.write(uint8_tflite_model)
    print(f"[OK] Saved UINT8 model to: {UINT8_MODEL_PATH} ({len(uint8_tflite_model)} bytes)")

    # 10. Quantize to INT8 (signed) TFLite model
    print("Quantizing model to INT8 (signed) per-tensor...")
    converter_int8 = tf.lite.TFLiteConverter.from_keras_model(model)
    converter_int8.optimizations = [tf.lite.Optimize.DEFAULT]
    converter_int8.representative_dataset = representative_dataset_gen
    converter_int8.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    converter_int8.inference_input_type = tf.int8
    converter_int8.inference_output_type = tf.int8

    int8_tflite_model = converter_int8.convert()
    with open(INT8_MODEL_PATH, "wb") as f:
        f.write(int8_tflite_model)
    print(f"[OK] Saved INT8 model to: {INT8_MODEL_PATH} ({len(int8_tflite_model)} bytes)")
    print("=" * 65)

if __name__ == "__main__":
    train_and_export()
