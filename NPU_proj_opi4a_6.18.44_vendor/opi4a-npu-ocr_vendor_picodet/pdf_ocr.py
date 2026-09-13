#!/usr/bin/env python3
"""Two-Stage Hardware-Accelerated PDF OCR Pipeline for Orange Pi 4A (Allwinner T527).

Architecture:
Stage 1: PicoDet-Layout (1600x1600 or 2048x2048) on VIP9000 NPU (/dev/vipcore)
         Decomposes page into macro structural regions:
         - Text blocks (paragraphs, multi-column divisions)
         - Title / Section headings
         - Lists
         - Tables (isolated structured tabular blocks)
         - Figures (diagrams, plots, illustrations)

Stage 2: PP-OCRv6 DBNet (1600x1600 or 2048x2048) on VIP9000 NPU
         High-resolution 1-shot micro text line detection with zero tiling.

Stage 3: Spatial Association & Structural Reading Order
         Maps detected text lines to enclosing macro layout blocks, resolving
         multi-column document flow without naive column-splitting guesswork.

Stage 4: English PP-OCRv4 Recognition (33ms/line on 8x ARM Cortex-A55 Neon FP16)
         Zero CJK hallucination dictionary decoding.

Usage:
    pdf_ocr.py samples/sample-compressor.pdf
    pdf_ocr.py document.pdf --dpi 200 --layout-model models/picodet_layout_2048.nb --det-model models/ppocrv6_det_2048.nb --vis --json --md
"""
import argparse
import glob
import json
import os
import subprocess
import sys
import time
import cv2
import numpy as np

# Add local ocr_engine package to sys.path
PKG_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(PKG_DIR, "ocr_engine"))

from ppocr_det import TextDetector
from ppocr_rec import TextRecognizer
from picodet_layout import PicoDetLayout, draw_layout, COLOR_MAP

DEFAULT_LAYOUT_MODEL = os.path.join(PKG_DIR, "models", "picodet_layout_1600.nb")
DEFAULT_DET_MODEL = os.path.join(PKG_DIR, "models", "ppocrv6_det_1600.nb")
DEFAULT_REC_MODEL = os.path.join(PKG_DIR, "models", "en_pp_ocrv4_rec_dynamic.mnn")
DEFAULT_REC_DICT = os.path.join(PKG_DIR, "models", "en_dict.txt")
DEFAULT_BACKEND = "vipcore_npu" if os.path.exists("/dev/vipcore") else "mnn_cpu"

DEFAULT_DPI = 200
DROP_SCORE = 0.45
MAX_PAGE_DIM = 2400


def get_rotate_crop_image(img, points):
    """Crop and perspective-correct quadrilateral text box."""
    assert len(points) == 4
    points = np.asarray(points, dtype=np.float32)
    w = int(max(np.linalg.norm(points[0] - points[1]),
                np.linalg.norm(points[2] - points[3])))
    h = int(max(np.linalg.norm(points[0] - points[3]),
                np.linalg.norm(points[1] - points[2])))
    if w <= 0 or h <= 0:
        return None
    pts = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    M = cv2.getPerspectiveTransform(points, pts)
    dst = cv2.warpPerspective(img, M, (w, h),
                              borderMode=cv2.BORDER_REPLICATE,
                              flags=cv2.INTER_CUBIC)
    if dst.shape[0] * 1.0 / max(1, dst.shape[1]) >= 1.5:
        dst = np.rot90(dst)
    return dst


def sorted_boxes(dt_boxes):
    """Sort bounding boxes in standard reading order: top-to-bottom, left-to-right."""
    if len(dt_boxes) <= 1:
        return dt_boxes
    return sorted(dt_boxes, key=lambda b: (np.min(np.array(b)[:, 1]), np.min(np.array(b)[:, 0])))


