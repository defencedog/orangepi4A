/*
 * below file was taken from xdelta3 sources:
 *    xdelta3-3.0.8-dfsg/examples/encode_decode_test.c
 * and modified a bit.
 *
 * xdelta3 is copyright 2007 Ralf Junker and released under the terms of the
 * GPL2+
 */

//
// Permission to distribute this example by
// Copyright (C) 2007 Ralf Junker
// Ralf Junker <delphi@yunqa.de>
// http://www.yunqa.de/delphi/

//---------------------------------------------------------------------------

#define _POSIX_SOURCE
#include <stdio.h>
#include <sys/stat.h>
#include <stdlib.h>
#include <string.h>
#undef _POSIX_SOURCE
#include "../3rdparty/xdelta3-3.0.8/xdelta3.h"
#include "../3rdparty/xdelta3-3.0.8/xdelta3.c"
#include "../3rdparty/xdelta3-3.0.8/xdelta3-decode.h"

//---------------------------------------------------------------------------
static int code(int encode, FILE * InFile, FILE * SrcFile, FILE * OutFile,
                unsigned int BufSize)
{
    int             r,
                    ret;
    struct stat     statbuf;

    xd3_stream      stream;
    xd3_config      config;
    xd3_source      source;
    void           *Input_Buf;
    unsigned int    Input_Buf_Read;

    if (BufSize < XD3_ALLOCSIZE)
        BufSize = XD3_ALLOCSIZE;
    memset(&stream, 0, sizeof(stream));
    memset(&source, 0, sizeof(source));
    xd3_init_config(&config, XD3_ADLER32);
    config.winsize = BufSize;
    xd3_config_stream(&stream, &config);
    r = fstat(fileno(SrcFile), &statbuf);
    if (r)
        return r;
    source.blksize = BufSize;
    source.curblk = malloc(source.blksize);

    /* Load 1st block of stream. */
    r = fseek(SrcFile, 0, SEEK_SET);
    if (r)
        return r;
    source.onblk = fread((void *)source.curblk, 1, source.blksize, SrcFile);
    source.curblkno = 0;

    /* Set the stream. */
    xd3_set_source(&stream, &source);
    Input_Buf = malloc(BufSize);
    fseek(InFile, 0, SEEK_SET);

    do {
        Input_Buf_Read = fread(Input_Buf, 1, BufSize, InFile);
        if (Input_Buf_Read < BufSize) {
            xd3_set_flags(&stream, XD3_FLUSH | stream.flags);
        }
        xd3_avail_input(&stream, Input_Buf, Input_Buf_Read);
        for (;;) {
            if (encode)
                ret = xd3_encode_input(&stream);
            else
                ret = xd3_decode_input(&stream);
            if (ret == XD3_INPUT) {
                break;
            } else if (ret == XD3_OUTPUT) {
                r = fwrite(stream.next_out, 1, stream.avail_out, OutFile);
                if (r != (int)stream.avail_out)
                    return r;
                xd3_consume_output(&stream);
            } else if (ret == XD3_GETSRCBLK) {
                r = fseek(SrcFile, source.blksize * source.getblkno, SEEK_SET);
                if (r)
                    return r;
                source.onblk =
                    fread((void *)source.curblk, 1, source.blksize, SrcFile);
                source.curblkno = source.getblkno;
            } else if (ret == XD3_GOTHEADER || ret == XD3_WINSTART
                       || ret == XD3_WINFINISH) {
            } else {
                fprintf(stderr, "!!! INVALID %s %d !!!\n", stream.msg, ret);
                return ret;
            }
        }
    } while (Input_Buf_Read == BufSize);
    free(Input_Buf);
    free((void *)source.curblk);
    xd3_close_stream(&stream);
    xd3_free_stream(&stream);
    return 0;
}

int xdelta3_diff(FILE * old, FILE * new, FILE * diff)
{
    return code(1, new, old, diff, 0x1000);
}

int xdelta3_patch(FILE * old, FILE * diff, FILE * new)
{
    return code(0, diff, old, new, 0x1000);
}
