#!/usr/bin/env python3
"""
YOLOX-S Hardware NPU Inference Engine for Orange Pi 4A (Allwinner T527).
Executes on VeriSilicon VIP9000 Nano-DI NPU via VIPLite v1.13 (/dev/vipcore).
"""

import os
import sys
import time
import argparse
import numpy as np
import cv2

from vipcore_model import VIPCoreContainer

COCO_CLASSES = (
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat", "traffic light",
    "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow",
    "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee",
    "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove", "skateboard", "surfboard",
    "tennis racket", "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple",
    "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch",
    "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote", "keyboard", "cell phone",
    "microwave", "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase", "scissors", "teddy bear",
    "hair drier", "toothbrush"
)

# High-visibility palette for bounding box rendering
_PALETTE = np.array([
    [255, 56, 56], [255, 157, 151], [255, 112, 31], [255, 178, 29], [207, 210, 49],
    [72, 249, 10], [146, 204, 23], [61, 219, 134], [26, 147, 52], [0, 212, 187],
    [44, 153, 168], [0, 194, 255], [52, 69, 147], [100, 115, 255], [0, 24, 236],
    [132, 56, 255], [82, 0, 133], [203, 56, 255], [255, 149, 200], [255, 55, 199]
], dtype=np.uint8)


def nms(boxes, scores, nms_thr):
    """Vectorized single-class Non-Maximum Suppression."""
    x1 = boxes[:, 0]
    y1 = boxes[:, 1]
    x2 = boxes[:, 2]
    y2 = boxes[:, 3]

    areas = (x2 - x1 + 1) * (y2 - y1 + 1)
    order = scores.argsort()[::-1]

    keep = []
    while order.size > 0:
        i = order[0]
        keep.append(i)
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])

        w = np.maximum(0.0, xx2 - xx1 + 1)
        h = np.maximum(0.0, yy2 - yy1 + 1)
        inter = w * h
        ovr = inter / (areas[i] + areas[order[1:]] - inter)

        inds = np.where(ovr <= nms_thr)[0]
        order = order[inds + 1]

    return keep


def multiclass_nms(boxes, scores, nms_thr=0.45, score_thr=0.3):
    """Class-agnostic multiclass NMS matching official YOLOX."""
    cls_inds = scores.argmax(1)
    cls_scores = scores[np.arange(len(cls_inds)), cls_inds]

    valid_score_mask = cls_scores >= score_thr
    if not np.any(valid_score_mask):
        return None, None, None

    valid_scores = cls_scores[valid_score_mask]
    valid_boxes = boxes[valid_score_mask]
    valid_cls_inds = cls_inds[valid_score_mask]

    keep = nms(valid_boxes, valid_scores, nms_thr)
    if not keep:
        return None, None, None

    return valid_boxes[keep], valid_scores[keep], valid_cls_inds[keep]


def yolox_preprocess(img, input_size=(640, 640)):
    """
    YOLOX standard aspect-ratio preserving letterbox resize with top-left placement.
    Padding value is 114. Returns uint8 BGR array suitable for NPU preproc node.
    """
    h0, w0 = img.shape[:2]
    target_h, target_w = input_size

    ratio = min(target_h / h0, target_w / w0)
    new_w = int(round(w0 * ratio))
    new_h = int(round(h0 * ratio))

    resized_img = cv2.resize(
        img, (new_w, new_h), interpolation=cv2.INTER_LINEAR
    ).astype(np.uint8)

    padded_img = np.full((target_h, target_w, 3), 114, dtype=np.uint8)
    padded_img[:new_h, :new_w] = resized_img

    return padded_img, ratio


def process_multi_outputs(outputs):
    """
    Reshapes and concatenates multi-head outputs into merged prediction tensor.
    Each head: (1, 85, H, W) -> transpose to (1, H, W, 85) -> flatten to (1, H*W, 85).
    Merged shape: (1, 8400, 85).
    """
    all_predictions = []
    for out in outputs:
        # out shape: (1, 85, H, W)
        hwc_output = np.transpose(out, (0, 2, 3, 1))
        flattened = hwc_output.reshape(1, -1, 85)
        all_predictions.append(flattened)

    return np.concatenate(all_predictions, axis=1)


