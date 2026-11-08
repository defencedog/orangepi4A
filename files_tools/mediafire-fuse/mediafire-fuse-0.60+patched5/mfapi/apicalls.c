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

#include <jansson.h>
#include <string.h>
#include <stdio.h>

#include "../utils/http.h"

const char     *mfconn_file_link_types[] = {
    "normal_download",
    "direct_download",
    "view",
    "edit",
    "watch",
    "listen",
    "streaming",
    "one_time_download"
};

int mfapi_check_response(json_t * response, const char *apicall)
{
    json_t         *j_obj;
    int             error_code;

    j_obj = json_object_get(response, "result");
    if (j_obj == NULL || strcmp(json_string_value(j_obj), "Success") != 0) {
        // an error occurred
        j_obj = json_object_get(response, "message");
        if (j_obj == NULL) {
            fprintf(stderr, "no error message\n");
        } else {
            fprintf(stderr, "error message: %s\n", json_string_value(j_obj));
        }
        j_obj = json_object_get(response, "error");
        if (j_obj == NULL) {
            fprintf(stderr, "unknown error code\n");
            error_code = -1;
        } else {
            fprintf(stderr, "error code: %" JSON_INTEGER_FORMAT "\n",
                    json_integer_value(j_obj));
            error_code = json_integer_value(j_obj);
            if (error_code == 0)
                error_code = -1;
        }
        return error_code;
    }

    j_obj = json_object_get(response, "action");
    if (j_obj == NULL) {
        fprintf(stderr, "no value for action\n");
        return -1;
    }

    if (strcmp(json_string_value(j_obj), apicall) != 0) {
        fprintf(stderr, "expected action %s but got %s", apicall,
                json_string_value(j_obj));
        return -1;
    }

    return 0;
}

int mfapi_decode_common(mfhttp * conn, void *user_ptr)
{
    json_t         *root;
    json_t         *node;
    json_error_t    error;
    int             retval;
    char           *apicall;

    if (user_ptr == NULL) {
        fprintf(stderr, "user_ptr must not be null\n");
        return -1;
    }

    apicall = (char *)user_ptr;

    root = http_parse_buf_json(conn, 0, &error);

    if (root == NULL) {
        fprintf(stderr, "http_parse_buf_json failed at line %d\n", error.line);
        fprintf(stderr, "error message: %s\n", error.text);
        return -1;
    }

    node = json_object_get(root, "response");

    retval = mfapi_check_response(node, apicall);
    if (retval != 0) {
        fprintf(stderr, "invalid response\n");
        json_decref(root);
        return retval;
    }

    json_decref(root);

    return 0;
}
