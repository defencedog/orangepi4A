/*
 * g2d_image_demo.c — Real-image G2D hardware acceleration demo on Orange Pi 4A (T527)
 *
 * Loads an input PPM image (512x480 dummy_input.ppm), copies it into a DMA-BUF
 * allocated from /dev/dma_heap/system, executes 6 operations through /dev/g2d:
 *   1. 90-degree rotation (G2D_ROT_90 on G2D_ROT hardware engine)
 *   2. 180-degree rotation (G2D_ROT_180 on G2D_ROT hardware engine)
 *   3. Horizontal mirror/flip (G2D_ROT_H on G2D_ROT hardware engine)
 *   4. Solid color rectangle fill overlay (G2D_BLT_NONE_H, bbuff=0)
 *   5. 2x downscaling (512x480 -> 256x240 ARGB8888)
 *   6. Format conversion (ARGB8888 -> YUV420 NV21 + RGB preview reconstruction)
 */

#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#include <time.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <linux/types.h>
#include <linux/dma-heap.h>
#include <bsp/linux/sunxi-g2d.h>

#define DMA_HEAP_NAME "/dev/dma_heap/system"

static double get_time_ms(void)
{
	struct timespec ts;
	clock_gettime(CLOCK_MONOTONIC, &ts);
	return ts.tv_sec * 1000.0 + ts.tv_nsec / 1e6;
}

static int alloc_dmabuf(int *fd, void **vaddr, size_t size)
{
	struct dma_heap_allocation_data alloc_data = {
		.len = size,
		.fd_flags = O_RDWR | O_CLOEXEC,
		.heap_flags = 0,
	};

	int heap_fd = open(DMA_HEAP_NAME, O_RDONLY);
	if (heap_fd < 0) {
		perror("open /dev/dma_heap/system");
		return -1;
	}
	if (ioctl(heap_fd, DMA_HEAP_IOCTL_ALLOC, &alloc_data) < 0) {
		perror("DMA_HEAP_IOCTL_ALLOC");
		close(heap_fd);
		return -1;
	}
	close(heap_fd);

	*fd = alloc_data.fd;
	*vaddr = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_SHARED, *fd, 0);
	if (*vaddr == MAP_FAILED) {
		perror("mmap");
		close(*fd);
		return -1;
	}
	return 0;
}

static int load_ppm_to_argb(const char *path, uint32_t **out_argb, int *out_w, int *out_h)
{
	FILE *f = fopen(path, "rb");
	if (!f) {
		perror(path);
		return -1;
	}

	char magic[3] = {0};
	if (fscanf(f, "%2s", magic) != 1 || strcmp(magic, "P6") != 0) {
		fprintf(stderr, "Invalid PPM header in %s\n", path);
		fclose(f);
		return -1;
	}

	int c = fgetc(f);
	while (c == '#' || c == ' ' || c == '\t' || c == '\n' || c == '\r') {
		if (c == '#') {
			while ((c = fgetc(f)) != '\n' && c != EOF)
				;
		}
		c = fgetc(f);
	}
	ungetc(c, f);

	int w = 0, h = 0, maxval = 0;
	if (fscanf(f, "%d %d %d", &w, &h, &maxval) != 3 || w <= 0 || h <= 0) {
		fprintf(stderr, "Invalid PPM dimensions in %s\n", path);
		fclose(f);
		return -1;
	}
	fgetc(f); /* consume single whitespace after maxval */

	uint8_t *rgb = malloc((size_t)w * h * 3);
	uint32_t *argb = malloc((size_t)w * h * 4);
	if (!rgb || !argb) {
		free(rgb);
		free(argb);
		fclose(f);
		return -1;
	}

	if (fread(rgb, 3, (size_t)w * h, f) != (size_t)w * h) {
		fprintf(stderr, "Short read on %s\n", path);
		free(rgb);
		free(argb);
		fclose(f);
		return -1;
	}
	fclose(f);

	for (int i = 0; i < w * h; i++) {
		uint32_t r = rgb[i * 3 + 0];
		uint32_t g = rgb[i * 3 + 1];
		uint32_t b = rgb[i * 3 + 2];
		argb[i] = (0xffu << 24) | (r << 16) | (g << 8) | b;
	}

	free(rgb);
	*out_argb = argb;
	*out_w = w;
	*out_h = h;
	return 0;
}

