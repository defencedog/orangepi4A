#!/usr/bin/env python3
"""
End-to-End Face Detection, 5-Point Landmark Alignment, Identity Clustering, and Relational SQLite Indexer
Designed for Orange Pi 4A (Allwinner T527)
"""

import os
import sys
import glob
import random
import sqlite3
import argparse
import cv2
import numpy as np
import time

from face_detector import SCRFDFaceDetector
from face_embedder import MobileFaceNetEmbedder

# Hollywood-style random name generator
FIRST_NAMES = [
    "Marcus", "Elena", "Arthur", "Sienna", "Julian", "Cassidy", "Dominic", 
    "Valerie", "Victor", "Diana", "Sebastian", "Clara", "Adrian", "Natasha",
    "Gideon", "Miriam", "Leo", "Vivian", "Damian", "Serena", "Xavier", "Isla"
]

LAST_NAMES = [
    "Vance", "Sterling", "Cross", "Drake", "Hayes", "Brooks", "Mercer", 
    "Castillo", "Blackwood", "Sinclair", "Winter", "Hawthorne", "Caine", 
    "Vanderbilt", "Ashford", "Kingsley", "Monroe", "Delaney", "Rhodes"
]

def generate_unique_name(existing_names):
    for _ in range(1000):
        name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
        if name not in existing_names:
            return name
    return f"Person_{random.randint(1000, 9999)}"

def init_db(db_path, schema_path, reset=False):
    if reset and os.path.exists(db_path):
        os.remove(db_path)
    conn = sqlite3.connect(db_path)
    if os.path.exists(schema_path):
        with open(schema_path, "r") as f:
            conn.executescript(f.read())
    conn.commit()
    return conn

