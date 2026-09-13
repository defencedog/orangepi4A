#!/usr/bin/env python3
import sys
import os
import time
import cv2

PKG_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(PKG_DIR, "ocr_engine"))
from picodet_layout import PicoDetLayout, draw_layout

def main():
    img_path = os.path.join(PKG_DIR, "samples", "page_test-1.png")
    if not os.path.exists(img_path):
        print(f"File not found: {img_path}")
        return

    img = cv2.imread(img_path)
    print(f"Loaded image: {img.shape}")

    for m_name in ["picodet_layout_1600.nb", "picodet_layout_2048.nb"]:
        model_path = os.path.join(PKG_DIR, "models", m_name)
        if not os.path.exists(model_path):
            continue

        print(f"\n==========================================")
        print(f"Testing {m_name} on VIP9000 NPU")
        print(f"==========================================")
        detector = PicoDetLayout(model_path, backend="vipcore_npu", score_thresh=0.015, nms_thresh=0.4)

        # Warmup
        _ = detector.run(img)

        # Benchmark
        times = []
        for _ in range(3):
            t0 = time.time()
            results = detector.run(img)
            times.append((time.time() - t0) * 1000)

        avg_t = sum(times) / len(times)
        print(f"Inference + GFL Decode Latency: {avg_t:.1f} ms (min: {min(times):.1f} ms, max: {max(times):.1f} ms)")
        print(f"Detected {len(results)} layout regions:")

        # Summary by category
        cat_counts = {}
        for r in results:
            c = r["category"]
            cat_counts[c] = cat_counts.get(c, 0) + 1
        print("  Categories found:", cat_counts)

        for r in results[:10]:
            print(f"  [{r['category']:6s}] score={r['score']:.4f} bbox={r['bbox']}")

        out_name = f"layout_{m_name.replace('.nb', '')}.png"
        out_path = os.path.join(PKG_DIR, "ocr_output", out_name)
        draw_layout(img, results, out_path)
        print(f"Saved visualization to: {out_path}")

        detector.release()

if __name__ == "__main__":
    main()
