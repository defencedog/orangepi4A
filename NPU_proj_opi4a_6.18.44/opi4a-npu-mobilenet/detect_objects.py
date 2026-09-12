#!/usr/bin/env python3
"""
SSD MobileNet V1 Quantized Object Detection on Orange Pi 4A / Linux ARM64.
Supports LiteRT / TensorFlow Lite with CPU (XNNPACK) and NPU (libteflon.so).
"""

import argparse
import time
import os
import sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import ai_edge_litert.interpreter as tflite

def load_labels(filename):
    with open(filename, 'r') as f:
        return [line.strip() for line in f.readlines()]

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))

    default_image = os.path.join(script_dir, 'grace_hopper.jpg')

    default_model = os.path.join(script_dir, 'detect.tflite')
    if not os.path.exists(default_model):
        default_model = os.path.join(script_dir, 'models', 'detect.tflite')

    default_labels = os.path.join(script_dir, 'labelmap_coco.txt')
    if not os.path.exists(default_labels):
        default_labels = os.path.join(script_dir, 'models', 'labelmap_coco.txt')

    system_delegates = ['/usr/local/lib/libteflon.so', '/usr/lib/teflon/libteflon.so']
    default_delegate = next((p for p in system_delegates if os.path.exists(p)), None)

    parser = argparse.ArgumentParser(description="Object Detection with SSD MobileNet")
    parser.add_argument('-i', '--image', default=default_image, help='Path to input image')
    parser.add_argument('-m', '--model', default=default_model, help='Path to .tflite model')
    parser.add_argument('-l', '--labels', default=default_labels, help='Path to labelmap file')
    parser.add_argument('--npu', action='store_true', help='Run inference on VIP9000 NPU using system Mesa Teflon delegate (/usr/local/lib/libteflon.so)')
    parser.add_argument('-e', '--ext_delegate', default=None, help='Path to libteflon.so external delegate')
    parser.add_argument('-t', '--threshold', default=0.4, type=float, help='Confidence threshold')
    parser.add_argument('-o', '--output', default='detected_output.jpg', help='Output annotated image')
    parser.add_argument('--num_threads', default=4, type=int, help='CPU threads for XNNPACK')
    parser.add_argument('--runs', default=1, type=int, help='Inference iterations (default: 1)')
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
    if not os.path.exists(args.model):
        print(f"Error: Model '{args.model}' not found.")
        sys.exit(1)

    labels = load_labels(args.labels) if os.path.exists(args.labels) else []

    delegates = []
    if args.ext_delegate:
        print(f"Loading external delegate: {args.ext_delegate}")
        try:
            delegates.append(tflite.load_delegate(args.ext_delegate))
            print("External delegate loaded successfully.")
        except Exception as e:
            print(f"Warning: Failed to load external delegate ({e}). Falling back to CPU.")

    interpreter = tflite.Interpreter(
        model_path=args.model,
        experimental_delegates=delegates if delegates else None,
        num_threads=args.num_threads
    )
    interpreter.allocate_tensors()

    input_details = interpreter.get_input_details()
    output_details = interpreter.get_output_details()

    in_h = input_details[0]['shape'][1]
    in_w = input_details[0]['shape'][2]

    orig_img = Image.open(args.image).convert('RGB')
    orig_w, orig_h = orig_img.size

    resized_img = orig_img.resize((in_w, in_h))
    input_data = np.expand_dims(np.array(resized_img, dtype=np.uint8), axis=0)

    interpreter.set_tensor(input_details[0]['index'], input_data)

    # Benchmark runs
    num_runs = max(1, args.runs)
    t0 = time.time()
    for _ in range(num_runs):
        interpreter.invoke()
    latency_ms = (time.time() - t0) * 1000 / num_runs

    boxes = interpreter.get_tensor(output_details[0]['index'])[0]
    classes = interpreter.get_tensor(output_details[1]['index'])[0]
    scores = interpreter.get_tensor(output_details[2]['index'])[0]
    count = int(interpreter.get_tensor(output_details[3]['index'])[0])

    print("\n" + "="*50)
    print(f" Inference Latency: {latency_ms:.2f} ms ({num_runs} runs average)")
    print(f" Total Detections: {count}")
    print("="*50)

    draw = ImageDraw.Draw(orig_img)
    found = 0

    for i in range(count):
        score = scores[i]
        if score < args.threshold:
            continue
        found += 1
        cid = int(classes[i])
        # COCO 90-class label offset
        label_idx = cid + 1
        name = labels[label_idx] if label_idx < len(labels) else f"class_{cid}"

        ymin, xmin, ymax, xmax = boxes[i]
        left = int(xmin * orig_w)
        top = int(ymin * orig_h)
        right = int(xmax * orig_w)
        bottom = int(ymax * orig_h)

        print(f" [{found}] {name:<15} Score: {score:.3f} | Box: [{left}, {top}, {right}, {bottom}]")

        draw.rectangle([left, top, right, bottom], outline="red", width=3)
        draw.text((left + 5, max(0, top - 15)), f"{name} ({score:.2f})", fill="red")

    if found > 0 and args.output:
        orig_img.save(args.output)
        print(f"\nAnnotated image saved to: {args.output}")

if __name__ == '__main__':
    main()
