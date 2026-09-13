#include <vip_lite.h>
#include <stdio.h>
#include <stdint.h>
#include <memory.h>
#include <stdlib.h>
#include <string.h>


#ifdef __cplusplus
extern "C"{
#endif

#include "npu_util.h"


#define MAX_DIMENSION_NUMBER    4
#define MAX_INPUT_OUTPUT_NUM    20
#define MATH_ABS(x)      (((x) < 0)    ? -(x) :  (x))
#define MATH_MAX(a,b)    (((a) > (b)) ? (a) : (b))
#define MATH_MIN(a,b)    (((a) < (b)) ? (a) : (b))



vip_status_e vip_memset(vip_uint8_t *dst, vip_uint32_t size)
{
    vip_status_e status = VIP_SUCCESS;
#if 0
    vip_uint32_t i = 0;
    for (i = 0; i < size; i++) {
        dst[i] = 0;
    }
#else
    memset(dst, 0, size);
#endif
    return status;
}

vip_status_e vip_memcpy(vip_uint8_t *dst, vip_uint8_t *src, vip_uint32_t size)
{
    vip_status_e status = VIP_SUCCESS;
#if 0
    vip_uint32_t i = 0;
    for (i = 0; i < size; i++) {
        dst[i] = src[i];
    }
#else
    memcpy(dst, src, size);
#endif
    return status;
}

vip_uint8_t * malloc_aligned_buffer
    (
    vip_uint32_t mem_size,
    vip_uint32_t align_start_size,
    vip_uint32_t align_block_size
    )
{
    vip_uint32_t sz;
    long temp;
    vip_uint8_t* raw_addr;
    vip_uint8_t* p;
    vip_uint8_t* align_addr;
    aligned_header* header;

    sz = sizeof(aligned_header) + mem_size + align_start_size + align_block_size;
    raw_addr = (vip_uint8_t *)malloc(sz * sizeof(vip_uint8_t ) );
    memset(raw_addr, 0, sizeof(vip_uint8_t ) * sz);
    p = raw_addr + sizeof(aligned_header);

    temp = (long)(p) % align_start_size;
    if (temp == 0)
    {
        align_addr = p;
    }
    else
    {
        align_addr = p + align_start_size - temp;
    }
    header = (aligned_header*)(align_addr - sizeof(aligned_header));
    header->raw_addr = raw_addr;

    return align_addr;
}/* malloc_aligned_buffer() */

void free_aligned_buffer(vip_uint8_t* handle)
{
    aligned_header* header;
    header = (aligned_header*)(handle - sizeof(aligned_header));
    free(header->raw_addr);
}


unsigned int load_file_npu(const char *name, void *dst)
{
    FILE *fp = fopen(name, "rb");
    unsigned int size = 0;

    if (fp != NULL) {
        fseek(fp, 0, SEEK_END);
        size = ftell(fp);

        fseek(fp, 0, SEEK_SET);
        size = fread(dst, size, 1, fp);

        fclose(fp);
    }

    return size;
}

unsigned int save_file(const char *name, void *data, unsigned int size)
{
    FILE *fp = fopen(name, "wb+");
    unsigned int saved = 0;

    if (fp != NULL) {
        saved = fwrite(data, size, 1, fp);

        fclose(fp);
    }
    else {
        printf("Saving file %s failed.\n", name);
    }

    return saved;
}

unsigned int get_file_size(const char *name)
{
    FILE    *fp = fopen(name, "rb");
    unsigned int size = 0;

    if (fp != NULL) {
        fseek(fp, 0, SEEK_END);
        size = ftell(fp);

        fclose(fp);
    }
    else {
        printf("Checking file %s failed.\n", name);
    }

    return size;
}

file_type_e get_file_type(const char *file_name)
{
	file_type_e type = NN_FILE_NONE;
    const char *ptr;
    char sep = '.';
    unsigned int pos,n;
    char buff[32] = {0};

    ptr = strrchr(file_name, sep);
    pos = ptr - file_name;
    n = strlen(file_name) - (pos + 1);
    strncpy(buff, file_name+(pos+1), n);

    if(strcmp(buff, "jpg") == 0
            || strcmp(buff, "jpeg") == 0
            || strcmp(buff, "JPG") == 0
            || strcmp(buff, "JPEG") == 0 )
	{
		type = NN_FILE_JPG;
	}
	else if (strcmp(buff, "tensor") == 0) {
        type = NN_FILE_TENSOR;
    }
    else if(strcmp(buff, "dat") == 0 || !strcmp(buff, "bin"))
    {
        type = NN_FILE_BINARY;
    }
    else if(strcmp(buff, "txt") == 0)
    {
        type = NN_FILE_TEXT;
    }
    else {
        printf("unsupported input file type=%s.\n", buff);
    }

    return type;
}

vip_uint32_t type_get_bytes(const vip_enum type)
{
    switch(type)
    {
        case VIP_BUFFER_FORMAT_INT8:
        case VIP_BUFFER_FORMAT_UINT8:
        case VIP_BUFFER_FORMAT_BOOL8:
            return 1;
        case VIP_BUFFER_FORMAT_INT16:
        case VIP_BUFFER_FORMAT_UINT16:
        case VIP_BUFFER_FORMAT_FP16:
        case VIP_BUFFER_FORMAT_BFP16:
            return 2;
        case VIP_BUFFER_FORMAT_FP32:
        case VIP_BUFFER_FORMAT_INT32:
        case VIP_BUFFER_FORMAT_UINT32:
            return 4;
        case VIP_BUFFER_FORMAT_FP64:
        case VIP_BUFFER_FORMAT_INT64:
        case VIP_BUFFER_FORMAT_UINT64:
            return 8;

        default:
            return 0;
    }
}

 vip_uint32_t get_tensor_size(
    vip_int32_t *shape,
    vip_uint32_t dim_num,
    vip_enum type
    )
{
    vip_uint32_t sz;
    vip_uint32_t i;
    sz = 0;
    if(NULL == shape || 0 == dim_num)
    {
        return sz;
    }
    sz = 1;
    for(i = 0; i < dim_num; i ++)
    {
        sz *= shape[i];
    }
    sz *= type_get_bytes(type);

    return sz;
}

vip_uint32_t get_element_num(
    vip_int32_t *sizes,
    vip_uint32_t num_of_dims,
    vip_enum data_format
    )
{
    vip_uint32_t num;
    vip_uint32_t sz;
    vip_uint32_t dsize;

    sz = get_tensor_size(sizes, num_of_dims, data_format);
    dsize = type_get_bytes(data_format);
    num = (vip_uint32_t)(sz / dsize);

    return num;
}

vip_int32_t type_is_integer(const vip_enum type)
{
    vip_int32_t ret;
    ret = 0;
    switch(type)
    {
    case VIP_BUFFER_FORMAT_INT8:
    case VIP_BUFFER_FORMAT_INT16:
    case VIP_BUFFER_FORMAT_INT32:
    case VIP_BUFFER_FORMAT_UINT8:
    case VIP_BUFFER_FORMAT_UINT16:
    case VIP_BUFFER_FORMAT_UINT32:
    case VIP_BUFFER_FORMAT_BOOL8:
        ret = 1;
        break;
    default:
        break;
    }

    return ret;
}

vip_int32_t type_is_signed(const vip_enum type)
{
    vip_int32_t ret;
    ret = 0;
    switch(type)
    {
    case VIP_BUFFER_FORMAT_INT8:
    case VIP_BUFFER_FORMAT_INT16:
    case VIP_BUFFER_FORMAT_INT32:
    case VIP_BUFFER_FORMAT_BFP16:
    case VIP_BUFFER_FORMAT_FP16:
    case VIP_BUFFER_FORMAT_FP32:
        ret = 1;
        break;
    default:
        break;
    }

    return ret;
}

void type_get_range(vip_enum type, double *max_range, double * min_range)
{
    vip_int32_t bits;
    double from, to;
    from = 0.0;
    to = 0.0;
    bits = type_get_bytes(type) * 8;
    if(type_is_integer(type)) {
        if(type_is_signed(type)) {
            from = (double)(-(1L << (bits - 1)));
            to = (double)((1UL << (bits - 1)) - 1);
        }
        else {
            from = 0.0;
            to = (double)((1UL << bits) - 1);
        }
    }
    else {
        //  TODO: Add float
    }
    if(NULL != max_range) {
        *max_range = to;
    }
    if(NULL != min_range) {
        *min_range = from;
    }
}

double copy_sign(double number, double sign)
{
    double value = MATH_ABS(number);
    return (sign > 0) ? value : (-value);
}

int math_floorf(double x)
{
    if (x >= 0)
    {
        return (int)x;
    }
    else
    {
        return (int)x - 1;
    }
}

double rint(double x)
{
#define _EPSILON 1e-8
    double decimal;
    double inter;
    int intpart;

    intpart = (int)x;
    decimal = x - intpart;
    inter = (double)intpart;

    if(MATH_ABS((MATH_ABS(decimal) - 0.5f)) < _EPSILON )
    {
        inter += (vip_int32_t)(inter) % 2;
    }
    else
    {
        return copy_sign(math_floorf(MATH_ABS(x) + 0.5f), x);
    }

    return inter;
}

vip_int32_t fp32_to_dfp(const float in,  const signed char fl, const vip_enum type)
{
    vip_int32_t data;
    double max_range;
    double min_range;
    type_get_range(type, &max_range, &min_range);
    if(fl > 0 )
    {
        data = (vip_int32_t)rint(in * (float)(1 << fl ));
    }
    else
    {
        data = (vip_int32_t)rint(in * (1.0f / (float)(1 << -fl )));
    }
    data = MATH_MIN(data, (vip_int32_t)max_range);
    data = MATH_MAX(data, (vip_int32_t)min_range);

    return data;
}

vip_int32_t fp32_to_affine(
    const float in,
    const float scale,
    const  int zero_point,
    const vip_enum type
    )
{
    vip_int32_t data;
    double max_range;
    double min_range;
    type_get_range(type, &max_range, &min_range);
    data = (vip_int32_t)(rint(in / scale ) + zero_point);
    data = MATH_MAX((vip_int32_t)min_range, MATH_MIN((vip_int32_t)max_range , data ));
    return data;
}

vip_status_e integer_convert(
    const void * src,
    void *dest,
    vip_enum src_dtype,
    vip_enum dst_dtype
    )
{
	vip_status_e status = VIP_SUCCESS;

	unsigned char all_zeros[] = { 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00 };
	unsigned char all_ones[] = { 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff };
	vip_uint32_t src_sz = type_get_bytes(src_dtype);
	vip_uint32_t dest_sz = type_get_bytes(dst_dtype);
	unsigned char* buffer = all_zeros;
	if(((vip_int8_t *)src)[src_sz - 1] & 0x80 )
	{
		buffer = all_ones;
	}
	memcpy(buffer, src, src_sz);
	memcpy(dest, buffer, dest_sz);

    return status;
}

static unsigned short  fp32_to_bfp16_rtne(float in)
{
    /*
    Convert a float point to bfloat16, with round-nearest-to-even as rounding method.
    */
    vip_uint32_t fp32 = *((unsigned int *) &in);
    unsigned short  out;

    vip_uint32_t lsb = (fp32 >> 16) & 1;    /* Least significant bit of resulting bfloat. */
    vip_uint32_t rounding_bias = 0x7fff + lsb;

    if (0x7FC00000 == in ) {
        out = 0x7fc0;
    }
    else {
        fp32 += rounding_bias;
        out = (unsigned short ) (fp32 >> 16);
    }

    return out;
}

unsigned short fp32_to_fp16(float in)
{
    vip_uint32_t fp32 = 0;
    vip_uint32_t t1 = 0;
    vip_uint32_t t2 = 0;
    vip_uint32_t t3 = 0;
    vip_uint32_t fp16 = 0u;

    vip_memcpy((vip_uint8_t*)&fp32, (vip_uint8_t*)&in, sizeof(vip_uint32_t));

    t1 = (fp32 & 0x80000000u) >> 16;  /* sign bit. */
    t2 = (fp32 & 0x7F800000u) >> 13;  /* Exponent bits */
    t3 = (fp32 & 0x007FE000u) >> 13;  /* Mantissa bits, no rounding */

    if(t2 >= 0x023c00u )
    {
        fp16 = t1 | 0x7BFF;     /* Don't round to infinity. */
    }
    else if(t2 <= 0x01c000u )
    {
        fp16 = t1;
    }
    else
    {
        t2 -= 0x01c000u;
        fp16 = t1 | t2 | t3;
    }

    return (unsigned short) fp16;
}

vip_status_e float32_to_dtype(
    float src,
    unsigned char *dst,
    const vip_enum data_type,
    const vip_enum quant_format,
    signed char fixed_point_pos,
    float tf_scale,
    vip_int32_t tf_zerop
    )
{
    vip_status_e status = VIP_SUCCESS;

    switch(data_type )
    {
    case VIP_BUFFER_FORMAT_FP32:
        *(float *)dst = src;
        break;
    case VIP_BUFFER_FORMAT_FP16:
        *(vip_int16_t *)dst = fp32_to_fp16(src);
        break;
    case VIP_BUFFER_FORMAT_BFP16:
        *(vip_int16_t *)dst = fp32_to_bfp16_rtne(src);
        break;
    case VIP_BUFFER_FORMAT_INT8:
    case VIP_BUFFER_FORMAT_UINT8:
    case VIP_BUFFER_FORMAT_BOOL8:
    case VIP_BUFFER_FORMAT_INT16:
    case VIP_BUFFER_FORMAT_INT32:
        {
            vip_int32_t dst_value = 0;
            switch(quant_format)
            {
            case VIP_BUFFER_QUANTIZE_DYNAMIC_FIXED_POINT:
                dst_value = fp32_to_dfp(src, fixed_point_pos, data_type);
                break;
            case VIP_BUFFER_QUANTIZE_TF_ASYMM:
                dst_value = fp32_to_affine(src, tf_scale, tf_zerop, data_type);
                break;
            case VIP_BUFFER_QUANTIZE_NONE:
                dst_value = (vip_int32_t)src;
                break;
            default:
                break;
            }
            integer_convert(&dst_value, dst, VIP_BUFFER_FORMAT_INT32, data_type);
        }
        break;
    default:
        printf("unsupported tensor type\n");;
    }

    return status;
}

unsigned char *get_binary_data(
    char *file_name,
    vip_uint32_t *file_size
    )
{
    unsigned char *tensorData;

    *file_size = get_file_size((const char *)file_name);
    tensorData = (unsigned char *)malloc(*file_size * sizeof(unsigned char));
    load_file_npu(file_name, (void *)tensorData);

    return tensorData;
}

unsigned char *get_tensor_data(
    //batch_item *batch,
	vip_network     network,
    char *file_name,
    vip_uint32_t *file_size,
    vip_uint32_t index
    )
{
    vip_uint32_t sz = 1;
    vip_uint32_t stride = 1;
    vip_int32_t sizes[4];
    vip_uint32_t num_of_dims;
    vip_uint32_t i = 0;
    vip_enum data_format;
    vip_enum quant_format;
    vip_int32_t fixed_point_pos;
    float tf_scale;
    vip_int32_t tf_zerop;
    unsigned char *tensorData = NULL;
    FILE *tensorFile;
    float fval = 0.0;

    tensorFile = fopen(file_name, "rb");

    vip_query_input(network, index, VIP_BUFFER_PROP_NUM_OF_DIMENSION, &num_of_dims);
    vip_query_input(network, index, VIP_BUFFER_PROP_DATA_FORMAT, &data_format);
    vip_query_input(network, index, VIP_BUFFER_PROP_QUANT_FORMAT, &quant_format);
    vip_query_input(network, index, VIP_BUFFER_PROP_FIXED_POINT_POS, &fixed_point_pos);
    vip_query_input(network, index, VIP_BUFFER_PROP_TF_SCALE, &tf_scale);
    vip_query_input(network, index, VIP_BUFFER_PROP_SIZES_OF_DIMENSION, sizes);
    vip_query_input(network, index, VIP_BUFFER_PROP_TF_ZERO_POINT, &tf_zerop);

    sz = get_element_num(sizes, num_of_dims, data_format);
    stride = type_get_bytes(data_format);
    tensorData = (unsigned char *)malloc(stride * sz * sizeof(unsigned char));
    memset(tensorData, 0, stride * sz * sizeof(unsigned char));
    *file_size = stride * sz * sizeof(unsigned char);

    for(i = 0; i < sz; i++)
    {
        fscanf(tensorFile, "%f ", &fval);
        float32_to_dtype(fval, &tensorData[stride * i], data_format, quant_format,
                         fixed_point_pos, tf_scale, tf_zerop);
    }

    fclose(tensorFile);

    return tensorData;
}




float int8_to_fp32(signed char val, signed char fixedPointPos)
{
    float result = 0.0f;

    if (fixedPointPos > 0) {
        result = (float)val * (1.0f / ((float) (1 << fixedPointPos)));
    }
    else {
        result = (float)val * ((float) (1 << -fixedPointPos));
    }

    return result;
}

float int16_to_fp32(vip_int16_t val, signed char fixedPointPos)
{
    float result = 0.0f;

    if (fixedPointPos > 0) {
        result = (float)val * (1.0f / ((float) (1 << fixedPointPos)));
    }
    else {
        result = (float)val * ((float) (1 << -fixedPointPos));
    }

    return result;
}
vip_float_t affine_to_fp32(vip_int32_t val, vip_int32_t zeroPoint, vip_float_t scale)
{
    vip_float_t result = 0.0f;
    result = ((vip_float_t)val - zeroPoint) * scale;
    return result;
}

float uint8_to_fp32(vip_uint8_t val, vip_int32_t zeroPoint, vip_float_t scale)
{
    vip_float_t result = 0.0f;
    result = (val - (vip_uint8_t)zeroPoint) * scale;
    return result;
}

typedef union
{
    unsigned int u;
    float f;
} _fp32_t;

float fp16_to_fp32(const short in)
{
    const _fp32_t magic = { (254 - 15) << 23 };
    const _fp32_t infnan = { (127 + 16) << 23 };
    _fp32_t o;
    // Non-sign bits
    o.u = (in & 0x7fff ) << 13;
    o.f *= magic.f;
    if(o.f  >= infnan.f)
    {
        o.u |= 255 << 23;
    }
    //Sign bit
    o.u |= (in & 0x8000 ) << 16;
    return o.f;
}

int save_txt_file(
    void* buffer,
    unsigned int ele_size,
    signed int data_type,
    vip_int32_t quant_format,
    unsigned char fix_pos,
    vip_int32_t zeroPoint,
    vip_float_t scale,
    char *filename
    )
{
    #define TMPBUF_SZ  (512)
    vip_uint32_t i = 0;
    FILE        *fp;
    float fp_data = 0.0;
    vip_uint8_t *data = (vip_uint8_t*)buffer;
    vip_uint32_t type_size = type_get_bytes(data_type);
    vip_uint8_t buf[TMPBUF_SZ];
    vip_uint32_t count = 0;

    fp = fopen(filename, "w");

    for (i = 0; i < ele_size; i++) {
        if (data_type == VIP_BUFFER_FORMAT_INT8) {
            if (quant_format == VIP_BUFFER_QUANTIZE_DYNAMIC_FIXED_POINT) {
                fp_data = int8_to_fp32(*data, fix_pos);
            }
            else if (quant_format == VIP_BUFFER_QUANTIZE_TF_ASYMM) {
                vip_int32_t src_value = 0;
                integer_convert(data,&src_value, VIP_BUFFER_FORMAT_INT8, VIP_BUFFER_FORMAT_INT32);
                fp_data = affine_to_fp32(src_value, zeroPoint, scale);
            }
            else {
                fp_data = *((float*)data);
            }
        }
        else if (data_type == VIP_BUFFER_FORMAT_FP16) {
            fp_data = fp16_to_fp32(*((short *)data));
        }
        else if (data_type == VIP_BUFFER_FORMAT_UINT8) {
            fp_data = uint8_to_fp32(*data, zeroPoint, scale);
        }
        else if (data_type == VIP_BUFFER_FORMAT_INT16) {
            fp_data = int16_to_fp32(*((short *)data), fix_pos);
        }
        else if (data_type == VIP_BUFFER_FORMAT_FP32) {
            fp_data = *((float*)data);
        }
        else if(data_type == VIP_BUFFER_FORMAT_INT32) {
            if (quant_format == VIP_BUFFER_QUANTIZE_NONE) {
                fp_data = (float)(*((vip_int32_t*)data));
            }
        }
        else {
            printf("not support this format into output.txt file\n");
            break;
        }

        data += type_size;

        count += sprintf((char *)&buf[count], "%f%s", fp_data, "\n");

        if ((count + 50) > TMPBUF_SZ)
        {
            fwrite(buf, count, 1, fp );
            count = 0;
        }
    }

    fwrite(buf, count, 1, fp );
    fflush(fp);
    fclose(fp );

    return 0;
}

#ifdef __cplusplus
}
#endif