static int save_argb_to_ppm(const char *path, const uint32_t *argb, int w, int h)
{
	FILE *f = fopen(path, "wb");
	if (!f) {
		perror(path);
		return -1;
	}
	fprintf(f, "P6\n%d %d\n255\n", w, h);
	uint8_t *row = malloc((size_t)w * 3);
	if (!row) {
		fclose(f);
		return -1;
	}
	for (int y = 0; y < h; y++) {
		const uint32_t *src = argb + y * w;
		for (int x = 0; x < w; x++) {
			uint32_t px = src[x];
			row[x * 3 + 0] = (px >> 16) & 0xff;
			row[x * 3 + 1] = (px >> 8) & 0xff;
			row[x * 3 + 2] = px & 0xff;
		}
		fwrite(row, 3, (size_t)w, f);
	}
	free(row);
	fclose(f);
	return 0;
}

static uint8_t clamp_u8(int v)
{
	if (v < 0)
		return 0;
	if (v > 255)
		return 255;
	return (uint8_t)v;
}

static int save_nv21_to_ppm(const char *path, const uint8_t *nv21, int w, int h)
{
	uint32_t *argb = malloc((size_t)w * h * 4);
	if (!argb)
		return -1;

	const uint8_t *y_plane = nv21;
	const uint8_t *vu_plane = nv21 + w * h;

	for (int y = 0; y < h; y++) {
		for (int x = 0; x < w; x++) {
			int Y = (int)y_plane[y * w + x] - 16;
			int V = (int)vu_plane[(y / 2) * w + (x & ~1) + 0] - 128;
			int U = (int)vu_plane[(y / 2) * w + (x & ~1) + 1] - 128;
			if (Y < 0)
				Y = 0;
			int r = (298 * Y + 409 * V + 128) >> 8;
			int g = (298 * Y - 100 * U - 208 * V + 128) >> 8;
			int b = (298 * Y + 516 * U + 128) >> 8;
			argb[y * w + x] = (0xffu << 24) |
					  ((uint32_t)clamp_u8(r) << 16) |
					  ((uint32_t)clamp_u8(g) << 8) |
					  (uint32_t)clamp_u8(b);
		}
	}

	int ret = save_argb_to_ppm(path, argb, w, h);
	free(argb);
	return ret;
}

