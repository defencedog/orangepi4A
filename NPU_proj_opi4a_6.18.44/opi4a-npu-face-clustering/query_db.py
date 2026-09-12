#!/usr/bin/env python3
"""
CLI Query Utility for Orange Pi 4A Face Clustering SQLite Database
"""

import os
import sys
import argparse
import sqlite3

def query_people(conn):
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.id, p.assigned_name, COUNT(f.id) as appearance_count, p.thumbnail_path, p.first_detected_at
        FROM people p
        LEFT JOIN face_instances f ON p.id = f.person_id
        GROUP BY p.id
        ORDER BY appearance_count DESC, p.assigned_name ASC
    """)
    rows = cursor.fetchall()
    
    print("\n" + "=" * 75)
    print(f"{'ID':<4} | {'Assigned Name':<22} | {'Appearances':<12} | {'First Detected'}")
    print("-" * 75)
    for r in rows:
        pid, name, count, thumb, ts = r
        print(f"{pid:<4} | {name:<22} | {count:<12} | {ts}")
    print("=" * 75)
    print(f"Total Unique Individuals: {len(rows)}\n")

def query_person_scenes(conn, person_query):
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.id, p.assigned_name, i.file_name, i.file_path, f.bbox_x1, f.bbox_y1, f.bbox_x2, f.bbox_y2, f.confidence
        FROM people p
        JOIN face_instances f ON p.id = f.person_id
        JOIN images i ON f.image_id = i.id
        WHERE p.assigned_name LIKE ? OR p.id = ?
        ORDER BY i.file_name ASC
    """, (f"%{person_query}%", person_query if person_query.isdigit() else -1))
    rows = cursor.fetchall()

    if not rows:
        print(f"[!] No records found for person query: '{person_query}'")
        return

    person_name = rows[0][1]
    print("\n" + "=" * 80)
    print(f" Appearance History for: '{person_name}' (Total: {len(rows)} scenes)")
    print("=" * 80)
    for r in rows:
        _, _, file_name, file_path, x1, y1, x2, y2, conf = r
        print(f"  • Image: {file_name}")
        print(f"    Box:   [{x1}, {y1} -> {x2}, {y2}] (Confidence: {conf:.2f})")
        print(f"    Path:  {file_path}\n")

def query_image(conn, image_query):
    cursor = conn.cursor()
    cursor.execute("""
        SELECT i.id, i.file_name, i.width, i.height, p.assigned_name, f.bbox_x1, f.bbox_y1, f.bbox_x2, f.bbox_y2, f.confidence
        FROM images i
        JOIN face_instances f ON i.id = f.image_id
        JOIN people p ON f.person_id = p.id
        WHERE i.file_name LIKE ? OR i.file_path LIKE ?
        ORDER BY f.confidence DESC
    """, (f"%{image_query}%", f"%{image_query}%"))
    rows = cursor.fetchall()

    if not rows:
        print(f"[!] No records found for image query: '{image_query}'")
        return

    fname = rows[0][1]
    w, h = rows[0][2], rows[0][3]
    print("\n" + "=" * 75)
    print(f" Faces Detected in Image: '{fname}' ({w}x{h}, {len(rows)} people)")
    print("=" * 75)
    for r in rows:
        _, _, _, _, name, x1, y1, x2, y2, conf = r
        print(f"  • {name:<22} (Conf: {conf:.2f}) at [{x1},{y1} -> {x2},{y2}]")
    print("=" * 75 + "\n")

def main():
    parser = argparse.ArgumentParser(description="Query Face Clustering Database on Orange Pi 4A")
    parser.add_argument("--db", default=os.path.join(os.path.dirname(__file__), "faces.db"), help="Path to SQLite database")
    parser.add_argument("--list-people", action="store_true", help="List all indexed people and total appearances")
    parser.add_argument("--person", type=str, help="Search scenes and images for a specific person name or ID")
    parser.add_argument("--image", type=str, help="List all people detected in a specific image file")

    args = parser.parse_args()

    if not os.path.exists(args.db):
        print(f"[!] Database file does not exist: {args.db}")
        print("Run cluster_and_index.py first to detect and index faces.")
        sys.exit(1)

    conn = sqlite3.connect(args.db)

    if args.list_people:
        query_people(conn)
    elif args.person:
        query_person_scenes(conn, args.person)
    elif args.image:
        query_image(conn, args.image)
    else:
        query_people(conn)

    conn.close()

if __name__ == "__main__":
    main()
