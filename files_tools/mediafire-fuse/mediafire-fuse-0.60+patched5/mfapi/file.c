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

#define _POSIX_C_SOURCE 200809L // for strdup
#define _DEFAULT_SOURCE         // for strdup on old systems

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <openssl/sha.h>

#include "file.h"
#include "apicalls.h"

struct mffile {
    char            quickkey[MFAPI_MAX_LEN_KEY + 1];
    char            parent[MFAPI_MAX_LEN_NAME + 1];
    /* the hex representation takes twice the amount of the binary length plus
     * 1 for the terminating zero byte */
    char            hash[SHA256_DIGEST_LENGTH * 2 + 1];
    char            name[MFAPI_MAX_LEN_NAME + 1];
    time_t          created;
    uint64_t        revision;
    uint64_t        size;

    char           *share_link;
    char           *direct_link;
    char           *onetime_link;
};

mffile         *file_alloc(void)
{
    mffile         *file;

    file = (mffile *) calloc(1, sizeof(mffile));

    return file;
}

void file_free(mffile * file)
{
    if (file == NULL) {
        fprintf(stderr, "file cannot be NULL\n");
        return;
    }

    if (file->share_link != NULL)
        free(file->share_link);
    if (file->direct_link != NULL)
        free(file->direct_link);
    if (file->onetime_link != NULL)
        free(file->onetime_link);

    free(file);

    return;
}

int file_set_key(mffile * file, const char *key)
{
    int             len;

    if (file == NULL) {
        fprintf(stderr, "file cannot be NULL\n");
        return -1;
    }
    if (key == NULL) {
        fprintf(stderr, "key cannot be NULL\n");
        return -1;
    }

    len = strlen(key);
    if (len != 11 && len != 15) {
        fprintf(stderr, "key must be 11 or 15 chars long\n");
        return -1;
    }

    memset(file->quickkey, 0, sizeof(file->quickkey));
    strncpy(file->quickkey, key, sizeof(file->quickkey));

    return 0;
}

const char     *file_get_key(mffile * file)
{
    if (file == NULL) {
        fprintf(stderr, "file must not be NULL\n");
        return NULL;
    }

    return file->quickkey;
}

int file_set_parent(mffile * file, const char *parent_key)
{
    if (file == NULL) {
        fprintf(stderr, "file must not be NULL\n");
        return -1;
    }

    if (parent_key == NULL) {
        memset(file->parent, 0, sizeof(file->parent));
    } else {
        memset(file->parent, 0, sizeof(file->parent));
        strncpy(file->parent, parent_key, sizeof(file->parent));
    }

    return 0;
}

const char     *file_get_parent(mffile * file)
{
    if (file == NULL) {
        fprintf(stderr, "file must not be NULL\n");
        return NULL;
    }

    if (file->parent[0] == '\0') {
        return NULL;
    } else {
        return file->parent;
    }
}

int file_set_hash(mffile * file, const char *hash)
{
    if (file == NULL) {
        fprintf(stderr, "file must not be NULL\n");
        return -1;
    }
    if (hash == NULL) {
        fprintf(stderr, "hash cannot be NULL\n");
        return -1;
    }
    // system supports SHA256 (current) and MD5 (legacy)
    if (strlen(hash) < 32) {
        fprintf(stderr, "hash must not be shorter than 32\n");
        return -1;
    }

    memset(file->hash, 0, sizeof(file->hash));
    strncpy(file->hash, hash, sizeof(file->hash) - 1);

    return 0;
}

const char     *file_get_hash(mffile * file)
{
    if (file == NULL) {
        fprintf(stderr, "file must not be NULL\n");
        return NULL;
    }

    return file->hash;
}

int file_set_name(mffile * file, const char *name)
{
    if (file == NULL) {
        fprintf(stderr, "file must not be NULL\n");
        return -1;
    }
    if (name == NULL) {
        fprintf(stderr, "name must not be NULL\n");
        return -1;
    }

    if (strlen(name) > MFAPI_MAX_LEN_NAME) {
        fprintf(stderr, "name must not be longer than %d\n",
                MFAPI_MAX_LEN_NAME);
        return -1;
    }

    memset(file->name, 0, sizeof(file->name));
    strncpy(file->name, name, sizeof(file->name));

    return 0;
}

const char     *file_get_name(mffile * file)
{
    if (file == NULL) {
        fprintf(stderr, "file must not be NULL\n");
        return NULL;
    }

    return file->name;
}

int file_set_size(mffile * file, uint64_t size)
{
    if (file == NULL) {
        fprintf(stderr, "file must not be NULL\n");
        return -1;
    }

    file->size = size;

    return 0;
}

uint64_t file_get_size(mffile * file)
{
    if (file == NULL) {
        fprintf(stderr, "file must not be NULL\n");
        return -1;
    }

    return file->size;
}

int file_set_revision(mffile * file, uint64_t revision)
{
    if (file == NULL) {
        fprintf(stderr, "file must not be NULL\n");
        return -1;
    }

    file->revision = revision;

    return 0;
}

uint64_t file_get_revision(mffile * file)
{
    if (file == NULL) {
        fprintf(stderr, "file must not be NULL\n");
        return -1;
    }

    return file->revision;
}

int file_set_created(mffile * file, time_t created)
{
    if (file == NULL) {
        fprintf(stderr, "file must not be NULL\n");
        return -1;
    }

    file->created = created;

    return 0;
}

time_t file_get_created(mffile * file)
{
    if (file == NULL) {
        fprintf(stderr, "file must not be NULL\n");
        return -1;
    }

    return file->created;
}

int file_set_share_link(mffile * file, const char *share_link)
{
    if (file == NULL) {
        fprintf(stderr, "file must not be NULL\n");
        return -1;
    }
    if (share_link == NULL) {
        fprintf(stderr, "share_link must not be NULL\n");
        return -1;
    }

    if (file->share_link != NULL) {
        free(file->share_link);
        file->share_link = NULL;
    }

    file->share_link = strdup(share_link);

    return 0;
}

const char     *file_get_share_link(mffile * file)
{
    if (file == NULL) {
        fprintf(stderr, "file must not be NULL\n");
        return NULL;
    }

    return file->share_link;
}

int file_set_direct_link(mffile * file, const char *direct_link)
{
    if (file == NULL) {
        fprintf(stderr, "file must not be NULL\n");
        return -1;
    }
    if (direct_link == NULL) {
        fprintf(stderr, "direct_link must not be NULL\n");
        return -1;
    }

    if (file->direct_link != NULL) {
        free(file->direct_link);
        file->direct_link = NULL;
    }

    file->direct_link = strdup(direct_link);

    return 0;
}

const char     *file_get_direct_link(mffile * file)
{
    if (file == NULL) {
        fprintf(stderr, "file must not be NULL\n");
        return NULL;
    }

    return file->direct_link;
}

int file_set_onetime_link(mffile * file, const char *onetime_link)
{
    if (file == NULL) {
        fprintf(stderr, "file must not be NULL\n");
        return -1;
    }
    if (onetime_link == NULL) {
        fprintf(stderr, "onetime_link must not be NULL\n");
        return -1;
    }

    if (file->onetime_link != NULL) {
        free(file->onetime_link);
        file->onetime_link = NULL;
    }

    file->onetime_link = strdup(onetime_link);

    return 0;
}

const char     *file_get_onetime_link(mffile * file)
{
    if (file == NULL) {
        fprintf(stderr, "file must not be NULL\n");
        return NULL;
    }

    return file->onetime_link;
}
