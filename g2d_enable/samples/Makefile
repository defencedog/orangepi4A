CC      ?= gcc
CFLAGS  ?= -O2 -Wall -Wextra -I.

TARGETS := g2d_rotation \
           g2d_color_fill \
           g2d_format_conversion \
           g2d_scaler_or_down_sampling \
           g2d_image_demo

.PHONY: all clean

all: $(TARGETS)
	ln -sf g2d_rotation g2d_rotation_or_mirror
	ln -sf g2d_format_conversion g2d_format_conv
	ln -sf g2d_scaler_or_down_sampling g2d_scaler

g2d_rotation: g2d_rotation_or_mirror.c
	$(CC) $(CFLAGS) -o $@ $<

g2d_color_fill: g2d_color_fill.c
	$(CC) $(CFLAGS) -o $@ $<

g2d_format_conversion: g2d_format_conversion.c
	$(CC) $(CFLAGS) -o $@ $<

g2d_scaler_or_down_sampling: g2d_scaler_or_down_sampling.c
	$(CC) $(CFLAGS) -o $@ $<

g2d_image_demo: g2d_image_demo.c
	$(CC) $(CFLAGS) -o $@ $<

clean:
	rm -f $(TARGETS) g2d_rotation_or_mirror g2d_format_conv g2d_scaler
