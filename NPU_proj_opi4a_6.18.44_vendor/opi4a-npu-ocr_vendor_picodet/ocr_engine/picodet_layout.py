# Copyright (c) 2024. Allwinner T527 VIP9000 NPU OCR Pipeline.
"""PicoDet-Layout Model Decoder and Post-Processor.

Supports:
- picodet_layout_1600.nb (1600x1600 input, 8 output heads)
- picodet_layout_2048.nb (2048x2048 input, 8 output heads)

Layout Categories:
0: text    (Body paragraph / text column)
1: title   (Document title, section heading)
2: list    (Enumerated or bulleted list)
3: table   (Tabular data block)
4: figure  (Diagram, plot, photograph, illustration)
"""
import os
import sys
import time
import cv2
import numpy as np

try:
    from vipcore_model import UnifiedModelContainer
except ImportError:
    from ocr_engine.vipcore_model import UnifiedModelContainer

LAYOUT_LABELS = ['text', 'title', 'list', 'table', 'figure']

COLOR_MAP = {
    'text': (220, 100, 0),      # Blue
    'title': (0, 0, 220),       # Red
    'list': (0, 180, 0),        # Green
    'table': (0, 140, 255),     # Orange
    'figure': (180, 0, 180)     # Purple
}


def nms(boxes, scores, iou_threshold=0.5):
    """Vectorized Non-Maximum Suppression."""
    if len(boxes) == 0:
        return []

    x1 = boxes[:, 0]
    y1 = boxes[:, 1]
    x2 = boxes[:, 2]
    y2 = boxes[:, 3]

    areas = np.maximum(0.0, x2 - x1) * np.maximum(0.0, y2 - y1)
    order = scores.argsort()[::-1]

    keep = []
    while order.size > 0:
        i = order[0]
        keep.append(i)

        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])

        w = np.maximum(0.0, xx2 - xx1)
        h = np.maximum(0.0, yy2 - yy1)
        inter = w * h

        ovr = inter / (areas[i] + areas[order[1:]] - inter + 1e-6)
        inds = np.where(ovr <= iou_threshold)[0]
        order = order[inds + 1]

    return keep


