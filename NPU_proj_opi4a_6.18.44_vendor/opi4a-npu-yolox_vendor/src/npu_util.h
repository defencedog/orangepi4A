/****************************************************************************
*   npu_util header file
****************************************************************************/
#ifndef _NPU_UTIL_H_
#define _NPU_UTIL_H_


#include <stdint.h>

#ifdef __cplusplus
extern "C"{
#endif


#define CREATE_NETWORK_FROM_MEMORY  1
//#define CREATE_NETWORK_FROM_FLASH   1
//#define CREATE_NETWORK_FROM_FILE    1


#define MAX_SUPPORT_RUN_NETWORK   128

typedef enum _file_type_e
{
    NN_FILE_NONE,
    NN_FILE_JPG,
    NN_FILE_TENSOR,
    NN_FILE_BINARY,
    NN_FILE_TEXT
} file_type_e;

typedef struct
{
    vip_uint8_t* raw_addr;
} aligned_header;


vip_status_e vip_memset(vip_uint8_t *dst, vip_uint32_t size);
vip_status_e vip_memcpy(vip_uint8_t *dst, vip_uint8_t *src, vip_uint32_t size);


vip_uint8_t *malloc_aligned_buffer(
        vip_uint32_t mem_size,
        vip_uint32_t align_start_size,
        vip_uint32_t align_block_size);

void free_aligned_buffer(vip_uint8_t* handle);


unsigned int load_file_npu(const char *name, void *dst);
unsigned int save_file(const char *name, void *data, unsigned int size);

unsigned int get_file_size(const char *name);
file_type_e get_file_type(const char *file_name);

vip_uint32_t type_get_bytes(const vip_enum type);

unsigned char *get_binary_data(
    char *file_name,
    vip_uint32_t *file_size
    );

unsigned char *get_tensor_data(
    vip_network     network,
    char *file_name,
    vip_uint32_t *file_size,
    vip_uint32_t index
    );

int save_txt_file(
    void* buffer,
    unsigned int ele_size,
    signed int data_type,
    vip_int32_t quant_format,
    unsigned char fix_pos,
    vip_int32_t zeroPoint,
    vip_float_t scale,
    char *filename
    );

float int8_to_fp32(signed char val, signed char fixedPointPos);
float int16_to_fp32(vip_int16_t val, signed char fixedPointPos);
float uint8_to_fp32(vip_uint8_t val, vip_int32_t zeroPoint, vip_float_t scale);
float fp16_to_fp32(const short in);

vip_status_e integer_convert(
    const void * src,
    void *dest,
    vip_enum src_dtype,
    vip_enum dst_dtype
    );
vip_float_t affine_to_fp32(vip_int32_t val, vip_int32_t zeroPoint, vip_float_t scale);

#ifdef __cplusplus
}
#endif

#endif
