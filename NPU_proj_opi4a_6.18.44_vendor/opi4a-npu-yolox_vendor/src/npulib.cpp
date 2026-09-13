#include <vip_lite.h>
#include <stdio.h>
#include <stdint.h>
#include <memory.h>
#include <stdlib.h>
#include <string.h>
#if defined(__linux__)
#include <sys/time.h>
#endif

#ifdef __cplusplus
extern "C"{
#endif

#include "npu_util.h"
#include "npulib.h"


//#define MAX_SUPPORT_RUN_NETWORK   128
void *network_buffer[MAX_SUPPORT_RUN_NETWORK] = {VIP_NULL};

#ifdef LIBVIP_VERSION_85X
    #define USE_CREATE_BUFFER_FROM_HANDLE   0
#else
    #define USE_CREATE_BUFFER_FROM_HANDLE   1
#endif

#ifdef VPM_RUN_PROJECT
    #undef USE_CREATE_BUFFER_FROM_HANDLE
    #define USE_CREATE_BUFFER_FROM_HANDLE   0
#endif


#define GCVIP_ALIGN(n, align) \
    ( \
        ((n) + ((align) - 1)) & ~((align) - 1) \
    )


#if defined(__linux__)
#define TIME_SLOTS   10
static vip_uint64_t time_begin[TIME_SLOTS];
static vip_uint64_t time_end[TIME_SLOTS];
static vip_uint64_t GetTime()
{
    struct timeval time;
    gettimeofday(&time, NULL);
    return (vip_uint64_t)(time.tv_usec + time.tv_sec * 1000000);
}

static void TimeBegin(int id)
{
    time_begin[id] = GetTime();
}

static void TimeEnd(int id)
{
    time_end[id] = GetTime();
}

static vip_uint64_t TimeGet(int id)
{
    return time_end[id] - time_begin[id];
}
#endif


NpuUint::NpuUint(void)
{}

NpuUint::~NpuUint(void)
{
	npu_destroy();
	printf("~NpuUint. \n");
}

unsigned int NpuUint::get_driver_version(void)
{
	vip_uint32_t version = vip_get_version();
	return version;
}

int NpuUint::npu_init(unsigned int mem_size)
{
	int ret = 0;

    vip_status_e status = VIP_SUCCESS;

#ifdef LIBVIP_VERSION_85X
    if (mem_size == 0)
        mem_size = 30 * 1024 * 1024;    // default 30M
    status = vip_init(mem_size);
#else
    status = vip_init();
#endif

    if (status != VIP_SUCCESS) {
        printf("failed to init npu \n");
        ret = -10;	// need goto exit;
    }
    return ret;
}

int NpuUint::npu_destroy(void)
{
	vip_status_e status = vip_destroy();
    if (status != VIP_SUCCESS) {
        printf("fail to destory npu. \n");
    }
    else {
    	printf("destory npu finished. \n");
    }

    return (int)status;
}

NpuBuffer::NpuBuffer(void)
{
	m_buffer_obj = nullptr;
}

NpuBuffer::~NpuBuffer(void)
{
	if (m_buffer_obj != nullptr) {
		vip_destroy_buffer((vip_buffer)m_buffer_obj);
		m_buffer_obj = nullptr;
	}
}

void *NpuBuffer::create_buffer(unsigned int buffer_size)
{
    vip_status_e status = VIP_SUCCESS;
    vip_buffer_create_params_t param;

    memset(&param, 0, sizeof(param));
    param.memory_type = VIP_BUFFER_MEMORY_TYPE_DEFAULT;
    param.data_format = VIP_BUFFER_FORMAT_UINT8;
    param.num_of_dims = 1;
    param.sizes[0] = buffer_size;
    param.quant_format = VIP_BUFFER_QUANTIZE_NONE;

    /* Create a buffer */
    status = vip_create_buffer(&param, sizeof(param), (vip_buffer*)&m_buffer_obj);
    if (status != VIP_SUCCESS) {
        printf("fail to create memory pool buffer, status=%d\n", status);
        return nullptr;
    }

    return (void*)m_buffer_obj;
}


int NpuUint::query_hardware_info(void)
{
    vip_uint32_t version = vip_get_version();
    vip_uint32_t device_count = 0;
    vip_uint32_t cid = 0;
    vip_uint32_t *core_count = VIP_NULL;

    if (version >= 0x00010601) {
        vip_query_hardware(VIP_QUERY_HW_PROP_CID, sizeof(vip_uint32_t), &cid);
        vip_query_hardware(VIP_QUERY_HW_PROP_DEVICE_COUNT, sizeof(vip_uint32_t), &device_count);
        core_count = (vip_uint32_t*)malloc(sizeof(vip_uint32_t) * device_count);
        vip_query_hardware(VIP_QUERY_HW_PROP_CORE_COUNT_EACH_DEVICE,
                          sizeof(vip_uint32_t) * device_count, core_count);
//        printf("cid=0x%x, device_count=%d\n", cid, device_count);
//        for (int i = 0; i < device_count; i++) {
//            printf("  device[%d] core_count=%d\n", i, core_count[i]);
//        }
        free(core_count);
    }
    return VIP_SUCCESS;
}

NetworkItem::NetworkItem(void)
{
    m_nbg_name = 0;
    m_input_count = 0;
    m_output_count = 0;

    m_network = VIP_NULL;

    m_input_buffers = VIP_NULL;
    m_output_buffers = VIP_NULL;

    m_input_buffers_handle = VIP_NULL;
    m_output_buffers_handle = VIP_NULL;
}

NetworkItem::~NetworkItem(void)
{
    network_finish();
    network_destroy();
}


/* Create the network. */
int NetworkItem::network_create(char *model_file, unsigned int network_id)
{
    vip_status_e status = VIP_SUCCESS;
    char *file_name = VIP_NULL;
    int file_size = 0;
    int ret = 0;

    /* Load nbg data. */
    file_name = model_file;
    file_size = get_file_size((const char *) file_name);
    if (file_size <= 0) {
        printf("Network binary file %s can't be found.\n", file_name);
        status = VIP_ERROR_INVALID_ARGUMENTS;
        return status;
    }
    //printf("Network binary file %s, size: %d.\n", file_name, file_size);

#ifdef CREATE_NETWORK_FROM_MEMORY
    network_buffer[network_id] = malloc(file_size);
    load_file_npu(file_name, network_buffer[network_id]);

    #if defined (__linux__)
    TimeBegin(1);
    #endif

    status = vip_create_network(network_buffer[network_id], file_size, VIP_CREATE_NETWORK_FROM_MEMORY,
                                (vip_network*)&m_network);
    free(network_buffer[network_id]);
    network_buffer[network_id] = NULL;

#elif CREATE_NETWORK_FROM_FILE
    #if defined (__linux__)
    TimeBegin(1);
    #endif

    status = vip_create_network(file_name, 0, VIP_CREATE_NETWORK_FROM_FILE, (vip_network*)&m_network);
#endif
    if (status != VIP_SUCCESS) {
        printf("Network creating failed. Please validate the content of %s.\n", file_name);
        return status;
    }

    ret = network_create_io_buffer();
    if (ret != 0)
        return ret;

	#if defined (__linux__)
	TimeEnd(1);
	printf("nbg name=%s, size: %d. \n", file_name, file_size);
	printf("create network %d: %lu us.\n", network_id, (unsigned long)TimeGet(1));
	#endif

	return (int)status;
}


int NetworkItem::network_create_io_buffer(void)
{
    vip_status_e status = VIP_SUCCESS;
    int i = 0, k = 0;

    vip_buffer_create_params_t param;
    vip_uint32_t stride = 1;
    vip_uint32_t  input_size = 0;
    vip_uint32_t output_size = 0;

    vip_uint32_t version = vip_get_version();
    vip_uint32_t align = version <= 0x00020003 ? 64 : 256;

    /* Create input buffers. */
    vip_query_network((vip_network)m_network, VIP_NETWORK_PROP_INPUT_COUNT, &m_input_count);
    m_input_buffers = (npu_buffer *)malloc(sizeof(vip_buffer) * m_input_count);

#if USE_CREATE_BUFFER_FROM_HANDLE
    m_input_buffers_handle = (void**)malloc(sizeof(void *) * m_input_count);
#endif

    for (i = 0; i < m_input_count; i++) {
        unsigned int input_element = 1;
        vip_char_t name[256];
        memset(&param, 0, sizeof(param));
        param.memory_type = VIP_BUFFER_MEMORY_TYPE_DEFAULT;
        vip_query_input((vip_network)m_network, i, VIP_BUFFER_PROP_DATA_FORMAT, &param.data_format);
        vip_query_input((vip_network)m_network, i, VIP_BUFFER_PROP_NUM_OF_DIMENSION, &param.num_of_dims);
        vip_query_input((vip_network)m_network, i, VIP_BUFFER_PROP_SIZES_OF_DIMENSION, param.sizes);
        vip_query_input((vip_network)m_network, i, VIP_BUFFER_PROP_QUANT_FORMAT, &param.quant_format);
        vip_query_input((vip_network)m_network, i, VIP_BUFFER_PROP_NAME, name);
        switch(param.quant_format) {
            case VIP_BUFFER_QUANTIZE_DYNAMIC_FIXED_POINT:
                vip_query_input((vip_network)m_network, i, VIP_BUFFER_PROP_FIXED_POINT_POS,
                                &param.quant_data.dfp.fixed_point_pos);
                break;
            case VIP_BUFFER_QUANTIZE_TF_ASYMM:
                vip_query_input((vip_network)m_network, i, VIP_BUFFER_PROP_TF_SCALE,
                                &param.quant_data.affine.scale);
                vip_query_input((vip_network)m_network, i, VIP_BUFFER_PROP_TF_ZERO_POINT,
                                &param.quant_data.affine.zeroPoint);
                break;
            default:
                break;
        }

        printf("input  %d dim %d %d %d %d, data_format=%d, quant_format=%d, name=%s",
               i, param.sizes[0], param.sizes[1], param.sizes[2], param.sizes[3],
               param.data_format, param.quant_format, name);

        switch(param.quant_format) {
            case VIP_BUFFER_QUANTIZE_DYNAMIC_FIXED_POINT:
                printf(", dfp=%d\n", param.quant_data.dfp.fixed_point_pos);
                break;
            case VIP_BUFFER_QUANTIZE_TF_ASYMM:
                printf(", scale=%f, zero_point=%d\n", param.quant_data.affine.scale,
                       param.quant_data.affine.zeroPoint);
                break;
            default:
                printf(", none-quant\n");
        }

#if USE_CREATE_BUFFER_FROM_HANDLE
        stride = type_get_bytes(param.data_format);
        for (k = 0; k < param.num_of_dims; k++) {
            input_element *= param.sizes[k];
        }

        input_size = input_element * stride;
        input_size = GCVIP_ALIGN(input_size, align);
        void *ptr = (void*)malloc_aligned_buffer(input_size, align, align);
        m_input_buffers_handle[i] = ptr;

        param.memory_type = VIP_BUFFER_MEMORY_TYPE_HOST;
        status = vip_create_buffer_from_handle(&param, ptr, input_size, (vip_buffer*)&m_input_buffers[i]);

#else
        status = vip_create_buffer(&param, sizeof(param), (vip_buffer*)&m_input_buffers[i]);
#endif
        if (status != VIP_SUCCESS) {
            printf("fail to create input %d buffer, status=%d\n", i, status);
            return status;
        }
    }


    /* Create output buffer. */
    vip_query_network((vip_network)m_network, VIP_NETWORK_PROP_OUTPUT_COUNT, &m_output_count);
    m_output_buffers = (npu_buffer *)malloc(sizeof(vip_buffer) * m_output_count);

#if USE_CREATE_BUFFER_FROM_HANDLE
    m_output_buffers_handle = (void**)malloc(sizeof(void *) * m_output_count);
#endif

    for (i = 0; i < m_output_count; i++) {
        unsigned int output_element = 1;
        vip_char_t name[256];
        memset(&param, 0, sizeof(param));
        param.memory_type = VIP_BUFFER_MEMORY_TYPE_DEFAULT;
        vip_query_output((vip_network)m_network, i, VIP_BUFFER_PROP_DATA_FORMAT, &param.data_format);
        vip_query_output((vip_network)m_network, i, VIP_BUFFER_PROP_NUM_OF_DIMENSION, &param.num_of_dims);
        vip_query_output((vip_network)m_network, i, VIP_BUFFER_PROP_SIZES_OF_DIMENSION, param.sizes);
        vip_query_output((vip_network)m_network, i, VIP_BUFFER_PROP_QUANT_FORMAT, &param.quant_format);
        vip_query_output((vip_network)m_network, i, VIP_BUFFER_PROP_NAME, name);
        switch(param.quant_format) {
            case VIP_BUFFER_QUANTIZE_DYNAMIC_FIXED_POINT:
                vip_query_output((vip_network)m_network, i, VIP_BUFFER_PROP_FIXED_POINT_POS,
                                 &param.quant_data.dfp.fixed_point_pos);
                break;
            case VIP_BUFFER_QUANTIZE_TF_ASYMM:
                vip_query_output((vip_network)m_network, i, VIP_BUFFER_PROP_TF_SCALE,
                                 &param.quant_data.affine.scale);
                vip_query_output((vip_network)m_network, i, VIP_BUFFER_PROP_TF_ZERO_POINT,
                                 &param.quant_data.affine.zeroPoint);
                break;
            default:
                break;
        }

        printf("output %d dim %d %d %d %d, data_format=%d, name=%s",
               i, param.sizes[0], param.sizes[1], param.sizes[2], param.sizes[3],
               param.data_format, name);

        switch(param.quant_format) {
            case VIP_BUFFER_QUANTIZE_DYNAMIC_FIXED_POINT:
                printf(", dfp=%d\n", param.quant_data.dfp.fixed_point_pos);
                break;
            case VIP_BUFFER_QUANTIZE_TF_ASYMM:
                printf(", scale=%f, zero_point=%d\n", param.quant_data.affine.scale,
                       param.quant_data.affine.zeroPoint);
                break;
            default:
                printf(", none-quant\n");
        }

        for (k = 0; k < param.num_of_dims; k++) {
            output_element *= param.sizes[k];
        }

        if (i < MAX_NETWORK_OUTPUT)
            m_output_data_len[i] = output_element;

#if USE_CREATE_BUFFER_FROM_HANDLE
        stride = type_get_bytes(param.data_format);
        output_size = output_element * stride;
        output_size = GCVIP_ALIGN(output_size, align);
        void *ptr = (void*)malloc_aligned_buffer(output_size, align, align);
        m_output_buffers_handle[i] = ptr;

        param.memory_type = VIP_BUFFER_MEMORY_TYPE_HOST;
        status = vip_create_buffer_from_handle(&param, ptr, output_size, (vip_buffer*)&m_output_buffers[i]);
#else
        status = vip_create_buffer(&param, sizeof(param), (vip_buffer*)&m_output_buffers[i]);
#endif

        if (status != VIP_SUCCESS) {
            printf("fail to create output %d buffer, status=%d\n", i, status);
            return (int)status;
        }
    }

    return 0;
}

unsigned int NetworkItem::get_memory_pool_size(void)
{
    unsigned int mem_pool_size = 0;

    if (m_network == VIP_NULL) {
        printf("m_network is NULL. \n");
        return 0;
    }

    vip_query_network((vip_network)m_network, VIP_NETWORK_PROP_MEMORY_POOL_SIZE, &mem_pool_size);

    return mem_pool_size;
}

int NetworkItem::set_memory_pool_buffer(void *memory_pool_buffer_ptr)
{
    vip_status_e status = VIP_SUCCESS;

    if (m_network == VIP_NULL) {
        printf("m_network is NULL. \n");
        return -1;
    }

    /* Specify the memory pool buffer m_memory_pool_buffer for network. */
    status = vip_set_network((vip_network)m_network, VIP_NETWORK_PROP_SET_MEMORY_POOL, (vip_buffer)(memory_pool_buffer_ptr));
    if (status != VIP_SUCCESS) {
        printf("set memory_pool_buffer fail.\n");
        return -1;
    }

    return 0;
}

// only use in multi_thread demo
int NetworkItem::set_priority(unsigned char priority)
{
    vip_status_e status = VIP_SUCCESS;

   if (m_network == VIP_NULL) {
       printf("m_network is NULL. \n");
       return -1;
   }

   /* set priority of network. 0 ~ 255, 0 indicates the lowest priority. */
   status = vip_set_network((vip_network)m_network, VIP_NETWORK_PROP_SET_PRIORITY, &priority);
   if (status != VIP_SUCCESS) {
       printf("set priority %d fail.\n", priority);
       return -1;
   }

    return 0;
}

int NetworkItem::network_prepare(void)
{
	vip_status_e status = VIP_SUCCESS;

    #if defined (__linux__)
    TimeBegin(2);
    #endif

	status = vip_prepare_network((vip_network)m_network);

	#if defined (__linux__)
    TimeEnd(2);
    printf("prepare network: %lu us.\n", (unsigned long) TimeGet(2));
    #endif

	return (int)status;
}

/* set input/output buffer */
int NetworkItem::network_input_output_set(void)
{
    vip_status_e status = VIP_SUCCESS;
    int i = 0;

    for (i = 0; i < m_input_count; i++) {
        /* Set input. */
        status = vip_set_input((vip_network)m_network, i, (vip_buffer)m_input_buffers[i]);
        if (status != VIP_SUCCESS) {
            printf("fail to set input %d\n", i);
            goto ExitFunc;
        }
    }

    for (i = 0; i < m_output_count; i++) {
        if (m_output_buffers[i] != VIP_NULL) {
            status = vip_set_output((vip_network)m_network, i, (vip_buffer)m_output_buffers[i]);
            if (status != VIP_SUCCESS) {
                printf("fail to set output\n");
                goto ExitFunc;
            }
        }
        else {
            printf("fail output %d is null. m_output_counts=%d\n", i, m_output_count);
            status = VIP_ERROR_FAILURE;
            goto ExitFunc;
        }
    }

ExitFunc:
    return (int)status;
}


int NetworkItem::get_network_input_buff_info(int buff_idx, void **input_buff_ptr, unsigned int *buff_size)
{
    int i = buff_idx;

    if (buff_idx >= m_input_count) {
        printf("buff_idx error, buff_idx(%d) >= m_input_count(%d).\n", buff_idx, m_input_count);
        return -1;
    }

    /* get input buffer ptr and size. */
    *input_buff_ptr = vip_map_buffer((vip_buffer)m_input_buffers[i]);
    *buff_size = vip_get_buffer_size((vip_buffer)m_input_buffers[i]);
    vip_unmap_buffer((vip_buffer)m_input_buffers[i]);

    return 0;
}

int NetworkItem::get_network_output_buff_info(int buff_idx, void **output_buff_ptr, unsigned int *buff_size)
{
    int i = buff_idx;

    if (buff_idx >= m_output_count) {
        printf("buff_idx error, buff_idx(%d) >= m_output_count(%d).\n", buff_idx, m_output_count);
        return -1;
    }

    /* get output buffer ptr and size. */
    *output_buff_ptr = vip_map_buffer((vip_buffer)m_output_buffers[i]);
    *buff_size = vip_get_buffer_size((vip_buffer)m_output_buffers[i]);
    vip_unmap_buffer((vip_buffer)m_output_buffers[i]);

    return 0;
}


int NetworkItem::network_load_input_file(char **input_path)
{
    vip_status_e status = VIP_SUCCESS;
    char *file_name;

    /* Load input buffer data. */
    printf("input_count: %d \n", m_input_count);
    for (int i = 0; i < m_input_count; i++) {

        file_name = input_path[i];

        network_load_input_file_idx(file_name, i);
    }

    return status;
}

int NetworkItem::network_load_input_file_idx(char *input_path, int input_idx)
{
    vip_status_e status = VIP_SUCCESS;
    void *data;
    void *file_data = VIP_NULL;
    char *file_name;
    vip_uint32_t file_size;
    vip_uint32_t buff_size;
    int i = input_idx;


    if (input_idx >= m_input_count) {
        printf("input_idx error, input_idx(%d) >= m_input_count(%d).\n", input_idx, m_input_count);
        return -1;
    }

    /* Load input buffer data. */
	file_type_e file_type;
	file_name = input_path;
	printf("input %d name: %s\n", i , file_name);
	file_type = get_file_type(file_name);

	switch(file_type)
	{
		case NN_FILE_JPG:
			//file_data = (void *)image_preprocess(file_name, &file_size);
			break;
		case NN_FILE_TENSOR:
			file_data = (void *)get_tensor_data((vip_network)m_network, file_name, &file_size, i);
			break;
		case NN_FILE_BINARY:
			file_data = (void *)get_binary_data(file_name, &file_size);
			break;
		case NN_FILE_TEXT:
			file_data = (void *)get_tensor_data((vip_network)m_network, file_name, &file_size, i);
			break;
		default:
			printf("error input file type\n");
			break;
	}

	data = vip_map_buffer((vip_buffer)m_input_buffers[i]);
	buff_size = vip_get_buffer_size((vip_buffer)m_input_buffers[i]);
	vip_memcpy((unsigned char *)data, (unsigned char *)file_data, buff_size > file_size ? file_size : buff_size);
	vip_unmap_buffer((vip_buffer)m_input_buffers[i]);

	if (file_data != VIP_NULL) {
		free(file_data);
		file_data = VIP_NULL;
	}

    return status;
}

int NetworkItem::network_load_input_buffer(void *input_data, unsigned int input_size)
{
    vip_status_e status = VIP_SUCCESS;
    void *data;

    vip_uint32_t buff_size;
    int i = 0;

    /* Load input buffer data. */
	data = vip_map_buffer((vip_buffer)m_input_buffers[i]);
	buff_size = vip_get_buffer_size((vip_buffer)m_input_buffers[i]);
	vip_memcpy((unsigned char *)data, (unsigned char *)input_data, buff_size > input_size ? input_size : buff_size);
	vip_unmap_buffer((vip_buffer)m_input_buffers[i]);

    return status;
}

int NetworkItem::network_load_input_buffer_idx(void *input_data, unsigned int input_size, int input_idx)
{
    vip_status_e status = VIP_SUCCESS;
    void *data;

    vip_uint32_t buff_size;
    int i = input_idx;

    if (input_idx >= m_input_count) {
        printf("input_idx error, input_idx(%d) >= m_input_count(%d).\n", input_idx, m_input_count);
        return -1;
    }

    /* Load input buffer data. */
    data = vip_map_buffer((vip_buffer)m_input_buffers[i]);
    buff_size = vip_get_buffer_size((vip_buffer)m_input_buffers[i]);
    vip_memcpy((unsigned char *)data, (unsigned char *)input_data, buff_size > input_size ? input_size : buff_size);
    vip_unmap_buffer((vip_buffer)m_input_buffers[i]);

    return status;
}

int NetworkItem::network_load_input_yuv_buffer(void *yuv_data, int w, int h)
{
    vip_status_e status = VIP_SUCCESS;
    void *data;

    vip_uint32_t buff_size;
    int i = 0;

    int input_size = w * h;
    unsigned char *y_data = (unsigned char *)yuv_data;
    unsigned char *uv_data = (unsigned char *)yuv_data + input_size;

    /* Load input y buffer data. */
	data = vip_map_buffer((vip_buffer)m_input_buffers[i]);
	buff_size = vip_get_buffer_size((vip_buffer)m_input_buffers[i]);
	vip_memcpy((unsigned char *)data, y_data, buff_size > input_size ? input_size : buff_size);
	vip_unmap_buffer((vip_buffer)m_input_buffers[i]);


	i++;

	// uv buffer
	input_size =  w * h / 2;
	data = vip_map_buffer((vip_buffer)m_input_buffers[i]);
	buff_size = vip_get_buffer_size((vip_buffer)m_input_buffers[i]);
	vip_memcpy((unsigned char *)data, uv_data, buff_size > input_size ? input_size : buff_size);
	vip_unmap_buffer((vip_buffer)m_input_buffers[i]);

    return status;
}

int NetworkItem::network_load_input_yuv_file(char **input_path, int w, int h)
{
    vip_status_e status = VIP_SUCCESS;
    void *data;
    void *yuv_data = VIP_NULL;
    char *file_name;
    vip_uint32_t file_size;
    int i = 0;

    /* Load input buffer data. */
    file_name = input_path[i];
    printf("input %d name: %s\n", i , file_name);


    yuv_data = (void *)get_binary_data(file_name, &file_size);

    if (file_size != w * h * 3/2) {
        printf("yuv file is not yuv420(nv12 or nv21) \n");
    }

    network_load_input_yuv_buffer(yuv_data, w, h);

    if (yuv_data != VIP_NULL) {
        free(yuv_data);
        yuv_data = VIP_NULL;
    }

    return status;
}

int NetworkItem::network_run(void)
{
	vip_int32_t ret = 0;
	vip_status_e status = VIP_SUCCESS;

	for (int k = 0; k < m_input_count; k++) {
		if ((vip_flush_buffer((vip_buffer)m_input_buffers[k], VIP_BUFFER_OPER_TYPE_FLUSH)) != VIP_SUCCESS) {
			printf("flush input%d cache failed.\n", k);
		}
	}

	status = vip_run_network((vip_network)m_network);
	if (status != VIP_SUCCESS) {
		if (status == VIP_ERROR_CANCELED) {
			printf("network is canceled.\n");
			ret = VIP_ERROR_CANCELED;
		}
		else {
            printf("fail to run network, status=%d \n", status);
            ret = -1;
		}
	}

	for (int k = 0; k < m_output_count; k++) {
		if ((vip_flush_buffer((vip_buffer)m_output_buffers[k], VIP_BUFFER_OPER_TYPE_INVALIDATE)) != VIP_SUCCESS){
			printf("flush output%d cache failed.\n", k);
		}
	}

	return ret;
}

float** NetworkItem::get_output(float **output_float, save_file_type_e save_type)
{
	char out_name[255] = {'\0'};
	void *out_data = VIP_NULL;
	vip_int32_t j = 0;
	vip_uint32_t k = 0;
	vip_int32_t data_format = 0;
	vip_uint32_t stride = 1;
	vip_int32_t output_fp  = 0;
	vip_int32_t quant_format = 0;
	vip_int32_t m_output_counts = 0;
	vip_uint32_t output_size = 0;
	vip_int32_t zeroPoint = 0;
	vip_float_t scale = 1.0f;
	vip_buffer_create_params_t param;

	//float **output_float = NULL;

	m_output_counts = m_output_count;
	if (output_float == NULL) {
		output_float = (float **)calloc(m_output_counts, sizeof(float *));

		if (output_float == NULL) {
			printf("calloc buffer fail \n");
			return NULL;
		}
	}

	for (j = 0; j < m_output_counts; j++) {
		unsigned int output_element = 1;
		memset(&param, 0, sizeof(param));
		vip_query_output((vip_network)m_network, j, VIP_BUFFER_PROP_QUANT_FORMAT, &quant_format);
		vip_query_output((vip_network)m_network, j, VIP_BUFFER_PROP_TF_SCALE,
						 &param.quant_data.affine.scale);
		scale = param.quant_data.affine.scale;
		vip_query_output((vip_network)m_network, j, VIP_BUFFER_PROP_TF_ZERO_POINT,
						   &param.quant_data.affine.zeroPoint);
		zeroPoint = param.quant_data.affine.zeroPoint;
		vip_query_output((vip_network)m_network, j, VIP_BUFFER_PROP_DATA_FORMAT,
						 &param.data_format);
		data_format = param.data_format;
		stride = type_get_bytes(data_format);
		vip_query_output((vip_network)m_network, j, VIP_BUFFER_PROP_FIXED_POINT_POS,
						 &param.quant_data.dfp.fixed_point_pos);
		output_fp = param.quant_data.dfp.fixed_point_pos;

		output_element = m_output_data_len[j];
		output_size = output_element * stride;

		out_data = vip_map_buffer((vip_buffer)m_output_buffers[j]);

#if 1
        if (save_type == SAVE_BINARY) {
            /* save output to binary file */
            sprintf(out_name, "output_%d.bin", j);
            save_file(out_name, out_data, output_size);
        }
        else if (save_type == SAVE_TEXT) {
            /* save output to .txt file */
            char output_txt_filename[255] = {'\0'};
            sprintf(output_txt_filename, "output_%d.txt", j);
            save_txt_file(out_data, output_element, data_format, quant_format, output_fp, zeroPoint, scale, output_txt_filename);
		}
        else {}
#endif

		//calloc
		if (output_float[j] == NULL) {
		    //printf("calloc output buffer %d, size: %d. \n", j, output_element);
			output_float[j] = (float*)calloc(output_element, sizeof(float));

			if (output_float[j] == NULL) {
				printf("calloc output buffer fail, output_buffer size: %d. \n", output_element);
				return NULL;
			}
		}

		if (data_format == VIP_BUFFER_FORMAT_FP32) {
			memcpy(output_float[j], out_data, output_size);
		}
		else {
			float fp_data = 0.0;
			vip_uint8_t *data = (vip_uint8_t*)out_data;
			for (int i = 0; i < output_element; i++) {
				if (data_format == VIP_BUFFER_FORMAT_INT8) {
					if (quant_format == VIP_BUFFER_QUANTIZE_DYNAMIC_FIXED_POINT) {
                        fp_data = int8_to_fp32(*data, output_fp);
                    }
                    else if (quant_format == VIP_BUFFER_QUANTIZE_TF_ASYMM) {
                        vip_int32_t src_value = 0;
                        integer_convert(data, &src_value, VIP_BUFFER_FORMAT_INT8, VIP_BUFFER_FORMAT_INT32);
                        fp_data = affine_to_fp32(src_value, zeroPoint, scale);
                    }
                    else {
                        fp_data = *((float*)data);
                    }
				}
				else if (data_format == VIP_BUFFER_FORMAT_FP16) {
					fp_data = fp16_to_fp32(*((short *)data));
				}
				else if (data_format == VIP_BUFFER_FORMAT_UINT8) {
					fp_data = uint8_to_fp32(*data, zeroPoint, scale);
				}
				else if (data_format == VIP_BUFFER_FORMAT_INT16) {
					fp_data = int16_to_fp32(*((short *)data), output_fp);
				}
				else if (data_format == VIP_BUFFER_FORMAT_FP32) {
					fp_data = *((float*)data);
				}
				else if (data_format == VIP_BUFFER_FORMAT_INT32) {
                    if (quant_format == VIP_BUFFER_QUANTIZE_NONE) {
                        fp_data = (float)(*((int*)data));
                    }
                }
				else {
					printf("not support this format %d.\n", data_format);
					break;
				}

				output_float[j][i] = fp_data;	//save
				data += stride;
			}
		}

		vip_unmap_buffer((vip_buffer)m_output_buffers[j]);
	}

	return output_float;
}

/*
 * get output buffer ptr
 * if NPU network_run and CPU output postprocess in different threads, please use thread mutex.
 * */
void NetworkItem::get_output_fp_nocopy(output_info_s *outputs_info, save_file_type_e save_type)
{
    char out_name[255] = {'\0'};
    void *out_data = VIP_NULL;
    vip_int32_t j = 0;
    vip_uint32_t k = 0;
    vip_int32_t data_format = 0;
    vip_uint32_t stride = 1;
    vip_int32_t output_fp  = 0;
    vip_int32_t quant_format = 0;
    vip_int32_t m_output_counts = 0;
    vip_uint32_t output_size = 0;
    vip_int32_t zeroPoint = 0;
    vip_float_t scale = 1.0f;
    vip_buffer_create_params_t param;

    m_output_counts = m_output_count;

    if (outputs_info == NULL) {
        printf("outputs_info ptr is null, please check code. \n");
    }

    for (j = 0; j < m_output_counts; j++) {
        unsigned int output_element = 1;
        memset(&param, 0, sizeof(param));
        vip_query_output((vip_network)m_network, j, VIP_BUFFER_PROP_QUANT_FORMAT, &quant_format);
        vip_query_output((vip_network)m_network, j, VIP_BUFFER_PROP_TF_SCALE,
                         &param.quant_data.affine.scale);
        scale = param.quant_data.affine.scale;
        vip_query_output((vip_network)m_network, j, VIP_BUFFER_PROP_TF_ZERO_POINT,
                           &param.quant_data.affine.zeroPoint);
        zeroPoint = param.quant_data.affine.zeroPoint;
        vip_query_output((vip_network)m_network, j, VIP_BUFFER_PROP_DATA_FORMAT,
                         &param.data_format);
        data_format = param.data_format;
        stride = type_get_bytes(data_format);

        vip_query_output((vip_network)m_network, j, VIP_BUFFER_PROP_FIXED_POINT_POS,
                         &param.quant_data.dfp.fixed_point_pos);
        output_fp = param.quant_data.dfp.fixed_point_pos;

        output_element = m_output_data_len[j];
        output_size = output_element * stride;

        out_data = vip_map_buffer((vip_buffer)m_output_buffers[j]);

        if (save_type == SAVE_BINARY) {
            /* save output to binary file */
            sprintf(out_name, "output_%d.bin", j);
            save_file(out_name, out_data, output_size);
        }
        else if (save_type == SAVE_TEXT) {
            /* save output to .txt file */
            char output_txt_filename[255] = {'\0'};
            sprintf(output_txt_filename, "output_%d.txt", j);
            save_txt_file(out_data, output_element, data_format, quant_format, output_fp, zeroPoint, scale, output_txt_filename);
        }
        else {}

        if (data_format == VIP_BUFFER_FORMAT_FP32) {
            /* memcpy(output_float[j], out_data, output_size); */

            outputs_info[j].ptr = (float*)out_data;
            outputs_info[j].length = output_element;
        }
        else {
            printf("not support this format %d, please use get_output() .\n", data_format);
            break;
        }

        vip_unmap_buffer((vip_buffer)m_output_buffers[j]);
    }

    return ;
}

char* NetworkItem::get_ngb_name(void)
{
//	return base_strings[nbg_name];
    return nullptr;
}

int NetworkItem::get_output_cnt(void)
{
	return m_output_count;
}

void NetworkItem::network_finish(void)
{
    if (m_network != VIP_NULL)
        vip_finish_network((vip_network)m_network);
}

void NetworkItem::network_destroy(void)
{
    int i = 0;

    if (m_network != VIP_NULL)
        vip_destroy_network((vip_network)m_network);
    m_network = VIP_NULL;

    for (i = 0; i < m_input_count; i++) {
        if (m_input_buffers[i] != VIP_NULL)
            vip_destroy_buffer((vip_buffer)m_input_buffers[i]);
    }
    if (m_input_buffers != VIP_NULL)
        free(m_input_buffers);
    m_input_buffers = VIP_NULL;

#if USE_CREATE_BUFFER_FROM_HANDLE
    for (i = 0; i < m_input_count; i++) {
        if (m_input_buffers_handle[i] != VIP_NULL)
            free_aligned_buffer((uint8_t*)m_input_buffers_handle[i]);
    }

    if (m_input_buffers_handle != VIP_NULL)
        free(m_input_buffers_handle);
    m_input_buffers_handle = VIP_NULL;
#endif

    m_input_count = 0;


    for (i = 0; i < m_output_count; i++) {
        if (m_output_buffers[i] != VIP_NULL)
            vip_destroy_buffer((vip_buffer)m_output_buffers[i]);
    }
    if (m_output_buffers != VIP_NULL)
        free(m_output_buffers);
    m_output_buffers = VIP_NULL;

#if USE_CREATE_BUFFER_FROM_HANDLE
    for (i = 0; i < m_output_count; i++) {
        if (m_output_buffers_handle[i] != VIP_NULL)
            free_aligned_buffer((uint8_t*)m_output_buffers_handle[i]);
    }

    if (m_output_buffers_handle != VIP_NULL)
        free(m_output_buffers_handle);
    m_output_buffers_handle = VIP_NULL;
#endif

    m_output_count = 0;
}

#ifdef __cplusplus
}
#endif