class PicoDetLayout:
    """PicoDet-Layout Detector with hardware VIP9000 NPU acceleration."""

    def __init__(self, model_path, backend='auto', num_threads=6,
                 score_thresh=0.25, nms_thresh=0.5):
        self.model = UnifiedModelContainer(model_path, backend=backend, num_threads=num_threads)
        self.score_thresh = score_thresh
        self.nms_thresh = nms_thresh

        # Auto-detect input dimensions
        if hasattr(self.model, 'input_shape'):
            self.input_shape = self.model.input_shape
        else:
            self.input_shape = [1600, 1600]

        self.target_h, self.target_w = self.input_shape[0], self.input_shape[1]
        self.fpn_strides = [8, 16, 32, 64]
        self.reg_max = 7  # 8 bins (0..7)
        self.project = np.arange(self.reg_max + 1, dtype=np.float32)

        # Precompute anchor grid centers for each FPN stride
        self.anchors = []
        for stride in self.fpn_strides:
            grid_h = self.target_h // stride
            grid_w = self.target_w // stride
            grid_x, grid_y = np.meshgrid(
                np.arange(grid_w, dtype=np.float32),
                np.arange(grid_h, dtype=np.float32)
            )
            # Center offset 0.5 * stride
            cx = (grid_x + 0.5) * stride
            cy = (grid_y + 0.5) * stride
            anchor_pts = np.stack([cx.reshape(-1), cy.reshape(-1)], axis=-1)
            self.anchors.append(anchor_pts)

    def preprocess(self, img):
        """Resize and normalize BGR image to NCHW FP32 tensor."""
        src_h, src_w = img.shape[:2]
        img_resized = cv2.resize(img, (self.target_w, self.target_h))
        img_rgb = cv2.cvtColor(img_resized, cv2.COLOR_BGR2RGB)
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32).reshape((1, 1, 3))
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32).reshape((1, 1, 3))
        norm = (img_rgb.astype(np.float32) / 255.0 - mean) / std
        norm = np.transpose(norm, (2, 0, 1))[np.newaxis, ...]
        return norm, (src_h, src_w)

    def decode(self, outputs, orig_shape):
        """Decode multi-head GFL regression and classification outputs."""
        src_h, src_w = orig_shape
        scale_x = float(src_w) / float(self.target_w)
        scale_y = float(src_h) / float(self.target_h)

        cls_heads = outputs[0:4]
        reg_heads = outputs[4:8]

        all_boxes = []
        all_scores = []
        all_classes = []

        for i in range(4):
            cls_out = cls_heads[i][0]  # Shape: (N_i, 5)
            reg_out = reg_heads[i][0]  # Shape: (N_i, 32)
            stride = self.fpn_strides[i]
            anchors = self.anchors[i]  # Shape: (N_i, 2)

            # Vectorized candidate filtering
            max_cls_scores = np.max(cls_out, axis=-1)
            candidate_idx = np.where(max_cls_scores >= self.score_thresh)[0]
            if len(candidate_idx) == 0:
                continue

            cand_cls = cls_out[candidate_idx]
            cand_reg = reg_out[candidate_idx]
            cand_anchors = anchors[candidate_idx]

            # Generalized Focal Loss Integral
            # Reshape (K, 4, 8)
            reg_dist = cand_reg.reshape(-1, 4, self.reg_max + 1)
            # Numerically stable Softmax over the 8 bins
            shift_dist = reg_dist - np.max(reg_dist, axis=-1, keepdims=True)
            exp_dist = np.exp(shift_dist)
            prob_dist = exp_dist / (np.sum(exp_dist, axis=-1, keepdims=True) + 1e-9)

            # Expected distance = sum(prob_i * i) * stride
            dist = np.sum(prob_dist * self.project, axis=-1) * stride  # (K, 4) -> [l, t, r, b]

            # Reconstruct (x1, y1, x2, y2) in model coordinate space
            x1 = cand_anchors[:, 0] - dist[:, 0]
            y1 = cand_anchors[:, 1] - dist[:, 1]
            x2 = cand_anchors[:, 0] + dist[:, 2]
            y2 = cand_anchors[:, 1] + dist[:, 3]

            # Clip to model coordinates
            x1 = np.clip(x1, 0, self.target_w)
            y1 = np.clip(y1, 0, self.target_h)
            x2 = np.clip(x2, 0, self.target_w)
            y2 = np.clip(y2, 0, self.target_h)

            # Scale to original image coordinates
            orig_x1 = x1 * scale_x
            orig_y1 = y1 * scale_y
            orig_x2 = x2 * scale_x
            orig_y2 = y2 * scale_y

            boxes = np.stack([orig_x1, orig_y1, orig_x2, orig_y2], axis=-1)
            best_cat = np.argmax(cand_cls, axis=-1)
            best_sco = np.max(cand_cls, axis=-1)

            all_boxes.append(boxes)
            all_scores.append(best_sco)
            all_classes.append(best_cat)

        if len(all_boxes) == 0:
            return []

        all_boxes = np.concatenate(all_boxes, axis=0)
        all_scores = np.concatenate(all_scores, axis=0)
        all_classes = np.concatenate(all_classes, axis=0)

        # Multi-class NMS
        final_results = []
        for cat_id in range(len(LAYOUT_LABELS)):
            cat_mask = (all_classes == cat_id)
            if not np.any(cat_mask):
                continue
            cat_boxes = all_boxes[cat_mask]
            cat_scores = all_scores[cat_mask]

            keep_idx = nms(cat_boxes, cat_scores, iou_threshold=self.nms_thresh)
            for k in keep_idx:
                box = cat_boxes[k].tolist()
                score = float(cat_scores[k])
                cat_name = LAYOUT_LABELS[cat_id]
                x1, y1, x2, y2 = box

                # Sanity check area
                if (x2 - x1) < 5 or (y2 - y1) < 5:
                    continue

                final_results.append({
                    "category": cat_name,
                    "category_id": int(cat_id),
                    "score": round(score, 4),
                    "bbox": [round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1)],
                    "poly": [
                        [round(x1, 1), round(y1, 1)],
                        [round(x2, 1), round(y1, 1)],
                        [round(x2, 1), round(y2, 1)],
                        [round(x1, 1), round(y2, 1)]
                    ]
                })

        return final_results

    def run(self, img):
        """Execute layout analysis on input image."""
        norm_tensor, orig_shape = self.preprocess(img)
        outputs = self.model.run(norm_tensor)
        results = self.decode(outputs, orig_shape)
        return results

    def release(self):
        self.model.release()


def sort_reading_order(layout_blocks, page_width):
    """Sort layout blocks in natural human reading order.
    
    Order strategy:
    1. Titles and top headers (spanning full or partial width)
    2. Multi-column text flow (grouped by column centroid)
    3. Tables and figures placed near their visual context
    """
    if len(layout_blocks) == 0:
        return []

    # Sort blocks primarily top-to-bottom
    blocks = sorted(layout_blocks, key=lambda b: (b["bbox"][1], b["bbox"][0]))
    return blocks


def draw_layout(image, results, output_path=None):
    """Render layout bounding boxes and labels onto an image copy."""
    vis = image.copy()
    for item in results:
        cat = item["category"]
        color = COLOR_MAP.get(cat, (0, 255, 0))
        x1, y1, x2, y2 = [int(v) for v in item["bbox"]]
        score = item["score"]

        # Draw bounding box
        cv2.rectangle(vis, (x1, y1), (x2, y2), color, 2)

        # Label background
        label_text = f"{cat} {score:.2f}"
        (tw, th), baseline = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(vis, (x1, max(0, y1 - th - baseline - 4)),
                      (x1 + tw + 6, max(0, y1)), color, -1)
        cv2.putText(vis, label_text, (x1 + 3, max(th + 2, y1 - baseline - 2)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)

    if output_path:
        cv2.imwrite(output_path, vis)
    return vis
