#!/usr/bin/env python3
"""
Benchmark MobileNet V1 Classification & SSD Object Detection on Orange Pi 4A.
Measures latency and throughput across single and multi-threaded CPU XNNPACK.
"""

import os
import sys
import time
import numpy as np
from PIL import Image
import ai_edge_litert.interpreter as tflite

def benchmark_classification(image_path, model_path, threads=4, runs=20):
    interpreter = tflite.Interpreter(model_path=model_path, num_threads=threads)
    interpreter.allocate_tensors()
    input_details = interpreter.get_input_details()
    h, w = input_details[0]['shape'][1:3]
    img = Image.open(image_path).convert('RGB').resize((w, h))
    data = np.expand_dims(np.array(img, dtype=np.uint8), axis=0)
    interpreter.set_tensor(input_details[0]['index'], data)

    # Warmup
    for _ in range(3):
        interpreter.invoke()

    t0 = time.perf_counter()
    for _ in range(runs):
        interpreter.invoke()
    total_time = time.perf_counter() - t0
    avg_ms = (total_time / runs) * 1000
    fps = runs / total_time
    return avg_ms, fps

def benchmark_detection(image_path, model_path, threads=4, runs=20):
    interpreter = tflite.Interpreter(model_path=model_path, num_threads=threads)
    interpreter.allocate_tensors()
    input_details = interpreter.get_input_details()
    h, w = input_details[0]['shape'][1:3]
    img = Image.open(image_path).convert('RGB').resize((w, h))
    data = np.expand_dims(np.array(img, dtype=np.uint8), axis=0)
    interpreter.set_tensor(input_details[0]['index'], data)

    # Warmup
    for _ in range(3):
        interpreter.invoke()

    t0 = time.perf_counter()
    for _ in range(runs):
        interpreter.invoke()
    total_time = time.perf_counter() - t0
    avg_ms = (total_time / runs) * 1000
    fps = runs / total_time
    return avg_ms, fps

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    img_path = os.path.join(script_dir, 'grace_hopper.jpg')

    cls_model = os.path.join(script_dir, 'mobilenet_v1_1.0_224_quant.tflite')
    if not os.path.exists(cls_model):
        cls_model = os.path.join(script_dir, 'models', 'mobilenet_v1_1.0_224_quant.tflite')

    det_model = os.path.join(script_dir, 'detect.tflite')
    if not os.path.exists(det_model):
        det_model = os.path.join(script_dir, 'models', 'detect.tflite')

    print("======================================================================")
    print(" Orange Pi 4A (Allwinner T527 Octa-Core A55) Vision Benchmark")
    print("======================================================================")
    print(f"Test Image : {img_path}")
    print(f"Backend    : Google LiteRT / XNNPACK Delegate (ARM NEON FP16/INT8)")
    print("----------------------------------------------------------------------")
    print(f"{'Task':<22} | {'Threads':<8} | {'Avg Latency':<14} | {'Throughput':<12}")
    print("----------------------------------------------------------------------")

    for threads in [1, 2, 4, 8]:
        lat, fps = benchmark_classification(img_path, cls_model, threads=threads)
        print(f"{'Classification (224)':<22} | {threads:<8} | {lat:7.2f} ms     | {fps:5.1f} FPS")

    print("----------------------------------------------------------------------")
    for threads in [1, 2, 4, 8]:
        lat, fps = benchmark_detection(img_path, det_model, threads=threads)
        print(f"{'SSD Detection (300)':<22} | {threads:<8} | {lat:7.2f} ms     | {fps:5.1f} FPS")

    print("======================================================================")

if __name__ == '__main__':
    main()