int main(int argc, char **argv)
{
	const char *in_path = (argc > 1) ? argv[1] : "assets/dummy_input.ppm";
	const char *out_dir = (argc > 2) ? argv[2] : "assets/output";

	uint32_t *img_argb = NULL;
	int w = 0, h = 0;

	if (load_ppm_to_argb(in_path, &img_argb, &w, &h) < 0)
		return 1;

	printf("================================================================\n");
	printf("  Allwinner T527 G2D Real-Image Processing Demo (%dx%d)\n", w, h);
	printf("================================================================\n");
	printf("Input image : %s (%dx%d ARGB8888, %.2f KB)\n",
	       in_path, w, h, (w * h * 4) / 1024.0);

	int g2d_fd = open("/dev/g2d", O_RDWR);
	if (g2d_fd < 0) {
		perror("open /dev/g2d");
		free(img_argb);
		return 1;
	}

	size_t frame_bytes = (size_t)w * h * 4;
	int src_fd = -1, dst_fd = -1;
	void *src_v = NULL, *dst_v = NULL;

	if (alloc_dmabuf(&src_fd, &src_v, frame_bytes) < 0 ||
	    alloc_dmabuf(&dst_fd, &dst_v, frame_bytes) < 0) {
		fprintf(stderr, "Failed to allocate DMA-BUF\n");
		close(g2d_fd);
		free(img_argb);
		return 1;
	}

	memcpy(src_v, img_argb, frame_bytes);
	char out_path[512];

	/* 1. 90-degree Clockwise Rotation (G2D_ROT_90) */
	{
		g2d_blt_h blit;
		memset(&blit, 0, sizeof(blit));
		blit.flag_h = G2D_ROT_90;
		blit.src_image_h.fd = src_fd;
		blit.src_image_h.bbuff = 1;
		blit.src_image_h.format = G2D_FORMAT_ARGB8888;
		blit.src_image_h.width = w;
		blit.src_image_h.height = h;
		blit.src_image_h.clip_rect.w = w;
		blit.src_image_h.clip_rect.h = h;

		blit.dst_image_h.fd = dst_fd;
		blit.dst_image_h.bbuff = 1;
		blit.dst_image_h.format = G2D_FORMAT_ARGB8888;
		blit.dst_image_h.width = h;
		blit.dst_image_h.height = w;
		blit.dst_image_h.clip_rect.w = h;
		blit.dst_image_h.clip_rect.h = w;

		memset(dst_v, 0, frame_bytes);
		double t0 = get_time_ms();
		if (ioctl(g2d_fd, G2D_CMD_BITBLT_H, (unsigned long)&blit) < 0) {
			perror("G2D_ROT_90 failed");
			return 1;
		}
		double dt = get_time_ms() - t0;
		snprintf(out_path, sizeof(out_path), "%s/output_rotated_90.ppm", out_dir);
		save_argb_to_ppm(out_path, (const uint32_t *)dst_v, h, w);
		printf("[1/6] G2D_ROT_90   (%dx%d -> %dx%d) : %6.2f ms (%6.1f MP/s) -> %s\n",
		       w, h, h, w, dt, (w * h) / 1e6 / (dt / 1000.0), out_path);
	}

	/* 2. 180-degree Rotation (G2D_ROT_180) */
	{
		g2d_blt_h blit;
		memset(&blit, 0, sizeof(blit));
		blit.flag_h = G2D_ROT_180;
		blit.src_image_h.fd = src_fd;
		blit.src_image_h.bbuff = 1;
		blit.src_image_h.format = G2D_FORMAT_ARGB8888;
		blit.src_image_h.width = w;
		blit.src_image_h.height = h;
		blit.src_image_h.clip_rect.w = w;
		blit.src_image_h.clip_rect.h = h;

		blit.dst_image_h.fd = dst_fd;
		blit.dst_image_h.bbuff = 1;
		blit.dst_image_h.format = G2D_FORMAT_ARGB8888;
		blit.dst_image_h.width = w;
		blit.dst_image_h.height = h;
		blit.dst_image_h.clip_rect.w = w;
		blit.dst_image_h.clip_rect.h = h;

		memset(dst_v, 0, frame_bytes);
		double t0 = get_time_ms();
		if (ioctl(g2d_fd, G2D_CMD_BITBLT_H, (unsigned long)&blit) < 0) {
			perror("G2D_ROT_180 failed");
			return 1;
		}
		double dt = get_time_ms() - t0;
		snprintf(out_path, sizeof(out_path), "%s/output_rotated_180.ppm", out_dir);
		save_argb_to_ppm(out_path, (const uint32_t *)dst_v, w, h);
		printf("[2/6] G2D_ROT_180  (%dx%d -> %dx%d) : %6.2f ms (%6.1f MP/s) -> %s\n",
		       w, h, w, h, dt, (w * h) / 1e6 / (dt / 1000.0), out_path);
	}

	/* 3. Horizontal Mirror / Flip (G2D_ROT_H) */
	{
		g2d_blt_h blit;
		memset(&blit, 0, sizeof(blit));
		blit.flag_h = G2D_ROT_H;
		blit.src_image_h.fd = src_fd;
		blit.src_image_h.bbuff = 1;
		blit.src_image_h.format = G2D_FORMAT_ARGB8888;
		blit.src_image_h.width = w;
		blit.src_image_h.height = h;
		blit.src_image_h.clip_rect.w = w;
		blit.src_image_h.clip_rect.h = h;

		blit.dst_image_h.fd = dst_fd;
		blit.dst_image_h.bbuff = 1;
		blit.dst_image_h.format = G2D_FORMAT_ARGB8888;
		blit.dst_image_h.width = w;
		blit.dst_image_h.height = h;
		blit.dst_image_h.clip_rect.w = w;
		blit.dst_image_h.clip_rect.h = h;

		memset(dst_v, 0, frame_bytes);
		double t0 = get_time_ms();
		if (ioctl(g2d_fd, G2D_CMD_BITBLT_H, (unsigned long)&blit) < 0) {
			perror("G2D_ROT_H failed");
			return 1;
		}
		double dt = get_time_ms() - t0;
		snprintf(out_path, sizeof(out_path), "%s/output_flipped_h.ppm", out_dir);
		save_argb_to_ppm(out_path, (const uint32_t *)dst_v, w, h);
		printf("[3/6] G2D_ROT_H    (%dx%d -> %dx%d) : %6.2f ms (%6.1f MP/s) -> %s\n",
		       w, h, w, h, dt, (w * h) / 1e6 / (dt / 1000.0), out_path);
	}

	/* 4. Solid Color Fill Overlay (160x120 RED box at (32, 32)) */
	{
		memcpy(dst_v, img_argb, frame_bytes);
		g2d_blt_h blit;
		memset(&blit, 0, sizeof(blit));
		blit.flag_h = G2D_BLT_NONE_H;
		blit.src_image_h.bbuff = 0;
		blit.src_image_h.color = 0xffff2020; /* Red */
		blit.src_image_h.format = G2D_FORMAT_ARGB8888;
		blit.src_image_h.width = w;
		blit.src_image_h.height = h;
		blit.src_image_h.clip_rect.x = 32;
		blit.src_image_h.clip_rect.y = 32;
		blit.src_image_h.clip_rect.w = 160;
		blit.src_image_h.clip_rect.h = 120;

		blit.dst_image_h.fd = dst_fd;
		blit.dst_image_h.bbuff = 1;
		blit.dst_image_h.format = G2D_FORMAT_ARGB8888;
		blit.dst_image_h.width = w;
		blit.dst_image_h.height = h;
		blit.dst_image_h.clip_rect.x = 32;
		blit.dst_image_h.clip_rect.y = 32;
		blit.dst_image_h.clip_rect.w = 160;
		blit.dst_image_h.clip_rect.h = 120;

		double t0 = get_time_ms();
		if (ioctl(g2d_fd, G2D_CMD_BITBLT_H, (unsigned long)&blit) < 0) {
			perror("G2D color fill failed");
			return 1;
		}
		double dt = get_time_ms() - t0;
		snprintf(out_path, sizeof(out_path), "%s/output_color_fill.ppm", out_dir);
		save_argb_to_ppm(out_path, (const uint32_t *)dst_v, w, h);
		printf("[4/6] COLOR_FILL   (160x120 rect @ 32,32): %6.2f ms (%6.1f MP/s) -> %s\n",
		       dt, (160 * 120) / 1e6 / (dt / 1000.0), out_path);
	}

	/* 5. Downscaling 2x (w x h -> w/2 x h/2) */
	{
		int dw = w / 2, dh = h / 2;
		g2d_blt_h blit;
		memset(&blit, 0, sizeof(blit));
		blit.flag_h = G2D_BLT_NONE_H;
		blit.src_image_h.fd = src_fd;
		blit.src_image_h.bbuff = 1;
		blit.src_image_h.format = G2D_FORMAT_ARGB8888;
		blit.src_image_h.width = w;
		blit.src_image_h.height = h;
		blit.src_image_h.clip_rect.w = w;
		blit.src_image_h.clip_rect.h = h;

		blit.dst_image_h.fd = dst_fd;
		blit.dst_image_h.bbuff = 1;
		blit.dst_image_h.format = G2D_FORMAT_ARGB8888;
		blit.dst_image_h.width = dw;
		blit.dst_image_h.height = dh;
		blit.dst_image_h.clip_rect.w = dw;
		blit.dst_image_h.clip_rect.h = dh;

		memset(dst_v, 0, frame_bytes);
		double t0 = get_time_ms();
		if (ioctl(g2d_fd, G2D_CMD_BITBLT_H, (unsigned long)&blit) < 0) {
			perror("G2D downscale failed");
			return 1;
		}
		double dt = get_time_ms() - t0;
		snprintf(out_path, sizeof(out_path), "%s/output_scaled_%dx%d.ppm", out_dir, dw, dh);
		save_argb_to_ppm(out_path, (const uint32_t *)dst_v, dw, dh);
		printf("[5/6] DOWNSCALE    (%dx%d -> %dx%d) : %6.2f ms (%6.1f MP/s) -> %s\n",
		       w, h, dw, dh, dt, (w * h) / 1e6 / (dt / 1000.0), out_path);
	}

	/* 6. Format Conversion (ARGB8888 -> YUV420 NV21) */
	{
		g2d_blt_h blit;
		memset(&blit, 0, sizeof(blit));
		blit.flag_h = G2D_BLT_NONE_H;
		blit.src_image_h.fd = src_fd;
		blit.src_image_h.bbuff = 1;
		blit.src_image_h.format = G2D_FORMAT_ARGB8888;
		blit.src_image_h.width = w;
		blit.src_image_h.height = h;
		blit.src_image_h.clip_rect.w = w;
		blit.src_image_h.clip_rect.h = h;

		blit.dst_image_h.fd = dst_fd;
		blit.dst_image_h.bbuff = 1;
		blit.dst_image_h.format = G2D_FORMAT_YUV420UVC_U1V1U0V0;
		blit.dst_image_h.width = w;
		blit.dst_image_h.height = h;
		blit.dst_image_h.clip_rect.w = w;
		blit.dst_image_h.clip_rect.h = h;

		memset(dst_v, 0, frame_bytes);
		double t0 = get_time_ms();
		if (ioctl(g2d_fd, G2D_CMD_BITBLT_H, (unsigned long)&blit) < 0) {
			perror("G2D format conversion failed");
			return 1;
		}
		double dt = get_time_ms() - t0;
		snprintf(out_path, sizeof(out_path), "%s/output_nv21_reconstructed.ppm", out_dir);
		save_nv21_to_ppm(out_path, (const uint8_t *)dst_v, w, h);
		printf("[6/6] ARGB->YUV420 (%dx%d NV21 37.5%%) : %6.2f ms (%6.1f MP/s) -> %s\n",
		       w, h, dt, (w * h) / 1e6 / (dt / 1000.0), out_path);
	}

	printf("================================================================\n");

	munmap(src_v, frame_bytes);
	munmap(dst_v, frame_bytes);
	close(src_fd);
	close(dst_fd);
	close(g2d_fd);
	free(img_argb);
	return 0;
}
