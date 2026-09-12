#!/usr/bin/env python3
"""
MobileNet V1 Quantized Image Classification on Orange Pi 4A / Linux ARM64.
Based on zero2pro_NPU_example and Google LiteRT / TensorFlow Lite.
"""

import argparse
import os
import sys
import time
import numpy as np
from PIL import Image
import ai_edge_litert.interpreter as tflite


def load_labels(filename):
    with open(filename, 'r') as f:
        return [line.strip() for line in f.readlines()]


if __name__ == '__main__':
    script_dir = os.path.dirname(os.path.abspath(__file__))

    default_image = os.path.join(script_dir, 'grace_hopper.jpg')

    default_model = os.path.join(script_dir, 'mobilenet_v1_1.0_224_quant.tflite')
    if not os.path.exists(default_model):
        default_model = os.path.join(script_dir, 'models', 'mobilenet_v1_1.0_224_quant.tflite')

    default_labels = os.path.join(script_dir, 'labels_mobilenet_quant_v1_224.txt')
    if not os.path.exists(default_labels):
        default_labels = os.path.join(script_dir, 'models', 'labels_mobilenet_quant_v1_224.txt')

    system_delegates = ['/usr/local/lib/libteflon.so', '/usr/lib/teflon/libteflon.so']
    default_delegate = next((p for p in system_delegates if os.path.exists(p)), None)

    parser = argparse.ArgumentParser(description="MobileNet V1 Image Classification")
    parser.add_argument(
        '-i', '--image',
        default=default_image,
        help='Path to image to be classified (default: grace_hopper.bmp)')
    parser.add_argument(
        '-m', '--model_file',
        default=default_model,
        help='Path to .tflite model (default: mobilenet_v1_1.0_224_quant.tflite)')
    parser.add_argument(
        '-l', '--label_file',
        default=default_labels,
        help='Path to labels file (default: labels_mobilenet_quant_v1_224.txt)')
    parser.add_argument(
        '--input_mean',
        default=127.5, type=float,
        help='Input normalization mean')
    parser.add_argument(
        '--input_std',
        default=127.5, type=float,
        help='Input normalization std')
    parser.add_argument(
        '--num_threads', default=4, type=int, help='Number of CPU threads')
    parser.add_argument(
        '--npu', action='store_true',
        help='Run inference on VIP9000 NPU using system Mesa Teflon delegate (/usr/local/lib/libteflon.so)')
    parser.add_argument(
        '-e', '--ext_delegate', default=None,
        help='Path to external delegate library (e.g., /usr/local/lib/libteflon.so for NPU)')
    parser.add_argument(
        '-o', '--ext_delegate_options', default=None,
        help='External delegate options, format: "option1: value1; option2: value2"')

    args = parser.parse_args()

    if args.npu and args.ext_delegate is None:
        if default_delegate and os.path.exists(default_delegate):
            args.ext_delegate = default_delegate
        else:
            print("[!] Error: --npu requested but system Mesa Teflon delegate was not found.")
            print("[!] Expected /usr/local/lib/libteflon.so (install via ~/NPU_modules_opi4a_6.18.44/install.sh).")
            sys.exit(1)

    if not os.path.exists(args.image):
        print(f"Error: Image '{args.image}' not found.")
        sys.exit(1)
    if not os.path.exists(args.model_file):
        print(f"Error: Model file '{args.model_file}' not found.")
        sys.exit(1)
    if not os.path.exists(args.label_file):
        print(f"Error: Label file '{args.label_file}' not found.")
        sys.exit(1)

    ext_delegate = None
    ext_delegate_options = {}

    if args.ext_delegate_options is not None:
        options = args.ext_delegate_options.split(';')
        for o in options:
            kv = o.split(':')
            if len(kv) == 2:
                ext_delegate_options[kv[0].strip()] = kv[1].strip()
            else:
                raise RuntimeError('Error parsing delegate option: ' + o)

    if args.ext_delegate is not None:
        print(f'Loading external delegate from {args.ext_delegate} with args: {ext_delegate_options}')
        try:
            ext_delegate = [
                tflite.load_delegate(args.ext_delegate, ext_delegate_options)
            ]
            print('Delegate loaded successfully.')
        except Exception as e:
            print(f'Warning: Failed to load external delegate ({e}). Falling back to CPU.')
            ext_delegate = None

    interpreter = tflite.Interpreter(
        model_path=args.model_file,
        experimental_delegates=ext_delegate,
        num_threads=args.num_threads)
    interpreter.allocate_tensors()

    input_details = interpreter.get_input_details()
    output_details = interpreter.get_output_details()

    floating_model = input_details[0]['dtype'] == np.float32

    height = input_details[0]['shape'][1]
    width = input_details[0]['shape'][2]
    img = Image.open(args.image).convert('RGB').resize((width, height))
    img_array = np.array(img).astype(input_details[0]['dtype'])

    input_data = np.expand_dims(img_array, axis=0)

    if floating_model:
        input_data = (np.float32(input_data) - args.input_mean) / args.input_std

    interpreter.set_tensor(input_details[0]['index'], input_data)

    try:
        interpreter.invoke()
    except Exception as e:
        print(f"Invocation error: {e}")
        sys.exit(1)

    num_iterations = 5
    start_time = time.time()
    for _ in range(num_iterations):
        interpreter.invoke()
    latency_ms = (time.time() - start_time) * 1000 / num_iterations

    output_data = interpreter.get_tensor(output_details[0]['index'])
    results = np.squeeze(output_data)

    top_k = results.argsort()[-5:][::-1]
    labels = load_labels(args.label_file)

    print("\n" + "="*50)
    print(f" Inference Latency: {latency_ms:.2f} ms ({num_iterations} runs average)")
    print(" Top-5 Predictions:")
    print("="*50)
    for i in top_k:
        score = float(results[i]) if floating_model else float(results[i] / 255.0)
        label_text = labels[i] if i < len(labels) else f"Class {i}"
        print(f" {score:08.6f}: {label_text}")
    print("="*50)
