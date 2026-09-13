"""Unified Model Container for Orange Pi 4A (Allwinner T527).

Supports:
- VIPCore NPU (.nb): Native VeriSilicon VIP9000 2.0 TOPS NPU via VIPLite v1.13 (/dev/vipcore)
  Supports FP16, FP32, and UINT8 input tensors, and arbitrary multi-output tensor topologies.
"""
import os
import sys
import time
import ctypes
import numpy as np

# VIPLite C Constants and Enums
VIP_NETWORK_PROP_INPUT_COUNT = 1
VIP_NETWORK_PROP_OUTPUT_COUNT = 2

VIP_BUFFER_PROP_QUANT_FORMAT = 0
VIP_BUFFER_PROP_NUM_OF_DIMENSION = 1
VIP_BUFFER_PROP_SIZES_OF_DIMENSION = 2
VIP_BUFFER_PROP_DATA_FORMAT = 3
VIP_BUFFER_PROP_FIXED_POINT_POS = 4
VIP_BUFFER_PROP_TF_SCALE = 5
VIP_BUFFER_PROP_TF_ZERO_POINT = 6

VIP_BUFFER_FORMAT_FP32 = 0
VIP_BUFFER_FORMAT_FP16 = 1
VIP_BUFFER_FORMAT_UINT8 = 2
VIP_BUFFER_FORMAT_INT8 = 3

VIP_CREATE_NETWORK_FROM_FILE = 1
VIP_BUFFER_OPER_TYPE_FLUSH = 1
VIP_BUFFER_OPER_TYPE_INVALIDATE = 2

class DfpParam(ctypes.Structure):
    _fields_ = [("fixed_point_pos", ctypes.c_int32)]

class AffineParam(ctypes.Structure):
    _fields_ = [("scale", ctypes.c_float),
                ("zeroPoint", ctypes.c_int32)]

class QuantData(ctypes.Union):
    _fields_ = [("dfp", DfpParam),
                ("affine", AffineParam)]

class VipBufferCreateParams(ctypes.Structure):
    _fields_ = [
        ("num_of_dims", ctypes.c_uint32),
        ("sizes", ctypes.c_uint32 * 6),
        ("data_format", ctypes.c_int32),
        ("quant_format", ctypes.c_int32),
        ("quant_data", QuantData),
        ("memory_type", ctypes.c_uint32)
    ]


