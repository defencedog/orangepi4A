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

#include <stdio.h>
#include <string.h>

#include "../mfshell.h"
#include "../commands.h"        // IWYU pragma: keep

int mfshell_cmd_help(mfshell * mfshell, int argc, char *const argv[])
{
    (void)argv;
    unsigned int    column1_width = 0;
    unsigned int    column2_width = 0;
    mfcmd          *curr_cmd;

    if (argc != 1) {
        fprintf(stderr, "Invalid number of arguments\n");
        return -1;
    }

    printf("  arguments:\n\r"
           "           <optional>\n\r" "           [required]\n\r");

    printf("\n\r");

    for (curr_cmd = mfshell->commands; curr_cmd->name != NULL; curr_cmd++) {
        if (strlen(curr_cmd->name) > column1_width)
            column1_width = strlen(curr_cmd->name);
        if (strlen(curr_cmd->argstring) > column2_width)
            column2_width = strlen(curr_cmd->argstring);
    }

    for (curr_cmd = mfshell->commands; curr_cmd->name != NULL; curr_cmd++) {
        printf("%*s %*s %s\n", column1_width, curr_cmd->name,
               column2_width, curr_cmd->argstring, curr_cmd->help);
    }

    return 0;
}
