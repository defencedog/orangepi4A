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

#define _POSIX_C_SOURCE 200809L // for strdup
#define _DEFAULT_SOURCE         // for strdup on old systems

#include <stdint.h>
#include <openssl/sha.h>
#include <string.h>
#include <stdlib.h>
#include <stdio.h>

#include "patch.h"

struct mfpatch {
    /* revision of the file to be patched */
    uint64_t        source_revision;
    /* revision of the target file */
    uint64_t        target_revision;
    /* hash of the patch */
    char            hash[SHA256_DIGEST_LENGTH * 2 + 1];
    /* hash of the file to be patched */
    char            source_hash[SHA256_DIGEST_LENGTH * 2 + 1];
    /* hash of the patched file */
    char            target_hash[SHA256_DIGEST_LENGTH * 2 + 1];
    /* expected size of the patched file */
    uint64_t        target_size;
    char           *link;
};

mfpatch        *patch_alloc(void)
{
    mfpatch        *patch;

    patch = (mfpatch *) calloc(1, sizeof(mfpatch));
    return patch;
}

void patch_free(mfpatch * patch)
{
    if (patch == NULL) {
        fprintf(stderr, "patch must not be NULL\n");
        return;
    }

    if (patch->link != NULL)
        free(patch->link);

    free(patch);

    return;
}

uint64_t patch_get_source_revision(mfpatch * patch)
{
    if (patch == NULL) {
        fprintf(stderr, "patch must not be NULL\n");
        return -1;
    }

    return patch->source_revision;
}

int patch_set_source_revision(mfpatch * patch, uint64_t revision)
{
    if (patch == NULL) {
        fprintf(stderr, "patch must not be NULL\n");
        return -1;
    }

    patch->source_revision = revision;

    return 0;
}

uint64_t patch_get_target_revision(mfpatch * patch)
{
    if (patch == NULL) {
        fprintf(stderr, "patch must not be NULL\n");
        return -1;
    }

    return patch->target_revision;
}

int patch_set_target_revision(mfpatch * patch, uint64_t revision)
{
    if (patch == NULL) {
        fprintf(stderr, "patch must not be NULL\n");
        return -1;
    }

    patch->target_revision = revision;

    return 0;
}

const char     *patch_get_hash(mfpatch * patch)
{
    if (patch == NULL) {
        fprintf(stderr, "patch must not be NULL\n");
        return NULL;
    }

    return patch->hash;
}

int patch_set_hash(mfpatch * patch, const char *hash)
{
    if (patch == NULL) {
        fprintf(stderr, "patch must not be NULL\n");
        return -1;
    }
    if (hash == NULL) {
        fprintf(stderr, "hash must not be NULL\n");
        return -1;
    }

    if (strlen(hash) < 32) {
        fprintf(stderr, "hash must not be shorter than 32\n");
        return -1;
    }

    memset(patch->hash, 0, sizeof(patch->hash));
    strncpy(patch->hash, hash, sizeof(patch->hash) - 1);

    return 0;
}

const char     *patch_get_source_hash(mfpatch * patch)
{
    if (patch == NULL) {
        fprintf(stderr, "patch must not be NULL\n");
        return NULL;
    }

    return patch->source_hash;
}

int patch_set_source_hash(mfpatch * patch, const char *hash)
{
    if (patch == NULL) {
        fprintf(stderr, "patch must not be NULL\n");
        return -1;
    }
    if (hash == NULL) {
        fprintf(stderr, "hash must not be NULL\n");
        return -1;
    }

    if (strlen(hash) < 32) {
        fprintf(stderr, "hash must not be shorter than 32\n");
        return -1;
    }

    memset(patch->source_hash, 0, sizeof(patch->source_hash));
    strncpy(patch->source_hash, hash, sizeof(patch->source_hash) - 1);

    return 0;
}

const char     *patch_get_target_hash(mfpatch * patch)
{
    if (patch == NULL) {
        fprintf(stderr, "patch must not be NULL\n");
        return NULL;
    }

    return patch->target_hash;
}

int patch_set_target_hash(mfpatch * patch, const char *hash)
{
    if (patch == NULL) {
        fprintf(stderr, "patch must not be NULL\n");
        return -1;
    }
    if (hash == NULL) {
        fprintf(stderr, "hash must not be NULL\n");
        return -1;
    }

    if (strlen(hash) < 32) {
        fprintf(stderr, "hash must not be shorter than 32\n");
        return -1;
    }

    memset(patch->target_hash, 0, sizeof(patch->target_hash));
    strncpy(patch->target_hash, hash, sizeof(patch->target_hash) - 1);

    return 0;
}

uint64_t patch_get_target_size(mfpatch * patch)
{
    if (patch == NULL) {
        fprintf(stderr, "patch must not be NULL\n");
        return -1;
    }

    return patch->target_size;
}

int patch_set_target_size(mfpatch * patch, uint64_t size)
{
    if (patch == NULL) {
        fprintf(stderr, "patch must not be NULL\n");
        return -1;
    }

    patch->target_size = size;

    return 0;
}

const char     *patch_get_link(mfpatch * patch)
{
    if (patch == NULL) {
        fprintf(stderr, "patch must not be NULL\n");
        return NULL;
    }

    return patch->link;
}

int patch_set_link(mfpatch * patch, const char *link)
{
    if (patch == NULL) {
        fprintf(stderr, "patch must not be NULL\n");
        return -1;
    }
    if (link == NULL) {
        fprintf(stderr, "link must not be NULL\n");
        return -1;
    }

    if (patch->link != NULL) {
        free(patch->link);
    }

    patch->link = strdup(link);

    return 0;
}