def load_known_identities(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT id, assigned_name FROM people")
    people_rows = cursor.fetchall()
    
    known = {}
    for pid, name in people_rows:
        cursor.execute("SELECT embedding_blob FROM face_instances WHERE person_id = ?", (pid,))
        face_rows = cursor.fetchall()
        embs = [np.frombuffer(row[0], dtype=np.float32) for row in face_rows if row[0]]
        if embs:
            # Centroid normalized embedding
            mean_emb = np.mean(embs, axis=0)
            norm = np.linalg.norm(mean_emb)
            if norm > 0:
                mean_emb /= norm
            known[pid] = {
                "name": name,
                "embeddings": embs,
                "centroid": mean_emb
            }
        else:
            known[pid] = {
                "name": name,
                "embeddings": [],
                "centroid": None
            }
    return known

def find_matching_person(emb, known_people, threshold=0.38):
    """
    Compares embedding against known identity centroids using cosine similarity.
    Threshold: 0.38 (empirically validated for MobileFaceNet with canonical 5-point alignment).
    """
    best_pid = None
    best_sim = -1.0

    for pid, data in known_people.items():
        centroid = data["centroid"]
        if centroid is not None:
            sim = float(np.dot(centroid, emb))
            if sim > best_sim:
                best_sim = sim
                best_pid = pid

    if best_sim >= threshold:
        return best_pid, best_sim
    return None, best_sim

def main():
    parser = argparse.ArgumentParser(description="Index and Cluster Faces on Orange Pi 4A")
    parser.add_argument("--reset", action="store_true", help="Wipe database and re-index from scratch")
    parser.add_argument("--threshold", type=float, default=0.38, help="Cosine similarity clustering threshold (default: 0.38)")
    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.abspath(__file__))
    images_dir = os.path.join(base_dir, "images")
    crops_dir = os.path.join(base_dir, "crops")
    models_dir = os.path.join(base_dir, "models")
    db_path = os.path.join(base_dir, "faces.db")
    schema_path = os.path.join(base_dir, "database", "schema.sql")

    os.makedirs(crops_dir, exist_ok=True)

    det_model = os.path.join(models_dir, "scrfd_500m.onnx")
    rec_model = os.path.join(models_dir, "w600k_mbf.onnx")

    if not os.path.exists(det_model) or not os.path.exists(rec_model):
        print(f"Error: Model files not found in {models_dir}")
        sys.exit(1)

    print("=" * 70)
    print(" Orange Pi 4A: Face Detection, 5-Point Alignment & Clustering")
    print("=" * 70)
    if args.reset:
        print("[!] Reset flag specified: Clearing existing database and crop cache.")
        for f in glob.glob(os.path.join(crops_dir, "*.jpg")):
            try: os.remove(f)
            except: pass

    conn = init_db(db_path, schema_path, reset=args.reset)
    known_people = load_known_identities(conn)
    existing_names = {data["name"] for data in known_people.values()}
    print(f"[*] SQLite Database: {db_path} ({len(known_people)} known people)")
    print(f"[*] Similarity Threshold: {args.threshold:.2f}")

    # Read initial NPU active time
    npu_active_file = "/sys/devices/platform/soc/7122000.npu/power/runtime_active_time"
    npu_t0 = 0
    if os.path.exists(npu_active_file):
        try:
            with open(npu_active_file) as f:
                npu_t0 = int(f.read().strip())
        except Exception: pass

    print(f"[*] Initializing SCRFD 500M Face Detector (VIP9000 NPU + Cortex-A55)...")
    detector = SCRFDFaceDetector(det_model, input_size=(640, 640), conf_threshold=0.4, use_npu=True)

    print(f"[*] Initializing MobileFaceNet 512-D Embedder (5-Point Alignment)...")
    embedder = MobileFaceNetEmbedder(rec_model, num_threads=6)

    # Gather images
    valid_exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    image_files = [
        os.path.join(images_dir, f) for f in os.listdir(images_dir)
        if os.path.splitext(f.lower())[1] in valid_exts
    ]
    image_files.sort()

    if not image_files:
        print(f"[!] No image files found in {images_dir}. Place images there and rerun.")
        return

    print(f"[*] Found {len(image_files)} image files in ingestion queue.\n")

    total_faces = 0
    new_people_count = 0
    matched_faces_count = 0
    cursor = conn.cursor()

    for idx, img_path in enumerate(image_files, start=1):
        file_name = os.path.basename(img_path)
        
        # Check if already indexed
        cursor.execute("SELECT id FROM images WHERE file_path = ?", (img_path,))
        existing_img = cursor.fetchone()
        if existing_img:
            print(f"[{idx}/{len(image_files)}] Skipping already indexed: {file_name}")
            continue

        t0 = time.perf_counter()
        img = cv2.imread(img_path)
        if img is None:
            print(f"[!] Could not read image: {img_path}")
            continue

        h, w = img.shape[:2]
        
        # Insert image record
        cursor.execute(
            "INSERT INTO images (file_name, file_path, width, height) VALUES (?, ?, ?, ?)",
            (file_name, img_path, w, h)
        )
        image_id = cursor.lastrowid

        # Detect faces with 5 landmarks
        t_det0 = time.perf_counter()
        detections = detector.detect(img)
        t_det = (time.perf_counter() - t_det0) * 1000
        npu_str = f" [NPU: {detector.npu_time_ms:.1f}ms]" if detector.npu_interp else ""
        print(f"[{idx}/{len(image_files)}] {file_name} ({w}x{h}): {len(detections)} face(s){npu_str} [Total: {t_det:.1f}ms]")

        for f_idx, det in enumerate(detections, start=1):
            bbox = det["bbox"]
            conf = det["confidence"]
            lmk = det.get("landmarks")
            x1, y1, x2, y2 = bbox

            t_emb0 = time.perf_counter()
            emb, aligned_face = embedder.extract_embedding(img, landmarks_5pt=lmk, bbox=bbox)
            t_emb = (time.perf_counter() - t_emb0) * 1000

            if emb is None:
                continue

            # Identity Clustering
            matched_pid, sim = find_matching_person(emb, known_people, threshold=args.threshold)

            if matched_pid is not None:
                person_name = known_people[matched_pid]["name"]
                person_id = matched_pid
                # Update centroid with new sample
                known_people[person_id]["embeddings"].append(emb)
                mean_emb = np.mean(known_people[person_id]["embeddings"], axis=0)
                mean_emb /= np.linalg.norm(mean_emb)
                known_people[person_id]["centroid"] = mean_emb
                matched_faces_count += 1
                status_str = f"MATCHED '{person_name}' (sim: {sim:.2f})"
            else:
                new_name = generate_unique_name(existing_names)
                existing_names.add(new_name)
                # Save thumbnail crop
                thumb_name = f"{new_name.replace(' ', '_')}_{image_id}_{f_idx}.jpg"
                thumb_path = os.path.join(crops_dir, thumb_name)
                cv2.imwrite(thumb_path, aligned_face if aligned_face is not None else img[y1:y2, x1:x2])

                cursor.execute(
                    "INSERT INTO people (assigned_name, thumbnail_path) VALUES (?, ?)",
                    (new_name, thumb_path)
                )
                person_id = cursor.lastrowid
                known_people[person_id] = {
                    "name": new_name,
                    "embeddings": [emb],
                    "centroid": emb
                }
                new_people_count += 1
                person_name = new_name
                status_str = f"NEW PERSON -> Assigned '{new_name}'"

            # Save face crop instance
            crop_name = f"face_{image_id}_{f_idx}_{person_name.replace(' ', '_')}.jpg"
            crop_path = os.path.join(crops_dir, crop_name)
            cv2.imwrite(crop_path, aligned_face if aligned_face is not None else img[y1:y2, x1:x2])

            # Insert face instance
            cursor.execute(
                """INSERT INTO face_instances 
                   (person_id, image_id, bbox_x1, bbox_y1, bbox_x2, bbox_y2, confidence, crop_path, embedding_blob) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (person_id, image_id, x1, y1, x2, y2, conf, crop_path, emb.tobytes())
            )
            total_faces += 1
            print(f"    Face #{f_idx} [{x1},{y1} -> {x2},{y2}] Conf: {conf:.2f} -> {status_str} (Emb: {t_emb:.1f}ms)")

        conn.commit()
        t_total = (time.perf_counter() - t0) * 1000
        print(f"    Turnaround: {t_total:.1f}ms\n")

    conn.close()
    npu_delta = 0
    if os.path.exists(npu_active_file) and npu_t0 > 0:
        try:
            with open(npu_active_file) as f:
                npu_delta = int(f.read().strip()) - npu_t0
        except Exception: pass

    print("=" * 70)
    print(" Indexing Complete Summary:")
    print(f"   • Total Faces Detected & Indexed: {total_faces}")
    print(f"   • Total Unique People in Database: {len(known_people)}")
    print(f"   • Matched Across Images: {matched_faces_count}")
    print(f"   • Newly Discovered People: {new_people_count}")
    if npu_delta > 0:
        print(f"   • Hardware NPU Active Execution: {npu_delta} ms ({npu_delta/1000:.2f}s on silicon)")
    print(f"   • Relational SQLite File: {db_path}")
    print("=" * 70)

if __name__ == "__main__":
    main()