def rasterize_pdf(pdf_path, output_dir, dpi=200, max_pages=0):
    """Convert PDF pages to PNG using pdftoppm."""
    os.makedirs(output_dir, exist_ok=True)
    prefix = os.path.join(output_dir, "page")
    cmd = ["pdftoppm", "-png", "-r", str(dpi)]
    if max_pages > 0:
        cmd.extend(["-l", str(max_pages)])
    cmd.extend([pdf_path, prefix])

    ret = subprocess.run(cmd, capture_output=True, text=True)
    if ret.returncode != 0:
        raise RuntimeError(f"pdftoppm failed: {ret.stderr}")

    pattern = os.path.join(output_dir, "page-*.png")
    pages = sorted(glob.glob(pattern))
    if not pages:
        pattern = os.path.join(output_dir, "page_*.png")
        pages = sorted(glob.glob(pattern))
    return pages


def find_rendered_page(tmp_dir, page_num):
    """Find the pdftoppm rendered image file for a given 1-based page number."""
    prefix = os.path.join(tmp_dir, "page")
    for pattern in [f"{prefix}-{page_num:01d}.png", f"{prefix}-{page_num:02d}.png",
                    f"{prefix}-{page_num:03d}.png", f"{prefix}-{page_num:04d}.png"]:
        matches = glob.glob(pattern)
        if matches:
            return matches[0]
    return f"{prefix}-{page_num}.png"


def assign_lines_to_layout(dt_boxes, layout_blocks, page_w, page_h):
    """Map detected text line bounding boxes to macro layout blocks.
    
    Returns structured list of layout blocks with their associated text lines.
    """
    # Create wrapper containers for each layout block
    blocks = []
    for idx, b in enumerate(layout_blocks):
        blocks.append({
            "id": idx,
            "category": b["category"],
            "category_id": b.get("category_id", 0),
            "score": b["score"],
            "bbox": b["bbox"], # [x1, y1, x2, y2]
            "lines": []
        })

    unassigned_lines = []

    for box in dt_boxes:
        # Calculate line center and bounding rect
        pts = np.array(box, dtype=np.float32)
        cx = float(np.mean(pts[:, 0]))
        cy = float(np.mean(pts[:, 1]))
        lx1 = float(np.min(pts[:, 0]))
        ly1 = float(np.min(pts[:, 1]))
        lx2 = float(np.max(pts[:, 0]))
        ly2 = float(np.max(pts[:, 1]))

        best_block = None
        best_overlap = 0.0

        for blk in blocks:
            bx1, by1, bx2, by2 = blk["bbox"]
            # Check center containment first
            if bx1 <= cx <= bx2 and by1 <= cy <= by2:
                best_block = blk
                break

            # Calculate intersection area as fallback
            ix1 = max(lx1, bx1)
            iy1 = max(ly1, by1)
            ix2 = min(lx2, bx2)
            iy2 = min(ly2, by2)
            if ix2 > ix1 and iy2 > iy1:
                inter_area = (ix2 - ix1) * (iy2 - iy1)
                line_area = max(1.0, (lx2 - lx1) * (ly2 - ly1))
                overlap_ratio = inter_area / line_area
                if overlap_ratio > best_overlap and overlap_ratio >= 0.3:
                    best_overlap = overlap_ratio
                    best_block = blk

        if best_block is not None:
            best_block["lines"].append(box)
        else:
            unassigned_lines.append(box)

    # Sort lines within each block top-to-bottom
    for blk in blocks:
        if len(blk["lines"]) > 0:
            blk["lines"] = sorted(blk["lines"], key=lambda b: (np.min(np.array(b)[:, 1]), np.min(np.array(b)[:, 0])))

    # Handle unassigned lines: group by vertical reading position
    if len(unassigned_lines) > 0:
        unassigned_lines = sorted(unassigned_lines, key=lambda b: (np.min(np.array(b)[:, 1]), np.min(np.array(b)[:, 0])))
        # Create virtual block for unassigned lines
        blocks.append({
            "id": -1,
            "category": "text",
            "category_id": 0,
            "score": 1.0,
            "bbox": [0.0, 0.0, float(page_w), float(page_h)],
            "lines": unassigned_lines
        })

    # Sort blocks by document reading order:
    # 1. Full width blocks (spanning > 65% width) sorted top-to-bottom
    # 2. Multi-column blocks between full-width section breaks: Col 1 first, then Col 2
    sorted_blocks = sort_blocks_reading_order(blocks, page_w)
    return sorted_blocks


