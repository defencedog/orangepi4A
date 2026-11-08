/*
 * Copyright (C) 2013 Bryan Christ <bryan.christ@mediafire.com>
 *               2014 Johannes Schauer <j.schauer@email.de>
 *
 * This program is free software; you can redistribute it and/or modify it
 * under the terms of the GNU General Public License version 2, as published by
 * the Free Software Foundation.
 *
 * This program is distributed in the hope that it will be useful, but WITHOUT
 * ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
 * FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for
 * more details.
 *
 * You should have received a copy of the GNU General Public License along with
 * this program; if not, write to the Free Software Foundation, Inc., 51
 * Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
 *
 */

#ifndef __MFAPI_FILE_H__
#define __MFAPI_FILE_H__

#include <stdint.h>
#include <time.h>

typedef struct mffile mffile;

mffile         *file_alloc(void);

void            file_free(mffile * file);

int             file_set_key(mffile * file, const char *quickkey);

const char     *file_get_key(mffile * file);

int             file_set_parent(mffile * file, const char *parent_key);

const char     *file_get_parent(mffile * file);

int             file_set_hash(mffile * file, const char *hash);

const char     *file_get_hash(mffile * file);

int             file_set_name(mffile * file, const char *name);

const char     *file_get_name(mffile * file);

int             file_set_share_link(mffile * file, const char *share_link);

const char     *file_get_share_link(mffile * file);

int             file_set_direct_link(mffile * file, const char *direct_link);

const char     *file_get_direct_link(mffile * file);

int             file_set_onetime_link(mffile * file, const char *onetime_link);

const char     *file_get_onetime_link(mffile * file);

int             file_set_size(mffile * file, uint64_t size);

uint64_t        file_get_size(mffile * file);

int             file_set_revision(mffile * file, uint64_t revision);

uint64_t        file_get_revision(mffile * file);

int             file_set_created(mffile * file, time_t created);

time_t          file_get_created(mffile * file);

#endif