def demo_postprocess(outputs, img_size=(640, 640)):
    """
    Vectorized YOLOX anchor grid decoding across strides [8, 16, 32].
    """
    grids = []
    expanded_strides = []
    strides = [8, 16, 32]

    hsizes = [img_size[0] // stride for stride in strides]
    wsizes = [img_size[1] // stride for stride in strides]

    for hsize, wsize, stride in zip(hsizes, wsizes, strides):
        xv, yv = np.meshgrid(np.arange(wsize), np.arange(hsize))
        grid = np.stack((xv, yv), 2).reshape(1, -1, 2)
        grids.append(grid)
        shape = grid.shape[:2]
        expanded_strides.append(np.full((*shape, 1), stride))

    grids = np.concatenate(grids, 1)
    expanded_strides = np.concatenate(expanded_strides, 1)

    outputs_copy = outputs.copy()
    outputs_copy[..., :2] = (outputs_copy[..., :2] + grids) * expanded_strides
    outputs_copy[..., 2:4] = np.exp(outputs_copy[..., 2:4]) * expanded_strides

    return outputs_copy


def draw_detections(img, boxes, scores, classes):
    """Draw bounding boxes and class labels with colored background badges."""
    canvas = img.copy()
    for i in range(len(boxes)):
        x1, y1, x2, y2 = map(int, boxes[i])
        cls_id = int(classes[i])
        score = float(scores[i])

        color = [int(c) for c in _PALETTE[cls_id % len(_PALETTE)]]
        label = f"{COCO_CLASSES[cls_id]}: {score*100:.1f}%"

        cv2.rectangle(canvas, (x1, y1), (x2, y2), color, 2)

        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.5
        font_thickness = 1
        (txt_w, txt_h), baseline = cv2.getTextSize(label, font, font_scale, font_thickness)

        badge_y1 = max(0, y1 - txt_h - baseline - 4)
        badge_y2 = y1
        cv2.rectangle(canvas, (x1, badge_y1), (x1 + txt_w + 6, badge_y2), color, -1)

        luminance = 0.299 * color[2] + 0.587 * color[1] + 0.114 * color[0]
        text_color = (0, 0, 0) if luminance > 128 else (255, 255, 255)
        cv2.putText(canvas, label, (x1 + 3, badge_y2 - baseline - 1),
                    font, font_scale, text_color, font_thickness, cv2.LINE_AA)

    return canvas


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_model = os.path.join(script_dir, "models", "yolox_s_sim_uint8_t527.nb")
    default_dir = os.path.join(script_dir, "output")

    parser = argparse.ArgumentParser(description="YOLOX-S NPU Inference Engine for Orange Pi 4A (Allwinner T527)")
    parser.add_argument("image", nargs="?", default=None,
                        help="Path to input image (positional)")
    parser.add_argument("-m", "--model", type=str,
                        default=default_model,
                        help="Path to compiled NBG model file")
    parser.add_argument("-i", "--input", type=str, default=None,
                        help="Path to input image")
    parser.add_argument("-o", "--output", type=str, default=None,
                        help="Path to save annotated output image")
    parser.add_argument("-s", "--score_thr", type=float, default=0.35,
                        help="Detection confidence threshold")
    parser.add_argument("--nms_thr", type=float, default=0.45,
                        help="Non-Maximum Suppression IoU threshold")
    parser.add_argument("-l", "--loop", type=int, default=1,
                        help="Number of benchmark inference loops")
    args = parser.parse_args()

    input_path = args.input or args.image
    if not input_path:
        print("Error: No input image specified. Provide an image path or use -i/--input.")
        parser.print_help()
        sys.exit(1)

    if not os.path.exists(input_path):
        print(f"Error: Input image not found at {input_path}")
        sys.exit(1)

    args.input = input_path

    # Determine smart output path if not specified
    if not args.output:
        base_name = os.path.splitext(os.path.basename(input_path))[0]
        if os.path.exists("output") and os.path.isdir("output"):
            args.output = os.path.join("output", f"output_{base_name}.jpg")
        elif os.path.exists(default_dir):
            args.output = os.path.join(default_dir, f"output_{base_name}.jpg")
        else:
            args.output = f"output_{base_name}.jpg"

    print("=================================================================")
    print(" Orange Pi 4A (Allwinner T527) - YOLOX Hardware NPU Inference")
    print("=================================================================")
    print(f"Model Path   : {args.model}")
    print(f"Input Image  : {args.input}")
    print(f"Score Thresh : {args.score_thr}")
    print(f"NMS Thresh   : {args.nms_thr}")

    # 1. Initialize NPU Model
    print("\n[1/4] Initializing VIPLite v1.13 and loading NPU model...")
    t_init0 = time.perf_counter()
    model = VIPCoreContainer(args.model)
    t_init1 = time.perf_counter()
    print(f"      Model loaded in {(t_init1 - t_init0)*1000:.1f} ms")

    # 2. Pre-processing
    print("[2/4] Pre-processing input image (letterbox 640x640 top-left padding)...")
    orig_img = cv2.imread(args.input)
    if orig_img is None:
        print(f"Error: Failed to read image {args.input}")
        sys.exit(1)

    t_pre0 = time.perf_counter()
    input_tensor, ratio = yolox_preprocess(orig_img, (640, 640))
    t_pre1 = time.perf_counter()
    pre_time = (t_pre1 - t_pre0) * 1000
    print(f"      Pre-process time: {pre_time:.2f} ms (Original: {orig_img.shape[1]}x{orig_img.shape[0]})")

    # 3. Hardware Inference
    print(f"[3/4] Executing hardware NPU inference on /dev/vipcore (loops: {args.loop})...")
    # Warmup
    model.run(input_tensor)

    infer_times = []
    for _ in range(args.loop):
        t0 = time.perf_counter()
        outputs = model.run(input_tensor)
        t1 = time.perf_counter()
        infer_times.append((t1 - t0) * 1000)

    avg_infer_time = np.mean(infer_times)
    fps = 1000.0 / avg_infer_time
    print(f"      Average Hardware NPU Latency: {avg_infer_time:.2f} ms ({fps:.1f} FPS)")

    # 4. Post-processing & Bounding Box Reconstruction
    print("[4/4] Merging output heads (strides 8/16/32) and applying NMS...")
    t_post0 = time.perf_counter()

    merged_predictions = process_multi_outputs(outputs)
    decoded_predictions = demo_postprocess(merged_predictions, (640, 640))[0]

    boxes = decoded_predictions[:, :4]
    scores = decoded_predictions[:, 4:5] * decoded_predictions[:, 5:]

    # Center (cx, cy, w, h) -> (x1, y1, x2, y2)
    boxes_xyxy = np.empty_like(boxes)
    boxes_xyxy[:, 0] = boxes[:, 0] - boxes[:, 2] / 2.0
    boxes_xyxy[:, 1] = boxes[:, 1] - boxes[:, 3] / 2.0
    boxes_xyxy[:, 2] = boxes[:, 0] + boxes[:, 2] / 2.0
    boxes_xyxy[:, 3] = boxes[:, 1] + boxes[:, 3] / 2.0

    # Rescale back to original image coordinates
    boxes_xyxy /= ratio

    # Clip to image boundary
    orig_h, orig_w = orig_img.shape[:2]
    boxes_xyxy[:, 0] = np.clip(boxes_xyxy[:, 0], 0, orig_w - 1)
    boxes_xyxy[:, 1] = np.clip(boxes_xyxy[:, 1], 0, orig_h - 1)
    boxes_xyxy[:, 2] = np.clip(boxes_xyxy[:, 2], 0, orig_w - 1)
    boxes_xyxy[:, 3] = np.clip(boxes_xyxy[:, 3], 0, orig_h - 1)

    final_boxes, final_scores, final_classes = multiclass_nms(
        boxes_xyxy, scores, nms_thr=args.nms_thr, score_thr=args.score_thr
    )

    t_post1 = time.perf_counter()
    post_time = (t_post1 - t_post0) * 1000

    det_count = len(final_boxes) if final_boxes is not None else 0
    print(f"      Post-process time: {post_time:.2f} ms")
    print(f"      Total Pipeline Latency: {pre_time + avg_infer_time + post_time:.2f} ms")
    print(f"      Total Detections Found: {det_count}")

    # Display detections
    print("\n------------------- Detections -------------------")
    if det_count > 0:
        sort_idx = np.argsort(final_scores)[::-1]
        for rank, idx in enumerate(sort_idx, 1):
            cls_name = COCO_CLASSES[final_classes[idx]]
            score = final_scores[idx]
            box = final_boxes[idx]
            print(f"  #{rank}: {cls_name:<12} {score*100:>5.1f}%  [{box[0]:.0f}, {box[1]:.0f}, {box[2]:.0f}, {box[3]:.0f}]")

        os.makedirs(os.path.dirname(args.output), exist_ok=True)
        annotated_img = draw_detections(orig_img, final_boxes, final_scores, final_classes)
        cv2.imwrite(args.output, annotated_img)
        print(f"\nAnnotated visualization successfully saved to:\n  {args.output}")
    else:
        print("  No objects detected above threshold.")

    print("=================================================================")
    model.destroy()


if __name__ == "__main__":
    main()