def sort_blocks_reading_order(blocks, page_w):
    """Sort layout blocks in natural reading order."""
    if len(blocks) <= 1:
        return blocks

    # Remove empty blocks
    non_empty = [b for b in blocks if len(b["lines"]) > 0 or b["category"] in ["table", "figure"]]
    if not non_empty:
        return blocks

    midpoint = page_w / 2.0

    # Classify blocks: Full-Width vs Column 1 (Left) vs Column 2 (Right)
    def classify_pos(b):
        x1, y1, x2, y2 = b["bbox"]
        bw = x2 - x1
        cx = (x1 + x2) / 2.0
        if bw > (0.65 * page_w):
            return "full"
        elif cx < midpoint:
            return "col1"
        else:
            return "col2"

    # Sort all blocks by top y coordinate
    y_sorted = sorted(non_empty, key=lambda b: (b["bbox"][1], b["bbox"][0]))

    # Group into vertical sections split by full-width elements (e.g. titles or full-width tables)
    sections = []
    current_col_blocks = []

    for b in y_sorted:
        pos = classify_pos(b)
        if pos == "full" or b["category"] == "title":
            if current_col_blocks:
                sections.append(("cols", current_col_blocks))
                current_col_blocks = []
            sections.append(("full", [b]))
        else:
            current_col_blocks.append(b)

    if current_col_blocks:
        sections.append(("cols", current_col_blocks))

    # Assemble final reading order
    final_ordered = []
    for sec_type, sec_blocks in sections:
        if sec_type == "full":
            final_ordered.extend(sec_blocks)
        else:
            # Columnar section: sort Col 1 top-to-bottom, then Col 2 top-to-bottom
            col1 = [b for b in sec_blocks if classify_pos(b) == "col1"]
            col2 = [b for b in sec_blocks if classify_pos(b) == "col2"]
            col1_sorted = sorted(col1, key=lambda b: (b["bbox"][1], b["bbox"][0]))
            col2_sorted = sorted(col2, key=lambda b: (b["bbox"][1], b["bbox"][0]))
            final_ordered.extend(col1_sorted)
            final_ordered.extend(col2_sorted)

    return final_ordered


