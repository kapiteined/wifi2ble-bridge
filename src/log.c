#include <stdio.h>
#include "mesh_emu/log.h"

void mesh_emu_log_info(const char *message)
{
    if (message == 0) {
        return;
    }

    fprintf(stdout, "[info] %s\n", message);
}

void mesh_emu_log_error(const char *message)
{
    if (message == 0) {
        return;
    }

    fprintf(stderr, "[error] %s\n", message);
}
