#!/usr/bin/env python3
"""
MobileFaceNet ArcFace 512-D Identity Embedder with 5-Point Landmark Alignment
Extracts canonical normalized facial identity vectors.
"""

import cv2
import numpy as np
import onnxruntime as ort

# Standard ArcFace 112x112 canonical reference landmark positions
ARCFACE_REFERENCE_LANDMARKS = np.array([
    [38.2946, 51.6963],  # Left Eye
    [73.5318, 51.5014],  # Right Eye
    [56.0252, 71.7366],  # Nose Tip
    [41.5493, 92.3655],  # Left Mouth Corner
    [70.7299, 92.2041]   # Right Mouth Corner
], dtype=np.float32)

class MobileFaceNetEmbedder:
    def __init__(self, model_path, num_threads=6):
        self.model_path = model_path
        
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = num_threads
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        
        self.session = ort.InferenceSession(self.model_path, opts)
        self.input_name = self.session.get_inputs()[0].name

    def align_face(self, img_bgr, landmarks_5pt):
        """
        Performs 5-point affine similarity transform warping the face to
        standard canonical 112x112 ArcFace geometry.
        """
        if landmarks_5pt is None or len(landmarks_5pt) != 5:
            return None
        M, _ = cv2.estimateAffinePartial2D(landmarks_5pt, ARCFACE_REFERENCE_LANDMARKS, method=cv2.LMEDS)
        if M is None:
            return None
        aligned = cv2.warpAffine(img_bgr, M, (112, 112), borderValue=0.0)
        return aligned

    def extract_embedding(self, img_bgr, landmarks_5pt=None, bbox=None):
        """
        Extracts a 512-dimensional L2-normalized float32 identity vector.
        Uses 5-point landmark alignment if landmarks are provided;
        otherwise falls back to center-resized bbox crop.
        """
        if landmarks_5pt is not None:
            aligned = self.align_face(img_bgr, landmarks_5pt)
        elif bbox is not None:
            x1, y1, x2, y2 = bbox
            crop = img_bgr[y1:y2, x1:x2]
            if crop.size == 0:
                return None, None
            aligned = cv2.resize(crop, (112, 112))
        else:
            aligned = cv2.resize(img_bgr, (112, 112))

        if aligned is None or aligned.size == 0:
            return None, None

        # Preprocess: RGB format, (x - 127.5) / 127.5
        blob = cv2.dnn.blobFromImage(
            aligned, 
            scalefactor=1.0 / 127.5, 
            size=(112, 112), 
            mean=(127.5, 127.5, 127.5), 
            swapRB=True
        )

        outs = self.session.run(None, {self.input_name: blob})
        embedding = outs[0].flatten().astype(np.float32)

        # L2-normalization for cosine similarity
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding /= norm

        return embedding, aligned
