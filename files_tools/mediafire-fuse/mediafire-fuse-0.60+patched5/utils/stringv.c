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

#include <stdio.h>
#include <stdlib.h>
#include <stdbool.h>
#include <string.h>
#include <stddef.h>

#include "stringv.h"

struct stringv {
    size_t          len;
    char          **array;
};

stringv        *stringv_alloc(void)
{
    stringv        *sv;

    sv = (stringv *) calloc(1, sizeof(stringv));
    sv->len = 0;
    sv->array = NULL;
    return sv;
}

void stringv_free(stringv * sv)
{
    size_t          i;

    for (i = 0; i < sv->len; i++) {
        free(sv->array[i]);
    }
    free(sv->array);
    free(sv);
}

bool stringv_mem(stringv * sv, const char *e)
{
    size_t          i;

    for (i = 0; i < sv->len; i++) {
        if (strcmp(sv->array[i], e) == 0)
            return true;
    }
    return false;
}

int stringv_add(stringv * sv, const char *e)
{
    sv->len++;
    sv->array = realloc(sv->array, sizeof(char *) * sv->len);
    if (sv->array == NULL) {
        fprintf(stderr, "failed to realloc\n");
        return -1;
    }
    sv->array[sv->len - 1] = strdup(e);
    if (sv->array[sv->len - 1] == NULL) {
        fprintf(stderr, "failed to strdup\n");
        return -1;
    }
    return 0;
}

int stringv_del(stringv * sv, const char *e)
{
    size_t          i;

    for (i = 0; i < sv->len; i++) {
        if (strcmp(sv->array[i], e) == 0) {
            free(sv->array[i]);
            break;
        }
    }
    if (i == sv->len) {
        fprintf(stderr, "not found\n");
        return -1;
    }
    // shift the remaining entries one place to the left
    memmove(sv->array + i, sv->array + i + 1,
            sizeof(char *) * (sv->len - i - 1));
    sv->len--;
    if (sv->len == 0) {
        free(sv->array);
        sv->array = NULL;
    } else {
        sv->array = realloc(sv->array, sizeof(char *) * sv->len);
    }
    return 0;
}
