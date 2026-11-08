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

#define _POSIX_C_SOURCE 200809L // for getline
#define _GNU_SOURCE             // for getline on old systems

#include <stdio.h>
#include <stdlib.h>
#include <pwd.h>
#include <unistd.h>
#include <wordexp.h>
#include <string.h>
#include <stddef.h>

#include "config.h"
#include "options.h"
#include "../utils/strings.h"

void parse_config(struct mfshell_user_options *opts)
{
    FILE           *fp;
    char           *homedir;

    // parse the configuration file
    // if a value is not set (it is NULL) then it has not been set by the
    // commandline and should be set by the configuration file

    // try set config file first if set
    if (opts->config != NULL && (fp = fopen(opts->config, "r")) != NULL) {
        parse_config_file(fp, opts);
        fclose(fp);
        return;
    }
    // try "./.mediafire-tools.conf" second
    if ((fp = fopen("./.mediafire-tools.conf", "r")) != NULL) {
        parse_config_file(fp, opts);
        fclose(fp);
        return;
    }
    // try "~/.mediafire-tools.conf" third
    if ((homedir = getenv("HOME")) == NULL) {
        homedir = getpwuid(getuid())->pw_dir;
    }
    homedir = strdup_printf("%s/.mediafire-tools.conf", homedir);
    if ((fp = fopen("./.mediafire-tools.conf", "r")) != NULL) {
        parse_config_file(fp, opts);
        fclose(fp);
    }
    free(homedir);
}

void parse_config_file(FILE * fp, struct mfshell_user_options *opts)
{
    // read the config file line by line and pass each line to wordexp to
    // retain proper quoting
    char           *line = NULL;
    size_t          len = 0;
    ssize_t         read;
    wordexp_t       p;
    int             ret,
                    i;
    int             argc;
    char          **argv;

    while ((read = getline(&line, &len, fp)) != -1) {
        if (line[0] == '#')
            continue;

        // replace possible trailing newline by zero
        if (line[strlen(line) - 1] == '\n')
            line[strlen(line) - 1] = '\0';
        ret = wordexp(line, &p, WRDE_SHOWERR | WRDE_UNDEF);
        if (ret != 0) {
            switch (ret) {
                case WRDE_BADCHAR:
                    fprintf(stderr, "wordexp: WRDE_BADCHAR\n");
                    break;
                case WRDE_BADVAL:
                    fprintf(stderr, "wordexp: WRDE_BADVAL\n");
                    break;
                case WRDE_CMDSUB:
                    fprintf(stderr, "wordexp: WRDE_CMDSUB\n");
                    break;
                case WRDE_NOSPACE:
                    fprintf(stderr, "wordexp: WRDE_NOSPACE\n");
                    break;
                case WRDE_SYNTAX:
                    fprintf(stderr, "wordexp: WRDE_SYNTAX\n");
                    break;
            }
            wordfree(&p);
            continue;
        }
        // prepend a dummy program name so that getopt_long will be able to
        // parse it
        argc = p.we_wordc + 1;
        // allocate one more than argc for trailing NULL
        argv = (char **)malloc(sizeof(char *) * (argc + 1));
        argv[0] = "";           // dummy program name
        for (i = 1; i < argc; i++)
            argv[i] = p.we_wordv[i - 1];
        argv[argc] = NULL;
        parse_argv(argc, argv, opts);
        free(argv);
        wordfree(&p);
    }
    free(line);
}