class VIPCoreContainer:
    def __init__(self, model_path, viplite_lib='/usr/local/lib/libVIPlite.so'):
        self.model_path = model_path
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model file not found: {model_path}")
        if not os.path.exists(viplite_lib):
            raise FileNotFoundError(f"VIPLite library not found: {viplite_lib}")

        self.lib = ctypes.CDLL(viplite_lib)

        # Function signatures
        self.lib.vip_init.restype = ctypes.c_int32
        self.lib.vip_destroy.restype = ctypes.c_int32

        self.lib.vip_create_network.argtypes = [
            ctypes.c_char_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p)
        ]
        self.lib.vip_create_network.restype = ctypes.c_int32

        self.lib.vip_destroy_network.argtypes = [ctypes.c_void_p]
        self.lib.vip_destroy_network.restype = ctypes.c_int32

        self.lib.vip_create_buffer.argtypes = [
            ctypes.POINTER(VipBufferCreateParams), ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p)
        ]
        self.lib.vip_create_buffer.restype = ctypes.c_int32

        self.lib.vip_destroy_buffer.argtypes = [ctypes.c_void_p]
        self.lib.vip_destroy_buffer.restype = ctypes.c_int32

        self.lib.vip_set_input.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p]
        self.lib.vip_set_input.restype = ctypes.c_int32

        self.lib.vip_set_output.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p]
        self.lib.vip_set_output.restype = ctypes.c_int32

        self.lib.vip_prepare_network.argtypes = [ctypes.c_void_p]
        self.lib.vip_prepare_network.restype = ctypes.c_int32

        self.lib.vip_run_network.argtypes = [ctypes.c_void_p]
        self.lib.vip_run_network.restype = ctypes.c_int32

        self.lib.vip_map_buffer.argtypes = [ctypes.c_void_p]
        self.lib.vip_map_buffer.restype = ctypes.c_void_p

        self.lib.vip_unmap_buffer.argtypes = [ctypes.c_void_p]
        self.lib.vip_unmap_buffer.restype = ctypes.c_int32

        self.lib.vip_flush_buffer.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        self.lib.vip_flush_buffer.restype = ctypes.c_int32

        self.lib.vip_get_buffer_size.argtypes = [ctypes.c_void_p]
        self.lib.vip_get_buffer_size.restype = ctypes.c_uint32

        # Initialize VIPLite hardware runtime
        ret = self.lib.vip_init()
        if ret != 0:
            raise RuntimeError(f"vip_init failed: {ret}. Ensure /dev/vipcore is active ('npu vipcore').")

        # Load Network
        self.vip_net = ctypes.c_void_p()
        ret = self.lib.vip_create_network(self.model_path.encode('utf-8'), 0,
                                          VIP_CREATE_NETWORK_FROM_FILE,
                                          ctypes.byref(self.vip_net))
        if ret != 0:
            raise RuntimeError(f"vip_create_network failed for {self.model_path}: {ret}")

        # Query input buffer parameters
        self.in_param = VipBufferCreateParams()
        self.in_param.memory_type = 0
        self.lib.vip_query_input(self.vip_net, 0, VIP_BUFFER_PROP_DATA_FORMAT,
                                 ctypes.byref(self.in_param, VipBufferCreateParams.data_format.offset))
        self.lib.vip_query_input(self.vip_net, 0, VIP_BUFFER_PROP_NUM_OF_DIMENSION,
                                 ctypes.byref(self.in_param, VipBufferCreateParams.num_of_dims.offset))
        self.lib.vip_query_input(self.vip_net, 0, VIP_BUFFER_PROP_SIZES_OF_DIMENSION,
                                 ctypes.byref(self.in_param, VipBufferCreateParams.sizes.offset))
        self.lib.vip_query_input(self.vip_net, 0, VIP_BUFFER_PROP_QUANT_FORMAT,
                                 ctypes.byref(self.in_param, VipBufferCreateParams.quant_format.offset))

        scale = ctypes.c_float(0.0)
        zp = ctypes.c_int32(0)
        self.lib.vip_query_input(self.vip_net, 0, VIP_BUFFER_PROP_TF_SCALE, ctypes.byref(scale))
        self.lib.vip_query_input(self.vip_net, 0, VIP_BUFFER_PROP_TF_ZERO_POINT, ctypes.byref(zp))
        self.in_param.quant_data.affine.scale = scale.value
        self.in_param.quant_data.affine.zeroPoint = zp.value
        self.in_scale = scale.value if scale.value != 0 else 1.0
        self.in_zp = zp.value

        # Dimensions: in VIPLite sizes are [W, H, C, N]
        self.in_w = self.in_param.sizes[0]
        self.in_h = self.in_param.sizes[1]
        self.in_c = self.in_param.sizes[2] if self.in_param.num_of_dims > 2 else 1
        self.input_shape = [self.in_h, self.in_w]

        self.vip_in_buf = ctypes.c_void_p()
        ret = self.lib.vip_create_buffer(ctypes.byref(self.in_param),
                                         ctypes.sizeof(self.in_param),
                                         ctypes.byref(self.vip_in_buf))
        if ret != 0:
            raise RuntimeError(f"vip_create_buffer (input) failed: {ret}")

        self.in_buf_size = self.lib.vip_get_buffer_size(self.vip_in_buf)

        # Query outputs
        num_outputs = ctypes.c_uint32(0)
        ret = self.lib.vip_query_network(self.vip_net, VIP_NETWORK_PROP_OUTPUT_COUNT, ctypes.byref(num_outputs))
        self.num_outputs = num_outputs.value if ret == 0 and num_outputs.value > 0 else 1

        self.out_params = []
        self.out_scales = []
        self.out_zps = []
        self.out_shapes = []
        self.vip_out_bufs = []
        self.out_buf_sizes = []

        for i in range(self.num_outputs):
            out_p = VipBufferCreateParams()
            out_p.memory_type = 0
            self.lib.vip_query_output(self.vip_net, i, VIP_BUFFER_PROP_DATA_FORMAT,
                                      ctypes.byref(out_p, VipBufferCreateParams.data_format.offset))
            self.lib.vip_query_output(self.vip_net, i, VIP_BUFFER_PROP_NUM_OF_DIMENSION,
                                      ctypes.byref(out_p, VipBufferCreateParams.num_of_dims.offset))
            self.lib.vip_query_output(self.vip_net, i, VIP_BUFFER_PROP_SIZES_OF_DIMENSION,
                                      ctypes.byref(out_p, VipBufferCreateParams.sizes.offset))
            self.lib.vip_query_output(self.vip_net, i, VIP_BUFFER_PROP_QUANT_FORMAT,
                                      ctypes.byref(out_p, VipBufferCreateParams.quant_format.offset))

            s = ctypes.c_float(0.0)
            z = ctypes.c_int32(0)
            self.lib.vip_query_output(self.vip_net, i, VIP_BUFFER_PROP_TF_SCALE, ctypes.byref(s))
            self.lib.vip_query_output(self.vip_net, i, VIP_BUFFER_PROP_TF_ZERO_POINT, ctypes.byref(z))
            out_p.quant_data.affine.scale = s.value
            out_p.quant_data.affine.zeroPoint = z.value
            scale_val = s.value if s.value != 0 else (1.0 / 255.0)
            zp_val = z.value

            # VIPLite sizes are [W, H, C, N], reversed -> (N, C, H, W)
            num_d = out_p.num_of_dims
            dims = [out_p.sizes[d] for d in range(num_d)]
            np_shape = tuple(reversed(dims))

            out_buf = ctypes.c_void_p()
            ret = self.lib.vip_create_buffer(ctypes.byref(out_p),
                                              ctypes.sizeof(out_p),
                                              ctypes.byref(out_buf))
            if ret != 0:
                raise RuntimeError(f"vip_create_buffer (output {i}) failed: {ret}")

            self.out_params.append(out_p)
            self.out_scales.append(scale_val)
            self.out_zps.append(zp_val)
            self.out_shapes.append(np_shape)
            self.vip_out_bufs.append(out_buf)
            self.out_buf_sizes.append(self.lib.vip_get_buffer_size(out_buf))

        # Prepare network (generates command buffers and binds memory)
        ret = self.lib.vip_prepare_network(self.vip_net)
        if ret != 0:
            raise RuntimeError(f"vip_prepare_network failed: {ret}")

        # Bind buffers to network
        self.lib.vip_set_input(self.vip_net, 0, self.vip_in_buf)
        for i in range(self.num_outputs):
            self.lib.vip_set_output(self.vip_net, i, self.vip_out_bufs[i])

        print(f"[VIPCoreContainer] VIP9000 NPU loaded: {os.path.basename(self.model_path)} (input: [{self.in_c}, {self.in_h}, {self.in_w}], fmt: {self.in_param.data_format}, buf_size: {self.in_buf_size}, outputs: {self.num_outputs})")

    def run(self, inputs):
        if not isinstance(inputs, (list, tuple)):
            inputs = [inputs]

        data = inputs[0]
        if data.ndim == 3:
            data = np.expand_dims(data, axis=0)

        # Handle channel layout: check whether NPU buffer expects interleaved (HWC) or planar (NCHW)
        if self.in_param.sizes[0] in (1, 3):
            # Interleaved HWC expected (sizes[0] is channels)
            if data.shape[1] in (1, 3) and data.shape[-1] not in (1, 3):
                data = np.transpose(data, (0, 2, 3, 1))
        else:
            # Planar NCHW expected
            if data.shape[-1] in (1, 3) and data.shape[1] not in (1, 3):
                data = np.transpose(data, (0, 3, 1, 2))

        # Convert to expected input format
        if self.in_param.data_format == VIP_BUFFER_FORMAT_FP16:
            data_in = data.astype(np.float16)
        elif self.in_param.data_format == VIP_BUFFER_FORMAT_UINT8:
            if data.dtype != np.uint8:
                data_in = np.clip(np.round(data / self.in_scale) + self.in_zp, 0, 255).astype(np.uint8)
            else:
                data_in = data
        elif self.in_param.data_format == VIP_BUFFER_FORMAT_FP32:
            data_in = data.astype(np.float32)
        else:
            data_in = data.astype(np.float16)

        in_bytes = np.ascontiguousarray(data_in).tobytes()

        # Map & copy into NPU input buffer
        in_ptr = self.lib.vip_map_buffer(self.vip_in_buf)
        ctypes.memmove(in_ptr, in_bytes, min(len(in_bytes), self.in_buf_size))
        self.lib.vip_unmap_buffer(self.vip_in_buf)
        self.lib.vip_flush_buffer(self.vip_in_buf, VIP_BUFFER_OPER_TYPE_FLUSH)

        # Invoke hardware inference
        ret = self.lib.vip_run_network(self.vip_net)
        if ret != 0:
            raise RuntimeError(f"VIP9000 NPU execution error: {ret}")

        # Invalidate cache and extract outputs
        results = []
        for i in range(self.num_outputs):
            buf = self.vip_out_bufs[i]
            buf_sz = self.out_buf_sizes[i]
            self.lib.vip_flush_buffer(buf, VIP_BUFFER_OPER_TYPE_INVALIDATE)
            out_ptr = self.lib.vip_map_buffer(buf)

            if self.out_params[i].data_format == VIP_BUFFER_FORMAT_FP32:
                out_floats = (ctypes.c_float * (buf_sz // 4)).from_address(out_ptr)
                out_arr = np.frombuffer(out_floats, dtype=np.float32).copy()
                out_shaped = out_arr.reshape(self.out_shapes[i])
            elif self.out_params[i].data_format == VIP_BUFFER_FORMAT_FP16:
                out_f16 = (ctypes.c_uint16 * (buf_sz // 2)).from_address(out_ptr)
                out_arr = np.frombuffer(out_f16, dtype=np.float16).astype(np.float32).copy()
                out_shaped = out_arr.reshape(self.out_shapes[i])
            else:
                out_raw = (ctypes.c_uint8 * buf_sz).from_address(out_ptr)
                out_uint8 = np.frombuffer(out_raw, dtype=np.uint8).copy()
                out_float = (out_uint8.astype(np.float32) - self.out_zps[i]) * self.out_scales[i]
                out_shaped = out_float.reshape(self.out_shapes[i])

            self.lib.vip_unmap_buffer(buf)
            results.append(out_shaped)

        return results

    def destroy(self):
        if hasattr(self, 'lib') and self.lib:
            for buf in self.vip_out_bufs:
                self.lib.vip_destroy_buffer(buf)
            if hasattr(self, 'vip_in_buf'):
                self.lib.vip_destroy_buffer(self.vip_in_buf)
            if hasattr(self, 'vip_net'):
                self.lib.vip_destroy_network(self.vip_net)
            self.lib.vip_destroy()
