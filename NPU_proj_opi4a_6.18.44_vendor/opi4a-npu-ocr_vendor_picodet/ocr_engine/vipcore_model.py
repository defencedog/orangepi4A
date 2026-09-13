"""Unified Model Container for Orange Pi 4A (Allwinner T527).

Supports:
- VIPCore NPU (.nb): Native VeriSilicon VIP9000 2.0 TOPS NPU via VIPLite v1.13 (/dev/vipcore)
- MNN CPU (.mnn): 8x ARM Cortex-A55 cores with ARM Neon FP16 SIMD acceleration

Handles NCHW vs NHWC layouts and quantization transparently.
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
VIP_BUFFER_PROP_TF_SCALE = 5
VIP_BUFFER_PROP_TF_ZERO_POINT = 6

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


class UnifiedModelContainer:
    def __init__(self, model_path, backend='auto', num_threads=6, precision='low',
                 viplite_lib='/usr/local/lib/libVIPlite.so'):
        self.model_path = model_path
        self.num_threads = num_threads
        self.backend = backend
        self.precision = precision
        self.engine = None
        self.is_nchw = True
        self.input_shape = [1024, 1024]

        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model file not found: {model_path}")

        ext = os.path.splitext(model_path)[1].lower()
        if ext == '.nb':
            self.backend = 'vipcore_npu'
        elif ext == '.mnn':
            self.backend = 'mnn_gpu' if 'gpu' in backend else 'mnn_cpu'
        elif backend == 'auto':
            if ext == '.nb':
                self.backend = 'vipcore_npu'
            elif ext == '.mnn':
                self.backend = 'mnn_cpu'
            else:
                raise ValueError(f"Unknown model extension: {ext}")

        if 'vipcore' in self.backend or ext == '.nb':
            self._init_vipcore(viplite_lib)
        elif 'mnn' in self.backend:
            self._init_mnn()
        else:
            raise ValueError(f"Unsupported backend: {self.backend}")

    def _init_vipcore(self, viplite_lib):
        if not os.path.exists(viplite_lib):
            raise FileNotFoundError(f"VIPLite library not found at: {viplite_lib}")
        if not os.path.exists("/dev/vipcore"):
            raise FileNotFoundError("Device /dev/vipcore not found. Ensure vipcore.ko is loaded.")

        self.lib = ctypes.CDLL(viplite_lib)

        # Configure ctypes signatures
        self.lib.vip_init.restype = ctypes.c_int
        self.lib.vip_destroy.restype = ctypes.c_int
        self.lib.vip_create_network.restype = ctypes.c_int
        self.lib.vip_destroy_network.restype = ctypes.c_int
        self.lib.vip_query_network.restype = ctypes.c_int
        self.lib.vip_query_input.restype = ctypes.c_int
        self.lib.vip_query_output.restype = ctypes.c_int
        self.lib.vip_create_buffer.restype = ctypes.c_int
        self.lib.vip_destroy_buffer.restype = ctypes.c_int
        self.lib.vip_prepare_network.restype = ctypes.c_int
        self.lib.vip_set_input.restype = ctypes.c_int
        self.lib.vip_set_output.restype = ctypes.c_int
        self.lib.vip_run_network.restype = ctypes.c_int
        self.lib.vip_map_buffer.restype = ctypes.c_void_p
        self.lib.vip_unmap_buffer.restype = ctypes.c_int
        self.lib.vip_flush_buffer.restype = ctypes.c_int
        self.lib.vip_get_buffer_size.restype = ctypes.c_uint32

        # Initialize VIPLite driver
        ret = self.lib.vip_init()
        if ret != 0:
            raise RuntimeError(f"vip_init failed with code {ret}")

        # Load NBG binary
        self.vip_net = ctypes.c_void_p()
        ret = self.lib.vip_create_network(self.model_path.encode('utf-8'), 0,
                                          VIP_CREATE_NETWORK_FROM_FILE,
                                          ctypes.byref(self.vip_net))
        if ret != 0:
            raise RuntimeError(f"vip_create_network failed for {self.model_path}: {ret}")

        # Query input buffer info
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

        # Input dimensions: in VIPLite sizes are [W, H, C, N]
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

        # Query number of outputs
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

            # Dimensions: in VIPLite sizes are [W, H, C, N]
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

        # Backward compatibility aliases for single-output models (DBNet)
        self.out_param = self.out_params[0]
        self.out_scale = self.out_scales[0]
        self.out_zp = self.out_zps[0]
        self.vip_out_buf = self.vip_out_bufs[0]
        self.out_buf_size = self.out_buf_sizes[0]
        self.out_w = self.out_param.sizes[0]
        self.out_h = self.out_param.sizes[1]
        self.out_c = self.out_param.sizes[2] if self.out_param.num_of_dims > 2 else 1

        # Prepare network (generates command buffers and binds memory)
        ret = self.lib.vip_prepare_network(self.vip_net)
        if ret != 0:
            raise RuntimeError(f"vip_prepare_network failed: {ret}")

        # Bind buffers to network
        self.lib.vip_set_input(self.vip_net, 0, self.vip_in_buf)
        for i in range(self.num_outputs):
            self.lib.vip_set_output(self.vip_net, i, self.vip_out_bufs[i])

        self.in_buf_size = self.lib.vip_get_buffer_size(self.vip_in_buf)
        self.is_nchw = True
        self.engine = 'vipcore'
        print(f"[VIPCoreContainer] VIP9000 NPU loaded: {os.path.basename(self.model_path)} (input: [{self.in_c}, {self.in_h}, {self.in_w}], outputs: {self.num_outputs})")

    def _init_mnn(self):
        import MNN
        self.MNN = MNN
        self.interpreter = MNN.Interpreter(self.model_path)
        cfg_backend = 'OPENCL' if 'gpu' in self.backend else 'CPU'
        config = {
            'precision': self.precision,
            'backend': cfg_backend,
            'numThread': self.num_threads
        }
        self.session = self.interpreter.createSession(config)
        self.input_tensor = self.interpreter.getSessionInput(self.session)
        self.output_tensor = self.interpreter.getSessionOutput(self.session)
        shape = self.input_tensor.getShape()
        self.input_shape = [shape[2], shape[3]] if len(shape) == 4 else [1024, 1024]
        self.is_nchw = True
        self.engine = 'mnn'

    def run(self, inputs):
        if not isinstance(inputs, (list, tuple)):
            inputs = [inputs]

        data = inputs[0]
        if data.ndim == 3:
            data = np.expand_dims(data, axis=0)

        if self.engine == 'vipcore':
            # Format to NCHW
            if data.shape[-1] in (1, 3) and data.shape[1] not in (1, 3):
                data = np.transpose(data, (0, 3, 1, 2))

            # Quantize normalized float input to uint8
            if data.dtype != np.uint8:
                data_q = np.clip(np.round(data / self.in_scale) + self.in_zp, 0, 255).astype(np.uint8)
            else:
                data_q = data

            in_bytes = np.ascontiguousarray(data_q).tobytes()

            # Map & copy into NPU buffer
            in_ptr = self.lib.vip_map_buffer(self.vip_in_buf)
            ctypes.memmove(in_ptr, in_bytes, min(len(in_bytes), self.in_buf_size))
            self.lib.vip_unmap_buffer(self.vip_in_buf)
            self.lib.vip_flush_buffer(self.vip_in_buf, VIP_BUFFER_OPER_TYPE_FLUSH)

            # Invoke NPU hardware
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
                out_raw = (ctypes.c_uint8 * buf_sz).from_address(out_ptr)
                out_uint8 = np.frombuffer(out_raw, dtype=np.uint8).copy()
                self.lib.vip_unmap_buffer(buf)

                # Dequantize to float32
                out_float = (out_uint8.astype(np.float32) - self.out_zps[i]) * self.out_scales[i]
                out_shaped = out_float.reshape(self.out_shapes[i])
                results.append(out_shaped)
            return results

        elif self.engine == 'mnn':
            if self.is_nchw and data.shape[-1] in (1, 3) and data.shape[1] not in (1, 3):
                data = np.transpose(data, (0, 3, 1, 2))

            data = np.ascontiguousarray(data, dtype=np.float32)
            cur_shape = tuple(self.input_tensor.getShape())
            if cur_shape != data.shape:
                self.interpreter.resizeTensor(self.input_tensor, tuple(data.shape))
                self.interpreter.resizeSession(self.session)
            tmp_t = self.MNN.Tensor(data.shape, self.MNN.Halide_Type_Float, data, self.MNN.Tensor_DimensionType_Caffe)
            self.input_tensor.copyFrom(tmp_t)
            self.interpreter.runSession(self.session)

            out_t = self.interpreter.getSessionOutput(self.session)
            host_t = self.MNN.Tensor(out_t.getShape(), self.MNN.Halide_Type_Float, np.zeros(out_t.getShape(), dtype=np.float32), self.MNN.Tensor_DimensionType_Caffe)
            out_t.copyToHostTensor(host_t)
            out = np.array(host_t.getData()).reshape(out_t.getShape())
            return [out]

    def release(self):
        if self.engine == 'vipcore':
            if hasattr(self, 'vip_in_buf') and self.vip_in_buf:
                self.lib.vip_destroy_buffer(self.vip_in_buf)
                self.vip_in_buf = None
            if hasattr(self, 'vip_out_bufs') and self.vip_out_bufs:
                for b in self.vip_out_bufs:
                    if b:
                        self.lib.vip_destroy_buffer(b)
                self.vip_out_bufs = []
                self.vip_out_buf = None
            elif hasattr(self, 'vip_out_buf') and self.vip_out_buf:
                self.lib.vip_destroy_buffer(self.vip_out_buf)
                self.vip_out_buf = None
            if hasattr(self, 'vip_net') and self.vip_net:
                self.lib.vip_destroy_network(self.vip_net)
                self.vip_net = None
            if hasattr(self, 'lib') and self.lib:
                self.lib.vip_destroy()
                self.lib = None
        elif self.engine == 'mnn':
            self.session = None
            self.interpreter = None

VIPCore_model_container = UnifiedModelContainer
