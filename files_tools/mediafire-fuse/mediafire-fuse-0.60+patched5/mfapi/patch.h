/*
 * Copyright (C) 2014 Johannes Schauer <j.schauer@email.de>
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

#ifndef __MFAPI_PATCH_H__
#define __MFAPI_PATCH_H__

typedef struct mfpatch mfpatch;

mfpatch        *patch_alloc(void);

void            patch_free(mfpatch * patch);

uint64_t        patch_get_source_revision(mfpatch * patch);

int             patch_set_source_revision(mfpatch * patch, uint64_t revision);

uint64_t        patch_get_target_revision(mfpatch * patch);

int             patch_set_target_revision(mfpatch * patch, uint64_t revision);

const char     *patch_get_hash(mfpatch * patch);

int             patch_set_hash(mfpatch * patch, const char *hash);

const char     *patch_get_source_hash(mfpatch * patch);

int             patch_set_source_hash(mfpatch * patch, const char *hash);

const char     *patch_get_target_hash(mfpatch * patch);

int             patch_set_target_hash(mfpatch * patch, const char *hash);

uint64_t        patch_get_target_size(mfpatch * patch);

int             patch_set_target_size(mfpatch * patch, uint64_t size);

const char     *patch_get_link(mfpatch * patch);

int             patch_set_link(mfpatch * patch, const char *link);

#endif