def main():
    parser = argparse.ArgumentParser(description="Two-Stage Layout-Guided Hardware PDF OCR on Orange Pi 4A")
    parser.add_argument("pdf", help="Input PDF file")
    parser.add_argument("--dpi", type=int, default=DEFAULT_DPI, help=f"Rendering DPI (default: {DEFAULT_DPI})")
    parser.add_argument("--layout-model", default=DEFAULT_LAYOUT_MODEL, help="PicoDet layout model (.nb)")
    parser.add_argument("--no-layout", action="store_true", help="Bypass layout detection (single-stage mode)")
    parser.add_argument("--det-model", default=DEFAULT_DET_MODEL, help="Text detection model (.nb)")
    parser.add_argument("--rec-model", default=DEFAULT_REC_MODEL, help="Text recognition model (.mnn)")
    parser.add_argument("--dict", default=DEFAULT_REC_DICT, help="Path to character dictionary")
    parser.add_argument("--backend", default=DEFAULT_BACKEND, choices=["auto", "vipcore_npu", "mnn_cpu"])
    parser.add_argument("--threads", type=int, default=4, help="Inference threads (default: 4)")
    parser.add_argument("--max-pages", type=int, default=0, help="Max pages to process (0 = all)")
    parser.add_argument("--out-dir", default="./ocr_output", help="Output directory")
    parser.add_argument("--json", action="store_true", help="Export structured JSON output")
    parser.add_argument("--md", action="store_true", help="Export structured Markdown output")
    parser.add_argument("--vis", action="store_true", help="Export visual overlay diagrams")
    parser.add_argument("--layout-score-thresh", type=float, default=0.20, help="Layout score threshold (default: 0.20)")
    args = parser.parse_args()

    if not os.path.exists(args.pdf):
        print(f"Error: {args.pdf} not found")
        sys.exit(1)

    os.makedirs(args.out_dir, exist_ok=True)

    use_layout = (not args.no_layout) and os.path.exists(args.layout_model)

    print(f"==================================================")
    print(f"Orange Pi 4A (Allwinner T527) - Two-Stage OCR Engine")
    print(f"==================================================")
    print(f"  Target Hardware: VeriSilicon VIP9000 2.0 TOPS NPU + 8x Cortex-A55")
    print(f"  Rasterization:   {args.dpi} DPI")
    print(f"  Layout Model:    {args.layout_model if use_layout else 'Disabled'}")
    print(f"  Det Model:       {args.det_model}")
    print(f"  Rec Model:       {args.rec_model}")
    print(f"  Backend:         {args.backend}")
    print(f"  Threads:         {args.threads}")

    # Initialize models
    layout_detector = None
    if use_layout:
        layout_detector = PicoDetLayout(args.layout_model, backend=args.backend,
                                        num_threads=args.threads,
                                        score_thresh=args.layout_score_thresh)

    det = TextDetector(args.det_model, backend=args.backend, num_threads=args.threads)
    rec = TextRecognizer(args.rec_model, dict_path=args.dict, backend=args.backend, num_threads=args.threads)

    # 1. Rasterize PDF
    tmp_render_dir = os.path.join(args.out_dir, "_tmp_rendered")
    t0 = time.time()
    pages = rasterize_pdf(args.pdf, tmp_render_dir, dpi=args.dpi, max_pages=args.max_pages)
    t_raster = (time.time() - t0) * 1000
    print(f"Rasterized {len(pages)} page(s) at {args.dpi} DPI in {t_raster:.1f} ms")

    all_page_results = []
    total_layout_time = 0.0
    total_det_time = 0.0
    total_rec_time = 0.0

    for p_idx, page_file in enumerate(pages):
        p_num = p_idx + 1
        img = cv2.imread(page_file)
        if img is None:
            actual_page = find_rendered_page(tmp_render_dir, p_num)
            img = cv2.imread(actual_page)
            if img is None:
                print(f"[WARN] Failed to read rendered page {p_num}")
                continue

        h, w = img.shape[:2]
        if max(h, w) > MAX_PAGE_DIM:
            scale = MAX_PAGE_DIM / float(max(h, w))
            img = cv2.resize(img, (int(w * scale), int(h * scale)))
            h, w = img.shape[:2]

        # Stage 1: Layout Analysis
        t_layout = 0.0
        layout_blocks = []
        if layout_detector:
            t_lay0 = time.time()
            layout_blocks = layout_detector.run(img)
            t_layout = (time.time() - t_lay0) * 1000
            total_layout_time += t_layout

        # Stage 2: Text Line Detection
        t_det0 = time.time()
        dt_boxes = det.run(img)
        t_det = (time.time() - t_det0) * 1000
        total_det_time += t_det

        # Stage 3: Spatial Association & Reading Order
        if use_layout and len(layout_blocks) > 0:
            structured_blocks = assign_lines_to_layout(dt_boxes, layout_blocks, w, h)
        else:
            # Fallback simple top-to-bottom
                        structured_blocks = [{
                "id": 0,
                "category": "text",
                "category_id": 0,
                "score": 1.0,
                "bbox": [0.0, 0.0, float(w), float(h)],
                "lines": sorted_boxes(dt_boxes)
            }]

        # Flatten ordered boxes for batch recognition
        ordered_boxes = []
        box_to_block_map = []
        for blk in structured_blocks:
            for box in blk["lines"]:
                ordered_boxes.append(box)
                box_to_block_map.append(blk)

        # Stage 4: Text Line Recognition
        img_crop_list = []
        for box in ordered_boxes:
            crop = get_rotate_crop_image(img, box)
            if crop is not None:
                img_crop_list.append(crop)

        t_rec0 = time.time()
        rec_results = rec.run(img_crop_list)
        t_rec = (time.time() - t_rec0) * 1000
        total_rec_time += t_rec

        # Associate recognized text with structured blocks
        crop_idx = 0
        page_lines = []
        page_blocks_structured = []

        for blk in structured_blocks:
            blk_lines_recognized = []
            for box in blk["lines"]:
                if crop_idx >= len(rec_results):
                    break
                rec_res = rec_results[crop_idx]
                crop_idx += 1

                if isinstance(rec_res, (list, tuple)) and len(rec_res) > 0:
                    item = rec_res[0]
                    if isinstance(item, (list, tuple)) and len(item) >= 2:
                        text, score = item[0], item[1]
                    elif isinstance(item, str):
                        text, score = item, (rec_res[1] if len(rec_res) >= 2 and isinstance(rec_res[1], (int, float)) else 1.0)
                    else:
                        continue
                else:
                    continue

                if score >= DROP_SCORE and len(text.strip()) > 0:
                    line_data = {
                        "text": text,
                        "score": float(score),
                        "box": [p.tolist() if hasattr(p, "tolist") else p for p in box],
                        "category": blk["category"]
                    }
                    blk_lines_recognized.append(line_data)
                    page_lines.append(line_data)

            if len(blk_lines_recognized) > 0:
                page_blocks_structured.append({
                    "category": blk["category"],
                    "bbox": blk["bbox"],
                    "score": blk["score"],
                    "lines": blk_lines_recognized
                })
            elif blk["category"] == "figure" and blk.get("score", 0) >= 0.35:
                page_blocks_structured.append({
                    "category": "figure",
                    "bbox": blk["bbox"],
                    "score": blk["score"],
                    "lines": []
                })

        all_page_results.append({
            "page": p_num,
            "blocks": page_blocks_structured,
            "lines": page_lines,
            "layout_time_ms": t_layout,
            "det_time_ms": t_det,
            "rec_time_ms": t_rec,
            "total_time_ms": t_layout + t_det + t_rec
        })

        # Save single page text file
        page_txt_file = os.path.join(args.out_dir, f"page_{p_num:04d}.txt")
        with open(page_txt_file, "w", encoding="utf-8") as f:
            for blk in page_blocks_structured:
                cat = blk["category"]
                if cat == "title":
                    f.write("\n### " + " ".join([l["text"] for l in blk["lines"]]) + "\n\n")
                elif cat == "table":
                    f.write(f"\n[TABLE BBOX: {blk['bbox']}]\n")
                    for l in blk["lines"]:
                        f.write(l["text"] + "\n")
                    f.write("[END TABLE]\n\n")
                elif cat == "figure":
                    f.write(f"\n[FIGURE BBOX: {blk['bbox']}]\n")
                    for l in blk["lines"]:
                        f.write(l["text"] + "\n")
                    f.write("[END FIGURE]\n\n")
                else:
                    for l in blk["lines"]:
                        f.write(l["text"] + "\n")
                    f.write("\n")

        # Save visualization overlay if requested
        if args.vis:
            vis_img = draw_layout(img, layout_blocks)
            for line in page_lines:
                pts = np.array(line["box"], dtype=np.int32)
                cv2.polylines(vis_img, [pts], isClosed=True, color=(0, 255, 0), thickness=1)
            vis_path = os.path.join(args.out_dir, f"page_{p_num:04d}_vis.png")
            cv2.imwrite(vis_path, vis_img)

        print(f"  Page {p_num:02d}/{len(pages):02d} [{w}x{h}]: "
              f"{len(layout_blocks)} layout regions | {len(page_lines)} lines | "
              f"Layout: {t_layout:.1f}ms | Det: {t_det:.1f}ms | Rec: {t_rec:.1f}ms | "
              f"Total: {(t_layout + t_det + t_rec):.1f}ms")

    # Clean up temporary rendered images
    for p in pages:
        try:
            os.remove(p)
        except OSError:
            pass
    try:
        os.rmdir(tmp_render_dir)
    except OSError:
        pass

    # Save full combined text output
    combined_txt_file = os.path.join(args.out_dir, "document.txt")
    with open(combined_txt_file, "w", encoding="utf-8") as f:
        for p in all_page_results:
            f.write(f"==================================================\n")
            f.write(f"--- Page {p['page']} ---\n")
            f.write(f"==================================================\n\n")
            for blk in p["blocks"]:
                cat = blk["category"]
                if cat == "title":
                    f.write("### " + " ".join([l["text"] for l in blk["lines"]]) + "\n\n")
                elif cat == "table":
                    f.write(f"[TABLE BBOX: {blk['bbox']}]\n")
                    for l in blk["lines"]:
                        f.write(l["text"] + "\n")
                    f.write("[END TABLE]\n\n")
                elif cat == "figure":
                    f.write(f"[FIGURE BBOX: {blk['bbox']}]\n")
                    for l in blk["lines"]:
                        f.write(l["text"] + "\n")
                    f.write("[END FIGURE]\n\n")
                else:
                    for l in blk["lines"]:
                        f.write(l["text"] + "\n")
                    f.write("\n")

    # Save full combined Markdown output if requested
    if args.md:
        md_file = os.path.join(args.out_dir, "document.md")
        with open(md_file, "w", encoding="utf-8") as f:
            for p in all_page_results:
                f.write(f"\n## Page {p['page']}\n\n")
                for blk in p["blocks"]:
                    cat = blk["category"]
                    if cat == "title":
                        f.write("### " + " ".join([l["text"] for l in blk["lines"]]) + "\n\n")
                    elif cat == "list":
                        for l in blk["lines"]:
                            f.write(f"- {l['text']}\n")
                        f.write("\n")
                    elif cat == "table":
                        f.write(f"> **Table Region** `(bbox: {blk['bbox']})`\n>\n")
                        for l in blk["lines"]:
                            f.write(f"> {l['text']}\n")
                        f.write("\n")
                    elif cat == "figure":
                        f.write(f"> **Figure Region** `(bbox: {blk['bbox']})`\n>\n")
                        for l in blk["lines"]:
                            f.write(f"> {l['text']}\n")
                        f.write("\n")
                    else:
                        f.write(" ".join([l["text"] for l in blk["lines"]]) + "\n\n")

    if args.json:
        json_file = os.path.join(args.out_dir, "ocr_results.json")
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(all_page_results, f, indent=2, ensure_ascii=False)

    if layout_detector:
        layout_detector.release()
    det.release()
    rec.release()

    num_p = len(all_page_results)
    print(f"\n==================================================")
    print(f"Two-Stage OCR Complete:")
    print(f"  Total Pages:        {num_p}")
    print(f"  Avg Layout Latency: {total_layout_time/max(1, num_p):.1f} ms / page")
    print(f"  Avg Det Latency:    {total_det_time/max(1, num_p):.1f} ms / page")
    print(f"  Avg Rec Latency:    {total_rec_time/max(1, num_p):.1f} ms / page")
    print(f"  Avg Total Time:     {(total_layout_time + total_det_time + total_rec_time)/max(1, num_p):.1f} ms / page")
    print(f"  Results saved:      {args.out_dir}")
    print(f"==================================================")


if __name__ == "__main__":
    main()
